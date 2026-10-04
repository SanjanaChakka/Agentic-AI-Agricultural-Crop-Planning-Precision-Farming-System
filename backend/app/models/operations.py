"""Operational artefacts: planned farm activities, alerts, reports, references."""

from __future__ import annotations

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UTCDateTime
from app.models.types import JSONDict


class FarmActivity(Base, TimestampMixin):
    __tablename__ = "farm_activities"
    __table_args__ = (Index("ix_activity_field_scheduled", "field_id", "scheduled_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id", ondelete="CASCADE"), nullable=False, index=True)
    workflow_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    approval_request_id: Mapped[int | None] = mapped_column(
        ForeignKey("approval_requests.id", ondelete="SET NULL"), nullable=True
    )
    activity_type: Mapped[str] = mapped_column(String(48), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    scheduled_date: Mapped[UTCDateTime | None] = mapped_column(UTCDateTime, nullable=True)
    window_days: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="planned")
    responsible_person: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    priority: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    evidence: Mapped[list] = mapped_column(JSONDict, nullable=False, default=list)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class Alert(Base, TimestampMixin):
    """Deduplicated operational alert.

    ``fingerprint`` identifies an ongoing condition; a new alert is only raised
    when the fingerprint changes or the condition materially escalates.
    """

    __tablename__ = "alerts"
    __table_args__ = (Index("ix_alert_field_fingerprint_status", "field_id", "fingerprint", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey("farms.id", ondelete="CASCADE"), nullable=False, index=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id", ondelete="CASCADE"), nullable=False, index=True)
    alert_type: Mapped[str] = mapped_column(String(48), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[list] = mapped_column(JSONDict, nullable=False, default=list)
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    severity_rank: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="open")
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    triggered_at: Mapped[UTCDateTime] = mapped_column(UTCDateTime, nullable=False)
    last_observed_at: Mapped[UTCDateTime] = mapped_column(UTCDateTime, nullable=False)
    acknowledged_at: Mapped[UTCDateTime | None] = mapped_column(UTCDateTime, nullable=True)
    acknowledged_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    resolved_at: Mapped[UTCDateTime | None] = mapped_column(UTCDateTime, nullable=True)


class ReferenceDocument(Base, TimestampMixin):
    """A document that was ingested into the agricultural knowledge base."""

    __tablename__ = "reference_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    doc_key: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    organisation: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    source_url: Mapped[str | None] = mapped_column(String(400), nullable=True)
    region: Mapped[str | None] = mapped_column(String(120), nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Report(Base, TimestampMixin):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey("farms.id", ondelete="CASCADE"), nullable=False, index=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id", ondelete="CASCADE"), nullable=False, index=True)
    workflow_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="ready")
    file_name: Mapped[str | None] = mapped_column(String(240), nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(400), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section_summary: Mapped[dict] = mapped_column(JSONDict, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class WaterBalanceRecord(Base, TimestampMixin):
    """Lightweight audit of applied irrigation events (recorded by humans)."""

    __tablename__ = "water_balance_records"
    __table_args__ = (Index("ix_water_field_applied", "field_id", "applied_on"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id", ondelete="CASCADE"), nullable=False, index=True)
    applied_on: Mapped[UTCDateTime] = mapped_column(UTCDateTime, nullable=False)
    depth_mm: Mapped[float] = mapped_column(Float, nullable=False)
    volume_m3: Mapped[float | None] = mapped_column(Float, nullable=True)
    method: Mapped[str] = mapped_column(String(48), nullable=False, default="manual")
    applied_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
