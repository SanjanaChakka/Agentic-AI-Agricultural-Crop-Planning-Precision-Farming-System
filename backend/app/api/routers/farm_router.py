"""Farm and field registry endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession, FieldDep, PageDep, paginate
from app.core.errors import ConflictError, NotFoundError
from app.models.enums import AlertStatus, ApprovalStatus
from app.models.farm import Farm, Field
from app.models.operations import Alert
from app.models.sensor import SensorReading
from app.models.soil import SoilObservation
from app.models.workflow import ApprovalRequest, WorkflowRun
from app.schemas.farm import (
    FarmCreate,
    FarmOut,
    FarmOutWithFields,
    FarmSummary,
    FarmUpdate,
    FieldCreate,
    FieldOut,
    FieldUpdate,
)

router = APIRouter(tags=["farms & fields"])


def _field_out(field: Field) -> FieldOut:
    # ``effective_latitude``/``effective_longitude`` are properties on the ORM
    # model, so ``from_attributes`` picks them up automatically.
    return FieldOut.model_validate(field, from_attributes=True)


def _farm_out(db: DbSession, farm: Farm) -> FarmOut:
    fields = list(db.scalars(select(Field).where(Field.farm_id == farm.id)).all())
    payload = FarmOut.model_validate(farm, from_attributes=True).model_dump()
    payload["field_count"] = len(fields)
    payload["total_registered_area_ha"] = round(sum(f.area_ha for f in fields), 2)
    return FarmOut(**payload)


# ----------------------------------------------------------------------
# Farms
# ----------------------------------------------------------------------
@router.get("/farms", response_model=list[FarmOut], summary="List farms")
def list_farms(db: DbSession, page: PageDep, search: str | None = None) -> list[FarmOut]:
    statement = select(Farm).order_by(Farm.id)
    if search:
        pattern = f"%{search.strip()}%"
        statement = statement.where(Farm.name.ilike(pattern) | Farm.location_name.ilike(pattern))
    rows, _ = paginate(db, statement, page)
    return [_farm_out(db, farm) for farm in rows]


@router.post(
    "/farms",
    response_model=FarmOut,
    status_code=status.HTTP_201_CREATED,
    summary="Register a farm",
)
def create_farm(payload: FarmCreate, db: DbSession) -> FarmOut:
    farm = Farm(**payload.model_dump())
    db.add(farm)
    db.commit()
    db.refresh(farm)
    return _farm_out(db, farm)


@router.get("/farms/{farm_id}", response_model=FarmOutWithFields, summary="Get a farm with its fields")
def get_farm(farm_id: int, db: DbSession) -> FarmOutWithFields:
    farm = db.get(Farm, farm_id)
    if farm is None:
        msg = f"Farm {farm_id} was not found"
        raise NotFoundError(msg)
    base = _farm_out(db, farm)
    return FarmOutWithFields(
        **base.model_dump(),
        fields=[_field_out(field) for field in farm.fields],
    )


@router.patch("/farms/{farm_id}", response_model=FarmOut, summary="Update a farm")
def update_farm(farm_id: int, payload: FarmUpdate, db: DbSession) -> FarmOut:
    farm = db.get(Farm, farm_id)
    if farm is None:
        msg = f"Farm {farm_id} was not found"
        raise NotFoundError(msg)
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(farm, key, value)
    db.commit()
    db.refresh(farm)
    return _farm_out(db, farm)


@router.delete("/farms/{farm_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a farm and its fields")
def delete_farm(farm_id: int, db: DbSession) -> Response:
    farm = db.get(Farm, farm_id)
    if farm is None:
        msg = f"Farm {farm_id} was not found"
        raise NotFoundError(msg)
    db.delete(farm)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/farms/{farm_id}/summary", response_model=FarmSummary, summary="Dashboard summary for a farm")
def farm_summary(farm_id: int, db: DbSession) -> FarmSummary:
    farm = db.get(Farm, farm_id)
    if farm is None:
        msg = f"Farm {farm_id} was not found"
        raise NotFoundError(msg)

    field_ids = list(db.scalars(select(Field.id).where(Field.farm_id == farm_id)).all())
    fields_with_soil = 0
    fields_with_sensors = 0
    if field_ids:
        soil_fields = db.scalars(
            select(SoilObservation.field_id).where(SoilObservation.field_id.in_(field_ids)).distinct()
        ).all()
        sensor_fields = db.scalars(
            select(SensorReading.field_id).where(SensorReading.field_id.in_(field_ids)).distinct()
        ).all()
        fields_with_soil = len(set(soil_fields))
        fields_with_sensors = len(set(sensor_fields))

    open_alerts = int(
        db.scalar(
            select(func.count())
            .select_from(Alert)
            .where(Alert.farm_id == farm_id, Alert.status != AlertStatus.RESOLVED.value)
        )
        or 0
    )
    pending = int(
        db.scalar(
            select(func.count())
            .select_from(ApprovalRequest)
            .where(
                ApprovalRequest.field_id.in_(field_ids) if field_ids else False,
                ApprovalRequest.status == ApprovalStatus.PENDING.value,
            )
        )
        or 0
    )
    latest_run = db.scalars(
        select(WorkflowRun).where(WorkflowRun.farm_id == farm_id).order_by(WorkflowRun.id.desc())
    ).first()
    last_observation = (
        db.scalars(
            select(SoilObservation.observed_at)
            .where(SoilObservation.field_id.in_(field_ids))
            .order_by(SoilObservation.observed_at.desc())
        ).first()
        if field_ids
        else None
    )

    return FarmSummary(
        farm_id=farm.id,
        farm_name=farm.name,
        location_name=farm.location_name,
        field_count=len(field_ids),
        total_area_ha=farm.total_area_ha or 0.0,
        fields_with_soil_data=fields_with_soil,
        fields_with_sensors=fields_with_sensors,
        open_alert_count=open_alerts,
        pending_approval_count=pending,
        latest_workflow_status=latest_run.status if latest_run else None,
        last_observation_at=last_observation,
    )


# ----------------------------------------------------------------------
# Fields
# ----------------------------------------------------------------------
@router.get("/fields", response_model=list[FieldOut], summary="List fields")
def list_fields(
    db: DbSession,
    page: PageDep,
    farm_id: int | None = None,
    soil_type: str | None = None,
) -> list[FieldOut]:
    statement = select(Field).options(selectinload(Field.farm)).order_by(Field.id)
    if farm_id is not None:
        statement = statement.where(Field.farm_id == farm_id)
    if soil_type:
        statement = statement.where(Field.soil_type == soil_type)
    rows, _ = paginate(db, statement, page)
    return [_field_out(field) for field in rows]


@router.post(
    "/fields",
    response_model=FieldOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add a field to a farm",
)
def create_field(payload: FieldCreate, farm_id: int, db: DbSession) -> FieldOut:
    farm = db.get(Farm, farm_id)
    if farm is None:
        msg = f"Farm {farm_id} was not found"
        raise NotFoundError(msg)
    duplicate = db.scalar(select(Field).where(Field.farm_id == farm_id, Field.field_code == payload.field_code))
    if duplicate is not None:
        msg = f"Field code '{payload.field_code}' already exists on this farm"
        raise ConflictError(msg)

    field = Field(farm_id=farm_id, **payload.model_dump())
    db.add(field)
    db.commit()
    db.refresh(field)
    return _field_out(field)


@router.get("/fields/counts", response_model=dict[str, Any], summary="Field counts and totals")
def field_counts(db: DbSession, farm_id: int | None = None) -> dict[str, Any]:
    statement = select(Field)
    if farm_id is not None:
        statement = statement.where(Field.farm_id == farm_id)
    rows = list(db.scalars(statement).all())
    by_soil: dict[str, int] = {}
    for field in rows:
        by_soil[field.soil_type] = by_soil.get(field.soil_type, 0) + 1
    return {
        "field_count": len(rows),
        "total_area_ha": round(sum(field.area_ha for field in rows), 2),
        "by_soil_type": by_soil,
    }


@router.get("/fields/{field_id}", response_model=FieldOut, summary="Get a field")
def get_field_detail(field: FieldDep) -> FieldOut:
    return _field_out(field)


@router.patch("/fields/{field_id}", response_model=FieldOut, summary="Update a field")
def update_field(field_id: int, payload: FieldUpdate, db: DbSession) -> FieldOut:
    field = db.get(Field, field_id)
    if field is None:
        msg = f"Field {field_id} was not found"
        raise NotFoundError(msg)
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(field, key, value)
    db.commit()
    db.refresh(field)
    return _field_out(field)


@router.delete("/fields/{field_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a field")
def delete_field(field_id: int, db: DbSession) -> Response:
    field = db.get(Field, field_id)
    if field is None:
        msg = f"Field {field_id} was not found"
        raise NotFoundError(msg)
    db.delete(field)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
