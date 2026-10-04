"""Agents 4-6: knowledge retrieval, crop suitability and machine learning.

The knowledge agent is the retrieval gate for the whole run: it reads the field
profile, the soil interpretation and the weather context and returns the
reference documents that the downstream decision agents are allowed to cite.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.agents.base import AgentContext, AgentResult, BaseAgent, evidence_from_measurement
from app.core.logging import get_logger
from app.data.crop_catalog import EXTENDED_DRY_DAYS
from app.models.assessment import MLPrediction
from app.models.enums import MLTask, SourceKind
from app.schemas.common import (
    Evidence,
    SourceReference,
    as_source_reference,
    sources_as_dicts,
)
from app.services import ml_service, sensor_service, suitability_service
from app.services.soil_service import latest_observation

logger = get_logger(__name__)


class KnowledgeRetrievalAgent(BaseAgent):
    """Retrieves citable agronomic references for this specific field situation."""

    name = "knowledge_retrieval_agent"
    responsibility = "Retrieve and rank reference material (RAG over the FAISS index) for the current field"

    def run(self, ctx: AgentContext) -> AgentResult:
        if not ctx.retriever.available:
            ctx.warn(
                "RAG index is unavailable, so no reference documents can be cited; decisions fall back to "
                "built-in rule thresholds."
            )
            output = {
                "available": False,
                "queries": [],
                "references": [],
                "index_backend": ctx.retriever.index_backend,
                "detail": ctx.retriever.detail,
            }
            return AgentResult(
                name=self.name,
                responsibility=self.responsibility,
                status="succeeded",
                output=output,
                state_patch={"knowledge": output},
                reasoning="Retrieval index not loaded; recorded as unavailable rather than fabricating sources.",
            )

        field = ctx.field
        soil_state = ctx.options.get("soil") or {}

        queries = [
            (
                f"{ctx.requirements.name} {ctx.requirements.season} season agronomy requirements "
                f"temperature rainfall duration stage practices"
            ),
            (
                f"{field.soil_type} soil texture field capacity plant available water refill point "
                f"{ctx.requirements.name} moisture thresholds"
            ),
            (
                f"soil pH {ctx.requirements.ph_optimal[0]} to {ctx.requirements.ph_optimal[1]} nutrient "
                f"availability nitrogen phosphorus potassium organic carbon {ctx.requirements.name} recommendation dose"
            ),
            (
                "irrigation scheduling soil moisture depletion refill trigger rainfall substitution "
                "crop water requirement critical stage"
            ),
            (
                "disease favourable environment leaf wetness humidity temperature crop risk scouting "
                "heat stress waterlogging"
            ),
        ]
        if (soil_state.get("interpretation") or {}).get("missing_parameters"):
            queries.append("soil sampling protocol laboratory analysis parameters required frequency")

        retrieved: list[SourceReference] = []
        seen: set[str] = set()
        query_report: list[dict[str, Any]] = []
        for query in queries:
            references = [as_source_reference(item) for item in ctx.retrieve(query, top_k=3)]
            query_report.append(
                {"query": query, "hits": len(references), "doc_keys": [item.doc_key for item in references]}
            )
            for reference in references:
                if reference.doc_key in seen:
                    continue
                seen.add(reference.doc_key)
                retrieved.append(reference)

        sources = retrieved[:12]
        output = {
            "available": True,
            "index_backend": ctx.retriever.index_backend,
            "embedding": ctx.retriever.embedding,
            "documents": len(ctx.retriever.documents),
            "chunks": ctx.retriever.chunk_count,
            "retrieval_mode": ctx.retriever.retrieval_mode,
            "queries": query_report,
            "references": sources_as_dicts(sources),
            "reference_count": len(sources),
        }

        reasoning = (
            f"Ran {len(queries)} retrieval queries against a FAISS {ctx.retriever.index_backend} index holding "
            f"{ctx.retriever.chunk_count} chunks from {len(ctx.retriever.documents)} reference documents, and "
            f"kept {len(sources)} distinct documents. Every downstream recommendation cites these documents by "
            "key, so a reviewer can open the underlying guidance."
        )

        return AgentResult(
            name=self.name,
            responsibility=self.responsibility,
            output=output,
            state_patch={"knowledge": output},
            sources=sources,
            reasoning=reasoning,
        )


class CropSuitabilityAgent(BaseAgent):
    """Weighted multi-factor crop suitability assessment for the planned crop."""

    name = "crop_suitability_agent"
    responsibility = "Score crop suitability across seven weighted factors and report limiting factors"

    def run(self, ctx: AgentContext) -> AgentResult:
        soil = latest_observation(ctx.db, ctx.field.id)
        weather_bundle = ctx.options.get("weather_bundle")
        references = ctx.options.get("references") or []

        payload = suitability_service.evaluate(
            field=ctx.field,
            crop_name=ctx.crop,
            requirements=ctx.requirements,
            soil=soil,
            weather=weather_bundle,
            references=references,
        )
        status = payload["status"]
        score = payload["score"]

        output = {
            "crop": payload["crop"],
            "status": status,
            "score": score,
            "confidence": payload["confidence"],
            "evaluated_weight": payload["evaluated_weight"],
            "factor_scores": [item.model_dump(mode="json") for item in payload["factor_scores"]],
            "favorable_factors": payload["favorable_factors"],
            "limiting_factors": payload["limiting_factors"],
            "missing_information": payload["missing_information"],
            "requirements_used": payload["requirements_used"],
            "evidence": payload["evidence"],
            "narrative": narrative_for_suitability(payload),
        }

        if payload["missing_information"]:
            ctx.warn(f"Crop suitability is provisional; missing inputs: {', '.join(payload['missing_information'])}.")
        if status in {"agronomic_review_required", "additional_information_required"}:
            ctx.warn(f"Crop suitability status for {ctx.requirements.name} is '{status}'.")

        limiting = payload["limiting_factors"] or ["none identified"]
        reasoning = (
            f"{ctx.requirements.name} scored {score if score is not None else 'n/a'} (weighted over "
            f"{payload['evaluated_weight']:.2f} of available weight, confidence "
            f"{payload['confidence']:.2f}) and is classified '{status}'. Favourable: "
            f"{', '.join(payload['favorable_factors'] or ['none'])}. Limiting: {', '.join(limiting)}."
        )

        return AgentResult(
            name=self.name,
            responsibility=self.responsibility,
            output=output,
            state_patch={"suitability": output},
            evidence=[Evidence(**item) for item in payload["evidence"]],
            sources=references,
            reasoning=reasoning,
        )


class MLForecastAgent(BaseAgent):
    """Runs both trained models and persists their predictions for auditing."""

    name = "ml_forecast_agent"
    responsibility = "Produce the 7-day soil moisture forecast and model-classified risk severity"

    def run(self, ctx: AgentContext) -> AgentResult:
        registry = ctx.ml
        weather = ctx.options.get("weather") or {}
        soil_state = ctx.options.get("soil") or {}
        latest = sensor_service.latest_reading(ctx.db, ctx.field.id)
        _, trend_stats = sensor_service.trend(ctx.db, ctx.field.id, hours=168)

        # Feature assembly lives in app.services.ml_service so that this agent and
        # POST /api/v1/ml/predict score a field on identical evidence.
        features = ml_service.build_moisture_features(
            ctx.field, weather=weather, latest=latest, soil_state=soil_state, trend_stats=trend_stats
        )
        risk_features = ml_service.build_risk_features(
            ctx.field,
            weather=weather,
            latest=latest,
            soil_state=soil_state,
            trend_stats=trend_stats,
            requirements_name=ctx.requirements.name,
        )

        if not registry.available:
            ctx.warn("Trained ML models are unavailable; this run used rule logic only.")
            output = {
                "available": False,
                "predictions": [],
                "message": "No trained model artifacts were found; rule logic was used instead.",
            }
            return AgentResult(
                name=self.name,
                responsibility=self.responsibility,
                output=output,
                state_patch={"ml_predictions": []},
                evidence=[
                    evidence_from_measurement(
                        "ML soil moisture forecast",
                        None,
                        kind=SourceKind.ML_PREDICTION.value,
                        source="ml_forecast_agent",
                        note=output["message"],
                    )
                ],
                reasoning="Model artifacts missing; recorded the gap instead of guessing a value.",
            )

        moisture_prediction = registry.predict_soil_moisture(**features)
        risk_prediction = registry.predict_risk_severity(**risk_features)

        predictions: list[dict[str, Any]] = []
        for task_enum, prediction, extra in (
            (MLTask.SOIL_MOISTURE_FORECAST, moisture_prediction, {}),
            (MLTask.ENVIRONMENTAL_RISK_CLASSIFICATION, risk_prediction, {}),
        ):
            row = MLPrediction(
                field_id=ctx.field.id,
                workflow_run_id=ctx.workflow_run_id,
                model_name=str(prediction.get("model_name", "unknown")),
                model_version=str(prediction.get("model_version", "unknown")),
                task=task_enum.value,
                status=str(prediction.get("status", "ok")),
                prediction_value=prediction.get("prediction_value"),
                prediction_label=prediction.get("prediction_label"),
                confidence=prediction.get("confidence"),
                features=prediction.get("features", {}) or {},
                model_metadata={
                    "horizon_days": prediction.get("horizon_days"),
                    "imputed_features": prediction.get("imputed_features", []),
                    "class_distribution": prediction.get("class_distribution"),
                    "trained_on": "simulated FAO-56 style soil water balance seasons",
                    **registry.artifact_metadata(task_enum.value),
                    **extra,
                },
                message=prediction.get("message"),
            )
            ctx.db.add(row)
            ctx.db.flush()
            predictions.append(
                {
                    "id": row.id,
                    "task": row.task,
                    "model_name": row.model_name,
                    "model_version": row.model_version,
                    "status": row.status,
                    "prediction_value": row.prediction_value,
                    "prediction_label": row.prediction_label,
                    "confidence": row.confidence,
                    "unit": prediction.get("unit"),
                    "horizon_days": prediction.get("horizon_days"),
                    "message": row.message,
                    "features": row.features,
                    "imputed_features": prediction.get("imputed_features", []),
                    "class_distribution": prediction.get("class_distribution"),
                }
            )

        evidence = [
            Evidence(
                label=f"ML {pred['task']} ({pred['model_name']})",
                value=pred.get("prediction_value")
                if pred.get("prediction_label") is None
                else pred.get("prediction_label"),
                unit=pred.get("unit"),
                kind=SourceKind.ML_PREDICTION,
                source=f"{pred['model_name']} v{pred['model_version']}",
                note=str(pred.get("message", "")),
            )
            for pred in predictions
        ]

        output = {
            "available": True,
            "predictions": predictions,
            "feature_inputs": dict(features.items()),
            "trend_stats": trend_stats,
            "models": registry.describe_models(),
        }

        moisture_value = moisture_prediction.get("prediction_value")
        reasoning = (
            f"RandomForestRegressor v{moisture_prediction.get('model_version')} forecasts "
            f"{moisture_value}% VWC in {moisture_prediction.get('horizon_days')} days from the current "
            f"telemetry and forecast, and RandomForestClassifier v{risk_prediction.get('model_version')} "
            f"buckets environmental risk severity as '{risk_prediction.get('prediction_label')}' with "
            f"{float(risk_prediction.get('confidence') or 0) * 100:.0f}% confidence. Imputed features: "
            f"{', '.join(moisture_prediction.get('imputed_features', []) or []) or 'none'}. The models were "
            "trained on simulated soil-water-balance seasons, so they quantify how the system reproduces its "
            "own process rather than validated field outcomes."
        )

        return AgentResult(
            name=self.name,
            responsibility=self.responsibility,
            output=output,
            state_patch={"ml_predictions": predictions},
            evidence=evidence,
            reasoning=reasoning,
        )


# ----------------------------------------------------------------------
def _current_moisture(ctx: AgentContext) -> float | None:
    latest = sensor_service.latest_reading(ctx.db, ctx.field.id)
    if latest is not None and latest.soil_moisture_percent is not None:
        return latest.soil_moisture_percent
    measured = (ctx.options.get("soil") or {}).get("measured") or {}
    return measured.get("soil_moisture_percent")


def _dry_streak(ctx: AgentContext) -> int:
    """Count consecutive forecast days with negligible rain.

    Capped at 0 unless it reaches the extended-dry-spell threshold used by the
    risk rules.
    """
    daily = (ctx.options.get("weather") or {}).get("daily") or []
    streak = 0
    for day in daily:
        value = day.get("precipitation_mm")
        if value is None:
            break
        if float(value) < 2.0:
            streak += 1
        else:
            break
    return streak if streak >= EXTENDED_DRY_DAYS else 0


def narrative_for_suitability(payload: dict[str, Any]) -> str:
    status = payload["status"]
    score = payload["score"]
    favorable = ", ".join(payload["favorable_factors"] or []) or "no favourable factors identified"
    limiting = ", ".join(payload["limiting_factors"] or []) or "no limiting factors identified"
    score_text = f"{score:.2f}" if score is not None else "not computable with the data available"
    # The workflow passes the crop through lower-cased; capitalise it so the
    # narrative reads as a sentence instead of a log line.
    crop = str(payload["crop"]).strip()
    crop = crop[:1].upper() + crop[1:]
    headline = {
        "suitable": f"{crop} appears suitable for this field.",
        "suitable_with_conditions": f"{crop} is suitable with conditions.",
        "additional_information_required": (f"{crop} cannot be assessed properly because information is missing."),
        "agronomic_review_required": (f"{crop} needs agronomic review before it is committed to."),
    }[status]
    return (
        f"{headline} Weighted suitability score {score_text}. Favourable factors: {favorable}. "
        f"Limiting factors: {limiting}."
        + (
            " Missing information: " + ", ".join(payload["missing_information"]) + "."
            if payload["missing_information"]
            else ""
        )
    )


def utc_timestamp() -> str:  # pragma: no cover - trivial helper
    return datetime.now(UTC).isoformat(timespec="seconds")
