"""Unit tests for the environmental risk layer's non-diagnostic guarantee.

The system may say "conditions favour X".  It may never say "X is present" or
"name a disease as confirmed".  That guarantee is asserted here at the unit
level so it cannot be quietly weakened by a refactor.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

import pytest

from app.data.crop_catalog import CROP_REQUIREMENTS
from app.models.farm import Field
from app.models.sensor import SensorReading
from app.services import risk_service

COTTON = CROP_REQUIREMENTS["cotton"]

FORBIDDEN = (
    "disease confirmed",
    "confirmed disease",
    "diagnosed with",
    "diagnosis of",
    "is diagnosed",
    "disease present",
    "infection confirmed",
    "positively identified",
)
NEGATION_CUES = ("not ", "no ", "never", "cannot", "n't", "without ")


def _claims_diagnosis(text: str) -> list[str]:
    """Forbidden phrases asserted rather than denied, mirroring the PDF check."""
    flat = " ".join(text.split()).lower()
    offenders: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+", flat):
        if any(cue in sentence for cue in NEGATION_CUES):
            continue
        offenders.extend(phrase for phrase in FORBIDDEN if phrase in sentence)
    return offenders


def _field(**overrides) -> Field:  # noqa: ANN003
    base = {
        "id": 1,
        "farm_id": 1,
        "name": "Test Plot",
        "area_ha": 2.0,
        "soil_type": "black_soil",
        "proposed_crop": "cotton",
        "crop_stage": "flowering",
    }
    base.update(overrides)
    return Field(**base)


def _reading(**overrides) -> SensorReading:  # noqa: ANN003
    base = {
        "id": 1,
        "field_id": 1,
        "sensor_id": "SM-01",
        "recorded_at": datetime.now(UTC),
        "soil_moisture_percent": 20.0,
        "soil_temperature_c": 26.0,
        "air_humidity_percent": 70.0,
        "air_temperature_c": 30.0,
        "is_simulated": True,
    }
    base.update(overrides)
    return SensorReading(**base)


def _scan(field: Field, reading: SensorReading | None = None, **kwargs: Any) -> dict:
    return risk_service.scan(
        field=field,
        requirements=COTTON,
        weather=None,
        latest=reading,
        trend_stats=None,
        **kwargs,
    )


def test_disclaimer_is_always_returned() -> None:
    result = _scan(_field(), _reading())

    assert result["disclaimer"]
    assert "no diagnostic capability" in result["disclaimer"].lower()


def test_disclaimer_is_returned_even_with_no_findings() -> None:
    result = _scan(_field(), _reading(soil_moisture_percent=50.0))

    assert result["disclaimer"]


def test_every_finding_is_flagged_as_not_a_diagnosis() -> None:
    result = _scan(_field(), _reading(soil_moisture_percent=12.0))

    assert result["findings"], "a critical deficit must raise a finding"
    assert all(item["is_diagnosis"] is False for item in result["findings"])


def test_findings_use_the_favourability_phrase() -> None:
    result = _scan(_field(), _reading(soil_moisture_percent=12.0))

    for finding in result["findings"]:
        assert finding["statement"].lower().startswith("environmental conditions favourable for")


def test_no_finding_asserts_a_disease() -> None:
    result = _scan(_field(), _reading(soil_moisture_percent=12.0))

    for finding in result["findings"]:
        assert not _claims_diagnosis(finding["statement"])
        assert not _claims_diagnosis(finding["potential_impact"])


def test_every_finding_tells_the_reader_what_to_check_next() -> None:
    result = _scan(_field(), _reading(soil_moisture_percent=12.0))

    for finding in result["findings"]:
        assert finding["recommended_investigation"]


def test_finding_severity_is_a_declared_level() -> None:
    result = _scan(_field(), _reading(soil_moisture_percent=12.0))

    for finding in result["findings"]:
        assert finding["severity"] in set(risk_service.SEVERITY_RANK)


def test_overall_level_is_the_worst_finding() -> None:
    result = _scan(_field(), _reading(soil_moisture_percent=12.0))

    if result["findings"]:
        worst = max(
            (finding["severity"] for finding in result["findings"]),
            key=lambda level: risk_service.SEVERITY_RANK[level],
        )
        assert result["risk_level"] == worst


def test_risk_level_is_none_without_findings() -> None:
    result = _scan(_field(), _reading(soil_moisture_percent=50.0))

    assert result["risk_level"] in {"none", "none_min"}


def test_no_reading_and_no_weather_still_returns_a_valid_payload() -> None:
    result = _scan(_field(), reading=None)

    assert result["risk_level"] in {"none", "none_min"}
    assert result["disclaimer"]


def test_severity_ranks_are_strictly_ordered() -> None:
    ranks = [risk_service.SEVERITY_RANK[key] for key in ("info", "low", "medium", "high")]

    assert ranks == sorted(ranks)
    assert len(set(ranks)) == len(ranks)


def test_low_moisture_alert_reason_uses_the_critical_threshold() -> None:
    assert risk_service.low_moisture_alert_reason(5.0) is True
    assert risk_service.low_moisture_alert_reason(55.0) is False


@pytest.mark.parametrize("moisture", [5.0, 12.0, 20.0, 35.0, 60.0])
def test_no_moisture_level_produces_a_diagnostic_claim(moisture: float) -> None:
    result = _scan(_field(), _reading(soil_moisture_percent=moisture))

    for finding in result["findings"]:
        assert not _claims_diagnosis(finding["statement"])
        assert finding["is_diagnosis"] is False
