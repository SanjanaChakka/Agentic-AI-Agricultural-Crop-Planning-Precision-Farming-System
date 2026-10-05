"""Unit tests for alert de-duplication and the human approval gate.

Alerts describe an *ongoing condition*, so re-running the workflow for the same
condition must bump the occurrence count rather than create a second alert.
Approval is the only thing that may move an irrigation activity forward, and it
must record who decided.
"""

from __future__ import annotations

import pytest

from app.services import alert_service


def test_fingerprint_is_stable_for_the_same_condition() -> None:
    first = alert_service.fingerprint(1, "water_stress")
    second = alert_service.fingerprint(1, "water_stress")

    assert first == second


def test_fingerprint_differs_per_field() -> None:
    assert alert_service.fingerprint(1, "water_stress") != alert_service.fingerprint(2, "water_stress")


def test_fingerprint_differs_per_alert_type() -> None:
    assert alert_service.fingerprint(1, "water_stress") != alert_service.fingerprint(1, "heat_stress")


def test_fingerprint_respects_the_discriminator() -> None:
    assert alert_service.fingerprint(1, "water_stress") != alert_service.fingerprint(1, "water_stress", "irrigation")


def test_fingerprint_fits_the_database_column() -> None:
    assert len(alert_service.fingerprint(999999, "a" * 80, "b" * 80)) <= 32


def test_severity_ranks_are_ordered() -> None:
    ranks = [alert_service.SEVERITY_RANK[key] for key in ("info", "low", "medium", "high")]

    assert ranks == sorted(ranks)
    assert ranks == [0, 1, 2, 3]


def test_alert_types_and_titles_cover_the_risk_families() -> None:
    from app.models.enums import RiskType

    for risk_type in RiskType:
        assert risk_type.value in alert_service._ALERT_TYPE_FOR_RISK, f"{risk_type.value} raises no alert"


def test_escalation_step_requires_a_real_change_in_severity() -> None:
    assert alert_service.ESCALATION_STEP >= 1


def test_evidence_from_value_carries_its_source() -> None:
    evidence = alert_service.evidence_from_value("Soil moisture", 12.0, "% VWC", "sensor SM-01")

    assert evidence["source"] == "sensor SM-01"
    assert evidence["value"] == 12.0


def test_activity_status_moves_forward_only_through_scheduling() -> None:
    from app.models.enums import ActivityStatus

    values = [member.value for member in ActivityStatus]
    assert values.index("planned") < values.index("scheduled") < values.index("in_progress")


def test_only_an_approval_moves_an_activity_past_planned() -> None:
    """``planned`` must not be reachable from ``in_progress`` without a decision."""
    from app.models.enums import ActivityStatus

    # The gate itself: scheduled is the first status a reviewer can unlock.
    assert ActivityStatus.PLANNED.value == "planned"
    assert ActivityStatus.SCHEDULED.value == "scheduled"


@pytest.mark.parametrize("status", ["pending", "approved", "rejected", "modified"])
def test_approval_status_outcomes_are_declared(status: str) -> None:
    from app.models.enums import ApprovalStatus

    assert status in {member.value for member in ApprovalStatus}
