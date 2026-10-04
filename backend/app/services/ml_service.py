"""Single source of truth for the feature vectors fed to the trained models.

Both entry points must score a field on exactly the same evidence:

* ``ml_forecast_agent`` running inside a LangGraph workflow, and
* ``POST /api/v1/ml/predict`` called directly over HTTP.

When this assembly lived only inside the agent, the REST endpoint fell back to
median imputation for every soil and weather feature, so the classifier answered
from training medians instead of the field's real conditions - it reported
"risk severity: none" while the rule engine reported high water stress on the
very same field.  Centralising the assembly here keeps the two paths identical
and lets the derived series (mean temperature, minimum humidity, wet-day
fraction) be computed from the daily forecast rather than left as gaps.

Explicit values supplied by a caller always win; the field's own context fills
only what is missing, and the registry still reports whatever remained imputed.
"""

from __future__ import annotations

import math
from typing import Any

from app.models.farm import Field
from app.models.sensor import SensorReading

#: A day counts as "wet" for the wet-day fraction once it accumulates this much rain.
WET_DAY_RAINFALL_MM = 1.0


def weather_from_bundle(bundle: Any) -> dict[str, Any]:
    """Project a typed weather bundle onto the summary dict shape the feature builders expect.

    ``None`` (no geolocation / no forecast) yields an empty dict so builders
    fall back to their declared imputation defaults.
    """
    if bundle is None:
        return {}
    daily = [day.model_dump(mode="json") if hasattr(day, "model_dump") else dict(day) for day in (bundle.daily or [])]
    current = bundle.current.model_dump(mode="json") if getattr(bundle, "current", None) is not None else {}
    mean_temps = [row.get("temperature_mean_c") for row in daily if row.get("temperature_mean_c") is not None]
    humidities = [row.get("humidity_percent") for row in daily if row.get("humidity_percent") is not None]
    today = daily[0] if daily else {}
    return {
        "available": True,
        "source": bundle.source,
        "provider": bundle.provider,
        "is_simulated": bool(bundle.is_simulated),
        "current": current,
        "daily": daily,
        "total_precipitation_mm": bundle.total_precipitation_mm,
        "rainfall_next_3_days_mm": bundle.rainfall_next_3_days_mm,
        "max_temp_c": bundle.max_temp_c,
        "min_temp_c": bundle.min_temp_c,
        "mean_temp_c": round(sum(mean_temps) / len(mean_temps), 2) if mean_temps else None,
        "mean_humidity_percent": bundle.mean_humidity_percent,
        "min_humidity_percent": round(min(humidities), 2) if humidities else None,
        "total_et0_mm": bundle.total_et0_mm,
        "wind_speed_ms": current.get("wind_speed_ms"),
        "rainfall_today_mm": today.get("precipitation_mm"),
    }


def _as_float(value: Any) -> float | None:
    """Coerce to float, treating blanks and NaN as absent."""
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(result):  # NaN
        return None
    return result


def _daily_rows(weather: dict[str, Any]) -> list[dict[str, Any]]:
    rows = weather.get("daily") or []
    return [row for row in rows if isinstance(row, dict)]


def wet_day_fraction(weather: dict[str, Any]) -> float | None:
    """Fraction of the forecast window with measurable rain (>= 1 mm)."""
    daily = _daily_rows(weather)
    if not daily:
        return None
    wet = sum(1 for row in daily if (_as_float(row.get("precipitation_mm")) or 0.0) >= WET_DAY_RAINFALL_MM)
    return round(wet / len(daily), 3)


def mean_temperature(weather: dict[str, Any]) -> float | None:
    """Forecast-window mean temperature, from the bundle or the daily series."""
    direct = _as_float(weather.get("mean_temp_c"))
    if direct is not None:
        return direct

    current = weather.get("current") or {}
    daily = _daily_rows(weather)
    means = [m for m in (_as_float(row.get("temperature_mean_c")) for row in daily) if m is not None]
    if means:
        return round(sum(means) / len(means), 2)

    candidates = [
        value
        for value in (
            _as_float(current.get("temperature_c")),
            _as_float(weather.get("max_temp_c")),
            _as_float(weather.get("min_temp_c")),
        )
        if value is not None
    ]
    return round(sum(candidates) / len(candidates), 2) if candidates else None


def minimum_humidity(weather: dict[str, Any]) -> float | None:
    """Lowest forecast humidity - the value that drives foliar-disease favourability."""
    direct = _as_float(weather.get("min_humidity_percent"))
    if direct is not None:
        return direct

    daily = _daily_rows(weather)
    values = [h for h in (_as_float(row.get("humidity_percent")) for row in daily) if h is not None]
    if values:
        return round(min(values), 2)

    mean = _as_float(weather.get("mean_humidity_percent"))
    return round(mean, 2) if mean is not None else None


def _readings(
    latest: SensorReading | None,
    soil_state: dict[str, Any] | None,
) -> dict[str, Any]:
    """Flatten the newest sensor reading (with a soil-sample fallback)."""
    measured = (soil_state or {}).get("measured") or {}
    if latest is not None:
        return {
            "soil_moisture_percent": _as_float(latest.soil_moisture_percent),
            "soil_temperature_c": _as_float(latest.soil_temperature_c),
            "air_temperature_c": _as_float(latest.air_temperature_c),
            "humidity_percent": _as_float(latest.air_humidity_percent),
        }
    return {
        "soil_moisture_percent": _as_float(measured.get("soil_moisture_percent")),
        "soil_temperature_c": None,
        "air_temperature_c": None,
        "humidity_percent": None,
    }


def _apply(overrides: dict[str, Any], **resolved: Any) -> dict[str, Any]:
    """Fill gaps from field context; let explicit caller values override."""
    merged: dict[str, Any] = {}
    for key, value in resolved.items():
        supplied = overrides.get(key)
        merged[key] = supplied if supplied is not None else value
    return merged


def build_moisture_features(
    field: Field,
    *,
    weather: dict[str, Any] | None = None,
    latest: SensorReading | None = None,
    soil_state: dict[str, Any] | None = None,
    trend_stats: dict[str, Any] | None = None,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Features for the 7-day soil-moisture forecast regressor."""
    weather = weather or {}
    overrides = overrides or {}
    sensor = _readings(latest, soil_state)
    air_temp = (
        sensor["air_temperature_c"] if sensor["air_temperature_c"] is not None else _as_float(weather.get("max_temp_c"))
    )

    return _apply(
        overrides,
        soil_moisture_percent=sensor["soil_moisture_percent"],
        soil_moisture_change_3d=(trend_stats or {}).get("moisture_change_over_window"),
        soil_temperature_c=sensor["soil_temperature_c"],
        air_temperature_c=air_temp,
        humidity_percent=sensor["humidity_percent"]
        if sensor["humidity_percent"] is not None
        else _as_float(weather.get("mean_humidity_percent")),
        wind_speed_ms=_as_float((weather.get("current") or {}).get("wind_speed_ms"))
        or _as_float(weather.get("wind_speed_ms")),
        rainfall_7d_mm=_as_float(weather.get("total_precipitation_mm")),
        et0_7d_mm=_as_float(weather.get("total_et0_mm")),
        crop_stage=field.crop_stage,
        soil_type=field.soil_type,
        latitude=_as_float(field.effective_latitude),
        expected_rainfall_next_3d_mm=_as_float(weather.get("rainfall_next_3_days_mm")),
    )


def build_risk_features(
    field: Field,
    *,
    weather: dict[str, Any] | None = None,
    latest: SensorReading | None = None,
    soil_state: dict[str, Any] | None = None,
    trend_stats: dict[str, Any] | None = None,
    crop: str | None = None,
    requirements_name: str | None = None,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Features for the environmental risk-severity classifier.

    The keys mirror :func:`app.ml.features.build_risk_feature_vector` exactly so the
    classifier receives the same encoding it was trained on.
    """
    weather = weather or {}
    overrides = overrides or {}
    sensor = _readings(latest, soil_state)
    crop_name = (crop or requirements_name or field.proposed_crop or "").strip().lower()

    return _apply(
        overrides,
        temp_min_c=_as_float(weather.get("min_temp_c")),
        temp_max_c=_as_float(weather.get("max_temp_c")),
        temp_mean_c=mean_temperature(weather),
        humidity_mean_percent=sensor["humidity_percent"]
        if sensor["humidity_percent"] is not None
        else _as_float(weather.get("mean_humidity_percent")),
        humidity_min_percent=minimum_humidity(weather),
        wind_speed_ms=_as_float((weather.get("current") or {}).get("wind_speed_ms"))
        or _as_float(weather.get("wind_speed_ms")),
        rainfall_1d_mm=_as_float(weather.get("rainfall_today_mm")),
        rainfall_3d_mm=_as_float(weather.get("rainfall_next_3_days_mm")),
        rainfall_7d_mm=_as_float(weather.get("total_precipitation_mm")),
        wet_day_fraction_7d=wet_day_fraction(weather),
        et0_7d_mm=_as_float(weather.get("total_et0_mm")),
        soil_moisture_percent=sensor["soil_moisture_percent"],
        soil_moisture_change_3d=(trend_stats or {}).get("moisture_change_over_window"),
        crop_stage=field.crop_stage,
        soil_type=field.soil_type,
        latitude=_as_float(field.effective_latitude),
        crop=crop_name,
    )
