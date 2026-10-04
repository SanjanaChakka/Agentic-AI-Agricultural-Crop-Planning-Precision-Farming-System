"""Unit tests for the soil analysis layer.

Two invariants are load-bearing for the whole system and are asserted here
directly rather than only through the API:

1. ``SoilObservation`` stores what a lab reported.  The AI layer may add an
   interpretation, but it must never write a number back onto the measurement.
2. Missing parameters are reported as missing rather than silently imputed.
"""

from __future__ import annotations

import pytest

from app.models.soil import SoilObservation
from app.services import soil_service

FULL_VALUES = {
    "ph": 6.5,
    "nitrogen_available_kg_ha": 180.0,
    "phosphorus_available_kg_ha": 18.0,
    "potassium_available_kg_ha": 190.0,
    "organic_carbon_percent": 0.7,
    "soil_moisture_percent": 42.0,
    "electrical_conductivity_ds_m": 0.4,
}


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (4.2, "strongly_acidic"),
        (5.6, "moderately_acidic"),
        (6.5, "neutral"),
        (7.4, "neutral"),
        (7.8, "moderately_alkaline"),
        (8.9, "strongly_alkaline"),
    ],
)
def test_ph_class_bands(value: float, expected: str) -> None:
    assert soil_service._ph_class(value) == expected


def test_ph_class_of_missing_measurement_is_not_guessed() -> None:
    assert soil_service._ph_class(None) == "unknown"
    assert soil_service._ph_class(None) != "neutral", "an absent pH is never reported as neutral"


def test_missing_parameters_lists_every_unreported_field() -> None:
    observation = SoilObservation(field_id=1, ph=6.5)

    missing = soil_service.missing_parameters(observation)

    assert "nitrogen_available_kg_ha" in missing
    assert "potassium_available_kg_ha" in missing
    assert "ph" not in missing


def test_missing_parameters_is_empty_for_a_complete_lab_report() -> None:
    observation = SoilObservation(field_id=1, **FULL_VALUES)

    assert soil_service.missing_parameters(observation) == []


def test_interpretation_does_not_write_back_onto_the_measurement() -> None:
    observation = SoilObservation(field_id=1, data_source="lab_test", **FULL_VALUES)
    before = {key: getattr(observation, key) for key in FULL_VALUES}

    soil_service.interpret_observation(observation, crop="cotton")

    after = {key: getattr(observation, key) for key in FULL_VALUES}
    assert after == before, "the interpretation must not mutate measured values"


def test_interpretation_reports_the_limitation_of_a_partial_sample() -> None:
    observation = SoilObservation(field_id=1, ph=6.5, data_source="lab_test")

    interpretation = soil_service.interpret_observation(observation, crop="cotton")

    assert interpretation.limitations, "a partial sample must declare its limitations"
    assert "nitrogen_available_kg_ha" in interpretation.missing_parameters
    assert observation.nitrogen_available_kg_ha is None, "absent nutrients stay absent"


def test_measured_evidence_only_carries_reported_values() -> None:
    observation = SoilObservation(field_id=1, ph=6.5, data_source="lab_test")

    evidence = soil_service.observation_evidence(observation)

    assert evidence, "a sample with a pH reading must produce evidence"
    assert all(item.kind == "measured" for item in evidence)
    assert all(item.value is not None for item in evidence)


def test_evidence_does_not_invent_values_for_missing_parameters() -> None:
    observation = SoilObservation(field_id=1, ph=6.5, data_source="lab_test")

    labels = " ".join(item.label.lower() for item in soil_service.observation_evidence(observation))

    assert "potassium" not in labels, "no potassium was measured, so none may be reported"


def test_thresholds_payload_is_serialisable_and_advisory() -> None:
    payload = soil_service.soil_thresholds_payload()

    assert "ph_classes" in payload
    assert "nitrogen_available_kg_ha" in payload
    assert payload["ph_classes"]["neutral"] == "neutral (pH 6.5-7.5)"
