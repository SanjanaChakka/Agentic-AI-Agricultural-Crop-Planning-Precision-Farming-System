"""Agent orchestration endpoints (run, inspect, re-analyse)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, status

from app.agents import agent_catalogue, run_workflow
from app.agents.graph import get_graph
from app.api.deps import DbSession, PageDep
from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.models.farm import Field
from app.models.workflow import WorkflowRun
from app.schemas.common import Page
from app.schemas.workflow import (
    AgentTraceOut,
    ReanalysisRequest,
    WorkflowRunDetail,
    WorkflowRunOut,
    WorkflowRunRequest,
    WorkflowRunSummary,
)
from app.services import workflow_store

logger = get_logger(__name__)
router = APIRouter(tags=["agent workflow"])


def _run_out(db: DbSession, run: WorkflowRun) -> WorkflowRunOut:
    approval = workflow_store.latest_approval(db, run.id)
    payload = WorkflowRunOut.model_validate(run, from_attributes=True).model_dump()
    payload["approval_request_id"] = approval.id if approval else None
    payload["approval_status"] = approval.status if approval else None
    return WorkflowRunOut(**payload)


def _detail(db: DbSession, run: WorkflowRun) -> WorkflowRunDetail:
    approval = workflow_store.latest_approval(db, run.id)
    payload = WorkflowRunOut.model_validate(run, from_attributes=True).model_dump()
    payload["approval_request_id"] = approval.id if approval else None
    payload["approval_status"] = approval.status if approval else None
    return WorkflowRunDetail(
        **payload,
        state=run.state or {},
        traces=[AgentTraceOut.model_validate(trace, from_attributes=True) for trace in run.traces],
    )


@router.get("/agents", summary="The specialised agents in this workflow")
def list_agents() -> dict[str, Any]:
    agents = agent_catalogue()
    return {
        "count": len(agents),
        "agents": agents,
        "orchestration": {
            "framework": "langgraph",
            "topology": "linear state machine",
            "graph_nodes": len(agents),
            "state": "explicit, JSON-serialisable WorkflowState persisted on workflow_runs.state",
        },
    }


@router.get("/agents/graph", summary="Compiled graph topology")
def graph_topology() -> dict[str, Any]:
    graph = get_graph()
    nodes = list(getattr(graph, "nodes", {}) or [])
    return {
        "framework": "langgraph",
        "nodes": nodes,
        "edges": "each node feeds the next; the final node terminates the run",
        "persisted_state": "workflow_runs.state",
    }


@router.post(
    "/workflow/runs",
    response_model=WorkflowRunSummary,
    status_code=status.HTTP_201_CREATED,
    summary="Execute the full multi-agent planning cycle for a field",
)
def start_run(payload: WorkflowRunRequest, db: DbSession) -> WorkflowRunSummary:
    field = db.get(Field, payload.field_id)
    if field is None:
        msg = f"Field {payload.field_id} was not found"
        raise NotFoundError(msg)
    db.commit()

    summary = run_workflow(
        field_id=payload.field_id,
        crop=payload.crop,
        force_refresh_weather=payload.force_refresh_weather,
        simulate_sensors_if_missing=payload.simulate_sensors_if_missing,
        include_approved_only=payload.include_approved_only,
        responsible_person=payload.responsible_person,
        notes=payload.notes,
    )
    logger.info("Workflow run %s completed", summary.get("workflow_run_id"))
    return WorkflowRunSummary(**summary)


@router.get("/workflow/runs", response_model=list[WorkflowRunOut], summary="List workflow runs")
def list_runs(
    db: DbSession,
    page: PageDep,
    farm_id: int | None = None,
    field_id: int | None = None,
    run_status: str | None = None,
) -> list[WorkflowRunOut]:
    rows, _ = workflow_store.list_runs(
        db, farm_id=farm_id, field_id=field_id, status=run_status, limit=page.limit, offset=page.offset
    )
    return [_run_out(db, run) for run in rows]


@router.get("/workflow/runs/count", response_model=Page, summary="Count workflow runs")
def count_runs(db: DbSession, farm_id: int | None = None, field_id: int | None = None) -> Page:
    _, total = workflow_store.list_runs(db, farm_id=farm_id, field_id=field_id, limit=1)
    return Page(total=total, limit=1, offset=0)


@router.get("/workflow/runs/field/{field_id}/latest", response_model=WorkflowRunDetail | None, summary="Latest run")
def latest_run(field_id: int, db: DbSession) -> WorkflowRunDetail | None:
    run = workflow_store.latest_run_for_field(db, field_id)
    if run is None:
        return None
    return _detail(db, run)


@router.get("/workflow/runs/{run_id}", response_model=WorkflowRunDetail, summary="Run detail with agent traces")
def get_run(run_id: int, db: DbSession) -> WorkflowRunDetail:
    run = workflow_store.get_run(db, run_id)
    return _detail(db, run)


@router.get("/workflow/runs/{run_id}/traces", response_model=list[AgentTraceOut], summary="Per-agent audit trail")
def run_traces(run_id: int, db: DbSession) -> list[AgentTraceOut]:
    run = workflow_store.get_run(db, run_id)
    return [AgentTraceOut.model_validate(trace, from_attributes=True) for trace in run.traces]


@router.get("/workflow/runs/{run_id}/summary", response_model=WorkflowRunSummary, summary="Condensed result")
def run_summary(run_id: int, db: DbSession) -> WorkflowRunSummary:
    run = workflow_store.get_run(db, run_id)
    return WorkflowRunSummary(**workflow_store.build_summary(db, run))


@router.post(
    "/workflow/runs/{run_id}/reanalyse",
    response_model=WorkflowRunSummary,
    status_code=status.HTTP_201_CREATED,
    summary="Re-run the agents carrying the reviewer's observations",
)
def reanalyse(run_id: int, payload: ReanalysisRequest, db: DbSession) -> WorkflowRunSummary:
    original = workflow_store.get_run(db, run_id)
    db.commit()

    summary = run_workflow(
        field_id=original.field_id,
        crop=original.crop,
        force_refresh_weather=payload.force_refresh_weather,
        notes=payload.notes or f"Re-analysis of run {run_id}",
    )
    logger.info("Re-analysis of run %s produced run %s", run_id, summary.get("workflow_run_id"))
    return WorkflowRunSummary(**summary)


@router.post(
    "/workflow/runs/{run_id}/report",
    status_code=status.HTTP_201_CREATED,
    summary="Generate the PDF report for a run",
)
def report_for_run(run_id: int, db: DbSession) -> dict[str, Any]:
    from app.api.routers.report_router import generate_for_run

    return generate_for_run(db, run_id=run_id)
