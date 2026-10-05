"""Agents 7-10: irrigation, crop risk (reviewer), activity planner, advisory.

The crop risk agent is the *reviewer* agent of the system: it cross-checks the
rule-based findings against the machine-learning severity bucket, refuses any
finding whose wording is not evidence-based, and produces the final advisory.
"""

from __future__ import annotations

from typing import Any

from app.agents.base import AgentContext, AgentResult, BaseAgent
from app.core.logging import get_logger
from app.models.enums import IrrigationRecommendation, Severity, SourceKind
from app.schemas.common import Evidence
from app.services import activity_service, alert_service, irrigation_service, risk_service

logger = get_logger(__name__)

# Crop stage -> activity emphasis used when planning harvest operations.
STAGE_NOTES = {
    "flowering": "Flowering is the most moisture- and heat-sensitive stage; prioritise irrigation review here.",
    "fruiting": "Fruiting stage has high water demand; keep moisture above the refill trigger.",
    "maturity": "Reduce irrigation to avoid lodging; plan harvest operations.",
}


class IrrigationAgent(BaseAgent):
    """Rule-based irrigation decision support with rainfall substitution."""

    name = "irrigation_agent"
    responsibility = "Decide whether irrigation is needed, honouring forecast rainfall first"

    def run(self, ctx: AgentContext) -> AgentResult:
        from app.services import sensor_service

        latest = sensor_service.latest_reading(ctx.db, ctx.field.id)
        _, trend_stats = sensor_service.trend(ctx.db, ctx.field.id, hours=168)
        weather_bundle = ctx.options.get("weather_bundle")
        ml_predictions = ctx.options.get("ml_predictions") or []
        moisture_prediction = next(
            (item for item in ml_predictions if item.get("task") == "soil_moisture_forecast"),
            None,
        )

        payload = irrigation_service.evaluate(
            field=ctx.field,
            requirements=ctx.requirements,
            latest=latest,
            weather=weather_bundle,
            ml_prediction=moisture_prediction,
            crop_stage=ctx.field.crop_stage,
            references=ctx.options.get("references") or [],
        )

        output = {
            **payload,
            "trend_stats": trend_stats,
            "water_availability_m3_per_day": ctx.field.water_availability_m3_per_day,
            "authorisation_required": True,
        }

        if latest is not None and latest.is_simulated:
            ctx.warn("The irrigation decision rests on SIMULATED telemetry; treat it as a method demonstration.")
        if payload["recommendation"] == IrrigationRecommendation.IRRIGATE_SOON.value:
            ctx.warn(
                f"Irrigation proposed for {ctx.field.name} ({payload.get('estimated_water_mm')} mm). This "
                "requires explicit human authorisation; the system cannot apply water."
            )

        rules_fired = list(payload["rules_evaluated"])
        reasoning = (
            f"{len(rules_fired)} irrigation rule(s) evaluated; the outcome is "
            f"'{payload['recommendation']}' at urgency '{payload['urgency']}'. "
            f"{payload['rationale']} No equipment is actuated: the output is a proposal awaiting human approval."
        )

        return AgentResult(
            name=self.name,
            responsibility=self.responsibility,
            output=output,
            state_patch={"irrigation": output},
            evidence=[Evidence(**item) for item in payload["evidence"]],
            sources=ctx.options.get("references") or [],
            reasoning=reasoning,
        )


class CropRiskAdvisoryAgent(BaseAgent):
    """Environmental risk review - favours conditions, never diagnoses disease."""

    name = "crop_risk_advisory_agent"
    responsibility = (
        "Review environmental risk findings, cross-check the ML severity model and raise deduplicated alerts"
    )

    def run(self, ctx: AgentContext) -> AgentResult:
        from app.services import sensor_service

        latest = sensor_service.latest_reading(ctx.db, ctx.field.id)
        _, trend_stats = sensor_service.trend(ctx.db, ctx.field.id, hours=168)
        weather_bundle = ctx.options.get("weather_bundle")
        ml_predictions = ctx.options.get("ml_predictions") or []
        risk_prediction = next(
            (item for item in ml_predictions if item.get("task") == "environmental_risk_classification"),
            None,
        )

        scan = risk_service.scan(
            field=ctx.field,
            requirements=ctx.requirements,
            weather=weather_bundle,
            latest=latest,
            trend_stats=trend_stats,
            references=ctx.options.get("references") or [],
        )
        findings = scan["findings"]

        # --- reviewer cross-check: ML severity must not contradict the rules ---
        review_notes: list[str] = []
        if risk_prediction and risk_prediction.get("prediction_label"):
            model_level = str(risk_prediction["prediction_label"])
            rule_level = scan["risk_level"]
            review_notes.append(
                f"Rule-based risk level '{rule_level}' compared with model bucket '{model_level}' "
                f"(confidence {float(risk_prediction.get('confidence') or 0) * 100:.0f}%)."
            )
            if _escalate(model_level) > _escalate(rule_level):
                review_notes.append(
                    "The model judges the situation more severe than the rules; the finding set was widened "
                    "to include an explicit model-based watch item."
                )
                findings.append(_model_finding(risk_prediction, scan["disclaimer"], ctx))

        for finding in findings:
            finding["review_status"] = "confirmed_as_favourability_statement"
            if finding.get("is_diagnosis"):
                finding["review_status"] = "rejected_not_a_diagnosis"

        alerts = _sync_alerts(ctx, findings, ctx.options.get("irrigation") or {})

        output = {
            "findings": findings,
            "risk_level": scan["risk_level"],
            "disclaimer": scan["disclaimer"],
            "review_notes": review_notes,
            "model_severity": risk_prediction,
            "trend_stats": trend_stats,
            "finding_count": len(findings),
        }

        if not findings:
            review_notes.append("No hazard threshold was crossed; nothing to escalate.")
        elif scan["risk_level"] in {"high", "moderate"}:
            ctx.warn(f"Environmental risk level for {ctx.requirements.name} is '{scan['risk_level']}'.")

        reasoning = (
            f"{len(findings)} environmental finding(s) reviewed. Overall level '{scan['risk_level']}'. "
            + " ".join(review_notes)
            + " Every statement describes conditions favourable for a hazard and none asserts a diagnosis; "
            "field scouting and laboratory testing remain the only way to confirm a disease."
        )

        return AgentResult(
            name=self.name,
            responsibility=self.responsibility,
            output=output,
            state_patch={"risk": output, "alerts": alerts},
            evidence=[
                Evidence(**item["evidence"][position])
                for item in findings
                if item.get("evidence")
                for position in range(min(2, len(item["evidence"])))
            ],
            sources=ctx.options.get("references") or [],
            reasoning=reasoning,
        )


class ActivityPlannerAgent(BaseAgent):
    """Converts conclusions into a dated, human-assignable activity plan."""

    name = "activity_planner_agent"
    responsibility = "Schedule scouting, irrigation, nutrient and soil-testing activities with reasons"

    def run(self, ctx: AgentContext) -> AgentResult:
        from app.services import workflow_store

        run = workflow_store.get_run(ctx.db, ctx.workflow_run_id)
        include_approved_only = bool(ctx.options.get("include_approved_only"))

        rows = activity_service.plan_for_run(
            ctx.db,
            run,
            state=_planner_state(ctx),
            responsible_person=ctx.options.get("responsible_person"),
            include_approved_only=include_approved_only,
        )
        output = {
            "activity_count": len(rows),
            "activities": [
                {
                    "id": row.id,
                    "field_id": row.field_id,
                    "activity_type": row.activity_type,
                    "title": row.title,
                    "scheduled_date": row.scheduled_date.isoformat() if row.scheduled_date else None,
                    "window_days": row.window_days,
                    "status": row.status,
                    "priority": row.priority,
                    "responsible_person": row.responsible_person,
                    "reason": row.reason,
                    "approval_request_id": row.approval_request_id,
                }
                for row in rows
            ],
            "include_approved_only": include_approved_only,
        }

        reasoning = (
            f"{len(rows)} activity/activities planned. Irrigation activities stay in the 'planned' state and "
            "carry an explicit 'awaiting human authorisation' note until a reviewer approves the plan; "
            "nothing is scheduled for automatic execution."
        )

        return AgentResult(
            name=self.name,
            responsibility=self.responsibility,
            output=output,
            state_patch={"activities": output["activities"]},
            reasoning=reasoning,
        )


class AdvisoryNarrativeAgent(BaseAgent):
    """Produces the farmer-facing advisory (LLM-optional, evidence-grounded)."""

    name = "advisory_narrative_agent"
    responsibility = "Compose the final human-readable advisory from computed evidence"

    def run(self, ctx: AgentContext) -> AgentResult:
        from app.services import narrative_service

        suitability = ctx.options.get("suitability") or {}
        irrigation = ctx.options.get("irrigation") or {}
        risk = ctx.options.get("risk") or {}
        weather = ctx.options.get("weather") or {}
        soil = ctx.options.get("soil") or {}
        knowledge = ctx.options.get("knowledge") or {}

        fallback = _deterministic_advisory(
            crop=ctx.requirements.name,
            field=ctx.field,
            suitability=suitability,
            irrigation=irrigation,
            risk=risk,
            weather=weather,
        )
        composed = narrative_service.compose(
            instructions=(
                f"Write the daily advisory for a farmer growing {ctx.requirements.name} on {ctx.field.name} "
                f"({ctx.field.area_ha} ha, {ctx.field.soil_type}). State suitability, whether to irrigate, and "
                "what to scout for. Mention that irrigation needs human approval."
            ),
            context={
                "crop": ctx.requirements.name,
                "suitability_status": suitability.get("status"),
                "suitability_score": suitability.get("score"),
                "limiting_factors": ", ".join(suitability.get("limiting_factors") or []) or "none",
                "irrigation_recommendation": irrigation.get("recommendation"),
                "irrigation_urgency": irrigation.get("urgency"),
                "proposed_depth_mm": irrigation.get("estimated_water_mm"),
                "environmental_risk_level": risk.get("risk_level"),
                "risk_findings": len(risk.get("findings") or []),
                "forecast_rainfall_7d_mm": weather.get("total_precipitation_mm"),
                "forecast_max_temp_c": weather.get("max_temp_c"),
                "weather_source": weather.get("provider"),
                "weather_simulated": weather.get("is_simulated"),
                "soil_ph": (soil.get("measured") or {}).get("ph"),
                "references_cited": knowledge.get("reference_count", 0),
            },
            evidence=ctx.evidence[-24:],
            sources=ctx.sources[:10],
            fallback=fallback,
        )

        warnings = list(composed.get("warnings") or [])
        for message in warnings:
            ctx.warn(message)
        if composed["source"] == "llm_narrative":
            ctx.warn("The advisory text was phrased by a language model; all numbers come from the analysis services.")

        output = {
            "advisory": composed["narrative"],
            "narrative_source": composed["source"],
            "model": composed["model"],
            "deterministic_fallback": fallback,
            "warnings": warnings,
            "safety_notes": [
                risk_service.DISCLAIMER,
                "Irrigation and any other physical action requires explicit human authorisation; this system "
                "cannot actuate equipment.",
            ],
        }

        reasoning = (
            f"Advisory composed from {len(ctx.evidence)} evidence items and {len(ctx.sources)} cited documents "
            f"using narrative source '{composed['source']}'. The deterministic text is always retained so the "
            "wording can be reproduced without any external model."
        )

        return AgentResult(
            name=self.name,
            responsibility=self.responsibility,
            output=output,
            state_patch={"advisory": output},
            evidence=[
                Evidence(
                    label="Advisory narrative provenance",
                    value=composed["source"],
                    kind=SourceKind.LLM_NARRATIVE
                    if composed["source"] == "llm_narrative"
                    else SourceKind.DETERMINISTIC_NARRATIVE,
                    source=composed.get("model") or "deterministic composer",
                )
            ],
            reasoning=reasoning,
            model_used=composed.get("model"),
        )


# ----------------------------------------------------------------------
def _planner_state(ctx: AgentContext) -> dict[str, Any]:
    """Project the live graph state into the shape the activity planner reads.

    ``run.state`` is only persisted once the graph has finished, so an agent that
    runs *inside* the graph must be handed the accumulated state explicitly -
    otherwise the planner would see an empty run and produce no activities.
    """
    return {
        "irrigation": ctx.options.get("irrigation") or {},
        "suitability": ctx.options.get("suitability") or {},
        "risk": ctx.options.get("risk") or {},
        "weather": ctx.options.get("weather") or {},
        "soil": ctx.options.get("soil") or {},
        "telemetry": ctx.options.get("telemetry") or {},
    }


def _model_finding(
    prediction: dict[str, Any],
    disclaimer: str,
    ctx: AgentContext,  # noqa: ARG001 - kept for signature symmetry with the rule findings
) -> dict[str, Any]:
    return {
        "risk_type": "model_flagged_environmental_stress",
        "severity": Severity.MEDIUM.value
        if str(prediction.get("prediction_label")) in {"low", "moderate"}
        else Severity.HIGH.value,
        "statement": (
            "Environmental conditions favourable for stress: the trained classifier placed this field in the "
            f"'{prediction.get('prediction_label')}' severity bucket with "
            f"{float(prediction.get('confidence') or 0) * 100:.0f}% confidence, which is higher than the "
            "rule-based findings indicated."
        ),
        "potential_impact": (
            "A higher modelled severity usually means several mild signals are present together rather than one "
            "extreme value; the combined effect on the crop can still be material."
        ),
        "recommended_investigation": (
            "Walk the field, compare the model severity with the rule findings and check the two or three "
            "conditions that drove the classification."
        ),
        "evidence": [
            Evidence(
                label="ML environmental risk severity",
                value=prediction.get("prediction_label"),
                kind=SourceKind.ML_PREDICTION,
                source=f"{prediction.get('model_name')} v{prediction.get('model_version')}",
                note=str(prediction.get("message", "")),
            ).model_dump()
        ],
        "sources": [],
        "is_diagnosis": False,
        "disclaimer": disclaimer,
    }


def _sync_alerts(ctx: AgentContext, findings: list[dict[str, Any]], irrigation: dict[str, Any]) -> list[dict[str, Any]]:
    """Raise deduplicated operational alerts for the findings and resolve cleared ones."""
    alerts = alert_service.sync_findings(
        ctx.db,
        farm=ctx.farm,
        field=ctx.field,
        risk_findings=findings,
        irrigation_recommendation=str(irrigation.get("recommendation") or ""),
    )
    return [
        {
            "id": alert.id,
            "alert_type": alert.alert_type,
            "severity": alert.severity,
            "status": alert.status,
            "occurrence_count": alert.occurrence_count,
            "fingerprint": alert.fingerprint,
            "title": alert.title,
            "message": alert.message,
        }
        for alert in alerts
    ]


def _escalate(level: str | None) -> int:
    return {"none": 0, "info": 1, "low": 2, "moderate": 3, "high": 4, "none_min": 0}.get(str(level), 0)


def _deterministic_advisory(
    *,
    crop: str,
    field: Any,
    suitability: dict,
    irrigation: dict,
    risk: dict,
    weather: dict,
) -> str:
    parts: list[str] = [f"{field.name} ({field.area_ha} ha, {field.soil_type}) is planned for {crop}."]

    status = suitability.get("status")
    score = suitability.get("score")
    if status:
        parts.append(
            f"Suitability is '{status}'"
            + (f" with a weighted score of {score:.2f}" if isinstance(score, int | float) else "")
            + "."
        )
    limiting = suitability.get("limiting_factors") or []
    if limiting:
        parts.append(f"Limiting factors: {', '.join(limiting)}.")

    recommendation = irrigation.get("recommendation")
    if recommendation == IrrigationRecommendation.IRRIGATE_SOON.value:
        depth = irrigation.get("estimated_water_mm")
        volume = irrigation.get("estimated_volume_m3")
        parts.append(
            f"Irrigation of about {depth} mm ({volume} m3 over the plot) is proposed at "
            f"{irrigation.get('urgency')} urgency. This is a proposal only - a human reviewer must authorise it "
            "before any water is applied."
        )
    elif recommendation == IrrigationRecommendation.POSTPONE_IRRIGATION.value:
        parts.append(
            f"Do not irrigate yet: {irrigation.get('weather_context', {}).get('rainfall_next_48h_mm')} mm of "
            "rain is forecast inside the decision window and watering now would be wasted."
        )
    elif recommendation == IrrigationRecommendation.NO_IRRIGATION_NEEDED.value:
        parts.append("Soil moisture is inside the comfortable band; no irrigation is needed today.")
    elif irrigation.get("rationale"):
        parts.append(str(irrigation["rationale"]))

    findings = risk.get("findings") or []
    if findings:
        headline = ", ".join(
            f"{str(item.get('risk_type', '')).replace('_', ' ')} ({item.get('severity')})" for item in findings[:3]
        )
        parts.append(
            f"{len(findings)} environmental condition(s) worth scouting were flagged: {headline}. "
            "These describe favourable conditions only and confirm nothing about the crop's health."
        )
    else:
        parts.append("No environmental hazard threshold was crossed in the forecast window.")

    if weather.get("is_simulated"):
        parts.append(
            f"Weather for this advisory came from the '{weather.get('provider')}' offline fallback and is "
            "labelled simulated; verify against a live forecast before acting."
        )

    return " ".join(parts)
