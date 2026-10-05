"""Farm and Field registry.

Geolocation is captured at district-level precision only (two decimal places
~ 1.1 km) so that the system can serve weather and agro-advisory without
storing precise farm locations.
"""

from __future__ import annotations

from sqlalchemy import Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UTCDateTime

SOIL_TYPES = (
    "sandy",
    "sandy_loam",
    "loam",
    "silt_loam",
    "clay_loam",
    "clay",
    "red_soil",
    "black_soil",
    "alluvial",
    "red_laterite",
)
IRRIGATION_SOURCES = ("canal", "borewell", "tank", "well", "rainfed", "drip", "sprinkler", "other")
WATER_AVAILABILITY = ("abundant", "moderate", "limited", "seasonal", "none")


class Farm(Base, TimestampMixin):
    __tablename__ = "farms"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    owner_name: Mapped[str] = mapped_column(String(120), nullable=False)
    location_name: Mapped[str] = mapped_column(String(160), nullable=False)
    # Privacy-aware precision: rounded to 2 dp before persistence.
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    village: Mapped[str | None] = mapped_column(String(120), nullable=True)
    district: Mapped[str | None] = mapped_column(String(120), nullable=True)
    state: Mapped[str | None] = mapped_column(String(120), nullable=True)
    total_area_ha: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    fields: Mapped[list[Field]] = relationship(back_populates="farm", cascade="all, delete-orphan", order_by="Field.id")


class Field(Base, TimestampMixin):
    __tablename__ = "fields"
    __table_args__ = (Index("ix_fields_farm_id_code", "farm_id", "field_code", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey("farms.id", ondelete="CASCADE"), nullable=False, index=True)
    field_code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    area_ha: Mapped[float] = mapped_column(Float, nullable=False)
    soil_type: Mapped[str] = mapped_column(String(40), nullable=False)
    # Optional per-field override; falls back to the farm centroid.
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    previous_crop: Mapped[str | None] = mapped_column(String(64), nullable=True)
    proposed_crop: Mapped[str | None] = mapped_column(String(64), nullable=True)
    crop_stage: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    planting_window_start: Mapped[UTCDateTime | None] = mapped_column(UTCDateTime, nullable=True)
    irrigation_source: Mapped[str] = mapped_column(String(32), nullable=False, default="rainfed")
    water_availability: Mapped[str] = mapped_column(String(32), nullable=False, default="moderate")
    water_availability_m3_per_day: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    farm: Mapped[Farm] = relationship(back_populates="fields")

    @property
    def effective_latitude(self) -> float | None:
        return self.latitude if self.latitude is not None else (self.farm.latitude if self.farm else None)

    @property
    def effective_longitude(self) -> float | None:
        return self.longitude if self.longitude is not None else (self.farm.longitude if self.farm else None)
