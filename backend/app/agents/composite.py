"""Composite agents: six specialised agents, each a small ordered pipeline.

The assignment asks for a minimum of six specialised agents. The original
twelve-step graph split several concerns across dedicated nodes - telemetry
acquisition, the weather-bundle bridge, RAG retrieval, the ML forecast, activity
scheduling and narrative composition. Each of those steps still has to run, but
presenting twelve nodes makes the architecture harder to follow than the brief
describes.

A :class:`CompositeAgent` therefore groups the steps under the six agents the
brief actually specifies:

===  ==============================  ==================================
Node Steps folded in
===  ==============================  ==================================
1    farm field profile              sensor telemetry acquisition
2    soil and nutrient analysis      -
3    weather and climate analysis    typed weather-bundle bridge
4    crop planning and suitability   knowledge retrieval (RAG)
5    irrigation planning             ML forecast
6    crop risk and farm advisory     activity planning, advisory narrative
===  ==============================  ==================================

No behaviour is discarded. Each step is the *same* object the twelve-node graph
used, and the composite feeds every step's ``state_patch`` forward into
``ctx.options`` so a step reads exactly the state it would have read as its own
graph node. The composite collapses those steps into one ``AgentResult`` whose
``output`` carries a ``steps`` breakdown, so the UI and the PDF report can still
show which sub-step produced which conclusion.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from typing import Any

from app.agents.base import AgentContext, AgentResult, BaseAgent
from app.core.logging import get_logger
from app.schemas.common import SourceReference

logger = get_logger(__name__)


class CompositeAgent(BaseAgent):
    """Runs several :class:`BaseAgent` steps as one graph node.

    Sub-steps share a single :class:`AgentContext`, exactly as separate nodes
    would share ``WorkflowState``. After each step its ``state_patch`` is merged
    into ``ctx.options`` so the next step observes the same inputs it would have
    observed in the flat graph.
    """

    def __init__(self, name: str, responsibility: str, steps: Sequence[tuple[str, BaseAgent]]) -> None:
        self.name = name
        self.responsibility = responsibility
        self.steps = list(steps)

    def run(self, ctx: AgentContext) -> AgentResult:
        started = time.perf_counter()
        combined_output: dict[str, Any] = {}
        combined_patch: dict[str, Any] = {}
        combined_evidence: list[Any] = []
        combined_sources: list[SourceReference] = []
        reasoning_parts: list[str] = []
        step_report: list[dict[str, Any]] = []
        failures: list[str] = []

        for label, agent in self.steps:
            evidence_before = len(ctx.evidence)
            sources_before = len(ctx.sources)

            result = agent.execute(ctx)

            # Forward this step's state so the next step sees it, mirroring how
            # LangGraph threads WorkflowState between nodes.
            for key, value in result.state_patch.items():
                ctx.options[key] = value
                combined_patch[key] = value

            # Evidence and sources were appended to the context by execute();
            # take only the delta so the orchestrator does not double-count them.
            combined_evidence.extend(ctx.evidence[evidence_before:])
            combined_sources.extend(ctx.sources[sources_before:])

            # Expose each step's own output under its label, and merge any
            # unlabelled keys so callers relying on them keep working.
            combined_output[label] = result.output
            for key, value in result.output.items():
                combined_output.setdefault(key, value)

            if result.reasoning:
                reasoning_parts.append(f"[{label.replace('_', ' ')}] {result.reasoning}")

            status = result.status
            if result.error:
                failures.append(f"{label}: {result.error}")
            step_report.append(
                {
                    "step": label,
                    "agent_name": result.name,
                    "responsibility": result.responsibility,
                    "status": status,
                    "duration_ms": result.duration_ms,
                    "error": result.error,
                }
            )

        combined_output["steps"] = step_report
        combined_output["step_count"] = len(step_report)

        # A composite only reports failure if every step failed; one degraded
        # step is already reported through its own status and ctx.warn.
        all_failed = bool(step_report) and all(item["status"] == "failed" for item in step_report)
        status = "failed" if all_failed else "succeeded"

        return AgentResult(
            name=self.name,
            responsibility=self.responsibility,
            status=status,
            output=combined_output,
            state_patch=combined_patch,
            evidence=combined_evidence,
            sources=combined_sources,
            reasoning=" ".join(reasoning_parts),
            error="; ".join(failures) if all_failed and failures else None,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        )
