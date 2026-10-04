"""Health and dashboard aggregation endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter
from sqlalchemy import func, select

from app.agents import agent_catalogue
from app.api.deps import DbSession
from app.core.config import settings
from app.core.database import check_db_connection
from app.core.logging import get_logger
from app.ml.registry import get_ml_registry
from app.models.enums import AlertStatus, ApprovalStatus, WorkflowStatus
from app.models.farm import Farm, Field
from app.models.operations import Alert, FarmActivity
from app.models.sensor import SensorReading
from app.models.soil import SoilObservation
from app.models.workflow import ApprovalRequest, WorkflowRun
from app.rag.retriever import get_retriever
from app.schemas.common import HealthComponent, HealthResponse

logger = get_logger(__name__)
router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse, summary="Component health")
def health() -> HealthResponse:
    retriever = get_retriever()
    registry = get_ml_registry()

    db_ok = check_db_connection()
    components = [
        HealthComponent(
            name="database",
            status="up" if db_ok else "down",
            detail="SQLite (file)" if settings.is_sqlite else "PostgreSQL/other server",
        ),
        HealthComponent(
            name="retrieval",
            status="up" if retriever.available else "down",
            detail=f"{retriever.index_backend}, {retriever.chunk_count} chunks, {retriever.embedding}",
        ),
        HealthComponent(
            name="machine_learning",
            status="up" if registry.available else "degraded",
            detail=(
                f"{len(registry.describe_models())} model(s) loaded"
                if registry.available
                else "; ".join(registry.errors) or "no artifacts"
            ),
        ),
        HealthComponent(
            name="weather",
            status="up" if settings.weather_api_key else "fallback",
            detail=(
                "OpenWeatherMap key configured; Open-Meteo keyless fallback always available"
                if settings.weather_api_key
                else "no API key: Open-Meteo (keyless) then clearly-labelled offline climatology"
            ),
        ),
        HealthComponent(
            name="llm",
            status="configured" if settings.llm_configured else "deterministic",
            detail=(
                f"{settings.llm_model} for advisory phrasing"
                if settings.llm_configured
                else "no key: advisory narratives are composed deterministically from evidence"
            ),
        ),
    ]

    overall = "healthy" if db_ok else "unhealthy"
    return HealthResponse(
        status=overall,
        app=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        database="up" if db_ok else "down",
        ml="up" if registry.available else "degraded",
        rag="up" if retriever.available else "down",
        weather_provider="openweathermap" if settings.weather_api_key else "open-meteo",
        llm_provider=settings.llm_model if settings.llm_configured else "deterministic",
        components=components,
        timestamp=datetime.now(UTC),
    )


@router.get("/health/live", summary="Liveness probe")
def live() -> dict[str, str]:
    return {"status": "alive", "app": settings.app_name, "version": settings.app_version}


@router.get("/health/ready", summary="Readiness probe")
def ready() -> dict[str, Any]:
    db_ok = check_db_connection()
    return {
        "status": "ready" if db_ok else "not_ready",
        "database": db_ok,
        "rag": get_retriever().available,
        "ml": get_ml_registry().available,
    }


@router.get("/dashboard", summary="Cross-farm dashboard aggregates")
def dashboard(db: DbSession) -> dict[str, Any]:
    farm_count = int(db.scalar(select(func.count()).select_from(Farm)) or 0)
    field_count = int(db.scalar(select(func.count()).select_from(Field)) or 0)
    area_total = float(db.scalar(select(func.coalesce(func.sum(Field.area_ha), 0.0))) or 0.0)
    soil_count = int(db.scalar(select(func.count()).select_from(SoilObservation)) or 0)
    reading_count = int(db.scalar(select(func.count()).select_from(SensorReading)) or 0)
    simulated_readings = int(
        db.scalar(select(func.count()).select_from(SensorReading).where(SensorReading.is_simulated.is_(True))) or 0
    )
    open_alerts = int(
        db.scalar(
            select(func.count())
            .select_from(Alert)
            .where(Alert.status.in_([AlertStatus.OPEN.value, AlertStatus.ACKNOWLEDGED.value]))
        )
        or 0
    )
    pending_approvals = int(
        db.scalar(
            select(func.count())
            .select_from(ApprovalRequest)
            .where(ApprovalRequest.status == ApprovalStatus.PENDING.value)
        )
        or 0
    )
    runs_total = int(db.scalar(select(func.count()).select_from(WorkflowRun)) or 0)
    runs_completed = int(
        db.scalar(
            select(func.count())
            .select_from(WorkflowRun)
            .where(
                WorkflowRun.status.in_([WorkflowStatus.COMPLETED.value, WorkflowStatus.COMPLETED_WITH_WARNINGS.value])
            )
        )
        or 0
    )
    planned_activities = int(
        db.scalar(
            select(func.count())
            .select_from(FarmActivity)
            .where(FarmActivity.status.in_(["planned", "scheduled", "in_progress"]))
        )
        or 0
    )

    recent_runs = list(db.scalars(select(WorkflowRun).order_by(WorkflowRun.id.desc()).limit(10)).all())
    registry = get_ml_registry()
    retriever = get_retriever()

    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "farms": farm_count,
        "fields": field_count,
        "total_area_ha": round(area_total, 2),
        "soil_observations": soil_count,
        "sensor_readings": reading_count,
        "simulated_readings": simulated_readings,
        "open_alerts": open_alerts,
        "pending_approvals": pending_approvals,
        "planned_activities": planned_activities,
        "workflow_runs": {
            "total": runs_total,
            "completed": runs_completed,
            "recent": [
                {
                    "id": run.id,
                    "field_id": run.field_id,
                    "crop": run.crop,
                    "status": run.status,
                    "agents_invoked": run.agents_invoked,
                    "duration_ms": run.duration_ms,
                    "created_at": run.created_at.isoformat() if run.created_at else None,
                }
                for run in recent_runs
            ],
        },
        "agents": agent_catalogue(),
        "components": {
            "database": "up" if check_db_connection() else "down",
            "rag": {
                "available": retriever.available,
                "backend": retriever.index_backend,
                "documents": retriever.documents,
                "chunks": retriever.chunk_count,
            },
            "ml": {
                "available": registry.available,
                "models": [card.get("model_name") for card in registry.describe_models()],
            },
            "llm_configured": settings.llm_configured,
        },
    }
