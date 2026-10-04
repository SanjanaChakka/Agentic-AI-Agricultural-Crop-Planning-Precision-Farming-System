"""LangGraph orchestration of the specialised agents.

The graph is explicit: every node is one agent, every edge is a documented
dependency, and the shared :class:`WorkflowState` is the single source of truth
for the run.  Nothing is hidden in an implicit conversation transcript - the
state is serialisable and is persisted verbatim on ``workflow_runs.state``.

Flow::

    profile -> soil -> telemetry -> weather -> knowledge -> suitability -> ml
            -> irrigation -> risk -> activities -> advisory -> approval

``telemetry`` is a small in-graph node that guarantees the ML and irrigation
agents have sensor data (clearly flagged when it has to be simulated).
"""

from __future__ import annotations

import itertools
import time
from collections.abc import Callable
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from app.agents.analysis_agents import CropSuitabilityAgent, KnowledgeRetrievalAgent, MLForecastAgent
from app.agents.base import AgentContext, AgentResult, BaseAgent
from app.agents.context_agents import (
    FarmFieldProfileAgent,
    SoilNutrientAgent,
    WeatherClimateAgent,
)
from app.agents.decision_agents import (
    ActivityPlannerAgent,
    AdvisoryNarrativeAgent,
    CropRiskAdvisoryAgent,
    IrrigationAgent,
)
from app.core.database import SessionLocal
from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.data.crop_catalog import CROP_REQUIREMENTS, resolve_crop
from app.models.enums import WorkflowStatus
from app.models.farm import Field
from app.services import (
    approval_service,
    sensor_service,
    suitability_service,
    weather_service,
    workflow_store,
)
from app.services.soil_service import latest_observation

logger = get_logger(__name__)


class WorkflowState(TypedDict, total=False):
    """Explicit, serialisable workflow state."""

    # --- inputs ---------------------------------------------------------
    field_id: int
    crop: str | None
    force_refresh_weather: bool
    simulate_sensors_if_missing: bool
    include_approved_only: bool
    responsible_person: str | None
    notes: str | None

    # --- control --------------------------------------------------------
    workflow_run_id: int
    step: str
    sequence: int
    agents_invoked: list[str]
    trace_log: list[dict[str, Any]]
    warnings: list[str]
    errors: list[str]

    # --- agent outputs --------------------------------------------------
    farm_profile: dict[str, Any]
    soil: dict[str, Any]
    telemetry: dict[str, Any]
    weather: dict[str, Any]
    weather_bundle: dict[str, Any] | None
    knowledge: dict[str, Any]
    suitability: dict[str, Any]
    ml_predictions: list[dict[str, Any]]
    irrigation: dict[str, Any]
    risk: dict[str, Any]
    alerts: list[dict[str, Any]]
    activities: list[dict[str, Any]]
    approval: dict[str, Any] | None
    advisory: dict[str, Any]
    evidence: list[dict[str, Any]]
    sources: list[dict[str, Any]]
    status: str


def _reading_payload(reading: Any) -> dict[str, Any] | None:
    """JSON-serialisable view of the latest ``SensorReading`` (or ``None``)."""
    if reading is None:
        return None
    return {
        "sensor_id": reading.sensor_id,
        "recorded_at": reading.recorded_at.isoformat() if reading.recorded_at else None,
        "soil_moisture_percent": reading.soil_moisture_percent,
        "soil_temperature_c": reading.soil_temperature_c,
        "air_temperature_c": reading.air_temperature_c,
        "air_humidity_percent": reading.air_humidity_percent,
        "battery_percent": reading.battery_percent,
        "is_simulated": bool(reading.is_simulated),
        "quality_flags": list(reading.quality_flags or []),
        "notes": reading.notes,
    }


class SensorTelemetryAgent(BaseAgent):
    """Guarantees telemetry exists for the downstream ML and irrigation agents."""

    name = "sensor_telemetry_agent"
    responsibility = "Confirm telemetry availability and flag quality problems before decisions are made"

    def run(self, ctx: AgentContext) -> AgentResult:
        latest = sensor_service.latest_reading(ctx.db, ctx.field.id)
        series, stats = sensor_service.trend(ctx.db, ctx.field.id, hours=168)
        generated = 0

        if latest is None:
            if not bool(ctx.options.get("simulate_sensors_if_missing", True)):
                ctx.warn(
                    "No sensor telemetry exists and simulation was disabled; moisture-dependent steps are limited."
                )
            else:
                generated = len(
                    sensor_service.simulate_readings(
                        ctx.db,
                        ctx.field,
                        hours=72,
                        interval_hours=3.0,
                        sensor_id="SM-01",
                        seed=ctx.field.id * 977 + 13,
                    )
                )
                ctx.warn(
                    f"No telemetry existed for field {ctx.field.id}; {generated} SIMULATED readings were "
                    "generated for demonstration purposes and are flagged in the database."
                )
                latest = sensor_service.latest_reading(ctx.db, ctx.field.id)
                series, stats = sensor_service.trend(ctx.db, ctx.field.id, hours=168)

        evidence = sensor_service.reading_evidence(latest) if latest is not None else []
        flags = list(latest.quality_flags or []) if latest is not None else []
        faults = [flag for flag in flags if flag not in {"ok", "simulated"}]
        if faults:
            ctx.warn(f"Latest telemetry carries quality flags: {', '.join(faults)}.")

        output = {
            "available": latest is not None,
            "generated": generated,
            "latest": _reading_payload(latest),
            "reading_count": len(series),
            "window_hours": 168,
            "trend_stats": stats,
            "quality_flags": flags,
            "quality_faults": faults,
        }

        reasoning = (
            f"{len(series)} reading(s) in the 7-day window"
            + (f" ({generated} generated now)" if generated else "")
            + (
                f"; latest from {latest.sensor_id} at {latest.recorded_at.isoformat()}"
                if latest
                else "; none available"
            )
            + (f" flagged {', '.join(faults)}" if faults else "; no quality faults")
            + "."
        )

        return AgentResult(
            name=self.name,
            responsibility=self.responsibility,
            output=output,
            state_patch={"telemetry": output},
            evidence=evidence,
            reasoning=reasoning,
        )


class TelemetryBridgeAgent(BaseAgent):
    """Rebuilds the typed ``WeatherBundle`` the analysis services expect."""

    name = "weather_bundle_bridge"
    responsibility = "Adapt the stored weather summary into the typed bundle used by the analysis services"

    def run(self, ctx: AgentContext) -> AgentResult:
        weather = ctx.options.get("weather") or {}
        if not weather.get("available"):
            return AgentResult(
                name=self.name,
                responsibility=self.responsibility,
                output={"bundle": None},
                state_patch={"weather_bundle": None},
                reasoning="Weather unavailable; analysis services will run without forecast context.",
            )
        bundle = weather_service.bundle_from_summary(weather)
        return AgentResult(
            name=self.name,
            responsibility=self.responsibility,
            output={"bundle_source": bundle.source, "days": len(bundle.daily)},
            state_patch={"weather_bundle": bundle},
            reasoning=(
                f"Rehydrated a typed weather bundle ({bundle.source}, simulated={bundle.is_simulated}, "
                f"{len(bundle.daily)} days) from the stored summary."
            ),
        )


# ----------------------------------------------------------------------
# Node factories
# ----------------------------------------------------------------------
def _merge_text(existing: list[str], incoming: list[str]) -> list[str]:
    """Order-preserving de-duplication of plain strings."""
    merged = list(existing)
    for item in incoming:
        if item and item not in merged:
            merged.append(item)
    return merged


def _merge_evidence(existing: list[dict[str, Any]], incoming: list[Any]) -> list[dict[str, Any]]:
    """Accumulate evidence across the graph.

    Every node builds a *fresh* :class:`AgentContext`, so an agent only knows
    about its own evidence.  Without merging here the run summary would show
    just the last node's evidence.  De-duplication key is
    ``(kind, label, value, source)`` so the same measurement quoted by two
    agents is stored once.
    """
    merged = [dict(item) for item in existing]
    seen = {_evidence_key(item) for item in merged}
    for item in incoming:
        payload = item.model_dump(mode="json") if hasattr(item, "model_dump") else dict(item)
        key = _evidence_key(payload)
        if key in seen:
            continue
        seen.add(key)
        merged.append(payload)
    return merged


def _evidence_key(payload: dict[str, Any]) -> tuple[str, str, str, str]:
    kind = payload.get("kind")
    return (
        getattr(kind, "value", str(kind or "")),
        str(payload.get("label") or ""),
        str(payload.get("value") if payload.get("value") is not None else ""),
        str(payload.get("source") or ""),
    )


def _merge_sources(existing: list[dict[str, Any]], incoming: list[Any]) -> list[dict[str, Any]]:
    """Accumulate retrieved citations, de-duplicated by document key."""
    merged = [dict(item) for item in existing]
    seen = {str(item.get("doc_key") or "") for item in merged}
    for item in incoming:
        payload = item.model_dump(mode="json") if hasattr(item, "model_dump") else dict(item)
        doc_key = str(payload.get("doc_key") or payload.get("title") or "")
        if doc_key in seen:
            continue
        seen.add(doc_key)
        merged.append(payload)
    return merged


def _node(agent: BaseAgent) -> Callable[[WorkflowState], dict[str, Any]]:
    """Wrap an agent so the graph gets a small, serialisable state patch."""

    def _run(state: WorkflowState) -> dict[str, Any]:
        started = time.perf_counter()
        db = SessionLocal()
        try:
            run = workflow_store.get_run(db, int(state["workflow_run_id"]))
            field = db.get(Field, int(state["field_id"]))
            if field is None:
                msg = f"Field {state['field_id']} no longer exists"
                raise ValueError(msg)

            crop_name = state.get("crop") or field.proposed_crop
            requirements = suitability_service.resolve_requirements(crop_name)
            ctx = AgentContext(
                db=db,
                field=field,
                farm=field.farm,
                crop=requirements.name.lower() if crop_name else "unspecified",
                requirements=requirements,
                workflow_run_id=run.id,
                options=dict(_options_from_state(state)),
            )

            result = agent.execute(ctx)
            sequence = int(state.get("sequence", 0)) + 1

            workflow_store.record_trace(
                db,
                run,
                sequence=sequence,
                agent_name=result.name,
                responsibility=result.responsibility,
                status=result.status,
                input_summary=_input_summary(agent.name, state),
                output=_jsonable(result.output),
                evidence=[item.model_dump() for item in result.evidence],
                sources=[item.model_dump() for item in result.sources],
                reasoning=result.reasoning,
                error=result.error,
                duration_ms=result.duration_ms,
                model_used=result.model_used,
            )
            run.status = WorkflowStatus.RUNNING.value
            db.commit()

            patch: dict[str, Any] = dict(result.state_patch)
            # LangGraph drops keys that are not declared on WorkflowState, which
            # would silently lose an agent's output.  Fail loudly instead.
            unknown = sorted(set(patch) - set(WorkflowState.__annotations__))
            if unknown:
                msg = (
                    f"{result.name} returned state keys that WorkflowState does not declare: "
                    f"{', '.join(unknown)}. Add them to WorkflowState so they survive the graph."
                )
                raise KeyError(msg)
            patch.update(
                {
                    "step": result.name,
                    "sequence": sequence,
                    "agents_invoked": [*list(state.get("agents_invoked", [])), result.name],
                    "trace_log": [
                        *list(state.get("trace_log", [])),
                        {
                            "sequence": sequence,
                            "agent": result.name,
                            "responsibility": result.responsibility,
                            "status": result.status,
                            "duration_ms": result.duration_ms,
                            "error": result.error,
                        },
                    ],
                    "warnings": _merge_text(list(state.get("warnings") or []), list(ctx.warnings)),
                    "evidence": _merge_evidence(list(state.get("evidence") or []), ctx.evidence),
                    "sources": _merge_sources(list(state.get("sources") or []), ctx.sources),
                }
            )
            if result.error:
                patch["errors"] = _merge_text(list(state.get("errors") or []), [f"{result.name}: {result.error}"])
            logger.info(
                "Node %s finished in %s ms (workflow %s)",
                result.name,
                round((time.perf_counter() - started) * 1000, 2),
                run.id,
            )
            return patch
        finally:
            db.close()

    return _run


def _options_from_state(state: WorkflowState) -> dict[str, Any]:
    return {
        "soil": state.get("soil") or {},
        "telemetry": state.get("telemetry") or {},
        "weather": state.get("weather") or {},
        "weather_bundle": state.get("weather_bundle"),
        "knowledge": state.get("knowledge") or {},
        "suitability": state.get("suitability") or {},
        "ml_predictions": state.get("ml_predictions") or [],
        "irrigation": state.get("irrigation") or {},
        "risk": state.get("risk") or {},
        "references": state.get("sources") or [],
        "force_refresh_weather": bool(state.get("force_refresh_weather")),
        "simulate_sensors_if_missing": bool(state.get("simulate_sensors_if_missing", True)),
        "include_approved_only": bool(state.get("include_approved_only")),
        "responsible_person": state.get("responsible_person"),
        "weather_days": 7,
    }


def _input_summary(agent_name: str, state: WorkflowState) -> dict[str, Any]:
    if agent_name == "crop_suitability_agent":
        return {
            "field_id": state.get("field_id"),
            "crop": state.get("crop"),
            "soil_observation": bool(state.get("soil", {}).get("available")),
            "weather_available": bool(state.get("weather", {}).get("available")),
            "references": len(state.get("sources") or []),
        }
    if agent_name in {"irrigation_agent", "crop_risk_advisory_agent", "ml_forecast_agent"}:
        return {
            "field_id": state.get("field_id"),
            "crop": state.get("crop"),
            "latest_reading": (state.get("telemetry") or {}).get("latest"),
            "weather_source": (state.get("weather") or {}).get("source"),
            "ml_predictions": [item.get("task") for item in state.get("ml_predictions") or []],
        }
    return {
        "field_id": state.get("field_id"),
        "crop": state.get("crop"),
        "sequence": state.get("sequence", 0),
    }


def _jsonable(payload: Any) -> Any:
    """Strip ORM objects and datetimes so state stays JSON serialisable."""
    from datetime import date, datetime

    from sqlalchemy.orm import Session as SASession

    if isinstance(payload, dict):
        return {key: _jsonable(value) for key, value in payload.items()}
    if isinstance(payload, list):
        return [_jsonable(item) for item in payload]
    if isinstance(payload, datetime | date):
        return payload.isoformat()
    if isinstance(payload, SASession):
        return None
    if hasattr(payload, "model_dump"):
        try:
            return _jsonable(payload.model_dump(mode="json"))
        except Exception:  # noqa: BLE001 - defensive
            return str(payload)
    if hasattr(payload, "value") and hasattr(payload, "name"):
        return payload.value
    if isinstance(payload, str | int | float | bool) or payload is None:
        return payload
    return str(payload)


# ----------------------------------------------------------------------
# Graph construction
# ----------------------------------------------------------------------
AGENT_ORDER = [
    ("agent_profile", FarmFieldProfileAgent()),
    ("agent_soil", SoilNutrientAgent()),
    ("agent_telemetry", SensorTelemetryAgent()),
    ("agent_weather", WeatherClimateAgent()),
    ("agent_weather_bridge", TelemetryBridgeAgent()),
    ("agent_knowledge", KnowledgeRetrievalAgent()),
    ("agent_suitability", CropSuitabilityAgent()),
    ("agent_ml", MLForecastAgent()),
    ("agent_irrigation", IrrigationAgent()),
    ("agent_risk", CropRiskAdvisoryAgent()),
    ("agent_activities", ActivityPlannerAgent()),
    ("agent_advisory", AdvisoryNarrativeAgent()),
]


def build_graph():  # noqa: ANN201 - returns a compiled LangGraph
    graph = StateGraph(WorkflowState)
    for node_name, agent in AGENT_ORDER:
        graph.add_node(node_name, _node(agent))

    order = [name for name, _ in AGENT_ORDER]
    graph.set_entry_point(order[0])
    for current, following in itertools.pairwise(order):
        graph.add_edge(current, following)
    graph.add_edge(order[-1], END)
    return graph.compile()


_GRAPH = None  # type: ignore[assignment]


def get_graph():  # noqa: ANN201 - lazily compiled singleton
    global _GRAPH  # noqa: PLW0603
    if _GRAPH is None:
        _GRAPH = build_graph()
        logger.info("Compiled agent workflow graph with %s nodes", len(AGENT_ORDER))
    return _GRAPH


def run_workflow(
    *,
    field_id: int,
    crop: str | None = None,
    force_refresh_weather: bool = False,
    simulate_sensors_if_missing: bool = True,
    include_approved_only: bool = False,
    responsible_person: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Execute the whole agent graph and return the condensed run summary.

    This is intentionally synchronous: the LangGraph nodes run one after another
    and the weather node performs its own async HTTP call on a worker thread.
    """
    started = time.perf_counter()
    db = SessionLocal()
    try:
        field = db.get(Field, field_id)
        if field is None:
            msg = f"Field {field_id} was not found"
            raise NotFoundError(msg)

        resolved = crop or field.proposed_crop
        if resolved and resolve_crop(resolved) is None:
            supported = ", ".join(sorted({req.name for req in CROP_REQUIREMENTS.values()}))
            msg = f"Crop '{resolved}' is not in the supported crop catalogue. Supported crops: {supported}."
            raise ValueError(msg)

        run = workflow_store.create_run(db, field=field, crop=resolved)
        db.commit()

        initial: WorkflowState = {
            "field_id": field_id,
            "crop": resolved,
            "force_refresh_weather": force_refresh_weather,
            "simulate_sensors_if_missing": simulate_sensors_if_missing,
            "include_approved_only": include_approved_only,
            "responsible_person": responsible_person,
            "notes": notes,
            "workflow_run_id": run.id,
            "step": "created",
            "sequence": 0,
            "agents_invoked": [],
            "trace_log": [],
            "warnings": [],
            "errors": [],
            "evidence": [],
            "sources": [],
            "status": WorkflowStatus.RUNNING.value,
        }

        final: dict[str, Any] = dict(get_graph().invoke(initial))

        _finalise(db, run, final, started)
        db.commit()

        summary = workflow_store.build_summary(db, run)
        summary["state"] = _jsonable(final)
        summary["errors"] = final.get("errors", [])
        return summary
    finally:
        db.close()


def _finalise(db, run, final: dict[str, Any], started: float) -> None:  # noqa: ANN001
    """Persist the final state, raise the approval gate and set the run status."""
    state = {
        key: _jsonable(value)
        for key, value in final.items()
        if key
        not in {
            "weather_bundle",
            "trace_log",
            "sequence",
            "step",
            "field_id",
            "crop",
            "force_refresh_weather",
            "simulate_sensors_if_missing",
            "include_approved_only",
            "responsible_person",
            "notes",
        }
    }
    state["crop_requirements"] = suitability_service.resolve_requirements(final.get("crop")).name
    state["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    state["soil_observation_id"] = _observation_id(db, int(final["field_id"]))

    warnings = list(final.get("warnings") or [])
    errors = list(final.get("errors") or [])

    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    status = WorkflowStatus.COMPLETED_WITH_WARNINGS.value if errors or warnings else WorkflowStatus.COMPLETED.value

    workflow_store.finalise(
        db,
        run,
        state=state,
        status=status,
        warnings=warnings,
        error="; ".join(errors) or None,
        duration_ms=duration_ms,
    )
    approval_service.create_approval_request(db, run)
    db.flush()


def _observation_id(db, field_id: int) -> int | None:  # noqa: ANN001
    observation = latest_observation(db, field_id)
    return observation.id if observation is not None else None


def agent_catalogue() -> list[dict[str, str]]:
    """Machine-readable list of the agents this workflow uses."""
    return [
        {
            "name": agent.name,
            "responsibility": agent.responsibility,
            "class": type(agent).__name__,
        }
        for _, agent in AGENT_ORDER
    ]
