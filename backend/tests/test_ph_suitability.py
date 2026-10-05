"""Soil pH against a crop's retrieved reference range.

Covers the assignment scenario "soil pH outside configured crop range -> soil
limitation identified". The behaviour under test is the decision logic itself,
not the HTTP layer: the measured pH is judged against the crop's *retrieved*
optimum, and an unfavourable pH must both mark the factor limiting and be named
explicitly rather than being averaged away by the other factors.

Weather is deliberately left out of these assessments. That makes the overall
status `additional_information_required` for every case here, so the assertions
target the pH factor and the limiting-factor list - which is what the scenario
actually specifies - instead of a status string that would mostly be measuring
the absent weather bundle.
"""

from __future__ import annotations

import pytest

from app.data.crop_catalog import CROP_REQUIREMENTS
from app.models.farm import Field
from app.models.soil import SoilObservation
from app.schemas.analysis import FactorScore
from app.services import suitability_service
from app.services.suitability_service import evaluate

MAIZE = CROP_REQUIREMENTS["maize"]

FULL_SOIL = {
    "nitrogen_available_kg_ha": 180.0,
    "phosphorus_available_kg_ha": 18.0,
    "potassium_available_kg_ha": 190.0,
    "organic_carbon_percent": 0.7,
    "soil_moisture_percent": 42.0,
    "electrical_conductivity_ds_m": 0.4,
}


def _assess(ph: float | None) -> dict:
    field = Field(
        id=1,
        farm_id=1,
        field_code="FIELD-001",
        name="pH probe plot",
        area_ha=5.0,
        soil_type="loamy",
        proposed_crop="maize",
        water_availability="moderate",
    )
    observation = None if ph is None else SoilObservation(field_id=1, ph=ph, data_source="lab_test", **FULL_SOIL)
    return evaluate(
        field=field,
        crop_name="maize",
        requirements=MAIZE,
        soil=observation,
        weather=None,
        references=[],
    )


def _ph_factor(result: dict) -> FactorScore:
    return next(item for item in result["factor_scores"] if item.factor == "soil_ph")


def test_optimal_ph_is_favourable() -> None:
    factor = _ph_factor(_assess(6.5))
    assert factor.verdict == "favourable"


@pytest.mark.parametrize("ph", [4.2, 8.9])
def test_ph_outside_tolerable_range_is_a_limiting_factor(ph: float) -> None:
    """The assignment's pH scenario: the limitation must be named, not implied."""
    result = _assess(ph)

    factor = _ph_factor(result)
    assert factor.verdict == "unfavourable"
    assert factor.measured_value == ph
    assert "Soil pH" in result["limiting_factors"]


def test_out_of_range_ph_is_not_averaged_away() -> None:
    """A severe single-factor limitation must still move the weighted score."""
    ok = _assess(6.5)
    bad = _assess(8.9)

    assert bad["score"] < ok["score"]
    assert "Soil pH" not in ok["limiting_factors"]
    assert "Soil pH" in bad["limiting_factors"]


def test_measured_ph_is_never_rewritten() -> None:
    """The measured value must survive verbatim into the assessment and evidence."""
    result = _assess(4.2)

    assert _ph_factor(result).measured_value == 4.2
    assert any(item.get("value") == 4.2 for item in result["evidence"])


def test_reported_required_range_matches_the_retrieved_catalog() -> None:
    low, high = MAIZE.ph_optimal
    assert _ph_factor(_assess(6.5)).required_range == f"{low}-{high}"


def test_missing_ph_is_reported_as_missing_not_as_a_pass() -> None:
    result = _assess(None)

    factor = _ph_factor(result)
    assert factor.verdict == "unknown"
    assert factor.measured_value is None
    # Label casing differs between the two lists, so compare case-insensitively.
    assert any("ph" in item.lower() for item in result["missing_information"])


def test_band_score_tolerates_a_small_excursion() -> None:
    """Just inside tolerance scores partially rather than failing outright."""
    low, high = MAIZE.ph_optimal

    assert suitability_service._band_score(7.8, low, high, tolerance=1.5) not in (None, 0.0)
    assert suitability_service._band_score(9.5, low, high, tolerance=1.5) == 0.0
    assert suitability_service._band_score(None, low, high, tolerance=1.5) is None
