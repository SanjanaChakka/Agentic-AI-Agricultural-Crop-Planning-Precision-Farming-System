"""Analytical outputs: suitability, irrigation, risk and ML predictions.

Each table keeps ``evidence`` (provenance-tagged facts) separate from the
conclusion so the UI, the PDF report and the API can always show *why*.
"""

from __future__ import annotations

from sqlalchemy import Boolean, Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UTCDateTime
from app.models.types import JSONDict


class SuitabilityAssessment(Base, TimestampMixin):
    __tablename__ = "suitability_assessments"
    __table_args__ = (Index("ix_suitability_field_created", "field_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id", ondelete="CASCADE"), nullable=False, index=True)
    workflow_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    crop: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(48), nullable=False)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    factor_scores: Mapped[list] = mapped_column(JSONDict, nullable=False, default=list)
    favorable_factors: Mapped[list] = mapped_column(JSONDict, nullable=False, default=list)
    limiting_factors: Mapped[list] = mapped_column(JSONDict, nullable=False, default=list)
    missing_information: Mapped[list] = mapped_column(JSONDict, nullable=False, default=list)
    requirements_used: Mapped[dict] = mapped_column(JSONDict, nullable=False, default=dict)
    evidence: Mapped[list] = mapped_column(JSONDict, nullable=False, default=list)
    sources: Mapped[list] = mapped_column(JSONDict, nullable=False, default=list)
    narrative: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_by: Mapped[str] = mapped_column(String(32), nullable=False, default="deterministic_narrative")


class IrrigationAssessment(Base, TimestampMixin):
    __tablename__ = "irrigation_assessments"
    __table_args__ = (Index("ix_irrigation_field_created", "field_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id", ondelete="CASCADE"), nullable=False, index=True)
    workflow_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=True, index=True
    )

    recommendation: Mapped[str] = mapped_column(String(48), nullable=False)
    urgency: Mapped[str] = mapped_column(String(24), nullable=False, default="medium")
    # Consequential actions always require explicit human authorisation.
    requires_human_authorisation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    authorisation_state: Mapped[str] = mapped_column(String(32), nullable=False, default="not_authorised")

    estimated_water_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_volume_m3: Mapped[float | None] = mapped_column(Float, nullable=True)
    rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    rules_evaluated: Mapped[list] = mapped_column(JSONDict, nullable=False, default=list)
    sensor_context: Mapped[dict] = mapped_column(JSONDict, nullable=False, default=dict)
    weather_context: Mapped[dict] = mapped_column(JSONDict, nullable=False, default=dict)
    ml_prediction: Mapped[dict] = mapped_column(JSONDict, nullable=False, default=dict)
    evidence: Mapped[list] = mapped_column(JSONDict, nullable=False, default=list)
    sources: Mapped[list] = mapped_column(JSONDict, nullable=False, default=list)
    generated_by: Mapped[str] = mapped_column(String(32), nullable=False, default="deterministic_narrative")


class RiskFinding(Base, TimestampMixin):
    __tablename__ = "risk_findings"
    __table_args__ = (Index("ix_risk_field_created", "field_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id", ondelete="CASCADE"), nullable=False, index=True)
    workflow_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    risk_type: Mapped[str] = mapped_column(String(48), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    potential_impact: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_investigation: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence: Mapped[list] = mapped_column(JSONDict, nullable=False, default=list)
    sources: Mapped[list] = mapped_column(JSONDict, nullable=False, default=list)
    observed_at: Mapped[UTCDateTime] = mapped_column(UTCDateTime, nullable=False)
    is_diagnosis: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class MLPrediction(Base, TimestampMixin):
    __tablename__ = "ml_predictions"
    __table_args__ = (Index("ix_ml_field_created", "field_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id", ondelete="CASCADE"), nullable=False, index=True)
    workflow_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    model_name: Mapped[str] = mapped_column(String(80), nullable=False)
    model_version: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    task: Mapped[str] = mapped_column(String(48), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="ok")
    prediction_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    prediction_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    features: Mapped[dict] = mapped_column(JSONDict, nullable=False, default=dict)
    model_metadata: Mapped[dict] = mapped_column(JSONDict, nullable=False, default=dict)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
