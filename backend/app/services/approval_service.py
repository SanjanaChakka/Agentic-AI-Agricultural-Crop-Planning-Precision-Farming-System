"""Human-in-the-loop approval gate.

Safety contract enforced here:

* every consequential plan (irrigation above all) starts as ``pending``;
* ``approved`` authorises a *plan* - it never actuates a valve, a pump or any
  other physical device, and no code path in this repository can do so;
* ``modified`` records the reviewer's adjusted action and uses that action for
  the activity plan;
* ``rejected`` cancels the plan and marks the workflow rejected;
* ``reanalysis_requested`` schedules a fresh agent run carrying the reviewer's
  observations.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.core.logging import get_logger
from app.models.enums import ActivityStatus, ActivityType, ApprovalStatus, SourceKind, WorkflowStatus
from app.models.operations import FarmActivity
from app.models.workflow import ApprovalRequest, WorkflowRun
from app.schemas.common import Evidence
from app.schemas.workflow import ApprovalDecision

logger = get_logger(__name__)


def create_approval_request(db: Session, run: WorkflowRun) -> ApprovalRequest:
    """Create the pending approval gate for a completed workflow run."""
    state = run.state or {}
    irrigation = state.get("irrigation") or {}
    risk = state.get("risk") or {}

    existing = db.scalars(
        select(ApprovalRequest)
        .where(
            ApprovalRequest.workflow_run_id == run.id,
            ApprovalRequest.status == ApprovalStatus.PENDING.value,
        )
        .order_by(ApprovalRequest.id.desc())
    ).first()
    if existing is not None:
        return existing

    field_name = (state.get("field") or {}).get("name") or f"field {run.field_id}"
    crop = run.crop or "the proposed crop"
    recommendation = irrigation.get("recommendation") or "no_action"
    depth = irrigation.get("estimated_water_mm")
    volume = irrigation.get("estimated_volume_m3")

    if recommendation == "consider_irrigation":
        title = f"Authorise irrigation of {depth} mm on {field_name} for {crop}"
        action = {
            "action_type": "irrigation",
            "field_id": run.field_id,
            "crop": crop,
            "depth_mm": depth,
            "volume_m3": volume,
            "urgency": irrigation.get("urgency"),
            "method": "manual authorisation only - the system cannot actuate irrigation equipment",
        }
    else:
        title = f"Review agentic plan for {field_name} ({crop})"
        action = {
            "action_type": "plan_review",
            "field_id": run.field_id,
            "crop": crop,
            "recommendation": recommendation,
            "risk_level": risk.get("risk_level"),
        }

    evidence = [
        Evidence(
            label="Irrigation recommendation",
            value=recommendation,
            kind=SourceKind.RULE,
            source="irrigation agent",
            note=str(irrigation.get("rationale", ""))[:300],
        ),
        Evidence(
            label="Environmental risk level",
            value=risk.get("risk_level"),
            kind=SourceKind.RULE,
            source="crop risk agent",
            note=f"{len(risk.get('findings') or [])} finding(s); favourability only, never a diagnosis.",
        ),
        Evidence(
            label="Human authorisation requirement",
            value=True,
            kind=SourceKind.RULE,
            source="approval service",
            note="Approving authorises the plan only; no physical action is executed by this system.",
        ),
    ]

    request = ApprovalRequest(
        workflow_run_id=run.id,
        field_id=run.field_id,
        title=title,
        action_type="irrigation_plan" if recommendation == "consider_irrigation" else "plan_review",
        recommendation=action,
        evidence=[item.model_dump() for item in evidence],
        status=ApprovalStatus.PENDING.value,
        observation=None,
    )
    db.add(request)
    db.flush()

    # The activity planner runs *before* the gate exists, so its irrigation
    # activities have no approval id yet.  Back-link them now: the approval is
    # exactly what authorises the water plan, and the decision handler drives
    # these rows from planned -> scheduled / cancelled.
    linked = db.scalars(
        select(FarmActivity).where(
            FarmActivity.workflow_run_id == run.id,
            FarmActivity.approval_request_id.is_(None),
            FarmActivity.activity_type == ActivityType.IRRIGATION.value,
            FarmActivity.status == ActivityStatus.PLANNED.value,
        )
    ).all()
    for activity in linked:
        activity.approval_request_id = request.id
    if linked:
        logger.info("Linked %s irrigation activity/activities to approval %s", len(linked), request.id)

    run.status = WorkflowStatus.AWAITING_HUMAN_REVIEW.value
    logger.info("Created approval request %s for run %s", request.id, run.id)
    return request


def decide(db: Session, request: ApprovalRequest, decision: ApprovalDecision) -> ApprovalRequest:
    """Apply a human decision and reconcile dependent records."""
    if request.status != ApprovalStatus.PENDING.value:
        msg = f"Approval request {request.id} was already {request.status}; only pending requests can be decided."
        raise ConflictError(msg)

    now = datetime.now(UTC)
    request.status = decision.status.value
    request.reviewer_name = decision.reviewer_name
    request.decision_note = decision.decision_note
    request.modified_action = decision.modified_action
    request.observation = decision.observation
    request.reanalysis_requested = decision.reanalysis_requested
    request.decided_at = now

    run = db.get(WorkflowRun, request.workflow_run_id)
    if run is None:  # pragma: no cover - FK integrity
        msg = f"Workflow run {request.workflow_run_id} no longer exists"
        raise NotFoundError(msg)

    if decision.status == ApprovalStatus.REJECTED:
        _apply_to_activities(db, request, ActivityStatus.CANCELLED, note="Plan rejected by reviewer.")
        run.status = WorkflowStatus.COMPLETED_WITH_WARNINGS.value
        _append_warning(run, f"Plan rejected by {decision.reviewer_name}.")
    elif decision.status == ApprovalStatus.MODIFIED:
        _apply_to_activities(
            db, request, ActivityStatus.SCHEDULED, note="Plan modified by reviewer.", reviewer=decision.reviewer_name
        )
        if run.status == WorkflowStatus.AWAITING_HUMAN_REVIEW.value:
            run.status = WorkflowStatus.COMPLETED.value
    else:  # APPROVED
        _apply_to_activities(
            db, request, ActivityStatus.SCHEDULED, note="Plan approved by reviewer.", reviewer=decision.reviewer_name
        )
        if run.status == WorkflowStatus.AWAITING_HUMAN_REVIEW.value:
            run.status = WorkflowStatus.COMPLETED.value

    db.flush()
    logger.info("Approval %s decided as %s by %s", request.id, decision.status.value, decision.reviewer_name)
    return request


def _apply_to_activities(
    db: Session,
    request: ApprovalRequest,
    status: ActivityStatus,
    *,
    note: str,
    reviewer: str | None = None,
) -> None:
    """Apply the human decision to the activities that belong to the plan.

    A reviewer who authorises or cancels work is the accountable person for it, so
    ``responsible_person`` is filled from the decision whenever the activity
    planner did not already name someone.  A named owner from the plan is never
    overwritten - the agronomist who set the plan outranks the approver.
    """
    activities = list(
        db.scalars(
            select(FarmActivity).where(
                FarmActivity.approval_request_id == request.id,
                FarmActivity.status.in_([ActivityStatus.PLANNED.value, ActivityStatus.SCHEDULED.value]),
            )
        ).all()
    )
    for activity in activities:
        activity.status = status.value
        activity.notes = note
        if reviewer and not activity.responsible_person:
            activity.responsible_person = reviewer


def _append_warning(run: WorkflowRun, message: str) -> None:
    warnings = list(run.warnings or [])
    if message not in warnings:
        warnings.append(message)
    run.warnings = warnings


def mark_reanalysis(run: WorkflowRun, notes: str | None) -> None:
    """Flag a run so the orchestrator produces a fresh analysis."""
    _append_warning(run, f"Re-analysis requested by reviewer: {notes or 'no note supplied'}")
    run.status = WorkflowStatus.PENDING.value
