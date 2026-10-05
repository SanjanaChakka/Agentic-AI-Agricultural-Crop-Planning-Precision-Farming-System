"""Shared schema primitives: provenance-tagged evidence and citations."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import SourceKind


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Evidence(BaseModel):
    """A single, provenance-tagged fact used to justify a recommendation."""

    label: str = Field(..., examples=["Soil moisture", "Rainfall forecast (next 3 days)"])
    value: str | float | bool | None = None
    kind: SourceKind = SourceKind.MEASURED
    unit: str | None = None
    source: str | None = Field(default=None, description="API, document title or model name")
    reference: str | None = Field(default=None, description="Document key / endpoint for citation")
    note: str | None = None
    observed_at: datetime | None = None

    def as_line(self) -> str:
        unit = f" {self.unit}" if self.unit else ""
        value = "not available" if self.value is None else f"{self.value}{unit}"
        return f"{self.label}: {value}"


class SourceReference(BaseModel):
    """Citation for retrieved reference material or an upstream data provider."""

    doc_key: str = Field(..., examples=["crops.rice"])
    title: str
    category: str = ""
    organisation: str = ""
    url: str | None = None
    region: str | None = None
    score: float | None = None
    excerpt: str | None = None


class MessageResponse(BaseModel):
    message: str
    detail: str | None = None
    data: dict[str, Any] | None = None


def as_source_reference(item: SourceReference | dict[str, Any]) -> SourceReference:
    """Coerce a citation into :class:`SourceReference`.

    Services receive citations straight from the retriever (models) but also from
    the workflow state or the database (plain dicts).  Normalising once here keeps
    every downstream ``.model_dump()`` safe.
    """
    if isinstance(item, SourceReference):
        return item
    return SourceReference.model_validate(item)


def sources_as_dicts(items: list[SourceReference | dict[str, Any]]) -> list[dict[str, Any]]:
    """JSON-ready citation payloads."""
    return [as_source_reference(item).model_dump(mode="json") for item in items]


class Page(BaseModel):
    total: int
    limit: int
    offset: int


class HealthComponent(BaseModel):
    name: str
    status: str
    detail: str | None = None


class HealthResponse(BaseModel):
    status: str
    app: str
    version: str
    environment: str
    database: str
    ml: str
    rag: str
    weather_provider: str
    llm_provider: str
    components: list[HealthComponent] = Field(default_factory=list)
    timestamp: datetime
