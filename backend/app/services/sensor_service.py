"""Sensor ingestion, simulation and trend analysis.

The simulator produces physically plausible telemetry (diurnal temperature and
humidity cycles, soil-moisture depletion driven by evapotranspiration, rainfall
recharge, measurement noise) so that the whole downstream workflow can be
demonstrated without physical hardware.  Simulated rows are permanently flagged
with ``is_simulated=True`` and a ``simulated`` quality marker so they can never
be confused with real measurements.

Live telemetry can also be ingested from a real third-party feed
(:func:`sync_live_soil_telemetry`).  Those rows carry ``is_simulated=False`` but
a ``third_party_model`` marker, because the values come from a soil model rather
than from a probe installed in the field.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.data.crop_catalog import resolve_soil_type
from app.models.enums import SourceKind
from app.models.farm import Field
from app.models.sensor import SensorReading
from app.schemas.common import Evidence

# Plausibility envelopes used for quality control.
MAX_PLAUSIBLE_AIR_TEMP_C = 55.0
MAX_PLAUSIBLE_SOIL_MOISTURE = 65.0  # %VWC - only paddy soils reach this
MAX_STEP_CHANGE = 25.0  # %VWC between consecutive readings

QUALITY_OK = "ok"


def quality_flags_for(
    *,
    moisture: float | None,
    air_temp: float | None,
    previous: SensorReading | None,
    simulated: bool,
) -> list[str]:
    """Return quality markers for a reading. Values are never modified."""
    flags: list[str] = []
    if simulated:
        flags.append("simulated")
    if moisture is None:
        flags.append("missing_soil_moisture")
    elif moisture > MAX_PLAUSIBLE_SOIL_MOISTURE:
        flags.append("soil_moisture_above_plausible_ceiling")
    if air_temp is not None and air_temp > MAX_PLAUSIBLE_AIR_TEMP_C:
        flags.append("implausible_air_temperature")
    if previous is not None and moisture is not None and previous.soil_moisture_percent is not None:
        if math.isclose(moisture, previous.soil_moisture_percent, abs_tol=0.001):
            flags.append("identical_to_previous_reading")
        elif abs(moisture - previous.soil_moisture_percent) > MAX_STEP_CHANGE:
            flags.append("implausible_step_change")
    return flags or [QUALITY_OK]


def previous_reading(db: Session, field_id: int, sensor_id: str, before: datetime) -> SensorReading | None:
    statement = (
        select(SensorReading)
        .where(
            SensorReading.field_id == field_id,
            SensorReading.sensor_id == sensor_id,
            SensorReading.recorded_at < before,
        )
        .order_by(SensorReading.recorded_at.desc())
    )
    return db.execute(statement).scalars().first()


def simulated_readings_in_window(
    db: Session, field_id: int, *, start: datetime, end: datetime, sensor_id: str | None = None
) -> list[SensorReading]:
    """Simulated rows already stored for ``field_id`` inside ``[start, end]``.

    Used to stop a second ``/simulate`` call from stacking an overlapping series
    on top of the first, which duplicates every timestamp in the window.
    """
    statement = select(SensorReading).where(
        SensorReading.field_id == field_id,
        SensorReading.is_simulated.is_(True),
        SensorReading.recorded_at >= start,
        SensorReading.recorded_at <= end,
    )
    if sensor_id:
        statement = statement.where(SensorReading.sensor_id == sensor_id)
    return list(db.execute(statement).scalars())


def delete_simulated_readings(
    db: Session, field_id: int, *, start: datetime, end: datetime, sensor_id: str | None = None
) -> int:
    """Delete simulated rows in a window. Returns the number removed.

    Real readings are never touched: only ``is_simulated`` rows are eligible.
    """
    statement = delete(SensorReading).where(
        SensorReading.field_id == field_id,
        SensorReading.is_simulated.is_(True),
        SensorReading.recorded_at >= start,
        SensorReading.recorded_at <= end,
    )
    if sensor_id:
        statement = statement.where(SensorReading.sensor_id == sensor_id)
    result = db.execute(statement)
    return int(result.rowcount or 0)


def latest_reading(db: Session, field_id: int, sensor_id: str | None = None) -> SensorReading | None:
    statement = select(SensorReading).where(SensorReading.field_id == field_id)
    if sensor_id:
        statement = statement.where(SensorReading.sensor_id == sensor_id)
    statement = statement.order_by(SensorReading.recorded_at.desc(), SensorReading.id.desc())
    return db.execute(statement).scalars().first()


def reading_evidence(reading: SensorReading) -> list[Evidence]:
    evidence: list[Evidence] = []
    kind = SourceKind.SIMULATED if reading.is_simulated else SourceKind.OBSERVED
    suffix = " (simulated)" if reading.is_simulated else ""
    if reading.soil_moisture_percent is not None:
        evidence.append(
            Evidence(
                label=f"Sensor soil moisture{suffix}",
                value=reading.soil_moisture_percent,
                unit="% VWC",
                kind=kind,
                source=f"sensor {reading.sensor_id}",
                observed_at=reading.recorded_at,
            )
        )
    if reading.soil_temperature_c is not None:
        evidence.append(
            Evidence(
                label=f"Sensor soil temperature{suffix}",
                value=reading.soil_temperature_c,
                unit="deg C",
                kind=kind,
                source=f"sensor {reading.sensor_id}",
                observed_at=reading.recorded_at,
            )
        )
    if reading.air_humidity_percent is not None:
        evidence.append(
            Evidence(
                label=f"Sensor air humidity{suffix}",
                value=reading.air_humidity_percent,
                unit="%",
                kind=kind,
                source=f"sensor {reading.sensor_id}",
                observed_at=reading.recorded_at,
            )
        )
    if reading.quality_flags and reading.quality_flags != [QUALITY_OK]:
        evidence.append(
            Evidence(
                label="Sensor quality flags",
                value=", ".join(reading.quality_flags),
                kind=SourceKind.OBSERVED,
                source=f"sensor {reading.sensor_id}",
                observed_at=reading.recorded_at,
            )
        )
    return evidence


LIVE_SOIL_SENSOR_PREFIX = "OM-SOIL"
LIVE_SOIL_QUALITY_FLAG = "third_party_model"


def live_soil_sensor_id(field_id: int) -> str:
    return f"{LIVE_SOIL_SENSOR_PREFIX}-{field_id}"


def sync_live_soil_telemetry(
    db: Session,
    field: Field,
    *,
    points: list[dict],
    source_label: str,
) -> tuple[list[SensorReading], int]:
    """Persist live third-party soil telemetry, replacing any earlier live rows.

    Rows are written with ``is_simulated=False`` so downstream agents treat them
    as real data, but they keep a ``third_party_model`` quality marker because
    they are model output for the field's coordinates, not an on-farm probe.

    Returns ``(stored, replaced_live, replaced_simulated, dropped_future)``.
    Earlier live rows for the same sensor are deleted first so repeated syncs
    cannot duplicate timestamps, and any *simulated* rows falling inside the live
    window are dropped so the field never ends up with two overlapping series.

    Provider "hourly soil" arrays mix past analysis with *forecast* hours. Those
    future hours are discarded: a sensor reading is an observation, and storing a
    forecast value as a measurement would misrepresent the evidence chain.
    """
    now = datetime.now(UTC)
    future = [point for point in points if point.get("recorded_at") and point["recorded_at"] > now]
    points = [point for point in points if point.get("recorded_at") and point["recorded_at"] <= now]
    dropped_future = len(future)
    if not points:
        return [], 0, 0, dropped_future

    sensor_id = live_soil_sensor_id(field.id)
    stamps = [point["recorded_at"] for point in points if point.get("recorded_at") is not None]
    replaced_live = 0
    replaced_simulated = 0
    if stamps:
        replaced_live = int(
            (
                db.execute(
                    delete(SensorReading).where(
                        SensorReading.field_id == field.id,
                        SensorReading.sensor_id == sensor_id,
                        SensorReading.is_simulated.is_(False),
                    )
                )
            ).rowcount
            or 0
        )
        replaced_simulated = int(
            (
                db.execute(
                    delete(SensorReading).where(
                        SensorReading.field_id == field.id,
                        SensorReading.is_simulated.is_(True),
                        SensorReading.recorded_at >= min(stamps),
                        SensorReading.recorded_at <= max(stamps),
                    )
                )
            ).rowcount
            or 0
        )

    stored: list[SensorReading] = []
    for point in points:
        reading = SensorReading(
            field_id=field.id,
            sensor_id=sensor_id,
            recorded_at=point["recorded_at"],
            soil_moisture_percent=point.get("soil_moisture_percent"),
            soil_temperature_c=point.get("soil_temperature_c"),
            air_humidity_percent=point.get("air_humidity_percent"),
            air_temperature_c=point.get("air_temperature_c"),
            battery_percent=None,
            is_simulated=False,
            quality_flags=[LIVE_SOIL_QUALITY_FLAG],
            notes=(
                f"Live {source_label}. Third-party soil model output for this field's coordinates; "
                "not a physical probe installed on the farm."
            ),
        )
        db.add(reading)
        stored.append(reading)
    db.flush()
    return stored, replaced_live, replaced_simulated, dropped_future


def simulate_readings(
    db: Session,
    field: Field,
    *,
    hours: int = 72,
    interval_hours: float = 3.0,
    sensor_id: str = "SM-01",
    seed: int | None = None,
    start_at: datetime | None = None,
    initial_soil_moisture_percent: float | None = None,
    rainfall_events: bool = True,
    inject_fault: bool = False,
) -> list[SensorReading]:
    """Generate and persist a realistic telemetry series for a field."""
    bands = resolve_soil_type(field.soil_type)
    theta_fc = bands["field_capacity"]
    theta_wp = bands["wilting_point"]

    # The series is back-dated so that the newest reading lands on "now": a
    # forward-dated series would report telemetry that has not happened yet and
    # would silently poison every "latest reading" lookup in the system.
    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    start = start_at or (now - timedelta(hours=hours))
    rng = np.random.default_rng(seed)
    if seed is None:
        seed = int(abs(hash((field.id, sensor_id, start.isoformat()))) % (10**9))

    step_hours = max(0.25, float(interval_hours))
    count = max(2, int(round(hours / step_hours)) + 1)

    # Climatological baseline so simulated data matches plausible local conditions.
    doy = start.timetuple().tm_yday
    seasonal = 26.0 + 5.0 * math.sin(2 * math.pi * (doy - 100) / 365.0)
    if rainfall_events and doy in range(180, 260):  # south-west monsoon window
        seasonal -= 2.0

    moisture = (
        float(initial_soil_moisture_percent)
        if initial_soil_moisture_percent is not None
        else float(np.clip(theta_fc * 0.92, theta_wp + 2.0, theta_fc + 3.0))
    )

    # A single modest rain event a third of the way through the window.
    rain_index = int(count * 0.35) if rainfall_events else -1
    rain_mm = float(rng.gamma(2.0, 9.0)) if rainfall_events else 0.0

    readings: list[SensorReading] = []
    for index in range(count):
        when = start + timedelta(hours=step_hours * index)
        hour_of_day = when.hour + when.minute / 60.0

        # Diurnal cycles: temperature peaks mid-afternoon, humidity inversely.
        temp_wave = math.sin((hour_of_day - 9.0) / 24.0 * 2 * math.pi)
        air_temp = seasonal + 5.2 * temp_wave + float(rng.normal(0.0, 0.7))
        humidity = float(np.clip(80.0 - 2.1 * (air_temp - 24.0) + float(rng.normal(0.0, 4.0)), 22.0, 99.0))
        # Soil temperature lags air temperature by roughly 2 hours and has less amplitude.
        soil_temp = seasonal + 3.4 * math.sin((hour_of_day - 11.0) / 24.0 * 2 * math.pi) + float(rng.normal(0.0, 0.5))

        # Soil moisture: depletion by ET, recharge by the rain event, then slow
        # drainage.
        #
        # ET is not a flat rate. Extraction falls off as the soil dries, because
        # a soil approaching wilting point cannot supply the atmosphere with the
        # same flux - the curve is linear down to the stress point and then goes
        # to zero at wilting point. Without that limit the series walks straight
        # through wilting point to the clipping floor, which reads as "catastrophic
        # water stress" for a field that is merely drying out.
        theta_rf = bands["refill_trigger"]
        recharge = min(rain_mm * 0.8, theta_fc + 4.0 - moisture) if index == rain_index and rain_mm > 0 else 0.0

        potential_et = 0.16 * step_hours * (0.6 + 0.12 * max(0.0, air_temp - 22.0)) * (1.6 if humidity < 55.0 else 1.0)
        # Fraction of the extractable (refill-trigger to wilting-point) band
        # still available, so extraction tapers to zero as the soil dries out.
        extractable = max(0.0, moisture - theta_wp)
        band = max(1e-6, theta_rf - theta_wp)
        stress_factor = min(1.0, extractable / band)
        et_loss = potential_et * (0.25 + 0.75 * stress_factor)

        moisture = moisture + recharge - et_loss
        if moisture > theta_fc + 4.0:
            moisture = theta_fc + 4.0 - (moisture - (theta_fc + 4.0)) * 0.3  # drainage
        # Hard physical bounds: a probe cannot read above field capacity plus
        # free water, and cannot read below wilting point.
        moisture = float(np.clip(moisture, theta_wp, theta_fc + 4.0)) + float(rng.normal(0.0, 0.35))
        moisture = float(np.clip(moisture, theta_wp, theta_fc + 4.0))

        air_temp_value = round(air_temp, 2)
        moisture_value = round(moisture, 2)

        flags_extra: list[str] = []
        if inject_fault and index == count - 2:
            # Freeze the reported value: a classic stuck-probe failure.
            flags_extra.append("identical_to_previous_reading")
            moisture_value = readings[-1].soil_moisture_percent if readings else moisture_value

        reading = SensorReading(
            field_id=field.id,
            sensor_id=sensor_id,
            recorded_at=when,
            soil_moisture_percent=moisture_value,
            soil_temperature_c=round(soil_temp, 2),
            air_humidity_percent=round(humidity, 2),
            air_temperature_c=air_temp_value,
            battery_percent=round(max(5.0, 100.0 - index * 0.12 - float(rng.uniform(0, 0.2))), 1),
            is_simulated=True,
            notes=(
                f"Simulated telemetry (seed={seed}, step={step_hours}h, climate baseline {seasonal:.1f} deg C)"
                + (f"; rain event {rain_mm:.1f} mm at index {rain_index}" if rain_mm else "")
                + ("; fault injected" if inject_fault else "")
            ),
        )
        reading.quality_flags = ["simulated", *flags_extra]
        db.add(reading)
        readings.append(reading)

    db.flush()
    for index, reading in enumerate(readings):
        flags = quality_flags_for(
            moisture=reading.soil_moisture_percent,
            air_temp=reading.air_temperature_c,
            previous=readings[index - 1] if index > 0 else None,
            simulated=reading.is_simulated,
        )
        reading.quality_flags = sorted(set(flags) | set(reading.quality_flags or []))
    return readings


def trend(
    db: Session, field_id: int, *, hours: int = 168, sensor_id: str | None = None
) -> tuple[list[SensorReading], dict]:
    """Return readings for the window plus summary statistics."""
    since = datetime.now(UTC) - timedelta(hours=hours)
    statement = select(SensorReading).where(SensorReading.field_id == field_id, SensorReading.recorded_at >= since)
    if sensor_id:
        statement = statement.where(SensorReading.sensor_id == sensor_id)
    statement = statement.order_by(SensorReading.recorded_at.asc())
    rows = list(db.execute(statement).scalars())

    moisture = [row.soil_moisture_percent for row in rows if row.soil_moisture_percent is not None]
    soil_temp = [row.soil_temperature_c for row in rows if row.soil_temperature_c is not None]
    humidity = [row.air_humidity_percent for row in rows if row.air_humidity_percent is not None]

    sum(1 for row in rows if row.quality_flags and [flag for flag in row.quality_flags if flag != "simulated"])

    stats = {
        "sample_count": len(rows),
        "moisture_mean": round(float(np.mean(moisture)), 2) if moisture else None,
        "moisture_min": round(float(np.min(moisture)), 2) if moisture else None,
        "moisture_max": round(float(np.max(moisture)), 2) if moisture else None,
        "moisture_change_over_window": round(moisture[-1] - moisture[0], 2) if len(moisture) > 1 else None,
        "soil_temperature_mean": round(float(np.mean(soil_temp)), 2) if soil_temp else None,
        "air_humidity_mean": round(float(np.mean(humidity)), 2) if humidity else None,
        "simulated_sample_count": sum(1 for row in rows if row.is_simulated),
    }
    return rows, stats


def require_field(db: Session, field_id: int) -> Field:
    field = db.get(Field, field_id)
    if field is None:
        raise NotFoundError(message=f"Field {field_id} was not found.")
    return field
