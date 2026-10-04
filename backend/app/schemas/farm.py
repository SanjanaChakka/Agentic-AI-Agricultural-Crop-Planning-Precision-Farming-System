"""Farm and field request/response schemas with validation."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models.farm import IRRIGATION_SOURCES, SOIL_TYPES, WATER_AVAILABILITY
from app.schemas.common import ORMModel


def _round_2dp(value: float | None) -> float | None:
    """Privacy-aware rounding (≈1.1 km) applied to all stored coordinates."""
    return None if value is None else round(float(value), 2)


def normalise_soil_type(value: str) -> str:
    normalised = value.strip().lower().replace(" ", "_").replace("-", "_")
    if normalised not in SOIL_TYPES:
        msg = f"soil_type must be one of: {', '.join(SOIL_TYPES)}"
        raise ValueError(msg)
    return normalised


def normalise_irrigation_source(value: str) -> str:
    normalised = value.strip().lower().replace(" ", "_")
    if normalised not in IRRIGATION_SOURCES:
        msg = f"irrigation_source must be one of: {', '.join(IRRIGATION_SOURCES)}"
        raise ValueError(msg)
    return normalised


def normalise_water_availability(value: str) -> str:
    normalised = value.strip().lower()
    if normalised not in WATER_AVAILABILITY:
        msg = f"water_availability must be one of: {', '.join(WATER_AVAILABILITY)}"
        raise ValueError(msg)
    return normalised


ENUM_NORMALISERS = {
    "soil_type": normalise_soil_type,
    "irrigation_source": normalise_irrigation_source,
    "water_availability": normalise_water_availability,
}


class FarmBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=120, examples=["Sanjana Rice Farm"])
    owner_name: str = Field(..., min_length=2, max_length=120)
    location_name: str = Field(..., min_length=2, max_length=160, examples=["Kolanupalli, Kakinada"])
    latitude: float | None = Field(default=None, ge=-90, le=90, examples=[16.99])
    longitude: float | None = Field(default=None, ge=-180, le=180, examples=[82.25])
    village: str | None = Field(default=None, max_length=120)
    district: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=120)
    total_area_ha: float | None = Field(default=None, gt=0, le=10_000)
    notes: str | None = Field(default=None, max_length=2_000)

    @field_validator("latitude", "longitude")
    @classmethod
    def _round_coordinates(cls, value: float | None) -> float | None:
        return _round_2dp(value)


class FarmCreate(FarmBase):
    pass


class FarmUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    owner_name: str | None = Field(default=None, min_length=2, max_length=120)
    location_name: str | None = Field(default=None, min_length=2, max_length=160)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    village: str | None = Field(default=None, max_length=120)
    district: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=120)
    total_area_ha: float | None = Field(default=None, gt=0, le=10_000)
    notes: str | None = Field(default=None, max_length=2_000)

    @field_validator("latitude", "longitude")
    @classmethod
    def _round_coordinates(cls, value: float | None) -> float | None:
        return _round_2dp(value)


class FieldOut(ORMModel):
    id: int
    farm_id: int
    field_code: str
    name: str
    area_ha: float
    soil_type: str
    latitude: float | None
    longitude: float | None
    effective_latitude: float | None = None
    effective_longitude: float | None = None
    previous_crop: str | None
    proposed_crop: str | None
    crop_stage: str
    planting_window_start: datetime | None
    irrigation_source: str
    water_availability: str
    water_availability_m3_per_day: float | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class FieldOutWithFarm(FieldOut):
    farm_name: str | None = None
    location_name: str | None = None
    district: str | None = None
    state: str | None = None


class FieldBase(BaseModel):
    field_code: str = Field(..., min_length=1, max_length=64, examples=["F-01"])
    name: str = Field(..., min_length=1, max_length=120)
    area_ha: float = Field(..., gt=0, le=1_000, examples=[2.4])
    soil_type: str = Field(..., examples=["black_soil"])
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    previous_crop: str | None = Field(default=None, max_length=64)
    proposed_crop: str | None = Field(default=None, max_length=64)
    crop_stage: str = Field(default="unknown", max_length=32)
    planting_window_start: datetime | None = None
    irrigation_source: str = Field(default="rainfed")
    water_availability: str = Field(default="moderate")
    water_availability_m3_per_day: float | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=2_000)

    @field_validator("soil_type")
    @classmethod
    def _validate_soil_type(cls, value: str) -> str:
        return normalise_soil_type(value)

    @field_validator("irrigation_source")
    @classmethod
    def _validate_irrigation_source(cls, value: str) -> str:
        return normalise_irrigation_source(value)

    @field_validator("water_availability")
    @classmethod
    def _validate_water(cls, value: str) -> str:
        return normalise_water_availability(value)

    @field_validator("latitude", "longitude")
    @classmethod
    def _round_coordinates(cls, value: float | None) -> float | None:
        return _round_2dp(value)


class FieldCreate(FieldBase):
    pass


class FieldUpdate(BaseModel):
    field_code: str | None = Field(default=None, min_length=1, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    area_ha: float | None = Field(default=None, gt=0, le=1_000)
    soil_type: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    previous_crop: str | None = Field(default=None, max_length=64)
    proposed_crop: str | None = Field(default=None, max_length=64)
    crop_stage: str | None = Field(default=None, max_length=32)
    planting_window_start: datetime | None = None
    irrigation_source: str | None = None
    water_availability: str | None = None
    water_availability_m3_per_day: float | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=2_000)

    @field_validator("soil_type")
    @classmethod
    def _validate_soil_type(cls, value: str | None) -> str | None:
        return None if value is None else normalise_soil_type(value)

    @field_validator("irrigation_source")
    @classmethod
    def _validate_irrigation_source(cls, value: str | None) -> str | None:
        return None if value is None else normalise_irrigation_source(value)

    @field_validator("water_availability")
    @classmethod
    def _validate_water(cls, value: str | None) -> str | None:
        return None if value is None else normalise_water_availability(value)

    @field_validator("latitude", "longitude")
    @classmethod
    def _round_coordinates(cls, value: float | None) -> float | None:
        return _round_2dp(value)


class FarmOut(ORMModel):
    id: int
    name: str
    owner_name: str
    location_name: str
    latitude: float | None
    longitude: float | None
    village: str | None
    district: str | None
    state: str | None
    total_area_ha: float | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
    field_count: int = 0
    total_registered_area_ha: float = 0.0


class FarmOutWithFields(FarmOut):
    fields: list[FieldOut] = Field(default_factory=list)


class FarmSummary(BaseModel):
    """Dashboard aggregation."""

    farm_id: int
    farm_name: str
    location_name: str
    field_count: int
    total_area_ha: float
    fields_with_soil_data: int
    fields_with_sensors: int
    open_alert_count: int
    pending_approval_count: int
    latest_workflow_status: str | None = None
    last_observation_at: datetime | None = None
