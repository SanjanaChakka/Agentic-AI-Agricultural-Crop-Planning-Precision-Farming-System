"""Crop risk monitoring.

Every finding is phrased as *environmental conditions favourable for X* and is
flagged ``is_diagnosis=False``.  The module has no diagnostic capability: it
reports environmental favourability and recommends scouting.  Only an actual
field inspection plus laboratory confirmation can confirm a disease.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.data.crop_catalog import (
    EXTENDED_DRY_DAYS,
    HEAVY_RAINFALL_MM_3D,
    LOW_MOISTURE_CRITICAL,
    SEVERE_HEAT_TEMP_C,
    WATERLOGGING_RISK_MM_3D,
    CropRequirements,
)
from app.models.enums import RiskType, Severity, SourceKind
from app.models.farm import Field
from app.models.sensor import SensorReading
from app.schemas.common import Evidence, SourceReference, as_source_reference, sources_as_dicts
from app.schemas.weather import WeatherBundle

HEAT_DOC = "climate.heat_and_water_stress"
RAIN_DOC = "climate.rainfall_extremes_and_waterlogging"
DISEASE_DOC = "risk.disease_favourable_environment"
SENSOR_DOC = "practices.sensor_data_quality"

SEVERITY_RANK = {Severity.INFO.value: 0, Severity.LOW.value: 1, Severity.MEDIUM.value: 2, Severity.HIGH.value: 3}

DISCLAIMER = (
    "These findings describe environmental conditions only. The system has no diagnostic capability: "
    "no disease, pest or nutrient disorder is named here. Confirm anything through field scouting "
    "and, where necessary, laboratory testing."
)


def scan(
    *,
    field: Field,
    requirements: CropRequirements,
    weather: WeatherBundle | None,
    latest: SensorReading | None,
    trend_stats: dict | None = None,
    references: list[SourceReference] | None = None,
) -> dict:
    """Return ``{"findings": [...], "risk_level": ..., "disclaimer": ...}``."""
    sources: list[SourceReference] = [as_source_reference(item) for item in (references or [])]
    now = datetime.now(UTC)
    findings: list[dict] = []

    # ------------------------------------------------------------------
    # 1. Heat stress
    # ------------------------------------------------------------------
    if (
        weather is not None
        and weather.max_temp_c is not None
        and weather.max_temp_c >= requirements.heat_stress_threshold_c
    ):
        severity = Severity.HIGH if weather.max_temp_c >= SEVERE_HEAT_TEMP_C else Severity.MEDIUM
        findings.append(
            _finding(
                risk_type=RiskType.HEAT_STRESS,
                severity=severity,
                observed_at=now,
                statement=(
                    f"Environmental conditions favourable for heat stress: forecast maximum temperature "
                    f"{weather.max_temp_c} deg C is at or above the {requirements.heat_stress_threshold_c} deg C "
                    f"heat threshold for {requirements.name}."
                ),
                impact=(
                    "Heat above the crop ceiling reduces photosynthesis and can cause flower and fruit drop "
                    "and poor grain or seed filling, especially during flowering."
                ),
                investigation=(
                    "Scout the crop between 11:00 and 15:00 for wilting despite adequate soil moisture, "
                    "check pollination success at flowering, and confirm whether irrigation demand is rising."
                ),
                evidence=[
                    Evidence(
                        label="Forecast maximum temperature",
                        value=weather.max_temp_c,
                        unit="deg C",
                        kind=SourceKind.FORECAST,
                        source=weather.provider,
                        reference=HEAT_DOC,
                        note=f"{requirements.name} heat threshold {requirements.heat_stress_threshold_c} deg C"
                        + (" (simulated weather)" if weather.is_simulated else ""),
                    ),
                    Evidence(
                        label="Forecast reference evapotranspiration (7 day)",
                        value=weather.total_et0_mm,
                        unit="mm",
                        kind=SourceKind.FORECAST,
                        source=weather.provider,
                        reference=HEAT_DOC,
                    ),
                ],
                sources=sources,
            )
        )

    # ------------------------------------------------------------------
    # 2. Water stress
    # ------------------------------------------------------------------
    moisture = latest.soil_moisture_percent if latest else None
    if moisture is not None and moisture <= requirements.moisture_critical:
        severity = Severity.HIGH if moisture <= requirements.moisture_critical * 0.75 else Severity.MEDIUM
        findings.append(
            _finding(
                risk_type=RiskType.WATER_STRESS,
                severity=severity,
                observed_at=latest.recorded_at if latest else now,
                statement=(
                    f"Environmental conditions favourable for water stress: measured soil moisture "
                    f"{moisture}% VWC is at or below the critical threshold of "
                    f"{requirements.moisture_critical}% VWC for {requirements.name}."
                ),
                impact=(
                    "Water stress reduces nutrient uptake, photosynthesis and pollination; during flowering or "
                    "grain filling it causes irreversible yield loss."
                ),
                investigation=(
                    "Verify the probe reading with a manual check, then review the irrigation plan - this finding "
                    "requires human authorisation before any water is applied."
                ),
                evidence=[
                    Evidence(
                        label="Measured soil moisture",
                        value=moisture,
                        unit="% VWC",
                        kind=SourceKind.SIMULATED if (latest and latest.is_simulated) else SourceKind.MEASURED,
                        source=f"sensor {latest.sensor_id}" if latest else "soil test",
                        reference=HEAT_DOC,
                        note=f"critical threshold {requirements.moisture_critical}% VWC",
                        observed_at=latest.recorded_at if latest else None,
                    ),
                    Evidence(
                        label="Moisture change over monitoring window",
                        value=(trend_stats or {}).get("moisture_change_over_window"),
                        unit="%VWC",
                        kind=SourceKind.OBSERVED,
                        reference=HEAT_DOC,
                    ),
                ],
                sources=sources,
            )
        )

    # ------------------------------------------------------------------
    # 3. Excessive rainfall / waterlogging
    # ------------------------------------------------------------------
    if weather is not None:
        rain_3d = weather.rainfall_next_3_days_mm
        if rain_3d >= HEAVY_RAINFALL_MM_3D:
            severity = Severity.HIGH if rain_3d >= WATERLOGGING_RISK_MM_3D else Severity.MEDIUM
            findings.append(
                _finding(
                    risk_type=RiskType.EXCESSIVE_RAINFALL,
                    severity=severity,
                    observed_at=now,
                    statement=(
                        f"Environmental conditions favourable for waterlogging and nutrient loss: "
                        f"{rain_3d} mm of rainfall is forecast over the next three days "
                        f"({weather.total_precipitation_mm} mm over the full forecast window)."
                    ),
                    impact=(
                        "Saturated soil starves roots of oxygen, drives denitrification and leaching, and increases "
                        "fungal and bacterial disease pressure in the canopy."
                    ),
                    investigation=(
                        "Inspect field drainage and the standing-water depth, postpone planned fertiliser and "
                        "irrigation, and scout for lodging or early disease symptoms once the water recedes."
                    ),
                    evidence=[
                        Evidence(
                            label="Forecast rainfall (next 3 days)",
                            value=rain_3d,
                            unit="mm",
                            kind=SourceKind.FORECAST,
                            source=weather.provider,
                            reference=RAIN_DOC,
                            note=f"heavy-rain threshold {HEAVY_RAINFALL_MM_3D} mm/3d"
                            + (" (simulated weather)" if weather.is_simulated else ""),
                        ),
                        Evidence(
                            label="Field soil texture",
                            value=field.soil_type,
                            kind=SourceKind.USER_INPUT,
                            reference="soil.texture_and_water_holding",
                        ),
                    ],
                    sources=sources,
                )
            )

    # ------------------------------------------------------------------
    # 4. Extended dry period
    # ------------------------------------------------------------------
    if weather is not None and weather.daily:
        dry_streak = 0
        for day in weather.daily:
            if (day.precipitation_mm or 0.0) < 2.0:
                dry_streak += 1
            else:
                break
        if dry_streak >= EXTENDED_DRY_DAYS:
            findings.append(
                _finding(
                    risk_type=RiskType.EXTENDED_DRY_PERIOD,
                    severity=Severity.MEDIUM,
                    observed_at=now,
                    statement=(
                        f"Environmental conditions favourable for an extended dry period: {dry_streak} consecutive "
                        "forecast days with rainfall below 2 mm."
                    ),
                    impact=(
                        "Soil water reserves deplete, establishment and flowering are impaired and irrigation demand "
                        "rises sharply."
                    ),
                    investigation=(
                        "Check irrigation supply capacity and prioritise the most sensitive field, then re-check the "
                        "moisture forecast before committing water."
                    ),
                    evidence=[
                        Evidence(
                            label="Consecutive dry forecast days",
                            value=dry_streak,
                            kind=SourceKind.FORECAST,
                            source=weather.provider,
                            reference=RAIN_DOC,
                        ),
                        Evidence(
                            label="Forecast total evapotranspiration (7 day)",
                            value=weather.total_et0_mm,
                            unit="mm",
                            kind=SourceKind.FORECAST,
                            source=weather.provider,
                            reference=RAIN_DOC,
                        ),
                    ],
                    sources=sources,
                )
            )

    # ------------------------------------------------------------------
    # 5. Disease-favourable environment (favourability, never diagnosis)
    # ------------------------------------------------------------------
    if weather is not None and weather.daily:
        humidity = weather.mean_humidity_percent
        wet_days = sum(1 for day in weather.daily if (day.precipitation_mm or 0.0) >= 1.0)
        wet_fraction = wet_days / max(len(weather.daily), 1)
        if humidity is not None and humidity >= requirements.humidity_risk_threshold_percent and wet_fraction >= 0.4:
            findings.append(
                _finding(
                    risk_type=RiskType.DISEASE_FAVOURABLE_ENVIRONMENT,
                    severity=Severity.MEDIUM,
                    observed_at=now,
                    statement=(
                        f"Environmental conditions favourable for foliar disease: mean relative humidity "
                        f"{humidity}% (threshold {requirements.humidity_risk_threshold_percent}%) with "
                        f"{wet_days} of {len(weather.daily)} forecast days carrying measurable rainfall."
                    ),
                    impact=(
                        "Prolonged leaf wetness at moderate temperatures favours the development and spread of "
                        "fungal and bacterial leaf diseases and boll/rot pathogens."
                    ),
                    investigation=(
                        "Scout the canopy within 24-72 hours of the wet spell, inspect the underside of leaves for "
                        "early lesions, and avoid evening overhead irrigation. Confirm any suspected disease "
                        "through a plant clinic or laboratory before treating."
                    ),
                    evidence=[
                        Evidence(
                            label="Mean relative humidity (forecast)",
                            value=humidity,
                            unit="%",
                            kind=SourceKind.FORECAST,
                            source=weather.provider,
                            reference=DISEASE_DOC,
                            note=(
                                f"{requirements.name} disease-favourability humidity threshold "
                                f"{requirements.humidity_risk_threshold_percent}%"
                            ),
                        ),
                        Evidence(
                            label="Fraction of forecast days with rainfall >= 1 mm",
                            value=round(wet_fraction, 2),
                            kind=SourceKind.FORECAST,
                            source=weather.provider,
                            reference=DISEASE_DOC,
                        ),
                        Evidence(
                            label="Forecast rainfall (7 day)",
                            value=weather.total_precipitation_mm,
                            unit="mm",
                            kind=SourceKind.FORECAST,
                            source=weather.provider,
                            reference=DISEASE_DOC,
                        ),
                    ],
                    sources=sources,
                )
            )

    # ------------------------------------------------------------------
    # 6. Sensor malfunction
    # ------------------------------------------------------------------
    if latest is not None:
        faults = [flag for flag in (latest.quality_flags or []) if flag not in {"ok", "simulated"}]
        if faults:
            findings.append(
                _finding(
                    risk_type=RiskType.SENSOR_FAULT,
                    severity=Severity.MEDIUM,
                    observed_at=latest.recorded_at,
                    statement=(
                        "Sensor data quality check failed: the most recent reading from "
                        f"{latest.sensor_id} carries the flag(s) {', '.join(faults)}."
                    ),
                    impact=(
                        "Decisions based on this sensor can be wrong. An identical-to-previous value usually means "
                        "a stuck probe; a large step without rain or irrigation suggests wiring, units or a "
                        "calibration problem."
                    ),
                    investigation=(
                        "Compare against a manual probe reading, check power and wiring, confirm the sensor is "
                        "calibrated for this soil texture, and treat affected readings as missing rather than real."
                    ),
                    evidence=[
                        Evidence(
                            label="Sensor quality flags",
                            value=", ".join(faults),
                            kind=SourceKind.SIMULATED if latest.is_simulated else SourceKind.OBSERVED,
                            source=f"sensor {latest.sensor_id}",
                            reference=SENSOR_DOC,
                            observed_at=latest.recorded_at,
                        ),
                        Evidence(
                            label="Reported soil moisture",
                            value=latest.soil_moisture_percent,
                            unit="% VWC",
                            kind=SourceKind.SIMULATED if latest.is_simulated else SourceKind.OBSERVED,
                            source=f"sensor {latest.sensor_id}",
                            reference=SENSOR_DOC,
                            observed_at=latest.recorded_at,
                        ),
                    ],
                    sources=sources,
                )
            )

    risk_level = _overall_level(findings)
    return {"findings": findings, "risk_level": risk_level, "disclaimer": DISCLAIMER}


def _finding(
    *,
    risk_type: RiskType,
    severity: Severity,
    observed_at: datetime,
    statement: str,
    impact: str,
    investigation: str,
    evidence: list[Evidence],
    sources: list[SourceReference],
) -> dict:
    return {
        "risk_type": risk_type.value,
        "severity": severity.value,
        "statement": statement,
        "potential_impact": impact,
        "recommended_investigation": investigation,
        "evidence": [item.model_dump() for item in evidence],
        "sources": sources_as_dicts(sources),
        "observed_at": observed_at,
        "is_diagnosis": False,
    }


def _overall_level(findings: list[dict]) -> str:
    if not findings:
        return "none"
    ranks = [SEVERITY_RANK.get(item["severity"], 0) for item in findings]
    top = max(ranks)
    if top >= SEVERITY_RANK[Severity.HIGH.value]:
        return "high"
    if top >= SEVERITY_RANK[Severity.MEDIUM.value]:
        return "moderate"
    return "low"


def low_moisture_alert_reason(moisture: float) -> bool:
    """Shared threshold used by the alert service (single source of truth)."""
    return moisture <= LOW_MOISTURE_CRITICAL
