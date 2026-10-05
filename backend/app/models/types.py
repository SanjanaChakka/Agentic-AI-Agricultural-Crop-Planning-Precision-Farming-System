"""Shared SQLAlchemy column types.

The agent layer produces rich evidence payloads that occasionally contain
``datetime``/``Decimal``/NumPy scalars (e.g. a measurement timestamp inside an
evidence item).  The stock ``sqlalchemy.JSON`` type delegates to
``json.dumps`` and raises ``TypeError`` for those values, which would abort a
workflow halfway through.  ``JSONDict`` normalises the payload on the way into
the database while keeping the value readable by any JSON-aware client.
"""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from sqlalchemy import JSON
from sqlalchemy.types import TypeDecorator


def json_default(value: Any) -> Any:
    """Best-effort conversion of exotic Python values into JSON primitives."""
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    if isinstance(value, timedelta):
        return value.total_seconds()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, set | frozenset):
        return sorted(str(item) for item in value)
    if isinstance(value, bytes | bytearray):
        return value.decode("utf-8", errors="replace")
    # NumPy scalars and 0-d arrays expose .item()
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return item()
        except Exception:  # noqa: BLE001, S110 - a 0-d array that refuses .item() falls through
            pass
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        try:
            return dump(mode="json")
        except Exception:  # noqa: BLE001 - some models only support dump() without a mode
            return dump()
    if hasattr(value, "__dict__"):
        return {key: val for key, val in vars(value).items() if not key.startswith("_")}
    return str(value)


class JSONDict(TypeDecorator):
    """A ``JSON`` column that accepts datetimes, Decimals and NumPy scalars."""

    impl = JSON
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> Any:  # noqa: ARG002 - SQLAlchemy signature
        if value is None:
            return None
        return json.loads(json.dumps(value, default=json_default))


__all__ = ["JSONDict", "json_default"]
