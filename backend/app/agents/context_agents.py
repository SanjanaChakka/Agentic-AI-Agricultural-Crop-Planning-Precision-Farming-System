"""Agents 1-3: farm/field profile, soil & nutrients, weather & climate.

These three agents establish the *measured* baseline of a run.  They are the
only agents allowed to create observations; everything downstream may only
interpret them.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from app.agents.base import AgentContext, AgentResult, BaseAgent, evidence_from_measurement, run_coroutine
from app.core.logging import get_logger
from app.data.crop_catalog import resolve_soil_type
from app.models.enums import SourceKind
from app.models.weather import WeatherSnapshot
from app.schemas.common import SourceReference
from app.services import sensor_service, soil_service, weather_service

logger = get_logger(__name__)

PROFILE_DOC = "practices.crop_stages_and_practices"
TEXTURE_DOC = "soil.texture_and_water_holding"


class FarmFieldProfileAgent(BaseAgent):
    """Reads the farm/field record and normalises it into the run's baseline."""

    name = "farm_field_profile_agent"
    responsibility = "Validate the farm and field profile and expose texture water-holding bands"

    def run(self, ctx: AgentContext) -> AgentResult:
        field = ctx.field
        farm = ctx.farm
        bands = resolve_soil_type(field.soil_type)
        evidence = [
            evidence_from_measurement(
                "Field area",
                field.area_ha,
                unit="ha",
                kind=SourceKind.USER_INPUT.value,
                source="field record",
                reference=PROFILE_DOC,
            ),
            evidence_from_measurement(
                "Declared soil texture",
                field.soil_type,
                kind=SourceKind.USER_INPUT.value,
                source="field record",
                reference=TEXTURE_DOC,
            ),
            evidence_from_measurement(
                "Field capacity for declared texture",
                bands["field_capacity"],
                unit="% VWC",
                kind=SourceKind.RETRIEVED_REFERENCE.value,
                source="soil texture reference table",
                reference=TEXTURE_DOC,
                note="Texture class band, not a field measurement.",
            ),
            evidence_from_measurement(
                "Refill trigger for declared texture",
                bands["refill_trigger"],
                unit="% VWC",
                kind=SourceKind.RETRIEVED_REFERENCE.value,
                source="soil texture reference table",
                reference=TEXTURE_DOC,
            ),
            evidence_from_measurement(
                "Irrigation source",
                field.irrigation_source,
                kind=SourceKind.USER_INPUT.value,
                source="field record",
            ),
            evidence_from_measurement(
                "Water availability",
                field.water_availability,
                kind=SourceKind.USER_INPUT.value,
                source="field record",
            ),
        ]

        missing: list[str] = []
        for label, value in (
            ("area", field.area_ha),
            ("soil texture", field.soil_type),
            ("irrigation source", field.irrigation_source),
            ("previous crop", field.previous_crop),
            ("proposed crop", field.proposed_crop),
        ):
            if value in (None, ""):
                missing.append(label)
                ctx.warn(f"Field record is missing '{label}', which reduces confidence in later steps.")

        latitude = field.effective_latitude
        longitude = field.effective_longitude
        if latitude is None or longitude is None:
            missing.append("geolocation")
            ctx.warn("No geolocation available; weather will fall back to offline climatology.")

        window = None
        if field.planting_window_start is not None:
            window = {
                "start": field.planting_window_start.isoformat(),
                "end": (field.planting_window_start + timedelta(days=21)).isoformat(),
            }

        output: dict[str, Any] = {
            "farm": {
                "id": farm.id,
                "name": farm.name,
                "owner_name": farm.owner_name,
                "location_name": farm.location_name,
                "district": farm.district,
                "state": farm.state,
                "total_area_ha": farm.total_area_ha,
            },
            "field": {
                "id": field.id,
                "field_code": field.field_code,
                "name": field.name,
                "area_ha": field.area_ha,
                "soil_type": field.soil_type,
                "latitude": latitude,
                "longitude": longitude,
                "previous_crop": field.previous_crop,
                "proposed_crop": field.proposed_crop,
                "crop_stage": field.crop_stage,
                "irrigation_source": field.irrigation_source,
                "water_availability": field.water_availability,
                "water_availability_m3_per_day": field.water_availability_m3_per_day,
                "planting_window": window,
                "notes": field.notes,
            },
            "texture_bands": bands,
            "crop": ctx.crop,
            "crop_requirements": {
                "ph_optimal": list(ctx.requirements.ph_optimal),
                "temp_optimal": list(ctx.requirements.temp_optimal),
                "season_rainfall_mm": list(ctx.requirements.season_rainfall_mm),
                "water_requirement_mm": list(ctx.requirements.water_requirement_mm),
                "moisture_optimal": list(ctx.requirements.moisture_optimal),
                "moisture_critical": ctx.requirements.moisture_critical,
                "heat_stress_threshold_c": ctx.requirements.heat_stress_threshold_c,
                "season": ctx.requirements.season,
                "duration_days": list(ctx.requirements.duration_days),
                "critical_stages": list(ctx.requirements.critical_stages),
            },
            "missing_inputs": missing,
            "profile_complete": not missing,
        }

        sources = ctx.retrieve(
            f"{ctx.requirements.name} crop requirements {ctx.field.soil_type} soil texture water holding",
            top_k=3,
        )
        reasoning = (
            f"Field {field.field_code} covers {field.area_ha} ha of {field.soil_type} and is recorded as "
            f"'{field.irrigation_source}' irrigated with '{field.water_availability}' water availability. "
            f"The declared texture maps to a refill trigger of {bands['refill_trigger']}% VWC and field "
            f"capacity of {bands['field_capacity']}% VWC, which governs every later moisture threshold. "
            f"Planning crop for this run: {ctx.requirements.name}."
        )
        if missing:
            reasoning += f" Missing profile inputs: {', '.join(missing)}."

        return AgentResult(
            name=self.name,
            responsibility=self.responsibility,
            output=output,
            state_patch={"farm_profile": output},
            evidence=evidence,
            sources=sources,
            reasoning=reasoning,
        )


class SoilNutrientAgent(BaseAgent):
    """Interprets the latest measured soil test without ever altering it."""

    name = "soil_nutrient_agent"
    responsibility = "Interpret measured soil chemistry against crop requirements and flag limitations"

    def run(self, ctx: AgentContext) -> AgentResult:
        observation = soil_service.latest_observation(ctx.db, ctx.field.id)
        if observation is None:
            ctx.warn(
                "No soil observation exists for this field; soil-dependent decisions fall back to texture defaults."
            )
            output = {
                "available": False,
                "measured": {},
                "interpretation": None,
                "missing_parameters": ["entire soil test"],
                "narrative": (
                    "No soil test is on record for this field. The agent did not invent values; the "
                    "assessments below rely on texture defaults and are flagged accordingly."
                ),
            }
            return AgentResult(
                name=self.name,
                responsibility=self.responsibility,
                status="succeeded",
                output=output,
                state_patch={"soil": output},
                evidence=[
                    evidence_from_measurement(
                        "Soil test",
                        None,
                        kind=SourceKind.MEASURED.value,
                        note="No soil observation recorded for this field.",
                    )
                ],
                reasoning="No measured soil data; recorded the gap and continued with texture-based defaults.",
            )

        interpretation = soil_service.interpret_observation(
            observation, crop=ctx.requirements.name.lower(), persist=True
        )
        measured = observation.measured_payload()
        evidence = soil_service.observation_evidence(observation)
        sources: list[SourceReference] = list(interpretation.sources or [])

        missing = soil_service.missing_parameters(observation, crop=ctx.crop)
        if missing:
            ctx.warn(f"Soil test is incomplete; missing: {', '.join(missing)}.")

        output: dict[str, Any] = {
            "available": True,
            "observation_id": observation.id,
            "observed_at": observation.observed_at.isoformat(),
            "sample_depth_cm": observation.sample_depth_cm,
            "data_source": observation.data_source,
            "lab_name": observation.lab_name,
            "measured": measured,
            "interpretation": {
                "ph_class": interpretation.ph_class,
                "nutrient_status": interpretation.nutrient_status,
                "organic_matter_status": interpretation.organic_matter_status,
                "summary": interpretation.summary,
                "limitations": interpretation.limitations,
                "recommendations": interpretation.recommendations,
                "missing_parameters": interpretation.missing_parameters,
                "confidence": interpretation.confidence,
                "generated_by": interpretation.generated_by,
                "agent_name": interpretation.agent_name,
            },
            "missing_parameters": missing,
            "narrative": interpretation.summary,
        }

        ph_value = observation.ph
        reasoning = (
            f"Measured soil sample from {observation.observed_at.date()} "
            f"({observation.data_source}) gives pH {ph_value if ph_value is not None else 'not available'} "
            f"classified as '{interpretation.ph_class}'. Nutrient status: "
            f"{interpretation.nutrient_status or 'not available'}. These measured values are preserved "
            "exactly as reported; the assessment below is interpretation only and never rewrites the "
            "measurement."
        )

        return AgentResult(
            name=self.name,
            responsibility=self.responsibility,
            output=output,
            state_patch={"soil": output},
            evidence=evidence,
            sources=sources,
            reasoning=reasoning,
        )


class WeatherClimateAgent(BaseAgent):
    """Fetches live weather through the provider chain and records provenance."""

    name = "weather_climate_agent"
    responsibility = "Acquire forecast and climate context, labelling any fallback as simulated"

    def run(self, ctx: AgentContext) -> AgentResult:
        latitude = ctx.field.effective_latitude
        longitude = ctx.field.effective_longitude
        force = bool(ctx.options.get("force_refresh_weather"))

        if latitude is None or longitude is None:
            ctx.warn("Field has no geolocation; weather context unavailable.")
            output = {
                "available": False,
                "source": "unavailable",
                "provider": "unavailable",
                "is_simulated": False,
                "reason": "field_geolocation_missing",
                "daily": [],
            }
            return AgentResult(
                name=self.name,
                responsibility=self.responsibility,
                output=output,
                state_patch={"weather": output},
                evidence=[
                    evidence_from_measurement(
                        "Weather forecast",
                        None,
                        kind=SourceKind.FORECAST.value,
                        note="No geolocation available for this field.",
                    )
                ],
                reasoning="No geolocation on the field or farm, so no forecast could be requested.",
            )

        bundle = _fetch_bundle(latitude, longitude, ctx)
        _persist_snapshot(ctx, bundle)

        evidence = [
            evidence_from_measurement(
                "Forecast maximum temperature",
                bundle.max_temp_c,
                unit="deg C",
                kind=SourceKind.SIMULATED.value if bundle.is_simulated else SourceKind.FORECAST.value,
                source=bundle.provider_display,
                note=("OFFLINE CLIMATOLOGY ESTIMATE - not an API observation." if bundle.is_simulated else None),
            ),
            evidence_from_measurement(
                "Forecast minimum temperature",
                bundle.min_temp_c,
                unit="deg C",
                kind=SourceKind.SIMULATED.value if bundle.is_simulated else SourceKind.FORECAST.value,
                source=bundle.provider_display,
            ),
            evidence_from_measurement(
                "Rainfall next 3 days",
                bundle.rainfall_next_3_days_mm,
                unit="mm",
                kind=SourceKind.SIMULATED.value if bundle.is_simulated else SourceKind.FORECAST.value,
                source=bundle.provider_display,
            ),
            evidence_from_measurement(
                "Rainfall over full forecast window",
                bundle.total_precipitation_mm,
                unit="mm",
                kind=SourceKind.SIMULATED.value if bundle.is_simulated else SourceKind.FORECAST.value,
                source=bundle.provider_display,
            ),
            evidence_from_measurement(
                "Reference evapotranspiration over forecast window",
                bundle.total_et0_mm,
                unit="mm",
                kind=SourceKind.SIMULATED.value if bundle.is_simulated else SourceKind.FORECAST.value,
                source=bundle.provider_display,
                note="ET0 from the provider's own evapotranspiration model.",
            ),
            evidence_from_measurement(
                "Mean relative humidity",
                bundle.mean_humidity_percent,
                unit="%",
                kind=SourceKind.SIMULATED.value if bundle.is_simulated else SourceKind.FORECAST.value,
                source=bundle.provider_display,
            ),
        ]

        sources = ctx.retrieve(
            f"{ctx.requirements.name} heat stress rainfall extremes waterlogging temperature threshold",
            top_k=3,
            categories=["climate", "crops"],
        )

        output: dict[str, Any] = {
            "available": True,
            "source": bundle.source,
            "provider": bundle.provider,
            "is_simulated": bundle.is_simulated,
            "fallback_used": bundle.fallback_used,
            "fetched_at": bundle.fetched_at.isoformat(),
            "location_name": bundle.location_name,
            "latitude": latitude,
            "longitude": longitude,
            "current": bundle.current.model_dump(mode="json") if bundle.current else None,
            "daily": [day.model_dump(mode="json") for day in bundle.daily],
            "total_precipitation_mm": bundle.total_precipitation_mm,
            "rainfall_next_3_days_mm": bundle.rainfall_next_3_days_mm,
            "max_temp_c": bundle.max_temp_c,
            "min_temp_c": bundle.min_temp_c,
            "mean_humidity_percent": bundle.mean_humidity_percent,
            "total_et0_mm": bundle.total_et0_mm,
            "notes": bundle.notes,
            "requested_fresh": force,
        }

        if bundle.is_simulated:
            ctx.warn(
                "Weather came from the offline fallback and is flagged as SIMULATED; rainfall and heat "
                "rules in this run are indicative only."
            )

        reasoning = (
            f"Weather source '{bundle.source}' (provider '{bundle.provider}', simulated={bundle.is_simulated}) "
            f"returned {len(bundle.daily)} forecast days for {latitude}, {longitude}. Window totals: "
            f"{bundle.total_precipitation_mm} mm rain and {bundle.total_et0_mm} mm ET0, temperature range "
            f"{bundle.min_temp_c}-{bundle.max_temp_c} deg C. "
            + (
                "Because this is a clearly-labelled offline estimate, every forecast-driven rule in this run "
                "is marked as provisional."
                if bundle.is_simulated
                else "These are live provider values."
            )
        )

        return AgentResult(
            name=self.name,
            responsibility=self.responsibility,
            output=output,
            state_patch={"weather": output},
            evidence=evidence,
            sources=sources,
            reasoning=reasoning,
        )


def _fetch_bundle(latitude: float, longitude: float, ctx: AgentContext) -> Any:
    days = int(ctx.options.get("weather_days") or 7)
    location = ctx.farm.location_name if ctx.farm else None
    return run_coroutine(
        lambda: weather_service.fetch_weather(
            latitude,
            longitude,
            days=days,
            location_name=location,
            field_id=ctx.field.id,
        )
    )


def _persist_snapshot(ctx: AgentContext, bundle) -> None:  # noqa: ANN001 - WeatherBundle
    """Persist one snapshot row per forecast day plus the current observation."""
    rows: list[WeatherSnapshot] = []
    common = {
        "field_id": ctx.field.id,
        "farm_id": ctx.field.farm_id,
        "source": bundle.source,
        "is_simulated": bundle.is_simulated,
        "fetched_at": bundle.fetched_at,
        "raw_payload": {
            "provider": bundle.provider,
            "fallback_used": bundle.fallback_used,
            "notes": bundle.notes,
        },
        "notes": "; ".join(bundle.notes)[:500] if bundle.notes else None,
    }

    if bundle.current is not None:
        rows.append(
            WeatherSnapshot(
                **common,
                observed_at=bundle.current.observed_at,
                temperature_c=bundle.current.temperature_c,
                feels_like_c=bundle.current.feels_like_c,
                humidity_percent=bundle.current.humidity_percent,
                wind_speed_ms=bundle.current.wind_speed_ms,
                condition=bundle.current.condition,
            )
        )

    for day in bundle.daily:
        rows.append(
            WeatherSnapshot(
                **common,
                forecast_date=day.forecast_date,
                temp_min_c=day.temp_min_c,
                temp_max_c=day.temp_max_c,
                precipitation_mm=day.precipitation_mm,
                precipitation_probability_percent=day.precipitation_probability_percent,
                et0_mm=day.et0_mm,
            )
        )

    ctx.db.add_all(rows)
    ctx.db.flush()
    logger.info("Persisted %s weather snapshot rows for field %s", len(rows), ctx.field.id)


def latest_sensor_summary(ctx: AgentContext) -> dict[str, Any]:
    """Shared helper for telemetry state used by the sensor/ML agents."""
    latest = sensor_service.latest_reading(ctx.db, ctx.field.id)
    series, stats = sensor_service.trend(ctx.db, ctx.field.id, hours=168)
    return {
        "latest": latest,
        "series": series,
        "stats": stats,
        "count": len(series),
    }
