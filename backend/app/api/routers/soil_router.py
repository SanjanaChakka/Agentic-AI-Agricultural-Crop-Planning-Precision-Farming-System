"""Soil observation and interpretation endpoints.

Design rule exposed by this router: ``SoilObservation`` only ever contains
values a human, a laboratory or a device supplied.  The AI interpretation lives
in a separate object and is always returned in a separate block.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, status
from sqlalchemy import select

from app.api.deps import DbSession, PageDep, paginate
from app.core.errors import NotFoundError, UnprocessableEntityError
from app.models.farm import Field
from app.models.soil import SoilObservation
from app.schemas.soil import (
    SoilAnalysisResponse,
    SoilInterpretationOut,
    SoilObservationCreate,
    SoilObservationOut,
    SoilThresholdOut,
)
from app.services import soil_service
from app.services.suitability_service import resolve_requirements

router = APIRouter(tags=["soil"])


def _observation_out(observation: SoilObservation, crop: str | None = None) -> SoilObservationOut:
    payload = SoilObservationOut.model_validate(observation, from_attributes=True).model_dump()
    payload["missing_parameters"] = soil_service.missing_parameters(observation, crop=crop)
    return SoilObservationOut(**payload)


@router.get("/soil/observations", response_model=list[SoilObservationOut], summary="List soil observations")
def list_observations(
    db: DbSession,
    page: PageDep,
    field_id: int | None = None,
) -> list[SoilObservationOut]:
    statement = select(SoilObservation).order_by(SoilObservation.observed_at.desc(), SoilObservation.id.desc())
    if field_id is not None:
        statement = statement.where(SoilObservation.field_id == field_id)
    rows, _ = paginate(db, statement, page)
    return [_observation_out(row) for row in rows]


@router.post(
    "/soil/observations",
    response_model=SoilAnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record a measured soil test and generate its interpretation",
)
def create_observation(payload: SoilObservationCreate, db: DbSession) -> SoilAnalysisResponse:
    if payload.field_id is None:
        msg = "field_id is required to record a soil observation"
        raise UnprocessableEntityError(msg)
    field = db.get(Field, payload.field_id)
    if field is None:
        msg = f"Field {payload.field_id} was not found"
        raise NotFoundError(msg)

    crop = field.proposed_crop
    data = payload.model_dump(exclude={"field_id"})
    data["observed_at"] = data.get("observed_at") or datetime.now(UTC)
    data["soil_type"] = data.get("soil_type") or field.soil_type

    observation = SoilObservation(field_id=field.id, **data)
    db.add(observation)
    db.flush()

    interpretation = soil_service.interpret_observation(observation, crop=crop, persist=True)
    db.commit()
    db.refresh(observation)
    db.refresh(interpretation)

    return SoilAnalysisResponse(
        observation=_observation_out(observation, crop=crop),
        interpretation=SoilInterpretationOut.model_validate(interpretation, from_attributes=True),
    )


@router.get(
    "/soil/observations/{observation_id}",
    response_model=SoilAnalysisResponse,
    summary="Measured values and AI interpretation for one observation",
)
def get_observation(observation_id: int, db: DbSession) -> SoilAnalysisResponse:
    observation = soil_service.get_observation(db, observation_id)
    crop = None
    field = db.get(Field, observation.field_id)
    if field is not None:
        crop = field.proposed_crop
    return SoilAnalysisResponse(
        observation=_observation_out(observation, crop=crop),
        interpretation=(
            SoilInterpretationOut.model_validate(observation.interpretation, from_attributes=True)
            if observation.interpretation is not None
            else None
        ),
    )


@router.get(
    "/soil/fields/{field_id}/latest",
    response_model=SoilAnalysisResponse | None,
    summary="Latest soil test for a field",
)
def latest_for_field(field_id: int, db: DbSession) -> SoilAnalysisResponse | None:
    observation = soil_service.latest_observation(db, field_id)
    if observation is None:
        return None
    field = db.get(Field, field_id)
    return SoilAnalysisResponse(
        observation=_observation_out(observation, crop=field.proposed_crop if field else None),
        interpretation=(
            SoilInterpretationOut.model_validate(observation.interpretation, from_attributes=True)
            if observation.interpretation is not None
            else None
        ),
    )


@router.post(
    "/soil/observations/{observation_id}/reinterpret",
    response_model=SoilInterpretationOut,
    summary="Regenerate the AI interpretation for a measured observation",
)
def reinterpret(observation_id: int, crop: str | None, db: DbSession) -> SoilInterpretationOut:
    observation = soil_service.get_observation(db, observation_id)
    requirements = resolve_requirements(crop)
    interpretation = soil_service.interpret_observation(
        observation, crop=(requirements.name.lower() if requirements else crop), persist=True
    )
    db.commit()
    db.refresh(interpretation)
    return SoilInterpretationOut.model_validate(interpretation, from_attributes=True)


@router.get("/soil/thresholds", response_model=SoilThresholdOut, summary="Agronomic rating bands used")
def thresholds() -> SoilThresholdOut:
    payload = soil_service.soil_thresholds_payload()
    return SoilThresholdOut(
        nitrogen_available_kg_ha=payload["nitrogen_available_kg_ha"],
        phosphorus_available_kg_ha=payload["phosphorus_available_kg_ha"],
        potassium_available_kg_ha=payload["potassium_available_kg_ha"],
        organic_carbon_percent=payload["organic_carbon_percent"],
        ph_classes=payload["ph_classes"],
    )


@router.get("/soil/observations/{observation_id}/evidence", summary="Provenance-tagged evidence for an observation")
def observation_evidence(observation_id: int, db: DbSession) -> dict:
    observation = soil_service.get_observation(db, observation_id)
    evidence = [item.model_dump() for item in soil_service.observation_evidence(observation)]
    return {
        "observation_id": observation.id,
        "measured": observation.measured_payload(),
        "evidence": evidence,
        "note": (
            "MEASURED values are stored exactly as supplied. Everything else in this system is an "
            "interpretation derived from them."
        ),
    }
