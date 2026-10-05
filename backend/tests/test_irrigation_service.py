"""Unit tests for the irrigation safety gate.

The one behaviour that must never regress: irrigation is *always* advice that
requires a named human decision.  No code path may schedule water on its own,
simulated telemetry must be labelled, and a decision taken without a forecast
must still work rather than crashing.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from app.data.crop_catalog import CROP_REQUIREMENTS
from app.models.farm import Field
from app.models.sensor import SensorReading
from app.services import irrigation_service

COTTON = CROP_REQUIREMENTS["cotton"]


def _field(**overrides) -> Field:  # noqa: ANN003
    base = {
        "id": 1,
        "farm_id": 1,
        "name": "Test Plot",
        "area_ha": 2.0,
        "soil_type": "black_soil",
        "irrigation_source": "borewell",
        "water_availability": "moderate",
        "crop_stage": "flowering",
        "proposed_crop": "cotton",
    }
    base.update(overrides)
    return Field(**base)


def _reading(**overrides) -> SensorReading:  # noqa: ANN003
    base = {
        "id": 1,
        "field_id": 1,
        "sensor_id": "SM-01",
        "recorded_at": datetime.now(UTC),
        "soil_moisture_percent": 18.0,
        "soil_temperature_c": 26.0,
        "air_humidity_percent": 70.0,
        "air_temperature_c": 30.0,
        "is_simulated": True,
    }
    base.update(overrides)
    return SensorReading(**base)


def _evaluate(field: Field, reading: SensorReading | None = None, **kwargs: Any) -> dict:
    return irrigation_service.evaluate(
        field=field,
        requirements=COTTON,
        latest=reading,
        weather=None,
        ml_prediction=None,
        **kwargs,
    )


def _rules(result: dict) -> dict[str, dict]:
    return {rule["rule"]: rule for rule in result["rules_evaluated"]}


def test_assessment_is_never_pre_authorised() -> None:
    result = _evaluate(_field(), _reading())

    assert result["requires_human_authorisation"] is True


def test_dry_field_produces_a_depth_but_no_activity() -> None:
    result = _evaluate(_field(), _reading(soil_moisture_percent=12.0))

    assert result["recommendation"] in {"consider_irrigation", "review_required"}
    assert result["estimated_water_mm"] > 0
    assert result["estimated_volume_m3"] > 0
    assert "activities" not in result, "the service proposes; it never schedules"
    assert "status" not in result, "no activity state is created by the analysis"


def test_without_a_forecast_a_critical_deficit_is_held_for_review() -> None:
    """A critical deficit with no forecast is held, not committed.

    Below the critical threshold but with no forecast the service must not
    commit to watering; it escalates for a human instead.
    """
    result = _evaluate(_field(), _reading(soil_moisture_percent=12.0))

    assert "moisture_below_critical" in _rules(result)
    assert result["recommendation"] == "review_required"


def test_wet_field_is_told_not_to_irrigate() -> None:
    result = _evaluate(_field(), _reading(soil_moisture_percent=55.0))

    assert result["recommendation"] == "no_irrigation_needed"
    assert result["estimated_water_mm"] is None


def test_missing_forecast_still_produces_a_decision() -> None:
    """A field with no weather bundle used to raise UnboundLocalError here."""
    result = _evaluate(_field(), _reading(soil_moisture_percent=18.0))

    assert "forecast_available" in _rules(result)
    assert result["recommendation"] in {"consider_irrigation", "review_required"}


def test_missing_forecast_is_declared_as_a_limitation() -> None:
    result = _evaluate(_field(), _reading(soil_moisture_percent=18.0))

    rules = _rules(result)
    assert rules["forecast_available"]["outcome"] == "review"
    assert "cannot offset" in rules["forecast_available"]["detail"]


def test_absent_moisture_is_reported_as_insufficient_information() -> None:
    result = _evaluate(_field(), reading=None)

    assert result["recommendation"] == "insufficient_information"
    assert result["estimated_water_mm"] is None
    assert result["requires_human_authorisation"] is True
    assert "information_sufficiency" in _rules(result)


def test_simulated_telemetry_is_flagged_in_the_rule_trace() -> None:
    result = _evaluate(_field(), _reading(is_simulated=True))

    provenance = _rules(result).get("data_provenance", {})
    blob = " ".join(str(value) for value in provenance.values()).lower()
    assert "simulat" in blob, "a simulated probe must be visible in the decision trace"


def test_live_telemetry_is_not_flagged_as_simulated() -> None:
    result = _evaluate(_field(), _reading(is_simulated=False))

    provenance = _rules(result).get("data_provenance", {})
    blob = " ".join(str(value) for value in provenance.values()).lower()
    assert "simulat" not in blob


def test_urgency_is_a_declared_level() -> None:
    result = _evaluate(_field(), _reading(soil_moisture_percent=10.0))

    assert result["urgency"] in {"low", "medium", "high", "unknown"}


def test_every_assessment_carries_a_rationale() -> None:
    result = _evaluate(_field(), _reading(soil_moisture_percent=20.0))

    assert result["rationale"], "an irrigation proposal must explain itself"


def test_rainfall_thresholds_are_ordered() -> None:
    assert irrigation_service.SIGNIFICANT_RAIN_MM < irrigation_service.HEAVY_RAIN_MM
    assert irrigation_service.DECISION_HORIZON_HOURS > 0


def test_unknown_crop_stage_is_reported() -> None:
    result = _evaluate(_field(crop_stage=None), _reading(soil_moisture_percent=20.0))

    assert "crop_stage_known" in _rules(result)


@pytest.mark.parametrize("moisture", [5.0, 20.0, 45.0, 60.0])
def test_no_moisture_level_ever_pre_authorises_water(moisture: float) -> None:
    result = _evaluate(_field(), _reading(soil_moisture_percent=moisture))

    assert result["requires_human_authorisation"] is True
