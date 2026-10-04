"""Soil observations (measured data) and AI interpretations.

Design rule enforced by the schema: :class:`SoilObservation` only ever stores
*measured* values supplied by a lab test, a sensor or a manual entry, and is
never mutated by agents.  Machine/agent reasoning lives in the separate
:class:`SoilInterpretation` table so that provenance is unambiguous.
"""

from __future__ import annotations

from sqlalchemy import Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UTCDateTime
from app.models.types import JSONDict

SOIL_DATA_SOURCES = ("lab_test", "sensor", "manual_entry", "demo_seed")


class SoilObservation(Base, TimestampMixin):
    __tablename__ = "soil_observations"
    __table_args__ = (Index("ix_soil_observation_field_observed", "field_id", "observed_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id", ondelete="CASCADE"), nullable=False, index=True)
    observed_at: Mapped[UTCDateTime] = mapped_column(UTCDateTime, nullable=False)
    sample_depth_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    soil_type: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # --- MEASURED VALUES (never modified by the AI layer) ---
    ph: Mapped[float | None] = mapped_column(Float, nullable=True)
    nitrogen_available_kg_ha: Mapped[float | None] = mapped_column(Float, nullable=True)
    phosphorus_available_kg_ha: Mapped[float | None] = mapped_column(Float, nullable=True)
    potassium_available_kg_ha: Mapped[float | None] = mapped_column(Float, nullable=True)
    organic_carbon_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    soil_moisture_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    electrical_conductivity_ds_m: Mapped[float | None] = mapped_column(Float, nullable=True)

    data_source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual_entry")
    lab_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    interpretation: Mapped[SoilInterpretation | None] = relationship(
        back_populates="observation", cascade="all, delete-orphan", uselist=False
    )

    def measured_payload(self) -> dict[str, float | None]:
        """Only the measured numeric values (used for evidence + reports)."""
        return {
            "ph": self.ph,
            "nitrogen_available_kg_ha": self.nitrogen_available_kg_ha,
            "phosphorus_available_kg_ha": self.phosphorus_available_kg_ha,
            "potassium_available_kg_ha": self.potassium_available_kg_ha,
            "organic_carbon_percent": self.organic_carbon_percent,
            "soil_moisture_percent": self.soil_moisture_percent,
            "electrical_conductivity_ds_m": self.electrical_conductivity_ds_m,
        }


class SoilInterpretation(Base, TimestampMixin):
    """Agent-generated interpretation of a measured soil observation."""

    __tablename__ = "soil_interpretations"

    id: Mapped[int] = mapped_column(primary_key=True)
    soil_observation_id: Mapped[int] = mapped_column(
        ForeignKey("soil_observations.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    agent_name: Mapped[str] = mapped_column(String(80), nullable=False, default="soil_nutrient_analysis_agent")
    generated_by: Mapped[str] = mapped_column(String(32), nullable=False, default="rule+retrieval")

    ph_class: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    nutrient_status: Mapped[dict] = mapped_column(JSONDict, nullable=False, default=dict)
    organic_matter_status: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    limitations: Mapped[list] = mapped_column(JSONDict, nullable=False, default=list)
    recommendations: Mapped[list] = mapped_column(JSONDict, nullable=False, default=list)
    missing_parameters: Mapped[list] = mapped_column(JSONDict, nullable=False, default=list)
    evidence: Mapped[list] = mapped_column(JSONDict, nullable=False, default=list)
    sources: Mapped[list] = mapped_column(JSONDict, nullable=False, default=list)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    observation: Mapped[SoilObservation] = relationship(back_populates="interpretation")
