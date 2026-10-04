"""Workflow run persistence.

Owns the lifecycle of a :class:`~app.models.workflow.WorkflowRun`: creating the
shell row before the graph starts, recording every agent trace, snapshotting the
explicit workflow state at the end, and producing the condensed summary the API
and the PDF report consume.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.models.enums import WorkflowStatus
from app.models.farm import Farm, Field
from app.models.workflow import AgentTrace, ApprovalRequest, WorkflowRun

logger = get_logger(__name__)


def create_run(db: Session, *, field: Field, crop: str | None) -> WorkflowRun:
    run = WorkflowRun(
        farm_id=field.farm_id,
        field_id=field.id,
        status=WorkflowStatus.PENDING.value,
        current_step="created",
        crop=crop,
        state={},
        agents_invoked=[],
        warnings=[],
    )
    db.add(run)
    db.flush()
    logger.info("Created workflow run %s for field %s", run.id, field.id)
    return run


def record_trace(
    db: Session,
    run: WorkflowRun,
    *,
    sequence: int,
    agent_name: str,
    responsibility: str,
    status: str,
    input_summary: dict,
    output: dict,
    evidence: list[dict] | None = None,
    sources: list[dict] | None = None,
    reasoning: str | None = None,
    error: str | None = None,
    duration_ms: float | None = None,
    model_used: str | None = None,
) -> AgentTrace:
    trace = AgentTrace(
        workflow_run_id=run.id,
        sequence=sequence,
        agent_name=agent_name,
        responsibility=responsibility,
        status=status,
        input_summary=input_summary,
        output=output,
        evidence=evidence or [],
        sources=sources or [],
        reasoning=reasoning,
        error=error,
        duration_ms=duration_ms,
        model_used=model_used,
    )
    db.add(trace)

    invoked = list(run.agents_invoked or [])
    if agent_name not in invoked:
        invoked.append(agent_name)
    run.agents_invoked = invoked
    run.current_step = agent_name
    db.flush()
    return trace


def finalise(
    db: Session,
    run: WorkflowRun,
    *,
    state: dict[str, Any],
    status: str,
    warnings: list[str] | None = None,
    error: str | None = None,
    duration_ms: float | None = None,
) -> WorkflowRun:
    run.state = state
    run.warnings = list(warnings or [])
    run.error = error
    run.status = status
    run.completed_at = datetime.now(UTC)
    run.duration_ms = duration_ms
    run.current_step = "finished"
    db.flush()
    logger.info("Finalised workflow run %s with status %s", run.id, status)
    return run


def get_run(db: Session, run_id: int) -> WorkflowRun:
    run = db.get(WorkflowRun, run_id)
    if run is None:
        msg = f"Workflow run {run_id} was not found"
        raise NotFoundError(msg)
    return run


def latest_run_for_field(db: Session, field_id: int) -> WorkflowRun | None:
    return db.scalars(
        select(WorkflowRun).where(WorkflowRun.field_id == field_id).order_by(WorkflowRun.id.desc())
    ).first()


def list_runs(
    db: Session,
    *,
    farm_id: int | None = None,
    field_id: int | None = None,
    status: str | None = None,
    limit: int = 25,
    offset: int = 0,
) -> tuple[list[WorkflowRun], int]:
    statement = select(WorkflowRun)
    if farm_id is not None:
        statement = statement.where(WorkflowRun.farm_id == farm_id)
    if field_id is not None:
        statement = statement.where(WorkflowRun.field_id == field_id)
    if status:
        statement = statement.where(WorkflowRun.status == status)

    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = list(db.scalars(statement.order_by(WorkflowRun.id.desc()).limit(limit).offset(offset)).all())
    return rows, int(total)


def latest_approval(db: Session, run_id: int) -> ApprovalRequest | None:
    """Newest approval request attached to a run (pending or decided)."""
    return db.scalars(
        select(ApprovalRequest).where(ApprovalRequest.workflow_run_id == run_id).order_by(ApprovalRequest.id.desc())
    ).first()


def build_summary(db: Session, run: WorkflowRun) -> dict[str, Any]:
    """Condense a finished run into the shape used by the UI and the report.

    ``run`` is refreshed first: every graph node opens its own database session,
    so ``agents_invoked``, ``agents_invoked`` traces and ``state`` written by the
    nodes are invisible on the caller's session object until it is reloaded.
    """
    db.refresh(run)
    field = db.get(Field, run.field_id)
    farm = db.get(Farm, run.farm_id) if run.field_id else None
    state = run.state or {}
    approval = latest_approval(db, run.id)

    return {
        "workflow_run_id": run.id,
        "field_id": run.field_id,
        "field_name": field.name if field else f"Field {run.field_id}",
        "farm_name": farm.name if farm else f"Farm {run.farm_id}",
        "crop": run.crop or (field.proposed_crop if field else None) or "unspecified",
        "status": run.status,
        "suitability": state.get("suitability"),
        "irrigation": state.get("irrigation"),
        "risk_level": (state.get("risk") or {}).get("risk_level", "unknown"),
        "risk_findings": (state.get("risk") or {}).get("findings", []),
        "ml_predictions": state.get("ml_predictions", []),
        "alerts": state.get("alerts", []),
        "activities": state.get("activities", []),
        "approval": _approval_payload(approval),
        "sources": state.get("sources", []),
        "evidence": state.get("evidence", []),
        "warnings": list(run.warnings or []),
        "agents_invoked": list(run.agents_invoked or []),
        "completed_at": run.completed_at,
        "duration_ms": run.duration_ms,
    }


def _approval_payload(approval: ApprovalRequest | None) -> dict[str, Any] | None:
    if approval is None:
        return None
    return {
        "id": approval.id,
        "title": approval.title,
        "action_type": approval.action_type,
        "status": approval.status,
        "reviewer_name": approval.reviewer_name,
        "decision_note": approval.decision_note,
        "observation": approval.observation,
        "reanalysis_requested": approval.reanalysis_requested,
        "decided_at": approval.decided_at,
        "created_at": approval.created_at,
    }
