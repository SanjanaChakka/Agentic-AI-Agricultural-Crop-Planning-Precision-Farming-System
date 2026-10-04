"""Weather endpoints.

Two shapes are offered:

* ``GET /weather/fields/{field_id}`` - live forecast for a registered field;
* ``GET /weather/lookup`` - ad-hoc lookup for any coordinate.

Every response carries ``source``, ``provider`` and ``is_simulated``.  When the
provider chain fails the response is an explicitly-labelled offline climatology
estimate and never pretends to be an API reading.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.agents.base import run_coroutine
from app.api.deps import DbSession, FieldDep, PageDep, paginate
from app.core.errors import UnprocessableEntityError
from app.core.logging import get_logger
from app.models.enums import SourceKind
from app.models.weather import WeatherSnapshot
from app.schemas.common import Evidence
from app.schemas.weather import WeatherBundle, WeatherQueryOut, WeatherSnapshotOut
from app.services import weather_service

logger = get_logger(__name__)
router = APIRouter(tags=["weather"])


@router.get("/weather/lookup", response_model=WeatherQueryOut, summary="Forecast for any coordinate")
def lookup(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    location_name: str | None = None,
    forecast_days: int = Query(default=7, ge=1, le=16),
) -> WeatherQueryOut:
    bundle = run_coroutine(
        lambda: weather_service.fetch_weather(latitude, longitude, days=forecast_days, location_name=location_name)
    )
    return WeatherQueryOut(
        latitude=latitude,
        longitude=longitude,
        location_name=location_name,
        forecast_days=forecast_days,
        bundle=bundle,
    )


@router.get("/weather/fields/{field_id}", response_model=WeatherBundle, summary="Forecast for a registered field")
def field_weather(field: FieldDep, days: int = Query(default=7, ge=1, le=16)) -> WeatherBundle:
    latitude = field.effective_latitude
    longitude = field.effective_longitude
    if latitude is None or longitude is None:
        msg = "This field has no geolocation, so no forecast can be requested. Add coordinates to the field or farm."
        raise UnprocessableEntityError(msg)
    return run_coroutine(
        lambda: weather_service.fetch_weather(
            latitude,
            longitude,
            days=days,
            location_name=field.farm.location_name if field.farm else None,
            field_id=field.id,
        )
    )


@router.get(
    "/weather/snapshots",
    response_model=list[WeatherSnapshotOut],
    summary="Persisted weather snapshots",
)
def snapshots(
    db: DbSession,
    page: PageDep,
    field_id: int | None = None,
    limit_days: int | None = Query(default=None, ge=1, le=60),
) -> list[WeatherSnapshotOut]:
    statement = select(WeatherSnapshot).order_by(WeatherSnapshot.id.desc())
    if field_id is not None:
        statement = statement.where(WeatherSnapshot.field_id == field_id)
    rows, _ = paginate(db, statement, page)
    result = [WeatherSnapshotOut.model_validate(row, from_attributes=True) for row in rows]
    if limit_days:
        seen: dict[str, int] = {}
        trimmed: list[WeatherSnapshotOut] = []
        for row in result:
            key = str(row.forecast_date or row.observed_at or "")
            if key and seen.get(key, 0) >= limit_days:
                continue
            seen[key] = seen.get(key, 0) + 1
            trimmed.append(row)
        return trimmed
    return result


@router.get("/weather/snapshots/{snapshot_id}", response_model=WeatherSnapshotOut, summary="One weather snapshot")
def snapshot(snapshot_id: int, db: DbSession) -> WeatherSnapshotOut:
    row = db.get(WeatherSnapshot, snapshot_id)
    if row is None:
        msg = f"Weather snapshot {snapshot_id} was not found"
        raise UnprocessableEntityError(msg)
    return WeatherSnapshotOut.model_validate(row, from_attributes=True)


@router.get("/weather/fields/{field_id}/evidence", summary="Provenance-tagged weather evidence")
def field_weather_evidence(field: FieldDep, days: int = Query(default=7, ge=1, le=16)) -> dict[str, Any]:
    latitude = field.effective_latitude
    longitude = field.effective_longitude
    if latitude is None or longitude is None:
        return {
            "field_id": field.id,
            "available": False,
            "evidence": [],
            "note": "No geolocation; no weather evidence could be produced.",
        }

    bundle = run_coroutine(
        lambda: weather_service.fetch_weather(
            latitude, longitude, days=days, location_name=field.farm.location_name if field.farm else None
        )
    )
    kind = SourceKind.SIMULATED if bundle.is_simulated else SourceKind.FORECAST
    evidence = [
        Evidence(
            label="Forecast maximum temperature",
            value=bundle.max_temp_c,
            unit="deg C",
            kind=kind,
            source=bundle.provider_display,
            note="Offline climatology estimate - not an API observation." if bundle.is_simulated else None,
        ),
        Evidence(
            label="Forecast minimum temperature",
            value=bundle.min_temp_c,
            unit="deg C",
            kind=kind,
            source=bundle.provider_display,
        ),
        Evidence(
            label="Rainfall next 3 days",
            value=bundle.rainfall_next_3_days_mm,
            unit="mm",
            kind=kind,
            source=bundle.provider_display,
        ),
        Evidence(
            label="Total precipitation over the forecast window",
            value=bundle.total_precipitation_mm,
            unit="mm",
            kind=kind,
            source=bundle.provider_display,
        ),
        Evidence(
            label="Reference evapotranspiration over the forecast window",
            value=bundle.total_et0_mm,
            unit="mm",
            kind=kind,
            source=bundle.provider_display,
        ),
        Evidence(
            label="Mean relative humidity",
            value=bundle.mean_humidity_percent,
            unit="%",
            kind=kind,
            source=bundle.provider_display,
        ),
    ]
    return {
        "field_id": field.id,
        "available": True,
        "source": bundle.source,
        "provider": bundle.provider,
        "is_simulated": bundle.is_simulated,
        "fallback_used": bundle.fallback_used,
        "notes": bundle.notes,
        "evidence": [item.model_dump() for item in evidence],
    }
