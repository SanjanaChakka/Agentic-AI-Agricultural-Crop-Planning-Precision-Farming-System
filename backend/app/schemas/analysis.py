"""Suitability, irrigation, risk and ML schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar

from pydantic import BaseModel, Field

from app.schemas.common import Evidence, ORMModel, SourceReference


class FactorScore(BaseModel):
    factor: str
    label: str
    verdict: str = Field(..., description="favourable / unfavourable / unknown")
    score: float | None = None
    weight: float
    detail: str
    measured_value: str | float | None = None
    required_range: str | None = None


class SuitabilityRequest(BaseModel):
    crop: str | None = Field(default=None, description="Defaults to the field's proposed crop")
    soil_observation_id: int | None = None
    include_evidence: bool = True


class SuitabilityOut(ORMModel):
    id: int
    field_id: int
    workflow_run_id: int | None
    crop: str
    status: str
    score: float | None
    confidence: float | None
    factor_scores: list[FactorScore]
    favorable_factors: list[str]
    limiting_factors: list[str]
    missing_information: list[str]
    requirements_used: dict
    evidence: list[Evidence]
    sources: list[SourceReference]
    narrative: str | None
    generated_by: str
    created_at: datetime


class IrrigationOut(ORMModel):
    id: int
    field_id: int
    workflow_run_id: int | None
    recommendation: str
    urgency: str
    requires_human_authorisation: bool
    authorisation_state: str
    estimated_water_mm: float | None
    estimated_volume_m3: float | None
    rationale: str
    rules_evaluated: list[dict]
    sensor_context: dict
    weather_context: dict
    ml_prediction: dict
    evidence: list[Evidence]
    sources: list[SourceReference]
    generated_by: str
    created_at: datetime


class RiskOut(ORMModel):
    id: int
    field_id: int
    workflow_run_id: int | None
    risk_type: str
    severity: str
    statement: str
    potential_impact: str | None
    recommended_investigation: str | None
    evidence: list[Evidence]
    sources: list[SourceReference]
    observed_at: datetime
    is_diagnosis: bool


class RiskScanResponse(BaseModel):
    field_id: int
    findings: list[RiskOut]
    risk_level: str
    disclaimer: str


class MLPredictionOut(ORMModel):
    id: int
    field_id: int
    workflow_run_id: int | None
    model_name: str
    model_version: str
    task: str
    status: str
    prediction_value: float | None
    prediction_label: str | None
    confidence: float | None
    features: dict
    model_metadata: dict
    message: str | None
    created_at: datetime


class MLModelInfo(BaseModel):
    """Model card served by ``GET /api/v1/ml/models``."""

    task: str
    model_name: str
    model_version: str
    target: str
    algorithm: str
    features: list[str] = Field(default_factory=list)
    hyperparameters: dict[str, Any] = Field(default_factory=dict)
    train_samples: int = 0
    test_samples: int = 0
    metrics: dict[str, Any] = Field(default_factory=dict)
    split: dict[str, Any] = Field(default_factory=dict)
    dataset_summary: dict[str, Any] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    trained_at: datetime | None = None
    available: bool = False
    artifact_path: str | None = None
    documentation: str | None = None


class MLPredictRequest(BaseModel):
    """Optional feature overrides for a prediction.

    Anything omitted falls back to the field context and is reported back as an
    imputed feature.
    """

    soil_moisture_percent: float | None = Field(default=None, ge=0, le=100)
    soil_moisture_change_3d: float | None = Field(default=None, ge=-100, le=100)
    soil_temperature_c: float | None = Field(default=None, ge=-20, le=80)
    air_temperature_c: float | None = Field(default=None, ge=-30, le=70)
    humidity_percent: float | None = Field(default=None, ge=0, le=100)
    humidity_mean_percent: float | None = Field(default=None, ge=0, le=100)
    humidity_min_percent: float | None = Field(default=None, ge=0, le=100)
    wind_speed_ms: float | None = Field(default=None, ge=0, le=80)
    temp_min_c: float | None = Field(default=None, ge=-40, le=70)
    temp_max_c: float | None = Field(default=None, ge=-40, le=70)
    temp_mean_c: float | None = Field(default=None, ge=-40, le=70)
    rainfall_1d_mm: float | None = Field(default=None, ge=0, le=1_000)
    rainfall_3d_mm: float | None = Field(default=None, ge=0, le=1_500)
    rainfall_7d_mm: float | None = Field(default=None, ge=0, le=2_000)
    wet_day_fraction_7d: float | None = Field(default=None, ge=0, le=1)
    et0_7d_mm: float | None = Field(default=None, ge=0, le=500)
    expected_rainfall_next_3d_mm: float | None = Field(default=None, ge=0, le=1_500)
    crop_stage: str | None = None
    crop: str | None = None

    #: Only genuine model inputs.  ``crop``/``crop_stage`` are included because
    #: the feature builders already accept them as resolved values, so an
    #: explicit override lands in the same place as the field-derived default.
    OVERRIDE_FIELDS: ClassVar[tuple[str, ...]] = (
        "soil_moisture_percent",
        "soil_moisture_change_3d",
        "soil_temperature_c",
        "air_temperature_c",
        "humidity_percent",
        "humidity_mean_percent",
        "humidity_min_percent",
        "wind_speed_ms",
        "temp_min_c",
        "temp_max_c",
        "temp_mean_c",
        "rainfall_1d_mm",
        "rainfall_3d_mm",
        "rainfall_7d_mm",
        "wet_day_fraction_7d",
        "et0_7d_mm",
        "expected_rainfall_next_3d_mm",
        "crop_stage",
        "crop",
    )

    def overrides(self) -> dict[str, Any]:
        """The subset of the body that explicitly overrides field context.

        Returns only keys the caller actually supplied, so that
        :mod:`app.services.ml_service` can tell "not provided" (use the field's
        real sensor/weather data) apart from an explicit value.
        """
        return {name: value for name in self.OVERRIDE_FIELDS if (value := getattr(self, name)) is not None}
