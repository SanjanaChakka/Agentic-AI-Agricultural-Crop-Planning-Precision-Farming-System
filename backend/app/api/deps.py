"""Shared FastAPI dependencies.

``from __future__ import annotations`` is intentionally *not* used here: FastAPI
resolves ``Annotated[...]`` parameter annotations at runtime and nested
ForwardRefs inside ``Annotated`` cannot be evaluated from postponed strings.
"""

from collections.abc import Iterable, Iterator
from typing import Annotated, Any

from fastapi import Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import NotFoundError
from app.ml.registry import MLRegistry, get_ml_registry
from app.models.farm import Farm, Field
from app.rag.retriever import KnowledgeRetriever, get_retriever

DbSession = Annotated[Session, Depends(get_db)]


def get_retriever_dep() -> KnowledgeRetriever:
    return get_retriever()


def get_ml_registry_dep() -> MLRegistry:
    return get_ml_registry()


RetrieverDep = Annotated[KnowledgeRetriever, Depends(get_retriever_dep)]
MLRegistryDep = Annotated[MLRegistry, Depends(get_ml_registry_dep)]


def get_field(field_id: int, db: DbSession) -> Field:
    field = db.get(Field, field_id)
    if field is None:
        msg = f"Field {field_id} was not found"
        raise NotFoundError(msg)
    return field


def get_farm(farm_id: int, db: DbSession) -> Farm:
    farm = db.get(Farm, farm_id)
    if farm is None:
        msg = f"Farm {farm_id} was not found"
        raise NotFoundError(msg)
    return farm


FieldDep = Annotated[Field, Depends(get_field)]
FarmDep = Annotated[Farm, Depends(get_farm)]


class Pagination:
    def __init__(
        self,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> None:
        self.limit = limit
        self.offset = offset


PageDep = Annotated[Pagination, Depends(Pagination)]


def paginate(db: Session, statement, pagination: Pagination) -> tuple[list, int]:  # noqa: ANN001
    from sqlalchemy import func

    total = int(db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
    rows = list(db.scalars(statement.limit(pagination.limit).offset(pagination.offset)).all())
    return rows, total


def iter_rows(rows: Iterable[Any]) -> Iterator[Any]:
    yield from rows
