"""Weather integration with a resilient provider chain.

Provider order:

1. **OpenWeatherMap** - used when ``WEATHER_API_KEY`` is configured.
2. **Open-Meteo** - keyless public API, always attempted.  Provides current
   conditions, a daily forecast, precipitation probability and FAO reference
   evapotranspiration (ET0).
3. **Offline climatology** - a clearly-labelled deterministic estimate used only
   when every upstream call fails and ``ALLOW_OFFLINE_WEATHER_FALLBACK`` is on.

The offline path never masquerades as an API result: ``source`` becomes
``offline-climatology`` and ``is_simulated`` becomes ``True``, and the response
carries notes explaining why.  Callers can therefore always tell whether they
are looking at live data.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.weather import WeatherBundle, WeatherCurrentOut, WeatherDayOut

logger = get_logger(__name__)

PROVIDER_OPEN_METEO = "open-meteo"
PROVIDER_OWM = "openweathermap"
PROVIDER_OFFLINE = "offline-climatology"

WMO_WEATHER_CODES: dict[int, str] = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "depositing rime fog",
    51: "light drizzle",
    53: "moderate drizzle",
    55: "dense drizzle",
    61: "slight rain",
    63: "moderate rain",
    65: "heavy rain",
    71: "slight snow fall",
    73: "moderate snow fall",
    75: "heavy snow fall",
    77: "snow grains",
    80: "slight rain showers",
    81: "moderate rain showers",
    82: "violent rain showers",
    85: "slight snow showers",
    86: "heavy snow showers",
    95: "thunderstorm",
    96: "thunderstorm with slight hail",
    99: "thunderstorm with heavy hail",
}


class WeatherProviderError(Exception):
    """Raised inside the provider chain; converted to a bundle, not a 500."""


def _kmh_to_ms(value: float | None) -> float | None:
    return None if value is None else round(float(value) / 3.6, 2)


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _parse_epoch(value: Any) -> datetime | None:
    """OpenWeatherMap reports unix epoch seconds rather than ISO timestamps."""
    seconds = _safe_float(value)
    if seconds is None or seconds <= 0:
        return None
    try:
        return datetime.fromtimestamp(seconds, tz=UTC)
    except (OverflowError, OSError, ValueError):  # pragma: no cover - defensive
        return None


def _parse_iso(value: str | None, *, assume_tz: timezone = UTC) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=assume_tz)
    return parsed.astimezone(UTC)


# ---------------------------------------------------------------------------
# Open-Meteo (keyless)
# ---------------------------------------------------------------------------


async def _fetch_open_meteo(client: httpx.AsyncClient, lat: float, lon: float, days: int) -> WeatherBundle:
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": (
            "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,"
            "weather_code,wind_speed_10m,wind_direction_10m"
        ),
        "daily": (
            "temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,"
            "relative_humidity_2m_mean,relative_humidity_2m_min,wind_speed_10m_max,"
            "et0_fao_evapotranspiration,weather_code"
        ),
        "forecast_days": max(1, min(days, 16)),
        "timezone": "UTC",
    }
    response = await client.get(settings.open_meteo_base_url, params=params)
    if response.status_code != 200:
        msg = f"Open-Meteo returned HTTP {response.status_code}"
        raise WeatherProviderError(msg)
    payload = response.json()
    daily = payload.get("daily") or {}
    if not daily.get("time"):
        msg = "Open-Meteo response contained no daily forecast"
        raise WeatherProviderError(msg)

    current_raw = payload.get("current") or {}
    current = WeatherCurrentOut(
        observed_at=_parse_iso(current_raw.get("time")),
        temperature_c=_safe_float(current_raw.get("temperature_2m")),
        feels_like_c=_safe_float(current_raw.get("apparent_temperature")),
        humidity_percent=_safe_float(current_raw.get("relative_humidity_2m")),
        wind_speed_ms=_kmh_to_ms(_safe_float(current_raw.get("wind_speed_10m"))),
        wind_direction_deg=_safe_float(current_raw.get("wind_direction_10m")),
        condition=WMO_WEATHER_CODES.get(int(current_raw.get("weather_code", -1)), "unknown")
        if current_raw.get("weather_code") is not None
        else None,
    )

    days_out: list[WeatherDayOut] = []
    times: list[str] = list(daily.get("time") or [])
    for index, day in enumerate(times):
        forecast_date = _parse_iso(f"{day}T00:00:00")
        if forecast_date is None:
            continue
        t_max = _safe_float(_at(daily.get("temperature_2m_max"), index))
        t_min = _safe_float(_at(daily.get("temperature_2m_min"), index))
        days_out.append(
            WeatherDayOut(
                forecast_date=forecast_date,
                temp_min_c=t_min,
                temp_max_c=t_max,
                temperature_mean_c=round((t_min + t_max) / 2, 2) if t_min is not None and t_max is not None else None,
                precipitation_mm=_safe_float(_at(daily.get("precipitation_sum"), index)),
                precipitation_probability_percent=_safe_float(_at(daily.get("precipitation_probability_max"), index)),
                humidity_percent=_safe_float(_at(daily.get("relative_humidity_2m_mean"), index)),
                wind_speed_ms=_kmh_to_ms(_safe_float(_at(daily.get("wind_speed_10m_max"), index))),
                et0_mm=_safe_float(_at(daily.get("et0_fao_evapotranspiration"), index)),
                condition=WMO_WEATHER_CODES.get(int(code), "unknown")
                if (code := _at(daily.get("weather_code"), index)) is not None
                else None,
            )
        )

    return _finalise(
        days=days_out,
        current=current,
        source=PROVIDER_OPEN_METEO,
        provider="Open-Meteo (live API)",
        is_simulated=False,
        lat=lat,
        lon=lon,
        notes=["Live data retrieved from the Open-Meteo public forecast API."],
    )


# ---------------------------------------------------------------------------
# OpenWeatherMap (API key required)
# ---------------------------------------------------------------------------


async def _fetch_openweathermap(client: httpx.AsyncClient, lat: float, lon: float, days: int) -> WeatherBundle:
    api_key = settings.weather_api_key
    if not api_key:
        msg = "No OpenWeatherMap API key configured"
        raise WeatherProviderError(msg)

    current_resp = await client.get(
        f"{settings.weather_api_base_url}/weather",
        params={"lat": lat, "lon": lon, "units": "metric", "appid": api_key},
    )
    if current_resp.status_code != 200:
        msg = f"OpenWeatherMap current weather returned HTTP {current_resp.status_code}"
        raise WeatherProviderError(msg)
    current_payload = current_resp.json()

    forecast_resp = await client.get(
        f"{settings.weather_api_base_url}/forecast",
        params={"lat": lat, "lon": lon, "units": "metric", "appid": api_key},
    )
    if forecast_resp.status_code != 200:
        msg = f"OpenWeatherMap forecast returned HTTP {forecast_resp.status_code}"
        raise WeatherProviderError(msg)
    forecast_payload = forecast_resp.json()

    main = current_payload.get("main") or {}
    wind = current_payload.get("wind") or {}
    current = WeatherCurrentOut(
        observed_at=_parse_epoch(current_payload.get("dt")) or datetime.now(UTC),
        temperature_c=_safe_float(main.get("temp")),
        feels_like_c=_safe_float(main.get("feels_like")),
        humidity_percent=_safe_float(main.get("humidity")),
        wind_speed_ms=_safe_float(wind.get("speed")),
        wind_direction_deg=_safe_float(wind.get("deg")),
        condition=(current_payload.get("weather") or [{}])[0].get("description"),
    )

    buckets: dict[date, dict[str, list[float]]] = {}
    descriptions: dict[date, list[str]] = {}
    for entry in forecast_payload.get("list") or []:
        when = _parse_iso(entry.get("dt_txt"))
        if when is None:
            continue
        slot = buckets.setdefault(
            when.date(), {"tmin": [], "tmax": [], "rain": [], "humidity": [], "wind": [], "pop": []}
        )
        description = (entry.get("weather") or [{}])[0].get("description")
        if description:
            descriptions.setdefault(when.date(), []).append(description)
        entry_main = entry.get("main") or {}
        t_min = _safe_float(entry_main.get("temp_min"))
        t_max = _safe_float(entry_main.get("temp_max"))
        if t_min is not None:
            slot["tmin"].append(t_min)
        if t_max is not None:
            slot["tmax"].append(t_max)
        slot["rain"].append(float((entry.get("rain") or {}).get("3h", 0.0) or 0.0))
        if entry_main.get("humidity") is not None:
            slot["humidity"].append(float(entry_main["humidity"]))
        if (entry.get("wind") or {}).get("speed") is not None:
            slot["wind"].append(float(entry["wind"]["speed"]))
        slot["pop"].append(float(entry.get("pop", 0.0) or 0.0) * 100.0)

    days_out: list[WeatherDayOut] = []
    for day in sorted(buckets)[:days]:
        slot = buckets[day]
        t_min = round(min(slot["tmin"]), 2) if slot["tmin"] else None
        t_max = round(max(slot["tmax"]), 2) if slot["tmax"] else None
        days_out.append(
            WeatherDayOut(
                forecast_date=datetime(day.year, day.month, day.day, tzinfo=UTC),
                temp_min_c=t_min,
                temp_max_c=t_max,
                temperature_mean_c=round((t_min + t_max) / 2, 2) if t_min is not None and t_max is not None else None,
                precipitation_mm=round(sum(slot["rain"]), 2),
                precipitation_probability_percent=round(max(slot["pop"]), 1) if slot["pop"] else None,
                humidity_percent=round(sum(slot["humidity"]) / len(slot["humidity"]), 1) if slot["humidity"] else None,
                wind_speed_ms=round(max(slot["wind"]), 2) if slot["wind"] else None,
                et0_mm=_estimate_et0(t_min, t_max, lat, day),
                condition=_most_common(descriptions.get(day, [])),
            )
        )

    return _finalise(
        days=days_out,
        current=current,
        source=PROVIDER_OWM,
        provider="OpenWeatherMap (live API)",
        is_simulated=False,
        lat=lat,
        lon=lon,
        notes=["Live data retrieved from the OpenWeatherMap API using the configured WEATHER_API_KEY."],
    )


def _at(series: Sequence[float], index: int) -> Any:
    if series is None or index >= len(series):
        return None
    return series[index]


def _most_common(values: list[str]) -> str | None:
    """Most frequent description in a day - a fair summary of a 3-hourly API."""
    if not values:
        return None
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return max(counts.items(), key=lambda item: item[1])[0]


# ---------------------------------------------------------------------------
# Offline climatology fallback
# ---------------------------------------------------------------------------


def _offline_bundle(lat: float, lon: float, days: int, reason: str) -> WeatherBundle:
    """Deterministic month/latitude climatology, explicitly labelled simulated."""
    today = datetime.now(UTC).date()
    # Very rough monthly temperature climatology for the tropics/subtropics.
    mean_by_month = [24, 26, 29, 32, 33, 31, 29, 28, 28, 28, 26, 24]
    monsoon_by_month = [1, 2, 8, 22, 32, 38, 34, 30, 24, 12, 4, 1]
    # Humid month index shifts with latitude (monsoon arrives earlier near the equator).
    shift = int(max(0, min(3, (abs(lat) - 5) / 10)))

    days_out: list[WeatherDayOut] = []
    for offset in range(days):
        day = today + timedelta(days=offset)
        month_index = (day.month - 1 + shift) % 12
        base_temp = mean_by_month[month_index] - max(0.0, (abs(lat) - 20)) * 0.25
        diurnal = 9.0 if month_index in (3, 4, 9, 10) else 7.0
        rain = round(monsoon_by_month[month_index] / 31.0, 2)
        probability = min(95.0, round(rain * 22.0, 1))
        humidity = min(95.0, round(48.0 + rain * 4.0 + (18.0 if month_index in (6, 7, 8) else 0.0), 1))
        t_max = round(base_temp + diurnal / 2, 1)
        t_min = round(base_temp - diurnal / 2, 1)
        days_out.append(
            WeatherDayOut(
                forecast_date=datetime(day.year, day.month, day.day, tzinfo=UTC),
                temp_min_c=t_min,
                temp_max_c=t_max,
                temperature_mean_c=round(base_temp, 1),
                precipitation_mm=rain,
                precipitation_probability_percent=probability,
                humidity_percent=humidity,
                wind_speed_ms=round(3.0 + (2.0 if month_index in (3, 4, 5) else 0.0), 1),
                et0_mm=_estimate_et0(t_min, t_max, lat, day),
                condition="offline climatology estimate",
            )
        )

    current = WeatherCurrentOut(
        observed_at=datetime.now(UTC),
        temperature_c=days_out[0].temperature_mean_c if days_out else None,
        humidity_percent=days_out[0].humidity_percent if days_out else None,
        wind_speed_ms=days_out[0].wind_speed_ms if days_out else None,
        condition="offline climatology estimate",
    )

    return _finalise(
        days=days_out,
        current=current,
        source=PROVIDER_OFFLINE,
        provider="Offline climatology estimate (NOT a live observation)",
        is_simulated=True,
        lat=lat,
        lon=lon,
        notes=[
            f"SIMULATED DATA - every live weather provider failed: {reason}",
            "Values are a coarse monthly climatology estimate for this latitude and must not be used "
            "for operational decisions. Retry later or configure WEATHER_API_KEY.",
        ],
        fallback_used=True,
    )


def _estimate_et0(t_min: float | None, t_max: float | None, lat: float, day: date) -> float | None:
    """FAO-56 Hargreaves estimate used when a provider does not supply ET0."""
    if t_min is None or t_max is None:
        return None
    phi = math.radians(lat)
    doy = day.timetuple().tm_yday
    dr = 1 + 0.033 * math.cos(2 * math.pi * doy / 365)
    decl = 0.409 * math.sin(2 * math.pi * doy / 365 - 1.39)
    arg = max(-1.0, min(1.0, -math.tan(phi) * math.tan(decl)))
    ws = math.acos(arg)
    ra = (
        (24 * 60 / math.pi)
        * 0.0820
        * dr
        * (ws * math.sin(phi) * math.sin(decl) + math.cos(phi) * math.cos(decl) * math.sin(ws))
    )
    tmean = (t_min + t_max) / 2.0
    return round(max(0.0, 0.0023 * (tmean + 17.8) * math.sqrt(max(0.0, t_max - t_min)) * ra), 2)


# ---------------------------------------------------------------------------
# Aggregation + public entry point
# ---------------------------------------------------------------------------


def _finalise(
    *,
    days: list[WeatherDayOut],
    current: WeatherCurrentOut | None,
    source: str,
    provider: str,
    is_simulated: bool,
    lat: float,
    lon: float,
    notes: list[str],
    fallback_used: bool = False,
) -> WeatherBundle:
    total_rain = round(sum(day.precipitation_mm or 0.0 for day in days), 2)
    rain_3d = round(sum(day.precipitation_mm or 0.0 for day in days[:3]), 2)
    max_temp = (
        round(max((day.temp_max_c for day in days if day.temp_max_c is not None), default=0) or 0, 2)
        if any(day.temp_max_c is not None for day in days)
        else None
    )
    min_temp = (
        round(min(day.temp_min_c for day in days if day.temp_min_c is not None), 2)
        if any(day.temp_min_c is not None for day in days)
        else None
    )
    humidity_values = [day.humidity_percent for day in days if day.humidity_percent is not None]
    et0_values = [day.et0_mm for day in days if day.et0_mm is not None]

    return WeatherBundle(
        latitude=lat,
        longitude=lon,
        source=source,
        provider=provider,
        is_simulated=is_simulated,
        fetched_at=datetime.now(UTC),
        current=current,
        daily=days,
        total_precipitation_mm=total_rain,
        rainfall_next_3_days_mm=rain_3d,
        max_temp_c=max_temp,
        min_temp_c=min_temp,
        mean_humidity_percent=round(sum(humidity_values) / len(humidity_values), 1) if humidity_values else None,
        total_et0_mm=round(sum(et0_values), 2) if et0_values else 0.0,
        notes=notes,
        fallback_used=fallback_used,
    )


async def fetch_weather(
    latitude: float,
    longitude: float,
    *,
    days: int | None = None,
    location_name: str | None = None,
    field_id: int | None = None,
) -> WeatherBundle:
    """Fetch weather through the provider chain, never raising for provider faults."""
    days = days or settings.weather_forecast_days
    errors: list[str] = []

    try:
        timeout = httpx.Timeout(settings.weather_timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            if settings.weather_api_key:
                try:
                    bundle = await _fetch_openweathermap(client, latitude, longitude, days)
                    bundle.field_id = field_id
                    bundle.location_name = location_name
                    return bundle
                except (httpx.HTTPError, WeatherProviderError, KeyError, ValueError) as exc:
                    errors.append(f"openweathermap: {exc}")
                    logger.warning("OpenWeatherMap failed, falling back: %s", exc)

            try:
                bundle = await _fetch_open_meteo(client, latitude, longitude, days)
                bundle.field_id = field_id
                bundle.location_name = location_name
                if errors:
                    bundle.notes.extend(errors)
                return bundle
            except (httpx.HTTPError, WeatherProviderError, KeyError, ValueError) as exc:
                errors.append(f"open-meteo: {exc}")
                logger.warning("Open-Meteo failed: %s", exc)
    except httpx.HTTPError as exc:
        errors.append(f"transport: {exc}")
        logger.warning("Weather transport failure: %s", exc)

    if not settings.allow_offline_weather_fallback:
        raise WeatherProviderError("; ".join(errors) or "no weather provider available")

    bundle = _offline_bundle(latitude, longitude, days, "; ".join(errors) or "no provider responded")
    bundle.field_id = field_id
    bundle.location_name = location_name
    return bundle


async def fetch_soil_profile(
    latitude: float,
    longitude: float,
    *,
    days: int = 2,
) -> tuple[list[dict[str, Any]], str]:
    """Fetch live Open-Meteo soil moisture and soil temperature layers.

    Returns ``(hourly_points, source_label)``. Each point carries
    ``recorded_at``, ``soil_moisture_percent`` (root-zone mean of the 0-7 cm and
    7-28 cm layers, converted from m3/m3 to % VWC), ``soil_temperature_c`` and
    ``air_temperature_c``.

    This is a genuine live third-party feed, but it is a *soil model*, not a
    probe installed in the field, so callers must label it as such rather than
    claiming an on-farm measurement. Raises :class:`WeatherProviderError` if the
    provider does not answer with usable soil layers.
    """
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": (
            "soil_moisture_0_to_7cm,soil_moisture_7_to_28cm,soil_temperature_6cm,"
            "soil_temperature_18cm,temperature_2m,relative_humidity_2m"
        ),
        "forecast_days": max(1, min(days, 7)),
        "timezone": "UTC",
    }
    timeout = httpx.Timeout(settings.weather_timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        response = await client.get(settings.open_meteo_base_url, params=params)
    if response.status_code != 200:
        msg = f"Open-Meteo returned HTTP {response.status_code} for the soil profile request"
        raise WeatherProviderError(msg)

    hourly = (response.json() or {}).get("hourly") or {}
    times = hourly.get("time") or []
    if not times:
        msg = "Open-Meteo response contained no hourly soil layers"
        raise WeatherProviderError(msg)

    shallow = hourly.get("soil_moisture_0_to_7cm") or []
    root = hourly.get("soil_moisture_7_to_28cm") or []
    deep = hourly.get("soil_moisture_28_to_100cm") or []
    st_shallow = hourly.get("soil_temperature_6cm") or []
    st_deep = hourly.get("soil_temperature_18cm") or []
    air = hourly.get("temperature_2m") or []
    humidity = hourly.get("relative_humidity_2m") or []

    points: list[dict[str, Any]] = []
    for index, stamp in enumerate(times):
        recorded_at = _parse_iso(stamp)
        if recorded_at is None:
            continue

        # Root-zone proxy: average whichever soil moisture layers are present.
        # Open-Meteo reports m3/m3; %VWC is that value * 100.
        layers = [
            _safe_float(series[index]) * 100.0
            for series in (shallow, root, deep)
            if index < len(series) and series[index] is not None
        ]
        temps = [
            _safe_float(series[index])
            for series in (st_shallow, st_deep)
            if index < len(series) and series[index] is not None
        ]
        if not layers and not temps:
            continue

        points.append(
            {
                "recorded_at": recorded_at,
                "soil_moisture_percent": round(sum(layers) / len(layers), 2) if layers else None,
                "soil_temperature_c": round(sum(temps) / len(temps), 2) if temps else None,
                "air_temperature_c": _safe_float(air[index]) if index < len(air) else None,
                "air_humidity_percent": _safe_float(humidity[index]) if index < len(humidity) else None,
            }
        )

    if not points:
        msg = "Open-Meteo returned soil layers with no usable values"
        raise WeatherProviderError(msg)
    return points, "Open-Meteo soil model (live API)"


def feature_dict(bundle: WeatherBundle | None) -> dict:
    """The plain-dict weather shape every analysis service consumes.

    ``WeatherClimateAgent`` publishes exactly this mapping into the workflow
    state; rebuilding it here means a REST endpoint and the agent score a field
    from identical evidence instead of one of them falling back to defaults.
    """
    if bundle is None:
        return {}
    return {
        "available": True,
        "source": bundle.source,
        "provider": bundle.provider,
        "is_simulated": bundle.is_simulated,
        "fallback_used": bundle.fallback_used,
        "fetched_at": bundle.fetched_at.isoformat(),
        "location_name": bundle.location_name,
        "latitude": bundle.latitude,
        "longitude": bundle.longitude,
        "current": bundle.current.model_dump(mode="json") if bundle.current else None,
        "daily": [day.model_dump(mode="json") for day in bundle.daily],
        "total_precipitation_mm": bundle.total_precipitation_mm,
        "rainfall_today_mm": bundle.daily[0].precipitation_mm if bundle.daily else None,
        "rainfall_next_3_days_mm": bundle.rainfall_next_3_days_mm,
        "max_temp_c": bundle.max_temp_c,
        "min_temp_c": bundle.min_temp_c,
        "mean_humidity_percent": bundle.mean_humidity_percent,
        "min_humidity_percent": min(
            (day.humidity_percent for day in bundle.daily if day.humidity_percent is not None),
            default=bundle.mean_humidity_percent,
        ),
        "wind_speed_ms": bundle.current.wind_speed_ms if bundle.current else None,
        "total_et0_mm": bundle.total_et0_mm,
        "notes": bundle.notes,
    }


def bundle_from_summary(summary: dict) -> WeatherBundle:
    """Rebuild a typed :class:`WeatherBundle` from a JSON-serialised summary.

    The workflow state must stay JSON-serialisable so it can be persisted in
    ``workflow_runs.state``; the analysis services, however, want the typed
    model.  This function is the only bridge between the two.
    """
    current_payload = summary.get("current") or None
    return WeatherBundle(
        field_id=summary.get("field_id"),
        location_name=summary.get("location_name"),
        latitude=summary.get("latitude"),
        longitude=summary.get("longitude"),
        source=str(summary.get("source") or "unknown"),
        provider=str(summary.get("provider") or "unknown"),
        is_simulated=bool(summary.get("is_simulated")),
        fetched_at=_parse_iso(summary.get("fetched_at")) or datetime.now(UTC),
        current=WeatherCurrentOut(**current_payload) if current_payload else None,
        daily=[WeatherDayOut(**day) for day in summary.get("daily") or []],
        total_precipitation_mm=float(summary.get("total_precipitation_mm") or 0.0),
        rainfall_next_3_days_mm=float(summary.get("rainfall_next_3_days_mm") or 0.0),
        max_temp_c=summary.get("max_temp_c"),
        min_temp_c=summary.get("min_temp_c"),
        mean_humidity_percent=summary.get("mean_humidity_percent"),
        total_et0_mm=float(summary.get("total_et0_mm") or 0.0),
        notes=list(summary.get("notes") or []),
        fallback_used=bool(summary.get("fallback_used")),
    )
