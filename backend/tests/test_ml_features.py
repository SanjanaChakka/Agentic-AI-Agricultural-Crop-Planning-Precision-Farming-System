"""Unit tests for ML feature assembly.

The models are only trustworthy if the vector they receive is the truth.  Two
properties matter:

* the vector width always matches the declared feature list, so a retrained
  model cannot silently receive a mis-shaped input;
* any value the caller could not supply is median-imputed *and reported*, never
  quietly replaced by a plausible-looking default.
"""

from __future__ import annotations

import math

import pytest

from app.data.crop_catalog import CROP_REQUIREMENTS
from app.ml import features

COTTON = CROP_REQUIREMENTS["cotton"]


COTTON = CROP_REQUIREMENTS["cotton"]


def _risk_vector(**overrides) -> tuple[list[float], list[str]]:  # noqa: ANN003
    base = {"temp_min_c": 21.0, "temp_max_c": 34.0, "humidity_mean_percent": 80.0}
    base.update(overrides)
    return features.build_risk_feature_vector(**base)


def test_moisture_vector_has_one_slot_per_declared_feature() -> None:
    vector, _ = features.build_moisture_feature_vector(soil_moisture_percent=30.0)

    assert len(vector) == len(features.MOISTURE_FORECAST_FEATURES)


def test_risk_vector_has_one_slot_per_declared_feature() -> None:
    vector, _ = _risk_vector()

    assert len(vector) == len(features.RISK_FEATURES)


def test_complete_moisture_input_imputes_nothing() -> None:
    vector, missing = features.build_moisture_feature_vector(
        soil_moisture_percent=30.0,
        soil_moisture_change_3d=-2.0,
        soil_temperature_c=25.0,
        air_temperature_c=29.0,
        humidity_percent=65.0,
        wind_speed_ms=2.0,
        rainfall_7d_mm=4.0,
        et0_7d_mm=20.0,
        crop_stage="flowering",
        soil_type="black_soil",
        latitude=16.2,
        expected_rainfall_next_3d_mm=6.0,
    )

    assert missing == []


def test_absent_features_are_reported_as_imputed() -> None:
    _, missing = features.build_moisture_feature_vector(soil_moisture_percent=30.0)

    assert set(missing) <= set(features.MOISTURE_FORECAST_FEATURES)
    assert "air_temperature_c" in missing


def test_supplied_measurements_are_not_imputed() -> None:
    _, missing = features.build_moisture_feature_vector(
        soil_moisture_percent=13.7,
        air_temperature_c=24.2,
        humidity_percent=79.0,
    )

    assert "soil_moisture_percent" not in missing
    assert "air_temperature_c" not in missing
    assert "humidity_percent" not in missing


def test_the_measured_value_reaches_the_vector_unchanged() -> None:
    vector, _ = features.build_moisture_feature_vector(soil_moisture_percent=13.69)
    index = features.MOISTURE_FORECAST_FEATURES.index("soil_moisture_percent")

    assert vector[index] == pytest.approx(13.69)


def test_nan_input_is_treated_as_missing_not_propagated() -> None:
    vector, missing = features.build_moisture_feature_vector(soil_moisture_percent=30.0, air_temperature_c=math.nan)

    assert "air_temperature_c" in missing
    assert all(math.isfinite(value) for value in vector)


def test_inf_input_is_treated_as_missing_not_propagated() -> None:
    vector, missing = features.build_moisture_feature_vector(
        soil_moisture_percent=30.0,
        humidity_percent=math.inf,
    )

    assert "humidity_percent" in missing
    assert all(math.isfinite(value) for value in vector)


def test_every_vector_slot_is_finite() -> None:
    for vector, _ in (
        features.build_moisture_feature_vector(soil_moisture_percent=None),
        features.build_moisture_feature_vector(soil_moisture_percent=30.0),
        _risk_vector(temp_max_c=None),
        _risk_vector(),
    ):
        assert all(math.isfinite(value) for value in vector), "NaN/inf would crash the estimator"


def test_risk_margins_are_signed_around_the_crop_threshold() -> None:
    hot_and_humid = _risk_vector(
        temp_max_c=COTTON.heat_stress_threshold_c + 6.0,
        humidity_mean_percent=COTTON.humidity_risk_threshold_percent + 12.0,
        soil_moisture_percent=COTTON.moisture_critical + 9.0,
        rainfall_3d_mm=0.0,
    )
    _, missing = hot_and_humid
    assert not [name for name in missing if name.endswith("_margin_c") or name.endswith("_margin_percent")]

    hot_vector, _ = _risk_vector(
        temp_max_c=COTTON.heat_stress_threshold_c + 6.0,
        humidity_mean_percent=COTTON.humidity_risk_threshold_percent + 12.0,
        soil_moisture_percent=COTTON.moisture_critical + 9.0,
        rainfall_3d_mm=0.0,
    )
    heat = hot_vector[features.RISK_FEATURES.index("heat_margin_c")]
    humidity = hot_vector[features.RISK_FEATURES.index("humidity_margin_percent")]

    assert heat > 0, "hotter than the crop threshold is a positive margin"
    assert humidity > 0, "wetter than the crop threshold is a positive margin"


def test_drier_than_the_threshold_produces_a_negative_humidity_margin() -> None:
    vector, _ = _risk_vector(humidity_mean_percent=COTTON.humidity_risk_threshold_percent - 20.0)

    assert vector[features.RISK_FEATURES.index("humidity_margin_percent")] < 0


def test_soil_class_index_maps_unknown_textures_safely() -> None:
    assert features.soil_class_index("black_soil") in range(len(features.SOIL_CLASSES))
    assert features.soil_class_index("not-a-soil") in range(len(features.SOIL_CLASSES))
    assert features.soil_class_index(None) in range(len(features.SOIL_CLASSES))


def test_stage_index_maps_unknown_stages_safely() -> None:
    assert isinstance(features.stage_index("flowering"), float)
    assert isinstance(features.stage_index("nonsense"), float)
    assert isinstance(features.stage_index(None), float)


def test_hazard_margins_are_signed_around_the_threshold() -> None:
    thresholds = features.hazard_thresholds("cotton")

    above = features.hazard_margins(
        crop="cotton",
        temp_max_c=thresholds["heat_stress_threshold_c"] + 5.0,
        soil_moisture_percent=thresholds["moisture_critical"] + 5.0,
        humidity_mean_percent=thresholds["humidity_risk_threshold_percent"] + 10.0,
        rainfall_3d_mm=0.0,
    )

    assert above["heat_margin_c"] > 0, "hotter than the threshold is a positive margin"
    assert above["humidity_margin_percent"] > 0, "wetter than the threshold is a positive margin"
    assert above["moisture_margin_percent"] > 0
    assert above["heavy_rain_margin_mm"] < 0


def test_hazard_margins_go_negative_below_the_threshold() -> None:
    thresholds = features.hazard_thresholds("cotton")

    below = features.hazard_margins(
        crop="cotton",
        temp_max_c=thresholds["heat_stress_threshold_c"] - 5.0,
        soil_moisture_percent=thresholds["moisture_critical"] - 5.0,
        humidity_mean_percent=thresholds["humidity_risk_threshold_percent"] - 10.0,
        rainfall_3d_mm=thresholds["heavy_rain_threshold_mm_3d"] + 10.0,
    )

    assert below["heat_margin_c"] < 0
    assert below["humidity_margin_percent"] < 0
    assert below["moisture_margin_percent"] < 0
    assert below["heavy_rain_margin_mm"] > 0


def test_crop_defaults_exist_only_for_known_crops() -> None:
    assert features.crop_moisture_defaults("cotton") is not None
    assert features.crop_moisture_defaults("unobtainium") is None


def test_risk_classes_are_ordered_from_none_to_high() -> None:
    assert features.RISK_CLASSES == ("none", "low", "moderate", "high")
