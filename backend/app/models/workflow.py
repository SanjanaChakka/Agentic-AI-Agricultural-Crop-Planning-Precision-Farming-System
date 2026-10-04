"""Agent orchestration persistence: workflow runs, per-agent traces, approvals."""

from __future__ import annotations

from sqlalchemy import Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UTCDateTime
from app.models.types import JSONDict


class WorkflowRun(Base, TimestampMixin):
    """One end-to-end agentic planning cycle for a field.

    ``state`` holds the explicit workflow state (soil findings, weather
    findings, suitability, irrigation, ML output, risk findings, evidence,
    recommendations, approval state, activity plan) so the run is fully
    reproducible and auditable.
    """

    __tablename__ = "workflow_runs"
    __table_args__ = (Index("ix_workflow_field_created", "field_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey("farms.id", ondelete="CASCADE"), nullable=False, index=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    current_step: Mapped[str | None] = mapped_column(String(64), nullable=True)
    crop: Mapped[str | None] = mapped_column(String(64), nullable=True)
    state: Mapped[dict] = mapped_column(JSONDict, nullable=False, default=dict)
    agents_invoked: Mapped[list] = mapped_column(JSONDict, nullable=False, default=list)
    warnings: Mapped[list] = mapped_column(JSONDict, nullable=False, default=list)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[UTCDateTime | None] = mapped_column(UTCDateTime, nullable=True)
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    traces: Mapped[list[AgentTrace]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="AgentTrace.sequence"
    )


class AgentTrace(Base, TimestampMixin):
    """Per-agent audit record: inputs, outputs, evidence and outcome."""

    __tablename__ = "agent_traces"
    __table_args__ = (Index("ix_agent_trace_run_sequence", "workflow_run_id", "sequence"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    workflow_run_id: Mapped[int] = mapped_column(ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False)
    sequence: Mapped[int] = mapped_column(nullable=False, default=0)
    agent_name: Mapped[str] = mapped_column(String(80), nullable=False)
    responsibility: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="succeeded")
    input_summary: Mapped[dict] = mapped_column(JSONDict, nullable=False, default=dict)
    output: Mapped[dict] = mapped_column(JSONDict, nullable=False, default=dict)
    evidence: Mapped[list] = mapped_column(JSONDict, nullable=False, default=list)
    sources: Mapped[list] = mapped_column(JSONDict, nullable=False, default=list)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    model_used: Mapped[str | None] = mapped_column(String(64), nullable=True)

    run: Mapped[WorkflowRun] = relationship(back_populates="traces")


class ApprovalRequest(Base, TimestampMixin):
    """Human-in-the-loop gate.  No physical action is ever auto-executed."""

    __tablename__ = "approval_requests"
    __table_args__ = (Index("ix_approval_field_status", "field_id", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    workflow_run_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    action_type: Mapped[str] = mapped_column(String(48), nullable=False, default="irrigation_plan")
    recommendation: Mapped[dict] = mapped_column(JSONDict, nullable=False, default=dict)
    evidence: Mapped[list] = mapped_column(JSONDict, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    reviewer_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    modified_action: Mapped[dict | None] = mapped_column(JSONDict, nullable=True)
    observation: Mapped[str | None] = mapped_column(Text, nullable=True)
    reanalysis_requested: Mapped[bool] = mapped_column(nullable=False, default=False)
    decided_at: Mapped[UTCDateTime | None] = mapped_column(UTCDateTime, nullable=True)
