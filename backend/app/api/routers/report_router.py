"""PDF report generation, listing and download."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Response, status
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.api.deps import DbSession, FieldDep, PageDep, paginate
from app.core.config import settings
from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.models.farm import Farm, Field
from app.models.operations import Report
from app.models.workflow import WorkflowRun
from app.schemas.operations import ReportCreate, ReportOut
from app.services import report_builder, report_service, workflow_store

logger = get_logger(__name__)
router = APIRouter(tags=["reports"])


def _download_url(report_id: int) -> str:
    return f"{settings.api_v1_prefix}/reports/{report_id}/download"


def _report_out(row: Report) -> ReportOut:
    out = ReportOut.model_validate(row, from_attributes=True)
    return out.model_copy(update={"download_url": _download_url(row.id) if row.status == "ready" else None})


@router.get("/reports", response_model=list[ReportOut], summary="List generated reports")
def list_reports(
    db: DbSession,
    page: PageDep,
    field_id: int | None = None,
    farm_id: int | None = None,
) -> list[ReportOut]:
    statement = select(Report).order_by(Report.id.desc())
    if field_id is not None:
        statement = statement.where(Report.field_id == field_id)
    if farm_id is not None:
        statement = statement.where(Report.farm_id == farm_id)
    rows, _ = paginate(db, statement, page)
    return [_report_out(row) for row in rows]


@router.post(
    "/reports",
    response_model=ReportOut,
    status_code=status.HTTP_201_CREATED,
    summary="Generate a PDF report for a field",
)
def create_report(payload: ReportCreate, db: DbSession, field: FieldDep) -> ReportOut:
    run = None
    if payload.workflow_run_id is not None:
        run = workflow_store.get_run(db, payload.workflow_run_id)
        if run.field_id != field.id:
            msg = f"Workflow run {payload.workflow_run_id} belongs to field {run.field_id}, not field {field.id}"
            raise NotFoundError(msg)
    else:
        run = workflow_store.latest_run_for_field(db, field.id)

    row = _build(db, field=field, run=run, title=payload.title)
    db.commit()
    db.refresh(row)
    return _report_out(row)


@router.get("/reports/{report_id}", response_model=ReportOut, summary="Report metadata")
def get_report(report_id: int, db: DbSession) -> ReportOut:
    row = db.get(Report, report_id)
    if row is None:
        msg = f"Report {report_id} was not found"
        raise NotFoundError(msg)
    return _report_out(row)


@router.get("/reports/{report_id}/download", summary="Download the PDF")
def download(report_id: int, db: DbSession) -> FileResponse:
    row = db.get(Report, report_id)
    if row is None:
        msg = f"Report {report_id} was not found"
        raise NotFoundError(msg)
    if not row.file_path or not Path(row.file_path).is_file():
        msg = f"Report {report_id} has no file on disk (status '{row.status}'). Regenerate it first."
        raise NotFoundError(msg)
    return FileResponse(
        path=row.file_path,
        media_type="application/pdf",
        filename=row.file_name or f"report-{report_id}.pdf",
    )


@router.delete("/reports/{report_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a report")
def delete_report(report_id: int, db: DbSession) -> Response:
    row = db.get(Report, report_id)
    if row is None:
        msg = f"Report {report_id} was not found"
        raise NotFoundError(msg)
    if row.file_path:
        path = Path(row.file_path)
        if path.is_file():
            path.unlink()
    db.delete(row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def generate_for_run(db, *, run_id: int) -> dict[str, Any]:  # noqa: ANN001
    """Build (or rebuild) the report for a workflow run.  Used by the workflow router."""
    run = workflow_store.get_run(db, run_id)
    field = db.get(Field, run.field_id)
    if field is None:  # pragma: no cover - FK integrity
        msg = f"Field {run.field_id} no longer exists"
        raise NotFoundError(msg)

    existing = db.scalars(select(Report).where(Report.workflow_run_id == run_id, Report.status == "ready")).first()
    if existing is not None:
        return {
            "report_id": existing.id,
            "status": existing.status,
            "file_name": existing.file_name,
            "reused": True,
            "download_url": _download_url(existing.id),
        }

    row = _build(db, field=field, run=run, title=None)
    db.commit()
    db.refresh(row)
    return {
        "report_id": row.id,
        "status": row.status,
        "file_name": row.file_name,
        "size_bytes": row.size_bytes,
        "page_count": row.page_count,
        "reused": False,
        "download_url": _download_url(row.id),
    }


def _build(db, *, field: Field, run: WorkflowRun | None, title: str | None) -> Report:  # noqa: ANN001
    farm = db.get(Farm, field.farm_id)
    report_title = title or (f"Precision farming report - {field.name} ({field.proposed_crop or 'crop unspecified'})")

    state = (run.state if run else {}) or {}
    row = Report(
        farm_id=field.farm_id,
        field_id=field.id,
        workflow_run_id=run.id if run else None,
        title=report_title,
        status="generating",
        section_summary={},
    )
    db.add(row)
    db.flush()

    try:
        file_name = report_service.unique_file_name(f"{field.field_code}-{field.name}")
        destination = report_service.reports_root() / file_name
        context, sections = report_builder.build_sections(
            field=field, farm=farm, run=run, state=state, generated_at=None
        )
        rendered = report_service.build_report_pdf(
            destination=destination,
            title=report_title,
            context=context,
            sections=sections,
            references=state.get("sources", []),
        )
        row.file_name = file_name
        row.file_path = str(destination.resolve())
        row.size_bytes = rendered.size_bytes
        row.page_count = rendered.page_count
        row.status = "ready"
        row.section_summary = {
            "sections": [section["title"] for section in sections],
            "section_count": len(sections),
            "page_count": rendered.page_count,
            "evidence_items": len(state.get("evidence", [])),
            "references": len(state.get("sources", [])),
            "workflow_run_id": run.id if run else None,
            "agents_invoked": list(run.agents_invoked) if run else [],
        }
        row.error = None
        logger.info("Report %s generated (%s bytes)", row.id, row.size_bytes)
    except Exception as exc:
        row.status = "failed"
        row.error = f"{type(exc).__name__}: {exc}"
        logger.exception("Report generation failed for field %s", field.id)

    db.flush()
    return row
