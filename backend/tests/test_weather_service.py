"""Unit tests for the weather provider chain and its honesty guarantees.

The system's credibility rests on never presenting invented numbers as an API
result.  These tests pin that behaviour at the unit level: the offline branch is
the only source of simulated data and it must label itself wherever it is read.
"""

from __future__ import annotations

import pytest

from app.services import weather_service

API_SOURCES = {weather_service.PROVIDER_OPEN_METEO, weather_service.PROVIDER_OWM}
KNOWN_SOURCES = API_SOURCES | {weather_service.PROVIDER_OFFLINE}


def test_offline_bundle_is_labelled_simulated() -> None:
    bundle = weather_service._offline_bundle(16.2, 80.1, 7, reason="provider unreachable")

    assert bundle.source == weather_service.PROVIDER_OFFLINE
    assert bundle.is_simulated is True
    assert bundle.fallback_used is True
    assert any("simulat" in note.lower() or "offline" in note.lower() for note in bundle.notes)


def test_offline_bundle_never_claims_to_be_a_live_api_result() -> None:
    bundle = weather_service._offline_bundle(16.2, 80.1, 7, reason="provider unreachable")

    assert bundle.source not in API_SOURCES
    assert "open-meteo" not in bundle.provider.lower()
    assert "openweathermap" not in bundle.provider.lower()


def test_offline_bundle_produces_a_usable_number_of_days() -> None:
    bundle = weather_service._offline_bundle(16.2, 80.1, 7, reason="provider unreachable")

    assert len(bundle.daily) == 7
    assert all(day.forecast_date is not None for day in bundle.daily)


def test_feature_dict_of_a_missing_bundle_is_empty_not_defaulted() -> None:
    assert weather_service.feature_dict(None) == {}


def test_feature_dict_preserves_the_simulated_flag() -> None:
    bundle = weather_service._offline_bundle(16.2, 80.1, 7, reason="test")

    features = weather_service.feature_dict(bundle)

    assert features["available"] is True
    assert features["is_simulated"] is True
    assert features["source"] == weather_service.PROVIDER_OFFLINE


def test_feature_dict_round_trips_through_a_json_summary() -> None:
    bundle = weather_service._offline_bundle(16.2, 80.1, 7, reason="test")

    rebuilt = weather_service.bundle_from_summary(weather_service.feature_dict(bundle))

    assert rebuilt.source == bundle.source
    assert rebuilt.is_simulated is bundle.is_simulated
    assert len(rebuilt.daily) == len(bundle.daily)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, None), ("", None), ("12.5", 12.5), (7, 7.0), ("not-a-number", None)],
)
def test_safe_float_never_raises_on_junk_provider_payloads(value, expected) -> None:  # noqa: ANN001
    assert weather_service._safe_float(value) == expected


def test_kmh_to_ms_converts_and_passes_through_none() -> None:
    assert weather_service._kmh_to_ms(36.0) == pytest.approx(10.0)
    assert weather_service._kmh_to_ms(None) is None


def test_every_declared_provider_is_a_known_source() -> None:
    assert {weather_service.PROVIDER_OPEN_METEO, weather_service.PROVIDER_OWM} <= KNOWN_SOURCES
    assert weather_service.PROVIDER_OFFLINE not in API_SOURCES


def test_provider_error_is_a_distinct_exception() -> None:
    assert issubclass(weather_service.WeatherProviderError, Exception)
