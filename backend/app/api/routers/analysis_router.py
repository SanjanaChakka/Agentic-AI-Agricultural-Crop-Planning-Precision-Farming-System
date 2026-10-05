"""Suitability, irrigation, risk and ML endpoints.

These routers run the *same* service functions the agents use, so a farmer can
inspect any single step without running the whole workflow, and every answer
still carries evidence, sources and provenance.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Body, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.base import run_coroutine
from app.api.deps import DbSession, FieldDep, MLRegistryDep, PageDep, RetrieverDep, paginate
from app.core.errors import UnprocessableEntityError
from app.core.logging import get_logger
from app.models.assessment import IrrigationAssessment, MLPrediction, RiskFinding, SuitabilityAssessment
from app.models.enums import MLTask
from app.models.farm import Field
from app.models.soil import SoilObservation
from app.rag.retriever import get_retriever
from app.schemas.analysis import (
    IrrigationOut,
    MLModelInfo,
    MLPredictionOut,
    MLPredictRequest,
    RiskOut,
    RiskScanResponse,
    SuitabilityOut,
    SuitabilityRequest,
)
from app.schemas.weather import WeatherBundle
from app.services import (
    irrigation_service,
    ml_service,
    risk_service,
    sensor_service,
    suitability_service,
    weather_service,
)
from app.services.sensor_service import latest_reading, trend
from app.services.soil_service import latest_observation

logger = get_logger(__name__)

suitability_router = APIRouter(tags=["crop suitability"])
irrigation_router = APIRouter(tags=["irrigation"])
risk_router = APIRouter(tags=["crop risk"])
ml_router = APIRouter(tags=["machine learning"])


class IrrigationAssessRequest(BaseModel):
    crop: str | None = None
    crop_stage: str | None = None
    soil_moisture_percent: float | None = None


def _bundle_for(field: Field, db: Session) -> WeatherBundle | None:  # noqa: ARG001  # noqa: ANN202 - returns WeatherBundle | None
    """Fetch a forecast for the field, or ``None`` when it has no geolocation."""
    latitude = field.effective_latitude
    longitude = field.effective_longitude
    if latitude is None or longitude is None:
        return None
    return run_coroutine(
        lambda: weather_service.fetch_weather(
            latitude,
            longitude,
            days=7,
            location_name=field.farm.location_name if field.farm else None,
            field_id=field.id,
        )
    )


def _requirements_for(crop: str | None, field: Field):  # noqa: ANN202
    resolved = crop or field.proposed_crop
    if not resolved:
        msg = "No crop was supplied and the field has no proposed crop recorded."
        raise UnprocessableEntityError(msg)
    requirements = suitability_service.resolve_requirements(resolved)
    if requirements is None:
        from app.data.crop_catalog import CROP_REQUIREMENTS

        supported = ", ".join(sorted({item.name for item in CROP_REQUIREMENTS.values()}))
        msg = f"Crop '{resolved}' is not supported. Supported crops: {supported}."
        raise UnprocessableEntityError(msg)
    return requirements


# ----------------------------------------------------------------------
# Suitability
# ----------------------------------------------------------------------
@suitability_router.post(
    "/suitability/assess",
    response_model=SuitabilityOut,
    status_code=status.HTTP_201_CREATED,
    summary="Assess crop suitability for a field",
)
def assess(
    db: DbSession,
    retriever: RetrieverDep,
    field: FieldDep,
    payload: Annotated[SuitabilityRequest, Body()],
) -> SuitabilityOut:
    from app.agents.analysis_agents import narrative_for_suitability  # local import avoids a cycle

    requirements = _requirements_for(payload.crop, field)
    soil = (
        db.get(SoilObservation, payload.soil_observation_id)
        if payload.soil_observation_id
        else latest_observation(db, field.id)
    )
    bundle = _bundle_for(field, db)

    references = []
    if retriever.available:
        references = retriever.retrieve_references(
            f"{requirements.name} crop suitability {field.soil_type} soil requirements season",
            top_k=4,
        )

    result = suitability_service.evaluate(
        field=field,
        crop_name=requirements.name.lower(),
        requirements=requirements,
        soil=soil,
        weather=bundle,
        references=references,
    )
    row = SuitabilityAssessment(
        field_id=field.id,
        crop=requirements.name.lower(),
        status=result["status"],
        score=result["score"],
        confidence=result["confidence"],
        factor_scores=[item.model_dump() for item in result["factor_scores"]],
        favorable_factors=result["favorable_factors"],
        limiting_factors=result["limiting_factors"],
        missing_information=result["missing_information"],
        requirements_used=result["requirements_used"],
        evidence=result["evidence"] if payload.include_evidence else [],
        sources=result["sources"],
        narrative=narrative_for_suitability(result),
        generated_by="crop_suitability_agent+rules",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return SuitabilityOut.model_validate(row, from_attributes=True)


@suitability_router.get("/suitability/fields/{field_id}", response_model=list[SuitabilityOut], summary="History")
def suitability_history(field: FieldDep, db: DbSession, page: PageDep) -> list[SuitabilityOut]:
    statement = (
        select(SuitabilityAssessment)
        .where(SuitabilityAssessment.field_id == field.id)
        .order_by(SuitabilityAssessment.id.desc())
    )
    rows, _ = paginate(db, statement, page)
    return [SuitabilityOut.model_validate(row, from_attributes=True) for row in rows]


@suitability_router.get("/suitability/crops", summary="Supported crops and their agronomic thresholds")
def crop_catalogue() -> dict[str, Any]:
    from app.data.crop_catalog import CROP_REQUIREMENTS

    return {
        "count": len(CROP_REQUIREMENTS),
        "crops": [
            {
                "name": requirements.name,
                "aliases": list(requirements.aliases),
                "season": requirements.season,
                "ph_optimal": list(requirements.ph_optimal),
                "ph_tolerable": list(requirements.ph_tolerable),
                "temp_optimal": list(requirements.temp_optimal),
                "temp_absolute_max": requirements.temp_absolute_max,
                "heat_stress_threshold_c": requirements.heat_stress_threshold_c,
                "humidity_risk_threshold_percent": requirements.humidity_risk_threshold_percent,
                "season_rainfall_mm": list(requirements.season_rainfall_mm),
                "water_requirement_mm": list(requirements.water_requirement_mm),
                "moisture_optimal": list(requirements.moisture_optimal),
                "moisture_critical": requirements.moisture_critical,
                "duration_days": list(requirements.duration_days),
                "critical_stages": list(requirements.critical_stages),
                "suitable_soils": list(requirements.suitable_soils),
                "notes": requirements.notes,
                "doc_key": requirements.doc_key,
            }
            for requirements in CROP_REQUIREMENTS.values()
        ],
    }


# ----------------------------------------------------------------------
# Irrigation
# ----------------------------------------------------------------------
@irrigation_router.post(
    "/irrigation/assess",
    response_model=IrrigationOut,
    status_code=status.HTTP_201_CREATED,
    summary="Irrigation decision support (proposal only, never auto-applied)",
)
def assess_irrigation(
    db: DbSession,
    field: FieldDep,
    payload: Annotated[IrrigationAssessRequest, Body()] = IrrigationAssessRequest(),
) -> IrrigationOut:
    requirements = _requirements_for(payload.crop, field)
    reading = latest_reading(db, field.id)
    bundle = _bundle_for(field, db)
    ml_prediction = _latest_ml(db, field.id, MLTask.SOIL_MOISTURE_FORECAST.value)

    result = irrigation_service.evaluate(
        field=field,
        requirements=requirements,
        latest=reading,
        weather=bundle,
        ml_prediction=ml_prediction,
        soil_moisture_percent=payload.soil_moisture_percent,
        crop_stage=payload.crop_stage or field.crop_stage,
    )
    row = IrrigationAssessment(
        field_id=field.id,
        recommendation=result["recommendation"],
        urgency=result["urgency"],
        requires_human_authorisation=True,
        authorisation_state="not_authorised",
        estimated_water_mm=result["estimated_water_mm"],
        estimated_volume_m3=result["estimated_volume_m3"],
        rationale=result["rationale"],
        rules_evaluated=result["rules_evaluated"],
        sensor_context=result["sensor_context"],
        weather_context=result["weather_context"],
        ml_prediction=result["ml_prediction"],
        evidence=result["evidence"],
        sources=result["sources"],
        generated_by="irrigation_agent+rules",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return IrrigationOut.model_validate(row, from_attributes=True)


@irrigation_router.get("/irrigation/fields/{field_id}", response_model=list[IrrigationOut], summary="History")
def irrigation_history(field: FieldDep, db: DbSession, page: PageDep) -> list[IrrigationOut]:
    statement = (
        select(IrrigationAssessment)
        .where(IrrigationAssessment.field_id == field.id)
        .order_by(IrrigationAssessment.id.desc())
    )
    rows, _ = paginate(db, statement, page)
    return [IrrigationOut.model_validate(row, from_attributes=True) for row in rows]


# ----------------------------------------------------------------------
# Risk
# ----------------------------------------------------------------------
@risk_router.get("/risk/fields/{field_id}", response_model=RiskScanResponse, summary="Scan environmental risk")
def scan_risk(field: FieldDep, db: DbSession, crop: str | None = None) -> RiskScanResponse:
    requirements = _requirements_for(crop, field)
    bundle = _bundle_for(field, db)
    reading = latest_reading(db, field.id)
    _, trend_stats = trend(db, field.id, hours=168)

    references = []
    retriever = get_retriever()
    if retriever.available:
        references = retriever.retrieve_references(
            f"{requirements.name} disease favourable environment heat waterlogging risk scouting", top_k=3
        )

    result = risk_service.scan(
        field=field,
        requirements=requirements,
        weather=bundle,
        latest=reading,
        trend_stats=trend_stats,
        references=references,
    )

    rows: list[RiskFinding] = []
    for finding in result["findings"]:
        rows.append(
            RiskFinding(
                field_id=field.id,
                risk_type=finding["risk_type"],
                severity=finding["severity"],
                statement=finding["statement"],
                potential_impact=finding["potential_impact"],
                recommended_investigation=finding["recommended_investigation"],
                evidence=finding["evidence"],
                sources=finding["sources"],
                observed_at=_as_datetime(finding.get("observed_at")),
                is_diagnosis=False,
            )
        )
        db.add(rows[-1])
    db.commit()
    for row in rows:
        db.refresh(row)

    return RiskScanResponse(
        field_id=field.id,
        findings=[RiskOut.model_validate(row, from_attributes=True) for row in rows],
        risk_level=result["risk_level"],
        disclaimer=result["disclaimer"],
    )


@risk_router.get("/risk/fields/{field_id}/history", response_model=list[RiskOut], summary="Persisted findings")
def risk_history(field: FieldDep, db: DbSession, page: PageDep) -> list[RiskOut]:
    statement = select(RiskFinding).where(RiskFinding.field_id == field.id).order_by(RiskFinding.id.desc())
    rows, _ = paginate(db, statement, page)
    return [RiskOut.model_validate(row, from_attributes=True) for row in rows]


@risk_router.get("/risk/disclaimer", summary="The non-diagnostic disclaimer enforced by the system")
def disclaimer() -> dict[str, str]:
    return {
        "disclaimer": risk_service.DISCLAIMER,
        "wording_rule": (
            "Findings must be phrased as 'Environmental conditions favourable for X'. The system never states "
            "that a disease is confirmed, present or diagnosed."
        ),
    }


# ----------------------------------------------------------------------
# Machine learning
# ----------------------------------------------------------------------
@ml_router.get("/ml/models", response_model=list[MLModelInfo], summary="Trained models and their metrics")
def models(registry: MLRegistryDep) -> list[MLModelInfo]:
    return [MLModelInfo(**card) for card in registry.describe_models()]


@ml_router.get("/ml/status", summary="Model availability and load errors")
def ml_status(registry: MLRegistryDep) -> dict[str, Any]:
    return {
        "available": registry.available,
        "moisture_model": registry.moisture_available,
        "risk_model": registry.risk_available,
        "errors": registry.errors,
        "training_note": (
            "Training data is generated by an FAO-56 style soil-water-balance simulation (Hargreaves ET0, "
            "piecewise Kc, gamma-distributed rainfall, texture field-capacity bands). The reported metrics "
            "therefore measure how faithfully the models reproduce the simulation, not field accuracy."
        ),
    }


@ml_router.post(
    "/ml/predict",
    response_model=list[MLPredictionOut],
    status_code=status.HTTP_201_CREATED,
    summary="Run both models against a field's current conditions",
)
def predict(
    db: DbSession,
    registry: MLRegistryDep,
    field: FieldDep,
    payload: Annotated[MLPredictRequest, Body()] = MLPredictRequest(),
) -> list[MLPredictionOut]:
    """Score a field with both trained models.

    The body is optional: a bare ``POST /ml/predict?field_id=N`` scores the field
    on its own stored context (sensor telemetry, soil sample and live forecast),
    and any body field simply overrides that context.

    Feature assembly is delegated to :mod:`app.services.ml_service` so that this
    endpoint and the ``ml_forecast_agent`` are guaranteed to feed the models the
    same, real values.  Building the vector from the request body alone would
    silently median-impute every soil and weather feature and report the result
    as if it had been measured.
    """
    crop = (payload.crop or field.proposed_crop or "").strip().lower()
    _, trend_stats = sensor_service.trend(db, field.id, hours=168)
    latest = sensor_service.latest_reading(db, field.id)
    soil_observation = latest_observation(db, field.id)
    soil_state = {"measured": soil_observation.measured_payload()} if soil_observation else {}
    weather = weather_service.feature_dict(_bundle_for(field, db))

    overrides = payload.overrides()
    moisture_features = ml_service.build_moisture_features(
        field,
        weather=weather,
        latest=latest,
        soil_state=soil_state,
        trend_stats=trend_stats,
        overrides=overrides,
    )
    risk_features = ml_service.build_risk_features(
        field,
        weather=weather,
        latest=latest,
        soil_state=soil_state,
        trend_stats=trend_stats,
        crop=crop or None,
        overrides=overrides,
    )

    predictions = [
        (MLTask.SOIL_MOISTURE_FORECAST, registry.predict_soil_moisture(**moisture_features)),
        (MLTask.ENVIRONMENTAL_RISK_CLASSIFICATION, registry.predict_risk_severity(**risk_features)),
    ]
    cards = {card.get("task"): card for card in registry.describe_models()}

    rows: list[MLPrediction] = []
    for task, prediction in predictions:
        card = cards.get(task.value, {})
        dataset = card.get("dataset_summary") or {}
        row = MLPrediction(
            field_id=field.id,
            model_name=str(prediction.get("model_name", "unknown")),
            model_version=str(prediction.get("model_version", "unknown")),
            task=task.value,
            status=str(prediction.get("status", "ok")),
            prediction_value=prediction.get("prediction_value"),
            prediction_label=prediction.get("prediction_label"),
            confidence=prediction.get("confidence"),
            features=prediction.get("features", {}) or {},
            model_metadata={
                "horizon_days": prediction.get("horizon_days"),
                "imputed_features": prediction.get("imputed_features", []),
                "class_distribution": prediction.get("class_distribution"),
                "target": card.get("target"),
                "trained_at": card.get("trained_at"),
                "trained_on": dataset.get("type"),
            },
            message=prediction.get("message"),
        )
        db.add(row)
        rows.append(row)
    db.commit()
    for row in rows:
        db.refresh(row)
    return [MLPredictionOut.model_validate(row, from_attributes=True) for row in rows]


@ml_router.get("/ml/fields/{field_id}/predictions", response_model=list[MLPredictionOut], summary="Prediction history")
def prediction_history(field: FieldDep, db: DbSession, page: PageDep) -> list[MLPredictionOut]:
    statement = select(MLPrediction).where(MLPrediction.field_id == field.id).order_by(MLPrediction.id.desc())
    rows, _ = paginate(db, statement, page)
    return [MLPredictionOut.model_validate(row, from_attributes=True) for row in rows]


# ----------------------------------------------------------------------
def _latest_ml(db: DbSession, field_id: int, task: str) -> dict[str, Any] | None:
    row = db.scalars(
        select(MLPrediction)
        .where(MLPrediction.field_id == field_id, MLPrediction.task == task)
        .order_by(MLPrediction.id.desc())
    ).first()
    if row is None:
        return None
    return {
        "status": row.status,
        "model_name": row.model_name,
        "model_version": row.model_version,
        "prediction_value": row.prediction_value,
        "horizon_days": (row.model_metadata or {}).get("horizon_days"),
        "message": row.message,
    }


def _as_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            logger.debug("Unparseable observed_at %r; using current time", value)
    return datetime.now(UTC)
