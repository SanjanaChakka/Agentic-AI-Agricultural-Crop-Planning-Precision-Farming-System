"""Sensor ingestion / simulation schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ORMModel


class SensorReadingCreate(BaseModel):
    field_id: int | None = None
    sensor_id: str = Field(default="SM-01", min_length=1, max_length=64)
    recorded_at: datetime | None = None
    soil_moisture_percent: float | None = Field(default=None, ge=0, le=100)
    soil_temperature_c: float | None = Field(default=None, ge=-20, le=80)
    air_humidity_percent: float | None = Field(default=None, ge=0, le=100)
    air_temperature_c: float | None = Field(default=None, ge=-30, le=70)
    battery_percent: float | None = Field(default=None, ge=0, le=100)
    is_simulated: bool = False
    notes: str | None = Field(default=None, max_length=1_000)

    @field_validator("air_temperature_c")
    @classmethod
    def _guard_air_temperature(cls, value: float | None) -> float | None:
        # Above ~55 C an in-canopy air sensor is physically implausible and is
        # almost certainly a wiring/units fault.
        if value is not None and value > 55:
            msg = "air_temperature_c above 55 C is implausible; check sensor wiring and units"
            raise ValueError(msg)
        return value


class SensorReadingOut(ORMModel):
    id: int
    field_id: int
    sensor_id: str
    recorded_at: datetime
    soil_moisture_percent: float | None
    soil_temperature_c: float | None
    air_humidity_percent: float | None
    air_temperature_c: float | None
    battery_percent: float | None
    is_simulated: bool
    quality_flags: list[str]
    notes: str | None


class SensorSimulationRequest(BaseModel):
    hours: int = Field(default=72, ge=6, le=720, description="Window length to simulate")
    interval_hours: float = Field(default=3.0, gt=0, le=24)
    sensor_id: str = Field(default="SM-01", max_length=64)
    seed: int | None = Field(default=None, ge=0, le=10**9)
    start_at: datetime | None = None
    initial_soil_moisture_percent: float | None = Field(default=None, ge=0, le=100)
    rainfall_events: bool = Field(
        default=True, description="Include a rainfall event so downstream rain-adaptation logic is exercised"
    )
    inject_fault: bool = Field(default=False, description="Inject one sensor fault for alert testing")


class SensorSimulationResponse(BaseModel):
    field_id: int
    sensor_id: str
    readings_created: int
    simulated: bool = True
    start_at: datetime
    end_at: datetime
    readings: list[SensorReadingOut]
    summary: dict[str, float | str | None]


class SensorTrendPoint(BaseModel):
    recorded_at: datetime
    soil_moisture_percent: float | None
    soil_temperature_c: float | None
    air_humidity_percent: float | None


class SensorTrend(BaseModel):
    field_id: int
    sensor_id: str | None
    points: list[SensorTrendPoint]
    statistics: dict[str, float | None]
    quality_issue_count: int
    latest_reading: SensorReadingOut | None = None
