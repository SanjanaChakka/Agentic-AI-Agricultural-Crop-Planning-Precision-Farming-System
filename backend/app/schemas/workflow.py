"""Workflow orchestration, agent trace and human approval schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.models.enums import ApprovalStatus
from app.schemas.common import Evidence, ORMModel, SourceReference


class WorkflowRunRequest(BaseModel):
    field_id: int
    crop: str | None = Field(default=None, description="Overrides the field's proposed crop")
    force_refresh_weather: bool = Field(default=False, description="Ignore cached weather for this run")
    simulate_sensors_if_missing: bool = Field(
        default=True, description="Generate simulated sensor telemetry when the field has no readings"
    )
    include_approved_only: bool = Field(
        default=False,
        description=(
            "Only plan activities once a human has approved this run. When true (and no approval exists) "
            "the activity planner stays silent so nothing can be scheduled ahead of a reviewer."
        ),
    )
    responsible_person: str | None = Field(
        default=None,
        max_length=120,
        description="Optional name written onto every planned activity as the accountable person",
    )
    notes: str | None = Field(default=None, max_length=1_000)


class AgentTraceOut(ORMModel):
    id: int
    sequence: int
    agent_name: str
    responsibility: str
    status: str
    input_summary: dict
    output: dict
    evidence: list[Evidence]
    sources: list[SourceReference]
    reasoning: str | None
    error: str | None
    duration_ms: float | None
    model_used: str | None
    created_at: datetime


class WorkflowRunOut(ORMModel):
    id: int
    farm_id: int
    field_id: int
    status: str
    current_step: str | None
    crop: str | None
    agents_invoked: list[str]
    warnings: list[str]
    error: str | None
    completed_at: datetime | None
    duration_ms: float | None
    created_at: datetime
    approval_request_id: int | None = None
    approval_status: str | None = None


class WorkflowRunDetail(WorkflowRunOut):
    state: dict[str, Any] = Field(default_factory=dict)
    traces: list[AgentTraceOut] = Field(default_factory=list)


class WorkflowRunSummary(BaseModel):
    """Condensed result of a completed orchestration run."""

    workflow_run_id: int
    field_id: int
    field_name: str
    farm_name: str
    crop: str
    status: str
    suitability: dict[str, Any] | None = None
    irrigation: dict[str, Any] | None = None
    risk_level: str
    risk_findings: list[dict[str, Any]] = Field(default_factory=list)
    ml_predictions: list[dict[str, Any]] = Field(default_factory=list)
    alerts: list[dict[str, Any]] = Field(default_factory=list)
    activities: list[dict[str, Any]] = Field(default_factory=list)
    approval: dict[str, Any] | None = None
    sources: list[SourceReference] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    agents_invoked: list[str] = Field(default_factory=list)
    completed_at: datetime | None = None
    duration_ms: float | None = None


class ApprovalOut(ORMModel):
    id: int
    workflow_run_id: int
    field_id: int
    title: str
    action_type: str
    recommendation: dict
    evidence: list[Evidence]
    status: str
    reviewer_name: str | None
    decision_note: str | None
    modified_action: dict | None
    observation: str | None
    reanalysis_requested: bool
    decided_at: datetime | None
    created_at: datetime


class ApprovalDecision(BaseModel):
    """Human decision.  ``approved`` never triggers hardware - it authorises the plan only."""

    status: ApprovalStatus = Field(..., description="approved / rejected / modified")
    reviewer_name: str = Field(..., min_length=2, max_length=120)
    decision_note: str | None = Field(default=None, max_length=4_000)
    modified_action: dict[str, Any] | None = Field(
        default=None, description="Adjusted action the reviewer wants executed instead"
    )
    observation: str | None = Field(default=None, max_length=2_000)
    reanalysis_requested: bool = Field(
        default=False, description="Flag to trigger a fresh agent run with the reviewer's observations"
    )

    @field_validator("modified_action")
    @classmethod
    def _validate_modified(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is not None and not value:
            msg = "modified_action must not be an empty object"
            raise ValueError(msg)
        return value

    @field_validator("observation")
    @classmethod
    def _validate_observation(cls, value: str | None) -> str | None:
        if value is not None and len(value.strip()) < 3:
            msg = "observation must be at least 3 characters"
            raise ValueError(msg)
        return value

    def model_post(self, _ctx: Any) -> ApprovalDecision:
        if self.status == ApprovalStatus.MODIFIED and self.modified_action is None:
            msg = "modified_action is required when status is 'modified'"
            raise ValueError(msg)
        return self


class ReanalysisRequest(BaseModel):
    notes: str | None = Field(default=None, max_length=2_000)
    force_refresh_weather: bool = False
