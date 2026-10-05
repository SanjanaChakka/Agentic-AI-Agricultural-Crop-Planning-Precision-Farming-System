"""Sensor ingestion, simulation, trend and data-quality endpoints."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.agents.base import run_coroutine
from app.api.deps import DbSession, FieldDep, PageDep, paginate
from app.core.errors import NotFoundError, UnprocessableEntityError
from app.models.farm import Field
from app.models.sensor import SensorReading
from app.schemas.sensor import (
    LiveSoilSyncRequest,
    LiveSoilSyncResponse,
    SensorReadingCreate,
    SensorReadingOut,
    SensorSimulationRequest,
    SensorSimulationResponse,
    SensorTrend,
    SensorTrendPoint,
)
from app.services import sensor_service, weather_service

router = APIRouter(tags=["sensors"])


@router.get("/sensors/readings", response_model=list[SensorReadingOut], summary="List sensor readings")
def list_readings(
    db: DbSession,
    page: PageDep,
    field_id: int | None = None,
    sensor_id: str | None = None,
    since: datetime | None = None,
) -> list[SensorReadingOut]:
    statement = select(SensorReading).order_by(SensorReading.recorded_at.desc(), SensorReading.id.desc())
    if field_id is not None:
        statement = statement.where(SensorReading.field_id == field_id)
    if sensor_id:
        statement = statement.where(SensorReading.sensor_id == sensor_id)
    if since is not None:
        statement = statement.where(SensorReading.recorded_at >= since)
    rows, _ = paginate(db, statement, page)
    return [SensorReadingOut.model_validate(row, from_attributes=True) for row in rows]


@router.post(
    "/sensors/readings",
    response_model=SensorReadingOut,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest a device reading",
)
def create_reading(payload: SensorReadingCreate, db: DbSession) -> SensorReadingOut:
    if payload.field_id is None:
        msg = "field_id is required to store a sensor reading"
        raise UnprocessableEntityError(msg)
    field = db.get(Field, payload.field_id)
    if field is None:
        msg = f"Field {payload.field_id} was not found"
        raise NotFoundError(msg)

    data = payload.model_dump(exclude={"field_id"})
    data["recorded_at"] = data.get("recorded_at") or datetime.now(UTC)
    reading = SensorReading(field_id=field.id, **data)
    previous = sensor_service.previous_reading(db, field.id, reading.sensor_id, reading.recorded_at)
    reading.quality_flags = sorted(
        set(
            sensor_service.quality_flags_for(
                moisture=reading.soil_moisture_percent,
                air_temp=reading.air_temperature_c,
                previous=previous,
                simulated=reading.is_simulated,
            )
        )
        | ({"simulated"} if reading.is_simulated else set())
    )
    db.add(reading)
    db.commit()
    db.refresh(reading)
    return SensorReadingOut.model_validate(reading, from_attributes=True)


@router.get("/sensors/fields/{field_id}/latest", response_model=SensorReadingOut | None, summary="Latest reading")
def latest_reading(field: FieldDep, db: DbSession, sensor_id: str | None = None) -> SensorReadingOut | None:
    reading = sensor_service.latest_reading(db, field.id, sensor_id)
    if reading is None:
        return None
    return SensorReadingOut.model_validate(reading, from_attributes=True)


@router.post(
    "/sensors/fields/{field_id}/simulate",
    response_model=SensorSimulationResponse,
    summary="Generate simulated telemetry (every row is flagged as simulated)",
)
def simulate(payload: SensorSimulationRequest, field: FieldDep, db: DbSession) -> SensorSimulationResponse:
    # The window is back-dated so the newest reading lands on "now". Work out the
    # same bounds the generator will use so overlapping telemetry can be detected
    # *before* anything is written.
    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    window_start = payload.start_at or (now - timedelta(hours=payload.hours))
    window_end = payload.start_at + timedelta(hours=payload.hours) if payload.start_at else now

    existing = sensor_service.simulated_readings_in_window(
        db, field.id, start=window_start, end=window_end, sensor_id=payload.sensor_id
    )
    if existing and not payload.replace_existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Field {field.id} already has {len(existing)} simulated reading(s) for sensor "
                f"'{payload.sensor_id}' between {window_start.isoformat()} and {window_end.isoformat()}. "
                "Generating again would stack a second, overlapping series and duplicate every timestamp. "
                "Resend with replace_existing=true to replace them."
            ),
        )
    removed = (
        sensor_service.delete_simulated_readings(
            db, field.id, start=window_start, end=window_end, sensor_id=payload.sensor_id
        )
        if existing
        else 0
    )

    readings = sensor_service.simulate_readings(
        db,
        field,
        hours=payload.hours,
        interval_hours=payload.interval_hours,
        sensor_id=payload.sensor_id,
        seed=payload.seed,
        start_at=payload.start_at,
        initial_soil_moisture_percent=payload.initial_soil_moisture_percent,
        rainfall_events=payload.rainfall_events,
        inject_fault=payload.inject_fault,
    )
    db.commit()
    outputs = [SensorReadingOut.model_validate(reading, from_attributes=True) for reading in readings]
    return SensorSimulationResponse(
        field_id=field.id,
        sensor_id=payload.sensor_id,
        readings_created=len(outputs),
        simulated=True,
        start_at=outputs[0].recorded_at if outputs else datetime.now(UTC),
        end_at=outputs[-1].recorded_at if outputs else datetime.now(UTC),
        readings=outputs,
        summary={
            "mean_soil_moisture_percent": _mean(reading.soil_moisture_percent for reading in readings),
            "min_soil_moisture_percent": _min(reading.soil_moisture_percent for reading in readings),
            "max_soil_moisture_percent": _max(reading.soil_moisture_percent for reading in readings),
            "mean_soil_temperature_c": _mean(reading.soil_temperature_c for reading in readings),
            "mean_air_temperature_c": _mean(reading.air_temperature_c for reading in readings),
            "mean_air_humidity_percent": _mean(reading.air_humidity_percent for reading in readings),
            "min_battery_percent": _min(reading.battery_percent for reading in readings),
            "replaced_readings": removed,
        },
    )


@router.post(
    "/sensors/fields/{field_id}/sync-live-soil",
    response_model=LiveSoilSyncResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest live soil telemetry for a field",
)
def sync_live_soil(payload: LiveSoilSyncRequest, field: FieldDep, db: DbSession) -> LiveSoilSyncResponse:
    """Pull live soil moisture and soil temperature for this field's coordinates.

    The values come from Open-Meteo's live soil-model layers. They are real
    provider data, but they describe the grid cell the field sits in rather than
    a probe in the soil, so the response and every stored row say so explicitly.
    """
    latitude = field.effective_latitude
    longitude = field.effective_longitude
    if latitude is None or longitude is None:
        msg = (
            "This field has no geolocation, so live soil telemetry cannot be requested. "
            "Add coordinates to the field or farm first."
        )
        raise UnprocessableEntityError(msg)

    try:
        points, source_label = run_coroutine(
            lambda: weather_service.fetch_soil_profile(latitude, longitude, days=payload.days)
        )
    except weather_service.WeatherProviderError as exc:
        reason = f"The live soil provider did not return usable data: {exc}"
        raise UnprocessableEntityError(reason) from exc

    readings, replaced, replaced_simulated, dropped_future = sensor_service.sync_live_soil_telemetry(
        db, field, points=points, source_label=source_label
    )
    db.commit()

    moisture = [r.soil_moisture_percent for r in readings if r.soil_moisture_percent is not None]
    temps = [r.soil_temperature_c for r in readings if r.soil_temperature_c is not None]
    outputs = sorted(readings, key=lambda r: r.recorded_at)
    return LiveSoilSyncResponse(
        field_id=field.id,
        sensor_id=sensor_service.live_soil_sensor_id(field.id),
        readings_created=len(outputs),
        replaced_readings=replaced,
        replaced_simulated_readings=replaced_simulated,
        dropped_future_hours=dropped_future,
        simulated=False,
        source=source_label,
        caveat=(
            "Live third-party soil model output for this field's coordinates. It is not a physical "
            "probe installed on the farm, so treat it as regional reference data rather than an "
            "on-farm measurement."
        ),
        start_at=outputs[0].recorded_at if outputs else datetime.now(UTC),
        end_at=outputs[-1].recorded_at if outputs else datetime.now(UTC),
        summary={
            "mean_soil_moisture_percent": _mean(moisture),
            "min_soil_moisture_percent": _min(moisture),
            "max_soil_moisture_percent": _max(moisture),
            "mean_soil_temperature_c": _mean(temps),
        },
    )


@router.get("/sensors/fields/{field_id}/trend", response_model=SensorTrend, summary="Telemetry trend and statistics")
def trend(
    field: FieldDep,
    db: DbSession,
    hours: int = Query(default=168, ge=1, le=2_160),
    sensor_id: str | None = None,
) -> SensorTrend:
    series, stats = sensor_service.trend(db, field.id, hours=hours, sensor_id=sensor_id)
    points = [
        SensorTrendPoint(
            recorded_at=reading.recorded_at,
            soil_moisture_percent=reading.soil_moisture_percent,
            soil_temperature_c=reading.soil_temperature_c,
            air_humidity_percent=reading.air_humidity_percent,
        )
        for reading in reversed(series)
    ]
    quality_issues = sum(
        1 for reading in series if [f for f in (reading.quality_flags or []) if f not in {"ok", "simulated"}]
    )
    latest = series[0] if series else None
    return SensorTrend(
        field_id=field.id,
        sensor_id=sensor_id,
        points=points,
        statistics=stats,
        quality_issue_count=quality_issues,
        latest_reading=(SensorReadingOut.model_validate(latest, from_attributes=True) if latest is not None else None),
    )


@router.get("/sensors/fields/{field_id}/quality", summary="Data-quality audit for the latest telemetry")
def quality(field: FieldDep, db: DbSession) -> dict[str, Any]:
    reading = sensor_service.latest_reading(db, field.id)
    if reading is None:
        return {"field_id": field.id, "available": False, "reason": "no readings stored for this field"}
    flags = list(reading.quality_flags or [])
    faults = [flag for flag in flags if flag not in {"ok", "simulated"}]
    return {
        "field_id": field.id,
        "available": True,
        "sensor_id": reading.sensor_id,
        "recorded_at": reading.recorded_at.isoformat(),
        "quality_flags": flags,
        "faults": faults,
        "is_simulated": reading.is_simulated,
        "verdict": "unreliable - verify against a manual probe" if faults else "usable",
        "note": (
            "Simulated telemetry is a method demonstration and must not be used for an operational decision."
            if reading.is_simulated
            else None
        ),
    }


def _mean(values) -> float | None:  # noqa: ANN001
    items = [value for value in values if value is not None]
    return round(sum(items) / len(items), 2) if items else None


def _min(values) -> float | None:  # noqa: ANN001
    items = [value for value in values if value is not None]
    return min(items) if items else None


def _max(values) -> float | None:  # noqa: ANN001
    items = [value for value in values if value is not None]
    return max(items) if items else None
