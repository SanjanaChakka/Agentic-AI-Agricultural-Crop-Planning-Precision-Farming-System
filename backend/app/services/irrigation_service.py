"""Irrigation decision support.

The engine keeps the four evidence classes strictly separated:

* ``sensor_context``   - measured telemetry
* ``weather_context``  - forecast values
* ``rules_evaluated``  - the explicit decision rules that fired
* ``ml_prediction``    - the soil-moisture forecast model output

and combines them through an ordered rule set.  The critical behaviour is that
low soil moisture **plus** significant near-term rainfall does *not* produce a
blind "irrigate now" - the rainfall rule is evaluated first and can defer the
recommendation.

Nothing here actuates equipment.  Every result is a proposal that requires
explicit human authorisation.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.data.crop_catalog import CropRequirements, resolve_soil_type
from app.models.enums import IrrigationRecommendation, SourceKind
from app.models.farm import Field
from app.models.sensor import SensorReading
from app.schemas.common import Evidence, SourceReference, as_source_reference, sources_as_dicts
from app.schemas.weather import WeatherBundle

SCHEDULING_DOC = "irrigation.scheduling_principles"
STAGE_WATER_DOC = "irrigation.water_requirements_by_stage"

# Rainfall that can substitute for an irrigation within the decision horizon.
SIGNIFICANT_RAIN_MM = 10.0
HEAVY_RAIN_MM = 40.0
DECISION_HORIZON_HOURS = 48


def _round(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(float(value), digits)


def evaluate(
    *,
    field: Field,
    requirements: CropRequirements,
    latest: SensorReading | None,
    weather: WeatherBundle | None,
    ml_prediction: dict | None,
    soil_moisture_percent: float | None = None,
    crop_stage: str | None = None,
    references: list[SourceReference] | None = None,
) -> dict:
    """Produce the irrigation assessment payload (not yet persisted)."""
    sources: list[SourceReference] = [as_source_reference(item) for item in (references or [])]
    evidence: list[Evidence] = []
    rules: list[dict] = []

    stage = (crop_stage or field.crop_stage or "unknown").strip().lower()
    bands = resolve_soil_type(field.soil_type)
    refill_trigger = bands["refill_trigger"]
    field_capacity = bands["field_capacity"]
    available_water_per_10cm = bands["available_water_mm_per_10cm"]

    measured_moisture = soil_moisture_percent
    source_label = "soil test"
    if measured_moisture is None and latest is not None:
        measured_moisture = latest.soil_moisture_percent
        source_label = f"sensor {latest.sensor_id}"

    if measured_moisture is not None:
        evidence.append(
            Evidence(
                label="Measured soil moisture",
                value=measured_moisture,
                unit="% VWC",
                kind=SourceKind.SIMULATED if (latest and latest.is_simulated) else SourceKind.MEASURED,
                source=source_label,
                reference=SCHEDULING_DOC,
                note=f"Texture '{field.soil_type}' refill trigger is {refill_trigger}% VWC.",
                observed_at=latest.recorded_at if latest else None,
            )
        )
    else:
        evidence.append(
            Evidence(
                label="Measured soil moisture",
                value=None,
                kind=SourceKind.MEASURED,
                note="Not available - no sensor reading and no soil-test moisture value.",
            )
        )

    forecast: dict[str, float | None] = {}
    if weather is not None:
        horizon_days = [
            day
            for day in weather.daily
            if day.forecast_date is not None
            and day.forecast_date <= datetime.now(UTC) + timedelta(hours=DECISION_HORIZON_HOURS)
        ]
        rainfall_48h = round(sum(day.precipitation_mm or 0.0 for day in horizon_days), 2)
        max_probability = max(
            (day.precipitation_probability_percent or 0.0 for day in weather.daily[:3]),
            default=0.0,
        )
        forecast = {
            "rainfall_next_48h_mm": rainfall_48h,
            "rainfall_next_3d_mm": weather.rainfall_next_3_days_mm,
            "rainfall_7d_mm": weather.total_precipitation_mm,
            "max_precipitation_probability_3d_percent": _round(max_probability, 1),
            "max_temp_c": weather.max_temp_c,
            "total_et0_mm": weather.total_et0_mm,
            "mean_humidity_percent": weather.mean_humidity_percent,
            "source": weather.provider,
            "is_simulated": weather.is_simulated,
        }
        evidence.append(
            Evidence(
                label="Forecast rainfall (next 48 h)",
                value=rainfall_48h,
                unit="mm",
                kind=SourceKind.FORECAST,
                source=weather.provider,
                reference=SCHEDULING_DOC,
                note=(
                    "SIMULATED fallback weather - not a live forecast."
                    if weather.is_simulated
                    else f"Max 3-day precipitation probability {max_probability:.0f}%."
                ),
            )
        )
        evidence.append(
            Evidence(
                label="Forecast reference evapotranspiration (7 day)",
                value=weather.total_et0_mm,
                unit="mm",
                kind=SourceKind.FORECAST,
                source=weather.provider,
                reference=STAGE_WATER_DOC,
            )
        )

    rainfall_48h = forecast.get("rainfall_next_48h_mm")
    max_prob = forecast.get("max_precipitation_probability_3d_percent") or 0.0

    # ------------------------------------------------------------------
    # Rule 1 - information sufficiency
    # ------------------------------------------------------------------
    if measured_moisture is None:
        rules.append(
            {
                "rule": "information_sufficiency",
                "outcome": "insufficient_information",
                "detail": "No soil moisture measurement is available, so irrigation need cannot be judged.",
            }
        )
        return {
            "recommendation": IrrigationRecommendation.INSUFFICIENT_INFORMATION.value,
            "urgency": "unknown",
            "estimated_water_mm": None,
            "estimated_volume_m3": None,
            "rationale": (
                "Irrigation need cannot be determined because soil moisture is not available. "
                "Install or repair the soil-moisture probe, or record a soil-test moisture value, "
                "and re-run the analysis."
            ),
            "rules_evaluated": rules,
            "sensor_context": _sensor_context(field, latest, measured_moisture, refill_trigger),
            "weather_context": forecast,
            "ml_prediction": ml_prediction or {},
            "evidence": [item.model_dump() for item in evidence],
            "sources": sources_as_dicts(sources),
            "requires_human_authorisation": True,
        }

    if stage == "unknown":
        rules.append(
            {
                "rule": "crop_stage_known",
                "outcome": "warning",
                "detail": "Crop stage is unknown, so stage sensitivity could not be applied to the decision.",
            }
        )

    # ------------------------------------------------------------------
    # Rule 2 - rainfall substitution (evaluated BEFORE recommending water)
    # ------------------------------------------------------------------
    rainfall_48h_value = rainfall_48h if rainfall_48h is not None else 0.0
    if weather is None:
        rules.append(
            {
                "rule": "forecast_available",
                "outcome": "review",
                "detail": "No forecast is available, so expected rainfall cannot offset the moisture deficit.",
            }
        )
    elif rainfall_48h_value >= HEAVY_RAIN_MM or (rainfall_48h_value >= SIGNIFICANT_RAIN_MM and max_prob >= 50.0):
        rules.append(
            {
                "rule": "rainfall_substitution",
                "outcome": "postpone",
                "detail": (
                    f"{rainfall_48h_value} mm of rain is forecast within 48 hours "
                    f"(max probability {max_prob:.0f}%). Irrigating now would likely be wasted."
                ),
                "rainfall_mm": rainfall_48h_value,
            }
        )
        recommendation = IrrigationRecommendation.POSTPONE_IRRIGATION
        urgency = "low"
        depth_mm = None
    elif measured_moisture <= requirements.moisture_critical:
        rules.append(
            {
                "rule": "moisture_below_critical",
                "outcome": "irrigate",
                "detail": (
                    f"Measured moisture {measured_moisture}% VWC is at or below the critical threshold "
                    f"{requirements.moisture_critical}% VWC for {requirements.name} and little useful rain is forecast."
                ),
                "critical_percent": requirements.moisture_critical,
            }
        )
        recommendation = IrrigationRecommendation.IRRIGATE_SOON
        urgency = "high" if measured_moisture <= requirements.moisture_critical * 0.7 else "medium"
        depth_mm = _target_depth(measured_moisture, field_capacity, available_water_per_10cm, field.area_ha)
    elif measured_moisture <= refill_trigger:
        rules.append(
            {
                "rule": "moisture_at_refill_trigger",
                "outcome": "irrigate_if_not_raining",
                "detail": (
                    f"Measured moisture {measured_moisture}% VWC is at the texture refill trigger "
                    f"({refill_trigger}% VWC) but only {rainfall_48h_value} mm of rain is forecast in 48 hours."
                ),
                "refill_trigger_percent": refill_trigger,
            }
        )
        recommendation = IrrigationRecommendation.IRRIGATE_SOON
        urgency = "medium"
        depth_mm = _target_depth(measured_moisture, field_capacity, available_water_per_10cm, field.area_ha)
    elif measured_moisture < requirements.moisture_optimal[0]:
        rules.append(
            {
                "rule": "moisture_slightly_below_optimal",
                "outcome": "monitor",
                "detail": (
                    f"Measured moisture {measured_moisture}% VWC is below the comfortable band "
                    f"({requirements.moisture_optimal[0]}-{requirements.moisture_optimal[1]}% VWC) "
                    "but above the refill trigger."
                ),
            }
        )
        recommendation = IrrigationRecommendation.REVIEW_REQUIRED
        urgency = "low"
        depth_mm = None
    else:
        rules.append(
            {
                "rule": "moisture_adequate",
                "outcome": "no_irrigation",
                "detail": (
                    f"Measured moisture {measured_moisture}% VWC is inside the comfortable band "
                    f"for {requirements.name}."
                ),
            }
        )
        recommendation = IrrigationRecommendation.NO_IRRIGATION_NEEDED
        urgency = "low"
        depth_mm = None

    # ------------------------------------------------------------------
    # Rule 3 - water availability constraint
    # ------------------------------------------------------------------
    if recommendation == IrrigationRecommendation.IRRIGATE_SOON and field.water_availability in {"limited", "none"}:
        rules.append(
            {
                "rule": "water_availability",
                "outcome": "constrain",
                "detail": (
                    f"Water availability is '{field.water_availability}' via {field.irrigation_source}; "
                    "prioritise the most sensitive part of the field and consider prioritising sowing date over depth."
                ),
            }
        )
        urgency = "high" if field.water_availability == "none" else urgency

    # ------------------------------------------------------------------
    # Rule 4 - ML cross-check
    # ------------------------------------------------------------------
    ml_summary: dict = dict(ml_prediction or {})
    if ml_prediction and ml_prediction.get("status") == "ok":
        ml_value = ml_prediction.get("prediction_value")
        rules.append(
            {
                "rule": "ml_soil_moisture_crosscheck",
                "outcome": "review"
                if ml_value is not None and ml_value < requirements.moisture_critical
                else "confirm",
                "detail": (
                    f"{ml_prediction.get('model_name')} forecasts {ml_value}% VWC in "
                    f"{ml_prediction.get('horizon_days', 7)} days "
                    f"(model {ml_prediction.get('model_version')})."
                    if ml_value is not None
                    else str(ml_prediction.get("message", "model returned no value"))
                ),
                "predicted_soil_moisture_percent": ml_value,
            }
        )
        evidence.append(
            Evidence(
                label="ML 7-day soil moisture forecast",
                value=ml_value,
                unit="% VWC",
                kind=SourceKind.ML_PREDICTION,
                source=f"{ml_prediction.get('model_name')} v{ml_prediction.get('model_version')}",
                note=str(ml_prediction.get("message", "")),
            )
        )
        # A confident near-term drying forecast upgrades urgency, never overrides the rain rule.
        if ml_value is not None and ml_value < requirements.moisture_critical:
            if recommendation == IrrigationRecommendation.IRRIGATE_SOON:
                urgency = "high"
            elif (
                recommendation == IrrigationRecommendation.REVIEW_REQUIRED and rainfall_48h_value < SIGNIFICANT_RAIN_MM
            ):
                recommendation = IrrigationRecommendation.IRRIGATE_SOON
                urgency = "high"
                depth_mm = _target_depth(measured_moisture, field_capacity, available_water_per_10cm, field.area_ha)
                rules.append(
                    {
                        "rule": "ml_upgrade_to_irrigate",
                        "outcome": "irrigate",
                        "detail": (
                            "Moisture is currently acceptable but the model projects depletion below the critical "
                            "threshold within the week, so irrigation is advanced."
                        ),
                    }
                )
    elif ml_prediction and ml_prediction.get("status") == "unavailable":
        rules.append(
            {
                "rule": "ml_availability",
                "outcome": "skipped",
                "detail": str(ml_prediction.get("message", "ML model unavailable; rule logic only.")),
            }
        )

    # ------------------------------------------------------------------
    # Rule 5 - simulated data caveat
    # ------------------------------------------------------------------
    if latest is not None and latest.is_simulated:
        rules.append(
            {
                "rule": "data_provenance",
                "outcome": "warning",
                "detail": (
                    "The moisture value came from SIMULATED telemetry. Treat this recommendation as a "
                    "demonstration of method, not an operational instruction."
                ),
            }
        )
    if weather is not None and weather.is_simulated:
        rules.append(
            {
                "rule": "weather_provenance",
                "outcome": "warning",
                "detail": (
                    "Weather came from the offline fallback and is labelled simulated; "
                    "rainfall rules may be unreliable."
                ),
            }
        )

    if weather is None and measured_moisture <= refill_trigger:
        recommendation = IrrigationRecommendation.REVIEW_REQUIRED
        rules.append(
            {
                "rule": "forecast_missing_for_decision",
                "outcome": "review",
                "detail": (
                    "Soil moisture is below the refill trigger but no forecast is available to confirm that rain "
                    "will not supply the deficit, so a human decision is required."
                ),
            }
        )

    rationale = _rationale(recommendation, measured_moisture, requirements, stage, field, rules)
    volume = _round(depth_mm * field.area_ha, 1) if depth_mm is not None else None

    return {
        "recommendation": recommendation.value,
        "urgency": urgency,
        "estimated_water_mm": _round(depth_mm),
        "estimated_volume_m3": volume,
        "rationale": rationale,
        "rules_evaluated": rules,
        "sensor_context": _sensor_context(field, latest, measured_moisture, refill_trigger),
        "weather_context": forecast,
        "ml_prediction": ml_summary,
        "evidence": [item.model_dump() for item in evidence],
        "sources": sources_as_dicts(sources),
        "requires_human_authorisation": True,
    }


def _target_depth(
    moisture: float,
    field_capacity: float,
    available_water_per_10cm: float,
    area_ha: float,  # noqa: ARG001 - accepted for the documented agronomic signature; depth is area-independent
) -> float | None:
    """Depth (mm) to refill the top 30 cm from field capacity, at 0.9 efficiency."""
    depletion_fraction = max(0.0, (field_capacity - moisture) / max(field_capacity, 1.0))
    gross_mm = (depletion_fraction * available_water_per_10cm * 3.0) / 0.9
    return round(max(0.0, min(gross_mm, 80.0)), 1)


def _sensor_context(
    field: Field,
    latest: SensorReading | None,
    moisture: float | None,
    refill_trigger: float,
) -> dict:
    return {
        "latest_reading_at": latest.recorded_at.isoformat() if latest else None,
        "sensor_id": latest.sensor_id if latest else None,
        "is_simulated": bool(latest.is_simulated) if latest else None,
        "soil_moisture_percent": moisture,
        "soil_temperature_c": latest.soil_temperature_c if latest else None,
        "air_humidity_percent": latest.air_humidity_percent if latest else None,
        "quality_flags": latest.quality_flags if latest else None,
        "refill_trigger_percent": refill_trigger,
        "field_capacity_percent": resolve_soil_type(field.soil_type)["field_capacity"],
    }


def _rationale(
    recommendation: IrrigationRecommendation,
    moisture: float,
    requirements: CropRequirements,
    stage: str,
    field: Field,
    rules: list[dict],
) -> str:
    stage_text = f" at the {stage.replace('_', ' ')} stage" if stage != "unknown" else " (crop stage unknown)"
    if recommendation == IrrigationRecommendation.IRRIGATE_SOON:
        return (
            f"Measured soil moisture is {moisture}% VWC{stage_text}. The texture-specific refill trigger for "
            f"{field.soil_type} is {resolve_soil_type(field.soil_type)['refill_trigger']}% VWC and the critical "
            f"threshold for {requirements.name} is {requirements.moisture_critical}% VWC, with insufficient "
            "rainfall forecast inside the decision window. Irrigation is recommended and requires human authorisation."
        )
    if recommendation == IrrigationRecommendation.POSTPONE_IRRIGATION:
        return (
            f"Although soil moisture is {moisture}% VWC, significant rainfall is forecast within the decision "
            "window. Irrigating now would waste water, risk leaching below the root zone and add leaf wetness, "
            "so the recommendation is to postpone and re-check after the rain event."
        )
    if recommendation == IrrigationRecommendation.NO_IRRIGATION_NEEDED:
        return (
            f"Measured soil moisture is {moisture}% VWC, inside the comfortable band for {requirements.name}"
            f"{stage_text}. No irrigation is needed on current evidence; continue routine monitoring."
        )
    if recommendation == IrrigationRecommendation.INSUFFICIENT_INFORMATION:
        return "Soil moisture is unavailable, so irrigation need cannot be determined."
    return (
        f"Measured soil moisture is {moisture}% VWC{stage_text}. Signals are mixed or incomplete "
        f"({len(rules)} rule(s) evaluated), so a human agronomist should review before irrigating."
    )
