"""Crop suitability analysis.

A weighted, transparent multi-factor assessment.  Every factor reports:

* a verdict (``favourable`` / ``unfavourable`` / ``unknown``),
* a 0-1 score,
* the measured or forecast value it used,
* the agronomic band it was compared against,
* and the source document that defines that band.

Weights are renormalised over the factors that could actually be evaluated, so a
missing input reduces confidence rather than silently producing a wrong number.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from app.core.errors import UnprocessableEntityError
from app.data.crop_catalog import CROP_REQUIREMENTS, CropRequirements, nutrient_status_for, resolve_crop
from app.models.enums import SourceKind, SuitabilityStatus
from app.models.farm import Field
from app.models.soil import SoilObservation
from app.schemas.analysis import FactorScore
from app.schemas.common import Evidence, SourceReference, as_source_reference, sources_as_dicts
from app.schemas.weather import WeatherBundle

# Relative importance of each factor. Renormalised over evaluated factors.
FACTOR_WEIGHTS: dict[str, float] = {
    "soil_ph": 0.22,
    "soil_type": 0.12,
    "soil_moisture": 0.18,
    "temperature": 0.16,
    "rainfall_and_water": 0.14,
    "soil_fertility": 0.10,
    "crop_history": 0.08,
}

FACTOR_LABELS = {
    "soil_ph": "Soil pH",
    "soil_type": "Soil texture",
    "soil_moisture": "Soil moisture",
    "temperature": "Temperature regime",
    "rainfall_and_water": "Rainfall and water availability",
    "soil_fertility": "Soil fertility",
    "crop_history": "Crop history",
}

FACTOR_DOC = {
    "soil_ph": "soil.soil_ph_and_fertility",
    "soil_type": "soil.texture_and_water_holding",
    "soil_moisture": "soil.texture_and_water_holding",
    "temperature": "crops.*",
    "rainfall_and_water": "irrigation.scheduling_principles",
    "soil_fertility": "soil.soil_ph_and_fertility",
    "crop_history": "practices.crop_stages_and_practices",
}

SCORE_FAVOURABLE = 0.80
SCORE_CONDITIONAL = 0.58


@dataclass
class FactorOutcome:
    factor: str
    verdict: str
    score: float | None
    weight: float
    detail: str
    measured_value: str | float | None = None
    required_range: str | None = None
    limiting: bool = False


def _band_score(value: float | None, low: float, high: float, *, tolerance: float) -> float | None:
    """1.0 inside the band, decaying linearly outside it."""
    if value is None:
        return None
    if low <= value <= high:
        return 1.0
    distance = (low - value) if value < low else (value - high)
    return round(max(0.0, 1.0 - distance / max(tolerance, 1e-6)), 3)


def evaluate(
    *,
    field: Field,
    crop_name: str,
    requirements: CropRequirements,
    soil: SoilObservation | None,
    weather: WeatherBundle | None,
    references: list[SourceReference],
) -> dict:
    """Return the full suitability assessment payload (not yet persisted)."""
    factors: list[FactorOutcome] = []
    limiting: list[str] = []
    favorable: list[str] = []
    missing: list[str] = []
    evidence: list[Evidence] = []
    sources: list[SourceReference] = [as_source_reference(item) for item in references]

    # ---------------- soil pH ----------------
    ph_value = soil.ph if soil else None
    low, high = requirements.ph_optimal
    ph_score = _band_score(ph_value, low, high, tolerance=1.5)
    if ph_score is None:
        factors.append(
            FactorOutcome(
                factor="soil_ph",
                verdict="unknown",
                score=None,
                weight=FACTOR_WEIGHTS["soil_ph"],
                detail="Soil pH has not been measured, so the crop's pH tolerance cannot be checked.",
                required_range=f"{low}-{high}",
            )
        )
        missing.append("soil pH")
    else:
        tolerable = ph_value is not None and requirements.ph_tolerable[0] <= ph_value <= requirements.ph_tolerable[1]
        verdict = "favourable" if ph_score >= 0.9 else "unfavourable"
        detail = (
            f"Measured pH {ph_value} is inside the optimal {low}-{high} band for {requirements.name}."
            if verdict == "favourable"
            else f"Measured pH {ph_value} falls outside the optimal {low}-{high} band for {requirements.name}"
            + (
                ""
                if tolerable
                else (
                    " and also outside its tolerable range "
                    f"{requirements.ph_tolerable[0]}-{requirements.ph_tolerable[1]}."
                )
            )
        )
        factors.append(
            FactorOutcome(
                factor="soil_ph",
                verdict=verdict,
                score=ph_score,
                weight=FACTOR_WEIGHTS["soil_ph"],
                detail=detail,
                measured_value=ph_value,
                required_range=f"{low}-{high}",
                limiting=verdict == "unfavourable",
            )
        )
        evidence.append(
            Evidence(
                label=f"Measured soil pH vs {requirements.name} optimum",
                value=ph_value,
                kind=SourceKind.MEASURED,
                source=soil.data_source if soil else None,
                reference=requirements.doc(),
                note=f"optimal {low}-{high}; tolerable {requirements.ph_tolerable[0]}-{requirements.ph_tolerable[1]}",
                observed_at=soil.observed_at if soil else None,
            )
        )
        if verdict == "unfavourable":
            limiting.append(FACTOR_LABELS["soil_ph"])
        else:
            favorable.append(FACTOR_LABELS["soil_ph"])

    # ---------------- soil texture ----------------
    suitable_soils = requirements.suitable_soils
    if suitable_soils and field.soil_type:
        matches = field.soil_type in suitable_soils
        verdict = "favourable" if matches else "unfavourable"
        detail = (
            f"Recorded soil type '{field.soil_type}' is among the textures normally used for {requirements.name}."
            if matches
            else (
                f"Recorded soil type '{field.soil_type}' is not in the preferred set for "
                f"{requirements.name} ({', '.join(suitable_soils)})."
            )
        )
        factors.append(
            FactorOutcome(
                factor="soil_type",
                verdict=verdict,
                score=1.0 if matches else 0.45,
                weight=FACTOR_WEIGHTS["soil_type"],
                detail=detail,
                measured_value=field.soil_type,
                required_range=", ".join(suitable_soils),
            )
        )
        (favorable if matches else limiting).append(FACTOR_LABELS["soil_type"])
    else:
        factors.append(
            FactorOutcome(
                factor="soil_type",
                verdict="unknown",
                score=None,
                weight=FACTOR_WEIGHTS["soil_type"],
                detail="Soil type was not recorded for this field.",
            )
        )
        missing.append("soil texture")

    # ---------------- soil moisture ----------------
    moisture = soil.soil_moisture_percent if soil else None
    m_low, m_high = requirements.moisture_optimal
    moisture_score = _band_score(moisture, m_low, m_high, tolerance=max(6.0, m_low * 0.35))
    if moisture_score is None:
        factors.append(
            FactorOutcome(
                factor="soil_moisture",
                verdict="unknown",
                score=None,
                weight=FACTOR_WEIGHTS["soil_moisture"],
                detail="Current soil moisture was not measured; moisture status cannot be assessed.",
                required_range=f"{m_low}-{m_high} %VWC",
            )
        )
        missing.append("soil moisture")
    else:
        verdict = (
            "favourable"
            if moisture_score >= 0.9
            else ("unfavourable" if moisture <= requirements.moisture_critical else "favourable")
        )
        detail = (
            f"Measured soil moisture {moisture}% VWC is within the comfortable band "
            f"{m_low}-{m_high}% for {requirements.name}."
            if verdict == "favourable"
            else (
                f"Measured soil moisture {moisture}% VWC is below the critical threshold of "
                f"{requirements.moisture_critical}% VWC for {requirements.name}."
            )
        )
        factors.append(
            FactorOutcome(
                factor="soil_moisture",
                verdict=verdict,
                score=moisture_score,
                weight=FACTOR_WEIGHTS["soil_moisture"],
                detail=detail,
                measured_value=moisture,
                required_range=f"{m_low}-{m_high} %VWC",
                limiting=verdict == "unfavourable",
            )
        )
        evidence.append(
            Evidence(
                label="Measured soil moisture vs crop optimum",
                value=moisture,
                unit="% VWC",
                kind=SourceKind.MEASURED,
                source=soil.data_source if soil else None,
                reference=FACTOR_DOC["soil_moisture"],
                note=f"optimal {m_low}-{m_high} %VWC; critical {requirements.moisture_critical} %VWC",
                observed_at=soil.observed_at if soil else None,
            )
        )
        (favorable if verdict == "favourable" else limiting).append(FACTOR_LABELS["soil_moisture"])

    # ---------------- temperature ----------------
    mean_temp = None
    if weather and weather.daily:
        values = [day.temperature_mean_c for day in weather.daily if day.temperature_mean_c is not None]
        mean_temp = round(sum(values) / len(values), 2) if values else None
    t_low, t_high = requirements.temp_optimal
    temp_score = _band_score(mean_temp, t_low, t_high, tolerance=5.0)
    if temp_score is None:
        factors.append(
            FactorOutcome(
                factor="temperature",
                verdict="unknown",
                score=None,
                weight=FACTOR_WEIGHTS["temperature"],
                detail="No temperature data is available for this field.",
                required_range=f"{t_low}-{t_high} deg C",
            )
        )
        missing.append("weather/temperature data")
    else:
        verdict = "favourable" if temp_score >= 0.85 else "unfavourable"
        detail = (
            f"Forecast mean temperature {mean_temp} deg C sits inside the optimal "
            f"{t_low}-{t_high} deg C band for {requirements.name}."
            if verdict == "favourable"
            else (
                f"Forecast mean temperature {mean_temp} deg C is outside the optimal "
                f"{t_low}-{t_high} deg C band for {requirements.name}."
            )
        )
        factors.append(
            FactorOutcome(
                factor="temperature",
                verdict=verdict,
                score=temp_score,
                weight=FACTOR_WEIGHTS["temperature"],
                detail=detail,
                measured_value=mean_temp,
                required_range=f"{t_low}-{t_high} deg C",
                limiting=verdict == "unfavourable",
            )
        )
        evidence.append(
            Evidence(
                label="Forecast mean temperature vs crop optimum",
                value=mean_temp,
                unit="deg C",
                kind=SourceKind.FORECAST,
                source=f"weather provider: {weather.provider}",
                reference=requirements.doc(),
                note=f"optimal {t_low}-{t_high} deg C",
            )
        )
        (favorable if verdict == "favourable" else limiting).append(FACTOR_LABELS["temperature"])
        if weather.is_simulated:
            missing.append("verified live weather (current weather source is a simulated fallback)")

    # ---------------- rainfall and water availability ----------------
    season_rainfall = requirements.season_rainfall_mm
    water_verdict, water_score, water_detail, water_measured = _water_factor(field, requirements, weather)
    if water_verdict == "unknown":
        factors.append(
            FactorOutcome(
                factor="rainfall_and_water",
                verdict="unknown",
                score=None,
                weight=FACTOR_WEIGHTS["rainfall_and_water"],
                detail=water_detail,
                required_range=f"season rainfall {season_rainfall[0]:.0f}-{season_rainfall[1]:.0f} mm",
            )
        )
        missing.append("rainfall history / water availability")
    else:
        factors.append(
            FactorOutcome(
                factor="rainfall_and_water",
                verdict=water_verdict,
                score=water_score,
                weight=FACTOR_WEIGHTS["rainfall_and_water"],
                detail=water_detail,
                measured_value=water_measured,
                required_range=f"season rainfall {season_rainfall[0]:.0f}-{season_rainfall[1]:.0f} mm",
                limiting=water_verdict == "unfavourable",
            )
        )
        (favorable if water_verdict == "favourable" else limiting).append(FACTOR_LABELS["rainfall_and_water"])
        if water_verdict == "favourable":
            missing.append("historical seasonal rainfall totals (only the forecast window was assessed)")
        if weather and weather.is_simulated:
            missing.append("verified rainfall forecast (weather source is a simulated fallback)")

    # ---------------- fertility ----------------
    fertility_verdict, fertility_score, fertility_detail = _fertility_factor(soil, requirements)
    if fertility_verdict == "unknown":
        factors.append(
            FactorOutcome(
                factor="soil_fertility",
                verdict="unknown",
                score=None,
                weight=FACTOR_WEIGHTS["soil_fertility"],
                detail=fertility_detail,
                required_range="available N 110-280 kg/ha, P2O5 10-25 kg/ha, K2O 110-280 kg/ha",
            )
        )
        missing.append("soil nutrient test values")
    else:
        factors.append(
            FactorOutcome(
                factor="soil_fertility",
                verdict=fertility_verdict,
                score=fertility_score,
                weight=FACTOR_WEIGHTS["soil_fertility"],
                detail=fertility_detail,
                measured_value="see soil test",
                required_range="available N 110-280 kg/ha, P2O5 10-25 kg/ha, K2O 110-280 kg/ha",
            )
        )
        (favorable if fertility_verdict == "favourable" else limiting).append(FACTOR_LABELS["soil_fertility"])

    # ---------------- crop history ----------------
    previous = (field.previous_crop or "").strip()
    if not previous:
        factors.append(
            FactorOutcome(
                factor="crop_history",
                verdict="unknown",
                score=None,
                weight=FACTOR_WEIGHTS["crop_history"],
                detail="No previous crop was recorded, so rotation and carry-over risk cannot be judged.",
                required_range=f"a crop other than {requirements.name} on the same field",
            )
        )
        missing.append("previous crop record")
    elif (
        previous.lower() in requirements.aliases
        or previous.lower() == requirements.name.lower()
        or previous.lower() == crop_name.lower()
    ):
        factors.append(
            FactorOutcome(
                factor="crop_history",
                verdict="unfavourable",
                score=0.4,
                weight=FACTOR_WEIGHTS["crop_history"],
                detail=(
                    f"{requirements.name} was grown on this field last season. Repeating the crop raises "
                    "soil-borne disease, pest carry-over and nutrient depletion risk."
                ),
                measured_value=previous,
                required_range=f"a crop other than {requirements.name} on the same field",
            )
        )
        limiting.append(FACTOR_LABELS["crop_history"])
    else:
        factors.append(
            FactorOutcome(
                factor="crop_history",
                verdict="favourable",
                score=1.0,
                weight=FACTOR_WEIGHTS["crop_history"],
                detail=f"The previous crop was {previous}, so rotating into {requirements.name} breaks the cycle.",
                measured_value=previous,
                required_range=f"a crop other than {requirements.name} on the same field",
            )
        )
        favorable.append(FACTOR_LABELS["crop_history"])

    # ---------------- aggregate ----------------
    evaluated = [f for f in factors if f.score is not None]
    total_weight = sum(f.weight for f in evaluated) or 1.0
    score = round(sum(f.weight * f.score for f in evaluated) / total_weight, 3) if evaluated else None
    coverage = round(total_weight, 3)
    confidence = round(min(1.0, coverage * (1.0 - 0.15 * len(missing))), 3)

    status = _decide_status(score, factors, missing, coverage, requirements, ph_value)

    return {
        "crop": crop_name,
        "status": status.value,
        "score": score,
        "confidence": confidence,
        "factor_scores": [
            FactorScore(
                factor=factor.factor,
                label=FACTOR_LABELS[factor.factor],
                verdict=factor.verdict,
                score=factor.score,
                weight=factor.weight,
                detail=factor.detail,
                measured_value=factor.measured_value,
                required_range=factor.required_range,
            )
            for factor in factors
        ],
        "factors_raw": [asdict(f) for f in factors],
        "favorable_factors": sorted(set(favorable)),
        "limiting_factors": sorted(set(limiting)),
        "missing_information": sorted(set(missing)),
        "requirements_used": _requirements_payload(requirements),
        "evidence": [item.model_dump() for item in evidence],
        "sources": sources_as_dicts(sources),
        "evaluated_weight": coverage,
    }


def _water_factor(
    field: Field, requirements: CropRequirements, weather: WeatherBundle | None
) -> tuple[str, float, str, str]:
    availability = field.water_availability
    availability_scores = {
        "abundant": 1.0,
        "moderate": 0.85,
        "seasonal": 0.6,
        "limited": 0.35,
        "none": 0.0,
    }
    if availability == "none":
        return (
            "unfavourable",
            0.0,
            (
                f"Water availability is recorded as 'none' but {requirements.name} needs roughly "
                f"{requirements.water_requirement_mm[0]:.0f}-"
                f"{requirements.water_requirement_mm[1]:.0f} mm over the season."
            ),
            availability,
        )

    forecast_text = ""
    if weather and weather.daily:
        forecast_text = (
            f" Forecast rainfall over the next {len(weather.daily)} day(s) is "
            f"{weather.total_precipitation_mm} mm ({weather.rainfall_next_3_days_mm} mm in the first three days)."
        )
    score = availability_scores.get(availability, 0.6)
    verdict = "favourable" if score >= 0.8 else ("unfavourable" if score <= 0.35 else "favourable")
    detail = (
        f"Water availability is '{availability}' (irrigation source: {field.irrigation_source})."
        f"{forecast_text} Seasonal rainfall history is not available to the system, so only the "
        "forecast window and declared water access were assessed."
    )
    return verdict, score, detail, availability


def _fertility_factor(
    soil: SoilObservation | None,
    requirements: CropRequirements,  # noqa: ARG001 - crop-specific nutrient targets arrive with the next catalogue release
) -> tuple[str, float, str]:
    if soil is None:
        return "unknown", 0.0, "No soil test is available, so fertility cannot be assessed."
    values = {
        "nitrogen": soil.nitrogen_available_kg_ha,
        "phosphorus": soil.phosphorus_available_kg_ha,
        "potassium": soil.potassium_available_kg_ha,
    }
    key_map = {
        "nitrogen": "nitrogen_available_kg_ha",
        "phosphorus": "phosphorus_available_kg_ha",
        "potassium": "potassium_available_kg_ha",
    }
    if all(value is None for value in values.values()):
        return "unknown", 0.0, "The soil test reports no available nutrient values."

    statuses = {name: nutrient_status_for(key_map[name], value) for name, value in values.items()}
    lows = [name for name, status in statuses.items() if status == "low"]

    highs = [name for name, status in statuses.items() if status == "high"]

    if lows and len(lows) >= 2:
        score, verdict = 0.4, "unfavourable"
    elif lows:
        score, verdict = 0.75, "favourable"
    elif highs:
        score, verdict = 0.9, "favourable"
    else:
        score, verdict = 1.0, "favourable"

    parts = [f"{name.capitalize()} rated {statuses[name]}" for name in values]
    detail = "; ".join(parts) + "."
    if lows:
        detail += " Corrective fertilisation is needed before or at sowing."
    return verdict, score, detail


def _decide_status(
    score: float | None,
    factors: list[FactorOutcome],
    missing: list[str],  # noqa: ARG001 - used by the crop-specific overrides added per catalog entry
    coverage: float,
    requirements: CropRequirements,
    ph_value: float | None,
) -> SuitabilityStatus:
    """Map the weighted assessment onto one of four explicit statuses."""
    if score is None:
        return SuitabilityStatus.ADDITIONAL_INFORMATION_REQUIRED

    # Hard agronomic blockers always force review, regardless of the average.
    if ph_value is not None and not (requirements.ph_tolerable[0] <= ph_value <= requirements.ph_tolerable[1]):
        return SuitabilityStatus.AGRONOMIC_REVIEW_REQUIRED

    temp_factor = next((f for f in factors if f.factor == "temperature"), None)
    if temp_factor and temp_factor.measured_value is not None:
        t_low, t_high = requirements.temp_optimal
        value = float(temp_factor.measured_value)
        if value < t_low - 6.0 or value > t_high + 6.0:
            return SuitabilityStatus.AGRONOMIC_REVIEW_REQUIRED

    water_factor = next((f for f in factors if f.factor == "rainfall_and_water"), None)
    if water_factor and water_factor.measured_value == "none":
        return SuitabilityStatus.AGRONOMIC_REVIEW_REQUIRED

    # Insufficient evidence: too little of the model could be evaluated.
    critical_unknown = {"soil_ph", "soil_type", "temperature"} & {f.factor for f in factors if f.verdict == "unknown"}
    if coverage < 0.6 or critical_unknown:
        return SuitabilityStatus.ADDITIONAL_INFORMATION_REQUIRED

    has_limiting = any(f.limiting for f in factors)
    if score >= SCORE_FAVOURABLE and not has_limiting:
        return SuitabilityStatus.SUITABLE
    if score >= SCORE_CONDITIONAL:
        return SuitabilityStatus.SUITABLE_WITH_CONDITIONS
    return SuitabilityStatus.AGRONOMIC_REVIEW_REQUIRED


def _requirements_payload(requirements: CropRequirements) -> dict:
    return {
        "crop": requirements.name,
        "ph_optimal": list(requirements.ph_optimal),
        "ph_tolerable": list(requirements.ph_tolerable),
        "temp_optimal_c": list(requirements.temp_optimal),
        "season_rainfall_mm": list(requirements.season_rainfall_mm),
        "water_requirement_mm": list(requirements.water_requirement_mm),
        "moisture_optimal_percent": list(requirements.moisture_optimal),
        "moisture_critical_percent": requirements.moisture_critical,
        "season": requirements.season,
        "duration_days": list(requirements.duration_days),
        "critical_stages": list(requirements.critical_stages),
        "source_document": requirements.doc(),
    }


def resolve_requirements(crop_name: str | None) -> CropRequirements:
    requirements = resolve_crop(crop_name)
    if requirements is None:
        supported = ", ".join(sorted({req.name for req in CROP_REQUIREMENTS.values()}))
        raise UnprocessableEntityError(
            message=f"Crop '{crop_name}' is not in the curated knowledge base.",
            supported_crops=supported,
        )
    return requirements
