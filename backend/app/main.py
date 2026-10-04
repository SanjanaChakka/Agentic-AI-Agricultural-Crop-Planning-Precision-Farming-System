"""FastAPI application entrypoint.

Responsibilities
----------------
* build the FastAPI app, CORS policy and OpenAPI metadata;
* on startup: ensure the schema, warm the RAG vector store, load the trained
  ML artifacts, seed demo data on an empty database and compile the LangGraph
  agent workflow (failures are logged, never fatal - the API must still boot so
  that the health endpoint can explain what is degraded);
* register every router under the versioned prefix;
* convert all errors into one consistent JSON envelope.

Run locally with::

    uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agents.graph import get_graph
from app.api.routers import ALL_ROUTERS
from app.core.config import settings
from app.core.database import init_db
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.ml.registry import get_ml_registry
from app.rag.retriever import get_retriever
from app.services.seed_service import seed_if_empty

logger = get_logger(__name__)

DESCRIPTION = """
Multi-agent decision support for crop planning and precision farming.

The workflow is orchestrated with **LangGraph** over twelve specialised agents
(farm profile, soil & nutrient, weather & climate, agricultural knowledge RAG,
crop suitability, ML forecasting, irrigation, crop-risk review, activity
planning and advisory). Every agent emits structured evidence, and every
physical action (irrigation in particular) requires **human approval** before it
can leave the `planned` state.
"""


def _bootstrap() -> dict[str, Any]:
    """Warm every optional subsystem.  Never raises."""
    summary: dict[str, Any] = {
        "started_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "database": "unknown",
        "retrieval": "unknown",
        "machine_learning": "unknown",
        "workflow": "unknown",
        "seed": "skipped",
    }

    # 1. Schema -----------------------------------------------------------
    try:
        init_db()
        summary["database"] = "ready"
    except Exception as exc:  # pragma: no cover - fatal for the API
        logger.exception("Database initialisation failed")
        summary["database"] = f"failed: {exc}"

    # 2. Agricultural RAG (FAISS vector index) ---------------------------
    try:
        retriever = get_retriever()
        loaded = retriever.load(force=settings.rag_rebuild_on_startup)
        summary["retrieval"] = (
            f"{retriever.index_backend} ready ({retriever.chunk_count} chunks from "
            f"{len(retriever.documents)} documents)"
            if loaded
            else f"unavailable: {retriever.detail or 'unknown reason'}"
        )
    except Exception as exc:
        logger.exception("Retrieval warm-up failed")
        summary["retrieval"] = f"failed: {exc}"

    # 3. Trained ML artifacts -------------------------------------------
    try:
        registry = get_ml_registry()
        if not registry.available:
            from app.ml.train import train_all

            logger.info("Trained ML artifacts missing - training both models now (first boot).")
            summary_train = train_all(seed=42, seasons=120)
            logger.info("Training finished; metrics.json written (%d model(s)).", len(summary_train.get("models", [])))
            registry.load(force=True)
        summary["machine_learning"] = (
            f"{len(registry.describe_models())} model(s) ready"
            if registry.available
            else f"degraded: {'; '.join(registry.errors) or 'no artifacts found'}"
        )
    except Exception as exc:
        logger.exception("ML registry warm-up failed")
        summary["machine_learning"] = f"failed: {exc}"

    # 4. LangGraph workflow ----------------------------------------------
    try:
        graph = get_graph()
        nodes = [name for name in getattr(graph, "nodes", {}) or {} if name.startswith("agent_")]
        summary["workflow"] = f"compiled with {len(nodes)} agent nodes"
    except Exception as exc:
        logger.exception("Agent workflow compilation failed")
        summary["workflow"] = f"failed: {exc}"

    # 5. Demo data (only for a genuinely empty database) ------------------
    if settings.seed_demo_data_on_startup:
        try:
            from app.core.database import session_scope

            with session_scope() as session:
                summary["seed"] = seed_if_empty(session)
        except Exception as exc:
            logger.exception("Demo data seeding failed")
            summary["seed"] = f"failed: {exc}"

    logger.info(
        "Startup complete | db=%s | rag=%s | ml=%s | workflow=%s | seed=%s",
        summary["database"],
        summary["retrieval"],
        summary["machine_learning"],
        summary["workflow"],
        summary["seed"],
    )
    return summary


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    logger.info("Starting %s v%s", settings.app_name, settings.app_version)
    _bootstrap()
    yield
    logger.info("Shutting down %s", settings.app_name)


def create_app() -> FastAPI:
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        summary="Agentic multi-agent crop planning and precision farming API.",
        description=DESCRIPTION,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        contact={"name": "Precision Farming Platform"},
        license_info={"name": "MIT"},
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list or ["*"],
        allow_origin_regex=r"https://.*\.vercel\.app|http://localhost:\d+|https://.*\.on\.render\.com",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(application)

    for router in ALL_ROUTERS:
        application.include_router(router, prefix=settings.api_v1_prefix)

    @application.get("/", tags=["system"], summary="Service banner")
    def root() -> dict[str, Any]:
        return {
            "app": settings.app_name,
            "version": settings.app_version,
            "environment": settings.environment,
            "api": f"{settings.api_v1_prefix}",
            "docs": "/docs",
            "health": f"{settings.api_v1_prefix}/health",
            "agents": f"{settings.api_v1_prefix}/workflow/agents",
        }

    return application


app = create_app()
