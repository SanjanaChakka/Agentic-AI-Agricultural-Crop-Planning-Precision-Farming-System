"""Weather snapshots persisted from the weather service.

``source`` and ``is_simulated`` are mandatory so that a fallback/climatological
estimate can never be mistaken for a live API reading.
"""

from __future__ import annotations

from sqlalchemy import Boolean, Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UTCDateTime
from app.models.types import JSONDict


class WeatherSnapshot(Base, TimestampMixin):
    __tablename__ = "weather_snapshots"
    __table_args__ = (Index("ix_weather_snapshot_field_date", "field_id", "forecast_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id", ondelete="CASCADE"), nullable=False, index=True)
    farm_id: Mapped[int | None] = mapped_column(ForeignKey("farms.id", ondelete="CASCADE"), nullable=True, index=True)

    source: Mapped[str] = mapped_column(String(64), nullable=False)
    is_simulated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    fetched_at: Mapped[UTCDateTime] = mapped_column(UTCDateTime, nullable=False)

    # Current observation (may be null when only a forecast is available)
    observed_at: Mapped[UTCDateTime | None] = mapped_column(UTCDateTime, nullable=True)
    temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    feels_like_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    humidity_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_speed_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    condition: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # Forecast day
    forecast_date: Mapped[UTCDateTime | None] = mapped_column(UTCDateTime, nullable=True)
    temp_min_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    temp_max_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    precipitation_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    precipitation_probability_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    et0_mm: Mapped[float | None] = mapped_column(Float, nullable=True)

    raw_payload: Mapped[dict | None] = mapped_column(JSONDict, nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
