"""Soil observation (measured) and interpretation (AI) schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.common import Evidence, ORMModel, SourceReference


class SoilObservationCreate(BaseModel):
    field_id: int | None = Field(default=None, description="Required for POST /soil-observations")
    observed_at: datetime | None = None
    sample_depth_cm: float | None = Field(default=None, gt=0, le=200)
    soil_type: str | None = Field(default=None, max_length=40)

    ph: float | None = Field(default=None, ge=0, le=14)
    nitrogen_available_kg_ha: float | None = Field(default=None, ge=0, le=2_000)
    phosphorus_available_kg_ha: float | None = Field(default=None, ge=0, le=1_000)
    potassium_available_kg_ha: float | None = Field(default=None, ge=0, le=2_000)
    organic_carbon_percent: float | None = Field(default=None, ge=0, le=100)
    soil_moisture_percent: float | None = Field(default=None, ge=0, le=100)
    electrical_conductivity_ds_m: float | None = Field(default=None, ge=0, le=20)

    data_source: str = Field(default="manual_entry")
    lab_name: str | None = Field(default=None, max_length=160)
    notes: str | None = Field(default=None, max_length=2_000)

    @field_validator("data_source")
    @classmethod
    def _validate_source(cls, value: str) -> str:
        allowed = {"lab_test", "sensor", "manual_entry", "demo_seed"}
        normalised = value.strip().lower()
        if normalised not in allowed:
            msg = f"data_source must be one of: {', '.join(sorted(allowed))}"
            raise ValueError(msg)
        return normalised

    @model_validator(mode="after")
    def _at_least_one_measurement(self) -> SoilObservationCreate:
        measured = [
            self.ph,
            self.nitrogen_available_kg_ha,
            self.phosphorus_available_kg_ha,
            self.potassium_available_kg_ha,
            self.organic_carbon_percent,
            self.soil_moisture_percent,
            self.electrical_conductivity_ds_m,
        ]
        if all(value is None for value in measured):
            msg = "At least one measured soil parameter must be supplied."
            raise ValueError(msg)
        return self


class SoilObservationOut(ORMModel):
    id: int
    field_id: int
    observed_at: datetime
    sample_depth_cm: float | None
    soil_type: str | None
    ph: float | None
    nitrogen_available_kg_ha: float | None
    phosphorus_available_kg_ha: float | None
    potassium_available_kg_ha: float | None
    organic_carbon_percent: float | None
    soil_moisture_percent: float | None
    electrical_conductivity_ds_m: float | None
    data_source: str
    lab_name: str | None
    notes: str | None
    created_at: datetime
    missing_parameters: list[str] = Field(default_factory=list)


class SoilInterpretationOut(ORMModel):
    id: int
    soil_observation_id: int
    agent_name: str
    generated_by: str
    ph_class: str
    nutrient_status: dict[str, str]
    organic_matter_status: str
    summary: str
    limitations: list[str]
    recommendations: list[dict]
    missing_parameters: list[str]
    evidence: list[Evidence]
    sources: list[SourceReference]
    confidence: float | None


class SoilAnalysisResponse(BaseModel):
    """Measured values and AI interpretation are deliberately separate blocks."""

    observation: SoilObservationOut
    interpretation: SoilInterpretationOut | None = None
    measured_values_note: str = (
        "Measured values above are recorded exactly as supplied by the data source and are never "
        "modified by the AI layer."
    )


class SoilThresholdOut(BaseModel):
    """The agronomic rating bands the system applies, exposed for transparency."""

    nitrogen_available_kg_ha: dict[str, float]
    phosphorus_available_kg_ha: dict[str, float]
    potassium_available_kg_ha: dict[str, float]
    organic_carbon_percent: dict[str, float]
    ph_classes: dict[str, str]
