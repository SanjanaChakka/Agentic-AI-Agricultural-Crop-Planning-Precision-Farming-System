"""In-field sensor readings (real ingestion or simulated telemetry)."""

from __future__ import annotations

from sqlalchemy import Boolean, Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UTCDateTime
from app.models.types import JSONDict


class SensorReading(Base, TimestampMixin):
    __tablename__ = "sensor_readings"
    __table_args__ = (Index("ix_sensor_reading_field_time", "field_id", "recorded_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id", ondelete="CASCADE"), nullable=False, index=True)
    sensor_id: Mapped[str] = mapped_column(String(64), nullable=False, default="SM-01")
    recorded_at: Mapped[UTCDateTime] = mapped_column(UTCDateTime, nullable=False)

    soil_moisture_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    soil_temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    air_humidity_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    air_temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    battery_percent: Mapped[float | None] = mapped_column(Float, nullable=True)

    is_simulated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    quality_flags: Mapped[list] = mapped_column(JSONDict, nullable=False, default=list)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
