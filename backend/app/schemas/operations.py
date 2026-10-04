"""Farm activity, alert, report and knowledge-base schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import ActivityStatus, ActivityType, AlertStatus
from app.schemas.common import Evidence, ORMModel, SourceReference


class FarmActivityCreate(BaseModel):
    field_id: int
    activity_type: ActivityType
    title: str = Field(..., min_length=2, max_length=200)
    scheduled_date: datetime | None = None
    window_days: int = Field(default=1, ge=0, le=90)
    responsible_person: str | None = Field(default=None, max_length=120)
    reason: str = Field(default="", max_length=2_000)
    priority: str = Field(default="medium", pattern="^(low|medium|high)$")


class FarmActivityUpdate(BaseModel):
    status: ActivityStatus | None = None
    scheduled_date: datetime | None = None
    responsible_person: str | None = Field(default=None, max_length=120)
    reason: str | None = Field(default=None, max_length=2_000)
    notes: str | None = Field(default=None, max_length=2_000)


class FarmActivityOut(ORMModel):
    id: int
    field_id: int
    workflow_run_id: int | None
    approval_request_id: int | None
    activity_type: str
    title: str
    scheduled_date: datetime | None
    window_days: int
    status: str
    responsible_person: str | None
    reason: str
    priority: str
    evidence: list[Evidence]
    notes: str | None
    created_at: datetime


class ActivityPlanRequest(BaseModel):
    workflow_run_id: int | None = Field(default=None, description="Plan from a specific workflow run")
    include_approved_only: bool = Field(
        default=False,
        description="Only generate activities for plans that a human has already approved",
    )
    responsible_person: str | None = Field(default=None, max_length=120)


class AlertOut(ORMModel):
    id: int
    farm_id: int
    field_id: int
    alert_type: str
    severity: str
    title: str
    message: str
    evidence: list[Evidence]
    fingerprint: str
    severity_rank: int
    status: str
    occurrence_count: int
    triggered_at: datetime
    last_observed_at: datetime
    acknowledged_at: datetime | None
    acknowledged_by: str | None
    resolved_at: datetime | None


class AlertUpdate(BaseModel):
    status: AlertStatus
    acknowledged_by: str | None = Field(default=None, max_length=120)
    note: str | None = Field(default=None, max_length=1_000)


class ReportCreate(BaseModel):
    workflow_run_id: int | None = None
    title: str | None = Field(default=None, max_length=240, description="Defaults to a generated title")
    include_evidence: bool = True


class ReportOut(ORMModel):
    id: int
    farm_id: int
    field_id: int
    workflow_run_id: int | None
    title: str
    status: str
    file_name: str | None
    size_bytes: int | None
    page_count: int | None
    section_summary: dict
    error: str | None
    created_at: datetime
    download_url: str | None = None


class ReferenceDocumentOut(ORMModel):
    id: int
    doc_key: str
    title: str
    category: str
    organisation: str
    source_url: str | None
    region: str | None
    chunk_count: int
    checksum: str | None
    is_active: bool


class KnowledgeQuery(BaseModel):
    query: str = Field(..., min_length=2, max_length=500)
    top_k: int = Field(default=4, ge=1, le=12)
    category: str | None = Field(default=None, max_length=64)


class KnowledgeChunk(BaseModel):
    chunk_id: str
    doc_key: str
    title: str
    category: str
    organisation: str
    source_url: str | None
    score: float
    text: str


class KnowledgeQueryResponse(BaseModel):
    query: str
    index_backend: str
    corpus_documents: int
    corpus_chunks: int
    retrieval_mode: str
    chunks: list[KnowledgeChunk]
    references: list[SourceReference]


class RagStatus(BaseModel):
    available: bool
    index_backend: str
    documents: int
    chunks: int
    embedding: str
    dimension: int | None = None
    built_at: datetime | None = None
    detail: str | None = None


class EvidenceBundle(BaseModel):
    """Reusable envelope: measurements, references, rules, ML and narrative."""

    measurements: list[Evidence] = Field(default_factory=list)
    forecast: list[Evidence] = Field(default_factory=list)
    retrieved_reference: list[SourceReference] = Field(default_factory=list)
    rule_derived: list[Evidence] = Field(default_factory=list)
    ml_predictions: list[Evidence] = Field(default_factory=list)
    narrative: str | None = None
    narrative_source: str | None = None
    safety_notes: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)
