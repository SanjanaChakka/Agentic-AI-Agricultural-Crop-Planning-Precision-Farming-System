"""Weather schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class WeatherDayOut(BaseModel):
    forecast_date: datetime
    temp_min_c: float | None = None
    temp_max_c: float | None = None
    temperature_mean_c: float | None = None
    precipitation_mm: float | None = None
    precipitation_probability_percent: float | None = None
    humidity_percent: float | None = None
    wind_speed_ms: float | None = None
    et0_mm: float | None = None
    condition: str | None = None


class WeatherCurrentOut(BaseModel):
    observed_at: datetime | None = None
    temperature_c: float | None = None
    feels_like_c: float | None = None
    humidity_percent: float | None = None
    wind_speed_ms: float | None = None
    wind_direction_deg: float | None = None
    condition: str | None = None


class WeatherBundle(BaseModel):
    """Weather context consumed by agents.  ``source``/``is_simulated`` are mandatory."""

    field_id: int | None = None
    location_name: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    source: str = Field(..., description="e.g. open-meteo, openweathermap, offline-climatology")
    provider: str = Field(..., description="Human readable provider name")
    is_simulated: bool = False
    fetched_at: datetime
    current: WeatherCurrentOut | None = None
    daily: list[WeatherDayOut] = Field(default_factory=list)
    total_precipitation_mm: float = 0.0
    rainfall_next_3_days_mm: float = 0.0
    max_temp_c: float | None = None
    min_temp_c: float | None = None
    mean_humidity_percent: float | None = None
    total_et0_mm: float = 0.0
    notes: list[str] = Field(default_factory=list)
    fallback_used: bool = False

    @property
    def provider_display(self) -> str:
        return f"{self.provider} (simulated)" if self.is_simulated else self.provider


class WeatherSnapshotOut(ORMModel):
    id: int
    field_id: int
    farm_id: int | None
    source: str
    is_simulated: bool
    fetched_at: datetime
    observed_at: datetime | None
    temperature_c: float | None
    humidity_percent: float | None
    wind_speed_ms: float | None
    condition: str | None
    forecast_date: datetime | None
    temp_min_c: float | None
    temp_max_c: float | None
    precipitation_mm: float | None
    precipitation_probability_percent: float | None
    et0_mm: float | None
    notes: str | None


class WeatherQueryOut(BaseModel):
    """Standalone weather lookup (no field persistence)."""

    latitude: float
    longitude: float
    location_name: str | None = None
    forecast_days: int = Field(default=7, ge=1, le=16)
    bundle: WeatherBundle
