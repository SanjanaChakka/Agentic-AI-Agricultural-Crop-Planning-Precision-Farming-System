"""Agent contracts shared by every specialised agent.

Each agent is a small, single-responsibility unit with an explicit contract:

* a stable ``name`` used in the workflow state, the API and the audit trail;
* a one-line ``responsibility`` shown in the UI;
* a deterministic ``run(ctx) -> AgentResult`` that never raises for expected
  conditions - it reports the problem in ``AgentResult.error`` and lets the
  orchestrator decide whether to continue.

Every result carries provenance-tagged :class:`Evidence` and citable
:class:`SourceReference` objects so that no conclusion can appear in the UI or
the PDF report without a traceable basis.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Coroutine
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.data.crop_catalog import CropRequirements
from app.ml.registry import MLRegistry, get_ml_registry
from app.models.farm import Farm, Field
from app.rag.retriever import KnowledgeRetriever, get_retriever
from app.schemas.common import Evidence, SourceReference

logger = get_logger(__name__)


class Agent(Protocol):
    """Structural type every agent satisfies."""

    name: str
    responsibility: str

    def run(self, ctx: AgentContext) -> AgentResult:  # pragma: no cover - protocol
        ...


@dataclass
class AgentContext:
    """Everything an agent is allowed to touch."""

    db: Session
    field: Field
    farm: Farm
    crop: str
    requirements: CropRequirements
    workflow_run_id: int
    retriever: KnowledgeRetriever = field(default_factory=get_retriever)
    ml: MLRegistry = field(default_factory=get_ml_registry)
    options: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    sources: list[SourceReference] = field(default_factory=list)

    def warn(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)
            logger.warning("Workflow %s: %s", self.workflow_run_id, message)

    def add_evidence(self, *items: Evidence) -> None:
        self.evidence.extend(items)

    def add_sources(self, *items: SourceReference | dict[str, Any]) -> None:
        """Merge citations, tolerating dicts produced by the service layer."""
        known = {source.doc_key for source in self.sources}
        for raw in items:
            item = SourceReference.model_validate(raw) if isinstance(raw, dict) else raw
            if item.doc_key not in known:
                self.sources.append(item)
                known.add(item.doc_key)

    def retrieve(self, query: str, **kwargs: Any) -> list[SourceReference]:
        """RAG lookup that degrades gracefully when the index is unavailable."""
        if not self.retriever.available:
            self.warn("Retrieval index unavailable; decisions for this step rely on rule logic only.")
            return []
        try:
            return self.retriever.retrieve_references(query, **kwargs)
        except Exception as exc:
            self.warn(f"Retrieval failed ({type(exc).__name__}); rule logic used instead.")
            logger.exception("RAG retrieval failed")
            return []


@dataclass
class AgentResult:
    """Structured output of one agent invocation."""

    name: str
    responsibility: str
    status: str = "succeeded"
    output: dict[str, Any] = field(default_factory=dict)
    state_patch: dict[str, Any] = field(default_factory=dict)
    evidence: list[Evidence] = field(default_factory=list)
    sources: list[SourceReference] = field(default_factory=list)
    reasoning: str = ""
    error: str | None = None
    model_used: str | None = None
    duration_ms: float | None = None

    def as_trace_payload(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reasoning": self.reasoning,
            "error": self.error,
            "model_used": self.model_used,
            "evidence_count": len(self.evidence),
            "source_count": len(self.sources),
        }


class BaseAgent:
    """Convenience base: timing, evidence merging and error containment."""

    name: str = "base_agent"
    responsibility: str = "abstract base agent"

    def execute(self, ctx: AgentContext) -> AgentResult:
        started = time.perf_counter()
        try:
            result = self.run(ctx)
        except Exception as exc:
            logger.exception("Agent %s failed on workflow %s", self.name, ctx.workflow_run_id)
            result = AgentResult(
                name=self.name,
                responsibility=self.responsibility,
                status="failed",
                error=f"{type(exc).__name__}: {exc}",
                reasoning=f"The {self.name} aborted; downstream steps treat its output as unavailable.",
            )
        result.duration_ms = round((time.perf_counter() - started) * 1000, 2)
        result.sources = [SourceReference.model_validate(item) for item in result.sources]
        ctx.add_evidence(*result.evidence)
        ctx.add_sources(*result.sources)
        if result.error:
            ctx.warn(f"{self.name}: {result.error}")
        return result

    def run(self, ctx: AgentContext) -> AgentResult:  # pragma: no cover - abstract
        raise NotImplementedError


def utcnow() -> datetime:
    return datetime.now(UTC)


def run_coroutine(factory: Callable[[], Coroutine[Any, Any, Any]]) -> Any:
    """Run a coroutine from synchronous code, even inside a running loop.

    The graph executes in a worker thread, but the API may be invoked from an
    async endpoint; this helper keeps both paths working.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(factory())

    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(factory())).result()


def evidence_from_measurement(
    label: str,
    value: Any,
    *,
    unit: str | None = None,
    kind: str = "measured",
    source: str | None = None,
    reference: str | None = None,
    note: str | None = None,
    observed_at: datetime | None = None,
) -> Evidence:
    return Evidence(
        label=label,
        value=value,
        unit=unit,
        kind=kind,  # type: ignore[arg-type]
        source=source,
        reference=reference,
        note=note,
        observed_at=observed_at,
    )


def serialise_evidence(items: list[Evidence]) -> list[dict[str, Any]]:
    return [item.model_dump() for item in items]


def serialise_sources(items: list[SourceReference]) -> list[dict[str, Any]]:
    return [item.model_dump() for item in items]
