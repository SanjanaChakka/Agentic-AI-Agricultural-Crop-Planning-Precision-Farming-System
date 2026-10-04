"""Feature engineering shared by training and inference.

Keeping the exact same builder for both guarantees that the model can never be
fed a differently-ordered feature vector at request time.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from app.data.crop_catalog import CropRequirements, resolve_crop

SOIL_CLASSES = (
    "sandy",
    "sandy_loam",
    "loam",
    "silt_loam",
    "clay_loam",
    "clay",
    "black_soil",
    "red_soil",
    "red_laterite",
    "alluvial",
)
STAGE_INDEX = {
    "sowing": 0,
    "emergence": 1,
    "vegetative": 2,
    "flowering": 3,
    "fruiting": 4,
    "maturity": 5,
    "post_harvest": 6,
    "unknown": 2,
}

MOISTURE_FORECAST_FEATURES = [
    "soil_moisture_percent",
    "soil_moisture_change_3d",
    "soil_temperature_c",
    "air_temperature_c",
    "humidity_percent",
    "wind_speed_ms",
    "rainfall_7d_mm",
    "et0_7d_mm",
    "crop_stage_index",
    "soil_class_index",
    "latitude",
    "expected_rainfall_next_3d_mm",
]

RISK_FEATURES = [
    "temp_min_c",
    "temp_max_c",
    "temp_mean_c",
    "humidity_mean_percent",
    "humidity_min_percent",
    "wind_speed_ms",
    "rainfall_1d_mm",
    "rainfall_3d_mm",
    "rainfall_7d_mm",
    "wet_day_fraction_7d",
    "et0_7d_mm",
    "soil_moisture_percent",
    "soil_moisture_change_3d",
    "crop_stage_index",
    "soil_class_index",
    "latitude",
    # Crop-relative hazard margins. Without these the model cannot know how far
    # conditions are from the crop's own thresholds (heat ceiling, critical soil
    # moisture, humidity risk limit, heavy-rain limit).
    "heat_margin_c",
    "moisture_margin_percent",
    "humidity_margin_percent",
    "heavy_rain_margin_mm",
]

# Generic hazard thresholds used when the crop is unknown.
DEFAULT_HAZARD_THRESHOLDS = {
    "heat_stress_threshold_c": 35.0,
    "moisture_critical": 30.0,
    "humidity_risk_threshold_percent": 85.0,
    "heavy_rain_threshold_mm_3d": 50.0,
}


def hazard_thresholds(crop: str | None) -> dict[str, float]:
    """Crop-specific hazard thresholds, falling back to conservative defaults."""
    requirements = resolve_crop(crop)
    if requirements is None:
        return dict(DEFAULT_HAZARD_THRESHOLDS)
    return {
        "heat_stress_threshold_c": requirements.heat_stress_threshold_c,
        "moisture_critical": requirements.moisture_critical,
        "humidity_risk_threshold_percent": requirements.humidity_risk_threshold_percent,
        "heavy_rain_threshold_mm_3d": requirements.heavy_rain_threshold_mm_3d,
    }


def hazard_margins(
    *,
    crop: str | None,
    temp_max_c: float,
    soil_moisture_percent: float,
    humidity_mean_percent: float,
    rainfall_3d_mm: float,
) -> dict[str, float]:
    thresholds = hazard_thresholds(crop)
    return {
        "heat_margin_c": temp_max_c - thresholds["heat_stress_threshold_c"],
        "moisture_margin_percent": soil_moisture_percent - thresholds["moisture_critical"],
        "humidity_margin_percent": humidity_mean_percent - thresholds["humidity_risk_threshold_percent"],
        "heavy_rain_margin_mm": rainfall_3d_mm - thresholds["heavy_rain_threshold_mm_3d"],
    }


RISK_CLASSES = ("none", "low", "moderate", "high")


def soil_class_index(soil_type: str | None) -> float:
    key = (soil_type or "loam").strip().lower().replace(" ", "_").replace("-", "_")
    try:
        return float(SOIL_CLASSES.index(key))
    except ValueError:
        return float(SOIL_CLASSES.index("loam"))


def stage_index(crop_stage: str | None) -> float:
    return float(STAGE_INDEX.get((crop_stage or "unknown").strip().lower(), 2))


def _num(value: Any, default: float) -> float:
    if value is None:
        return default
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    if not np.isfinite(result):
        return default
    return result


def build_moisture_feature_vector(
    *,
    soil_moisture_percent: float | None,
    soil_moisture_change_3d: float | None = None,
    soil_temperature_c: float | None = None,
    air_temperature_c: float | None = None,
    humidity_percent: float | None = None,
    wind_speed_ms: float | None = None,
    rainfall_7d_mm: float | None = None,
    et0_7d_mm: float | None = None,
    crop_stage: str | None = None,
    soil_type: str | None = None,
    latitude: float | None = None,
    expected_rainfall_next_3d_mm: float | None = None,
) -> tuple[list[float], list[str]]:
    """Return ``(vector, missing_feature_names)``.

    Median-imputation is applied for missing features and every imputed field is
    reported so that the API can state that the prediction was made on
    partially-assumed inputs.
    """
    defaults = {
        "soil_moisture_percent": 30.0,
        "soil_moisture_change_3d": 0.0,
        "soil_temperature_c": 25.0,
        "air_temperature_c": 25.0,
        "humidity_percent": 65.0,
        "wind_speed_ms": 2.0,
        "rainfall_7d_mm": 5.0,
        "et0_7d_mm": 20.0,
        "crop_stage_index": 2.0,
        "soil_class_index": 4.0,
        "latitude": 17.0,
        "expected_rainfall_next_3d_mm": 0.0,
    }

    raw = {
        "soil_moisture_percent": soil_moisture_percent,
        "soil_moisture_change_3d": soil_moisture_change_3d,
        "soil_temperature_c": soil_temperature_c,
        "air_temperature_c": air_temperature_c,
        "humidity_percent": humidity_percent,
        "wind_speed_ms": wind_speed_ms,
        "rainfall_7d_mm": rainfall_7d_mm,
        "et0_7d_mm": et0_7d_mm,
        "crop_stage_index": None if crop_stage is None else stage_index(crop_stage),
        "soil_class_index": None if soil_type is None else soil_class_index(soil_type),
        "latitude": latitude,
        "expected_rainfall_next_3d_mm": expected_rainfall_next_3d_mm,
    }

    vector: list[float] = []
    missing: list[str] = []
    for name in MOISTURE_FORECAST_FEATURES:
        value = raw[name]
        if value is None:
            missing.append(name)
            vector.append(defaults[name])
        else:
            vector.append(_num(value, defaults[name]))
    return vector, missing


def build_risk_feature_vector(
    *,
    temp_min_c: float | None,
    temp_max_c: float | None,
    temp_mean_c: float | None = None,
    humidity_mean_percent: float | None,
    humidity_min_percent: float | None = None,
    wind_speed_ms: float | None = None,
    rainfall_1d_mm: float | None = None,
    rainfall_3d_mm: float | None = None,
    rainfall_7d_mm: float | None = None,
    wet_day_fraction_7d: float | None = None,
    et0_7d_mm: float | None = None,
    soil_moisture_percent: float | None = None,
    soil_moisture_change_3d: float | None = None,
    crop_stage: str | None = None,
    soil_type: str | None = None,
    latitude: float | None = None,
    crop: str | None = None,
) -> tuple[list[float], list[str]]:
    defaults = {
        "temp_min_c": 20.0,
        "temp_max_c": 32.0,
        "temp_mean_c": 26.0,
        "humidity_mean_percent": 70.0,
        "humidity_min_percent": 45.0,
        "wind_speed_ms": 2.0,
        "rainfall_1d_mm": 0.0,
        "rainfall_3d_mm": 2.0,
        "rainfall_7d_mm": 8.0,
        "wet_day_fraction_7d": 0.2,
        "et0_7d_mm": 20.0,
        "soil_moisture_percent": 35.0,
        "soil_moisture_change_3d": -1.0,
        "crop_stage_index": 2.0,
        "soil_class_index": 4.0,
        "latitude": 17.0,
        "heat_margin_c": -3.0,
        "moisture_margin_percent": 5.0,
        "humidity_margin_percent": -15.0,
        "heavy_rain_margin_mm": -48.0,
    }

    if temp_mean_c is None and temp_min_c is not None and temp_max_c is not None:
        temp_mean_c = (_num(temp_min_c, 20.0) + _num(temp_max_c, 32.0)) / 2.0

    margins = hazard_margins(
        crop=crop,
        temp_max_c=_num(temp_max_c, defaults["temp_max_c"]),
        soil_moisture_percent=_num(soil_moisture_percent, defaults["soil_moisture_percent"]),
        humidity_mean_percent=_num(humidity_mean_percent, defaults["humidity_mean_percent"]),
        rainfall_3d_mm=_num(rainfall_3d_mm, defaults["rainfall_3d_mm"]),
    )

    raw = {
        "temp_min_c": temp_min_c,
        "temp_max_c": temp_max_c,
        "temp_mean_c": temp_mean_c,
        "humidity_mean_percent": humidity_mean_percent,
        "humidity_min_percent": humidity_min_percent,
        "wind_speed_ms": wind_speed_ms,
        "rainfall_1d_mm": rainfall_1d_mm,
        "rainfall_3d_mm": rainfall_3d_mm,
        "rainfall_7d_mm": rainfall_7d_mm,
        "wet_day_fraction_7d": wet_day_fraction_7d,
        "et0_7d_mm": et0_7d_mm,
        "soil_moisture_percent": soil_moisture_percent,
        "soil_moisture_change_3d": soil_moisture_change_3d,
        "crop_stage_index": None if crop_stage is None else stage_index(crop_stage),
        "soil_class_index": None if soil_type is None else soil_class_index(soil_type),
        "latitude": latitude,
        **margins,
    }

    vector: list[float] = []
    missing: list[str] = []
    for name in RISK_FEATURES:
        value = raw[name]
        if value is None:
            missing.append(name)
            vector.append(defaults[name])
        else:
            vector.append(_num(value, defaults[name]))
    return vector, missing


def crop_moisture_defaults(crop: str | None) -> dict[str, float] | None:
    """Texture/crop-derived defaults used when a model input is missing."""
    requirements: CropRequirements | None = resolve_crop(crop)
    if requirements is None:
        return None
    low, high = requirements.moisture_optimal
    return {"critical_moisture_percent": requirements.moisture_critical, "optimal_low": low, "optimal_high": high}
