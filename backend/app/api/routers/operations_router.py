"""Human-in-the-loop approvals, activity plan and alerts endpoints."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, status
from sqlalchemy import select

from app.api.deps import DbSession, FieldDep, PageDep, paginate
from app.core.errors import NotFoundError, UnprocessableEntityError
from app.core.logging import get_logger
from app.models.enums import AlertStatus, ApprovalStatus
from app.models.operations import Alert, FarmActivity
from app.models.workflow import ApprovalRequest
from app.schemas.operations import (
    ActivityPlanRequest,
    AlertOut,
    AlertUpdate,
    FarmActivityCreate,
    FarmActivityOut,
    FarmActivityUpdate,
)
from app.schemas.workflow import ApprovalDecision, ApprovalOut
from app.services import activity_service, approval_service, workflow_store

logger = get_logger(__name__)

approval_router = APIRouter(tags=["approvals"])
activity_router = APIRouter(tags=["activities"])
alert_router = APIRouter(tags=["alerts"])


# ----------------------------------------------------------------------
# Approvals
# ----------------------------------------------------------------------
@approval_router.get("/approvals", response_model=list[ApprovalOut], summary="List approval requests")
def list_approvals(
    db: DbSession,
    page: PageDep,
    field_id: int | None = None,
    approval_status: str | None = None,
) -> list[ApprovalOut]:
    statement = select(ApprovalRequest).order_by(ApprovalRequest.id.desc())
    if field_id is not None:
        statement = statement.where(ApprovalRequest.field_id == field_id)
    if approval_status:
        statement = statement.where(ApprovalRequest.status == approval_status)
    rows, _ = paginate(db, statement, page)
    return [ApprovalOut.model_validate(row, from_attributes=True) for row in rows]


@approval_router.get("/approvals/pending", response_model=list[ApprovalOut], summary="Pending human review")
def pending_approvals(db: DbSession, page: PageDep) -> list[ApprovalOut]:
    statement = (
        select(ApprovalRequest)
        .where(ApprovalRequest.status == ApprovalStatus.PENDING.value)
        .order_by(ApprovalRequest.id.desc())
    )
    rows, _ = paginate(db, statement, page)
    return [ApprovalOut.model_validate(row, from_attributes=True) for row in rows]


@approval_router.get(
    "/approvals/safety-contract",
    summary="What approval does and does not do",
)
def safety_contract() -> dict[str, object]:
    return {
        "approved": "Authorises the recorded plan and moves its activities to 'scheduled'.",
        "rejected": "Cancels the planned activities.",
        "modified": "Stores the reviewer's adjusted action and schedules it.",
        "reanalysis_requested": "Flags the run so a fresh multi-agent analysis can be started.",
        "never": (
            "This system has no code path that actuates a valve, pump or any other physical equipment. "
            "Approval authorises documentation only."
        ),
    }


@approval_router.get("/approvals/{approval_id}", response_model=ApprovalOut, summary="One approval request")
def get_approval(approval_id: int, db: DbSession) -> ApprovalOut:
    row = db.get(ApprovalRequest, approval_id)
    if row is None:
        msg = f"Approval request {approval_id} was not found"
        raise NotFoundError(msg)
    return ApprovalOut.model_validate(row, from_attributes=True)


@approval_router.post(
    "/approvals/{approval_id}/decision",
    response_model=ApprovalOut,
    summary="Approve, reject, modify or request re-analysis",
)
def decide(approval_id: int, decision: ApprovalDecision, db: DbSession) -> ApprovalOut:
    row = db.get(ApprovalRequest, approval_id)
    if row is None:
        msg = f"Approval request {approval_id} was not found"
        raise NotFoundError(msg)
    approval_service.decide(db, row, decision)
    db.commit()
    db.refresh(row)
    logger.info("Approval %s resolved as %s by %s", approval_id, decision.status.value, decision.reviewer_name)
    return ApprovalOut.model_validate(row, from_attributes=True)


# ----------------------------------------------------------------------
# Activities
# ----------------------------------------------------------------------
def _activity_out(row: FarmActivity) -> FarmActivityOut:
    return FarmActivityOut.model_validate(row, from_attributes=True)


@activity_router.get("/activities", response_model=list[FarmActivityOut], summary="List farm activities")
def list_activities(
    db: DbSession,
    page: PageDep,
    field_id: int | None = None,
    activity_status: str | None = None,
    workflow_run_id: int | None = None,
) -> list[FarmActivityOut]:
    statement = select(FarmActivity).order_by(
        FarmActivity.scheduled_date.is_(None), FarmActivity.scheduled_date, FarmActivity.id
    )
    if field_id is not None:
        statement = statement.where(FarmActivity.field_id == field_id)
    if activity_status:
        statement = statement.where(FarmActivity.status == activity_status)
    if workflow_run_id is not None:
        statement = statement.where(FarmActivity.workflow_run_id == workflow_run_id)
    rows, _ = paginate(db, statement, page)
    return [_activity_out(row) for row in rows]


@activity_router.post(
    "/activities",
    response_model=FarmActivityOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add a manual activity",
)
def create_activity(payload: FarmActivityCreate, db: DbSession) -> FarmActivityOut:
    from app.models.farm import Field

    field = db.get(Field, payload.field_id)
    if field is None:
        msg = f"Field {payload.field_id} was not found"
        raise NotFoundError(msg)
    row = FarmActivity(
        field_id=payload.field_id,
        activity_type=payload.activity_type.value,
        title=payload.title,
        scheduled_date=payload.scheduled_date,
        window_days=payload.window_days,
        responsible_person=payload.responsible_person,
        reason=payload.reason,
        priority=payload.priority,
        status="planned",
        evidence=[],
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _activity_out(row)


@activity_router.post(
    "/activities/plan",
    response_model=list[FarmActivityOut],
    summary="Plan activities from a completed workflow run",
)
def plan_activities(payload: ActivityPlanRequest, db: DbSession) -> list[FarmActivityOut]:
    if payload.workflow_run_id is None:
        msg = "workflow_run_id is required to plan activities"
        raise UnprocessableEntityError(msg)
    run = workflow_store.get_run(db, payload.workflow_run_id)
    rows = activity_service.plan_for_run(
        db,
        run,
        responsible_person=payload.responsible_person,
        include_approved_only=payload.include_approved_only,
    )
    db.commit()
    for row in rows:
        db.refresh(row)
    return [_activity_out(row) for row in rows]


@activity_router.get("/activities/fields/{field_id}/upcoming", response_model=list[FarmActivityOut], summary="Upcoming")
def upcoming(field: FieldDep, db: DbSession, days: int = 14) -> list[FarmActivityOut]:
    from datetime import timedelta

    horizon = datetime.now(UTC) + timedelta(days=days)
    statement = (
        select(FarmActivity)
        .where(
            FarmActivity.field_id == field.id,
            FarmActivity.status.in_(["planned", "scheduled", "in_progress"]),
        )
        .order_by(FarmActivity.scheduled_date.is_(None), FarmActivity.scheduled_date, FarmActivity.id)
    )
    rows = [row for row in db.scalars(statement).all() if row.scheduled_date is None or row.scheduled_date <= horizon]
    return [_activity_out(row) for row in rows]


@activity_router.patch("/activities/{activity_id}", response_model=FarmActivityOut, summary="Update an activity")
def update_activity(activity_id: int, payload: FarmActivityUpdate, db: DbSession) -> FarmActivityOut:
    row = db.get(FarmActivity, activity_id)
    if row is None:
        msg = f"Activity {activity_id} was not found"
        raise NotFoundError(msg)
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(row, key, value.value if hasattr(value, "value") else value)
    db.commit()
    db.refresh(row)
    return _activity_out(row)


# ----------------------------------------------------------------------
# Alerts
# ----------------------------------------------------------------------
@alert_router.get("/alerts", response_model=list[AlertOut], summary="List alerts")
def list_alerts(
    db: DbSession,
    page: PageDep,
    farm_id: int | None = None,
    field_id: int | None = None,
    alert_status: str | None = None,
    severity: str | None = None,
) -> list[AlertOut]:
    statement = select(Alert).order_by(Alert.last_observed_at.desc())
    if farm_id is not None:
        statement = statement.where(Alert.farm_id == farm_id)
    if field_id is not None:
        statement = statement.where(Alert.field_id == field_id)
    if alert_status:
        statement = statement.where(Alert.status == alert_status)
    if severity:
        statement = statement.where(Alert.severity == severity)
    rows, _ = paginate(db, statement, page)
    return [AlertOut.model_validate(row, from_attributes=True) for row in rows]


@alert_router.get("/alerts/open", response_model=list[AlertOut], summary="Open and acknowledged alerts")
def open_alerts(db: DbSession, farm_id: int | None = None) -> list[AlertOut]:
    statement = (
        select(Alert)
        .where(Alert.status.in_([AlertStatus.OPEN.value, AlertStatus.ACKNOWLEDGED.value]))
        .order_by(Alert.severity_rank.desc(), Alert.last_observed_at.desc())
    )
    if farm_id is not None:
        statement = statement.where(Alert.farm_id == farm_id)
    return [AlertOut.model_validate(row, from_attributes=True) for row in db.scalars(statement).all()]


@alert_router.patch("/alerts/{alert_id}", response_model=AlertOut, summary="Acknowledge or resolve an alert")
def update_alert(alert_id: int, payload: AlertUpdate, db: DbSession) -> AlertOut:
    row = db.get(Alert, alert_id)
    if row is None:
        msg = f"Alert {alert_id} was not found"
        raise NotFoundError(msg)
    now = datetime.now(UTC)
    row.status = payload.status.value
    if payload.acknowledged_by:
        row.acknowledged_by = payload.acknowledged_by
    if payload.status == AlertStatus.ACKNOWLEDGED and row.acknowledged_at is None:
        row.acknowledged_at = now
    if payload.status == AlertStatus.RESOLVED:
        row.resolved_at = now
        if row.acknowledged_at is None:
            row.acknowledged_at = now
            row.acknowledged_by = payload.acknowledged_by or "system"
    db.commit()
    db.refresh(row)
    return AlertOut.model_validate(row, from_attributes=True)


@alert_router.get("/alerts/dedup-policy", summary="How duplicate alerts are suppressed")
def dedup_policy() -> dict[str, str]:
    return {
        "key": "sha1(field_id | alert_type | discriminator)",
        "behaviour": (
            "Re-running a scan while the same condition persists updates the existing alert and increments "
            "occurrence_count instead of creating a duplicate. A new alert is raised only for a new "
            "fingerprint or a material severity escalation."
        ),
        "auto_resolve": "Alerts whose condition is no longer present are marked resolved automatically.",
    }
