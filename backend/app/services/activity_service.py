"""Activity planner.

Turns the conclusions of an agentic run into dated, human-assignable farm
activities.  The planner is deliberately conservative:

* an irrigation activity is only planned when the irrigation assessment proposes
  water **and** a human has authorised it (``include_approved_only``);
* nothing is ever scheduled to act automatically - every activity is created in
  the ``planned``/``scheduled`` state and needs a person;
* activities are idempotent per workflow run so that re-running the planner
  does not duplicate the plan.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.enums import (
    ActivityStatus,
    ActivityType,
    ApprovalStatus,
    IrrigationRecommendation,
    SourceKind,
    WorkflowStatus,
)
from app.models.farm import Field
from app.models.operations import FarmActivity
from app.models.workflow import ApprovalRequest, WorkflowRun
from app.schemas.common import Evidence

logger = get_logger(__name__)


def plan_for_run(
    db: Session,
    run: WorkflowRun,
    *,
    state: dict[str, Any] | None = None,
    responsible_person: str | None = None,
    include_approved_only: bool = False,
) -> list[FarmActivity]:
    """Create (or return the already existing) activity plan for a workflow run.

    ``state`` must be supplied when the planner runs *inside* the agent graph:
    ``run.state`` is only written when the run is finalised, which happens after
    this node.  It is optional so the HTTP endpoint can plan for a finished run.
    """
    state = state if state is not None else (run.state or {})
    field = db.get(Field, run.field_id)
    if field is None:  # pragma: no cover - FK integrity guarantees a row
        msg = f"Field {run.field_id} referenced by run {run.id} does not exist"
        raise ValueError(msg)

    existing = list(db.scalars(select(FarmActivity).where(FarmActivity.workflow_run_id == run.id)).all())
    if existing:
        logger.info("Activity plan already exists for run %s (%s rows)", run.id, len(existing))
        return existing

    approval = _latest_approval(db, run.id)
    approved = approval is not None and approval.status in {
        ApprovalStatus.APPROVED.value,
        ApprovalStatus.MODIFIED.value,
    }
    if include_approved_only and not approved:
        logger.info("Skipping activity plan for run %s: no human approval yet", run.id)
        return []

    irrigation = state.get("irrigation") or {}
    suitability = state.get("suitability") or {}
    risk = state.get("risk") or {}
    weather = state.get("weather") or {}
    soil = state.get("soil") or {}
    crop = run.crop or field.proposed_crop or "the proposed crop"
    today = datetime.now(UTC).replace(hour=6, minute=0, second=0, microsecond=0)
    approvals: list[FarmActivity] = []

    def _add(
        activity_type: ActivityType,
        title: str,
        *,
        offset_days: int,
        reason: str,
        evidence: list[Evidence],
        priority: str = "medium",
        window_days: int = 1,
    ) -> FarmActivity:
        approval_id = approval.id if (approved and activity_type == ActivityType.IRRIGATION) else None
        row = FarmActivity(
            field_id=field.id,
            workflow_run_id=run.id,
            approval_request_id=approval_id,
            activity_type=activity_type.value,
            title=title,
            scheduled_date=today + timedelta(days=offset_days),
            window_days=window_days,
            status=ActivityStatus.SCHEDULED.value if approved else ActivityStatus.PLANNED.value,
            responsible_person=responsible_person,
            reason=reason,
            priority=priority,
            evidence=[item.model_dump() for item in evidence],
            notes=None,
        )
        db.add(row)
        approvals.append(row)
        return row

    # 1. Field scouting driven by the risk findings
    findings = risk.get("findings") or []
    if findings:
        high = [f for f in findings if f.get("severity") == "high"]
        _add(
            ActivityType.FIELD_SCROUTING,
            f"Scout {field.name} for conditions favouring "
            + ", ".join(sorted({str(f.get("risk_type", "stress")).replace("_", " ") for f in high or findings})),
            offset_days=1 if high else 3,
            reason=(
                f"{len(findings)} environmental risk finding(s) reported; highest severity "
                f"'{risk.get('risk_level', 'unknown')}'. Scout to confirm presence or absence - the system "
                "does not diagnose."
            ),
            evidence=[
                Evidence(
                    label=f"Risk finding: {item.get('risk_type')}",
                    value=item.get("severity"),
                    kind=SourceKind.RULE,
                    source="crop risk monitoring agent",
                    note=str(item.get("statement", ""))[:280],
                )
                for item in (high or findings)[:4]
            ],
            priority="high" if high else "medium",
        )

    # 2. Irrigation - only when water is proposed and (optionally) authorised
    recommendation = irrigation.get("recommendation")
    if recommendation == IrrigationRecommendation.IRRIGATE_SOON.value:
        depth = irrigation.get("estimated_water_mm")
        volume = irrigation.get("estimated_volume_m3")
        _add(
            ActivityType.IRRIGATION,
            f"Apply {depth} mm irrigation to {field.name}" if depth else f"Review and apply irrigation on {field.name}",
            offset_days=0,
            reason=irrigation.get("rationale", "")
            + (
                " Plan authorised by a human reviewer."
                if approved
                else " AWAITING HUMAN AUTHORISATION - do not apply water until a reviewer approves this plan."
            ),
            evidence=[
                Evidence(
                    label="Irrigation recommendation",
                    value=str(recommendation),
                    kind=SourceKind.RULE,
                    source="irrigation agent",
                    note=f"Urgency: {irrigation.get('urgency')}; depth {depth} mm; volume {volume} m3.",
                )
            ],
            priority="high" if irrigation.get("urgency") == "high" else "medium",
        )
    elif recommendation == IrrigationRecommendation.POSTPONE_IRRIGATION.value:
        _add(
            ActivityType.CROP_OBSERVATION,
            f"Re-check soil moisture on {field.name} after the forecast rain event",
            offset_days=2,
            reason=irrigation.get("rationale", ""),
            evidence=[
                Evidence(
                    label="Forecast rainfall substituted for irrigation",
                    value=(irrigation.get("weather_context") or {}).get("rainfall_next_48h_mm"),
                    unit="mm",
                    kind=SourceKind.FORECAST,
                    source=(irrigation.get("weather_context") or {}).get("source", "weather service"),
                )
            ],
            priority="low",
        )

    # 3. Nutrient application when the soil agent flags a deficiency
    nutrient_actions = [
        item
        for item in (soil.get("recommendations") or [])
        if item.get("action_type") in {"nutrient_application", "soil_amendment"}
    ]
    if nutrient_actions:
        _add(
            ActivityType.NUTRIENT_APPLICATION,
            f"Plan nutrient application for {crop} on {field.name}",
            offset_days=3,
            reason="; ".join(str(item.get("detail", "")) for item in nutrient_actions[:3]),
            evidence=[
                Evidence(
                    label=f"Soil interpretation: {item.get('parameter', 'soil')}",
                    value=item.get("status"),
                    kind=SourceKind.RULE,
                    source="soil and nutrient agent",
                    note=str(item.get("detail", ""))[:280],
                )
                for item in nutrient_actions[:4]
            ],
            priority="medium",
            window_days=3,
        )

    # 4. Soil re-testing when key parameters are missing
    missing = suitability.get("missing_information") or []
    if missing:
        _add(
            ActivityType.SOIL_TESTING,
            f"Collect soil sample from {field.name} for missing parameters",
            offset_days=5,
            reason=(
                "The suitability assessment could not be completed because these inputs are absent: "
                + ", ".join(str(item) for item in missing)
            ),
            evidence=[
                Evidence(
                    label="Missing soil inputs",
                    value=", ".join(str(item) for item in missing),
                    kind=SourceKind.RULE,
                    source="crop suitability agent",
                )
            ],
            priority="low",
            window_days=7,
        )

    # 5. Harvest planning when the crop is mature
    stage = (field.crop_stage or "unknown").lower()
    if stage == "maturity":
        _add(
            ActivityType.HARVEST_PLANNING,
            f"Plan harvest and post-harvest operations for {crop} on {field.name}",
            offset_days=7,
            reason="Crop stage is recorded as maturity; harvesting and residue management should be planned.",
            evidence=[
                Evidence(
                    label="Recorded crop stage",
                    value=field.crop_stage,
                    kind=SourceKind.USER_INPUT,
                    source="field profile",
                )
            ],
            priority="medium",
            window_days=5,
        )
    elif stage in {"sowing", "unknown"} and suitability.get("status"):
        _add(
            ActivityType.SOWING,
            f"Confirm sowing window for {crop} on {field.name}",
            offset_days=2,
            reason=(
                f"Suitability status '{suitability.get('status')}' for {crop}"
                + (f" (score {suitability.get('score')})" if suitability.get("score") is not None else "")
                + ". Confirm the planting window before committing seed and input cost."
            ),
            evidence=[
                Evidence(
                    label="Suitability score",
                    value=suitability.get("score"),
                    kind=SourceKind.RULE,
                    source="crop suitability agent",
                    note=f"status: {suitability.get('status')}",
                )
            ],
            priority="medium",
        )

    # 6. Sensor maintenance when telemetry quality failed
    sensor_flags = (irrigation.get("sensor_context") or {}).get("quality_flags") or []
    faults = [flag for flag in sensor_flags if flag not in {"ok", "simulated"}]
    if faults:
        _add(
            ActivityType.CROP_OBSERVATION,
            f"Check soil moisture probe on {field.name}",
            offset_days=1,
            reason=f"Latest telemetry carried quality flags: {', '.join(faults)}.",
            evidence=[
                Evidence(
                    label="Sensor quality flags",
                    value=", ".join(faults),
                    kind=SourceKind.OBSERVED,
                    source=(irrigation.get("sensor_context") or {}).get("sensor_id") or "soil moisture probe",
                )
            ],
            priority="high",
        )

    if weather.get("is_simulated"):
        location = field.farm.location_name if field.farm else field.name
        _add(
            ActivityType.CROP_OBSERVATION,
            f"Verify the forecast for {location} against a live weather source",
            offset_days=0,
            reason=(
                "Weather for this run came from the offline fallback and is flagged as simulated; "
                "decisions should be re-checked against a live forecast."
            ),
            evidence=[
                Evidence(
                    label="Weather source",
                    value=weather.get("source", "offline-climatology"),
                    kind=SourceKind.SIMULATED,
                    source="weather agent",
                )
            ],
            priority="medium",
        )

    db.flush()
    logger.info("Planned %s activities for run %s", len(approvals), run.id)
    return approvals


def latest_pending_approval(db: Session, run_id: int) -> ApprovalRequest | None:
    """Return the newest approval request for a run (used by the API)."""
    return _latest_approval(db, run_id)


def _latest_approval(db: Session, run_id: int) -> ApprovalRequest | None:
    return db.scalars(
        select(ApprovalRequest).where(ApprovalRequest.workflow_run_id == run_id).order_by(ApprovalRequest.id.desc())
    ).first()


def run_is_complete(run: WorkflowRun) -> bool:
    return run.status in {WorkflowStatus.COMPLETED.value, WorkflowStatus.COMPLETED_WITH_WARNINGS.value}
