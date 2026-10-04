"""Sensor ingestion, simulation, trend and data-quality endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Query, status
from sqlalchemy import select

from app.api.deps import DbSession, FieldDep, PageDep, paginate
from app.core.errors import NotFoundError, UnprocessableEntityError
from app.models.farm import Field
from app.models.sensor import SensorReading
from app.schemas.sensor import (
    SensorReadingCreate,
    SensorReadingOut,
    SensorSimulationRequest,
    SensorSimulationResponse,
    SensorTrend,
    SensorTrendPoint,
)
from app.services import sensor_service

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
