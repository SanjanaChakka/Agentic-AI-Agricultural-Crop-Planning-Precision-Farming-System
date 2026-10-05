"""Alert generation with de-duplication.

Alerts are keyed by a ``fingerprint`` that describes *what* is happening, not
how many times the scan ran.  Re-running a scan while the same condition persists
updates the existing open alert (bumping ``occurrence_count`` and
``last_observed_at``) instead of creating a duplicate.  A new alert is raised
only when the fingerprint is new, or when the severity materially escalates.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.enums import AlertStatus, SourceKind
from app.models.farm import Farm, Field
from app.models.operations import Alert

logger = get_logger(__name__)

SEVERITY_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3}
ESCALATION_STEP = 1  # severity must move at least this many levels to re-alert


def fingerprint(field_id: int, alert_type: str, discriminator: str = "default") -> str:
    raw = f"{field_id}|{alert_type}|{discriminator}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:32]  # noqa: S324 - not a security hash


def raise_alert(
    db: Session,
    *,
    farm: Farm,
    field: Field,
    alert_type: str,
    severity: str,
    title: str,
    message: str,
    evidence: list[dict] | None = None,
    discriminator: str = "default",
) -> tuple[Alert, bool]:
    """Create or update an alert.  Returns ``(alert, created)``."""
    now = datetime.now(UTC)
    key = fingerprint(field.id, alert_type, discriminator)
    rank = SEVERITY_RANK.get(severity, 0)

    existing_stmt = (
        select(Alert)
        .where(Alert.field_id == field.id, Alert.fingerprint == key, Alert.status != AlertStatus.RESOLVED.value)
        .order_by(Alert.triggered_at.desc())
    )
    existing = db.execute(existing_stmt).scalars().first()

    if existing is not None:
        if rank > existing.severity_rank + (ESCALATION_STEP - 1):
            logger.info(
                "Escalating alert %s for field %s: %s -> %s", existing.id, field.id, existing.severity, severity
            )
            existing.severity = severity
            existing.severity_rank = rank
            existing.message = message
            existing.evidence = evidence or []
            existing.last_observed_at = now
            existing.occurrence_count += 1
            return existing, False

        existing.occurrence_count += 1
        existing.last_observed_at = now
        if evidence:
            existing.evidence = evidence
        return existing, False

    alert = Alert(
        farm_id=farm.id,
        field_id=field.id,
        alert_type=alert_type,
        severity=severity,
        title=title,
        message=message,
        evidence=evidence or [],
        fingerprint=key,
        severity_rank=rank,
        status=AlertStatus.OPEN.value,
        occurrence_count=1,
        triggered_at=now,
        last_observed_at=now,
    )
    db.add(alert)
    db.flush()
    logger.info("Raised %s alert '%s' for field %s", severity, alert_type, field.id)
    return alert, True


def sync_findings(
    db: Session,
    *,
    farm: Farm,
    field: Field,
    risk_findings: list[dict],
    irrigation_recommendation: str | None = None,
) -> list[Alert]:
    """Translate risk findings into alerts and auto-resolve cleared conditions."""
    raised: list[Alert] = []
    live_fingerprints: set[str] = set()

    for finding in risk_findings:
        risk_type = finding["risk_type"]
        alert_type = _ALERT_TYPE_FOR_RISK.get(risk_type)
        if alert_type is None:
            continue
        key = fingerprint(field.id, alert_type, risk_type)
        live_fingerprints.add(key)
        alert, _created = raise_alert(
            db,
            farm=farm,
            field=field,
            alert_type=alert_type,
            severity=finding["severity"],
            title=_ALERT_TITLE.get(alert_type, alert_type.replace("_", " ").title()),
            message=finding["statement"],
            evidence=finding.get("evidence", []),
            discriminator=risk_type,
        )
        raised.append(alert)

    if irrigation_recommendation in {"consider_irrigation", "review_required", "insufficient_information"}:
        alert_type = "water_stress"
        key = fingerprint(field.id, alert_type, "irrigation")
        live_fingerprints.add(key)
        alert, _created = raise_alert(
            db,
            farm=farm,
            field=field,
            alert_type=alert_type,
            severity="medium" if irrigation_recommendation == "consider_irrigation" else "low",
            title="Irrigation decision required",
            message=(
                "The irrigation planning agent recommends an irrigation decision review for this field. "
                f"Current recommendation: {irrigation_recommendation.replace('_', ' ')}."
            ),
            evidence=[],
            discriminator="irrigation",
        )
        raised.append(alert)

    resolve_cleared(db, field_id=field.id, keep=live_fingerprints)
    return raised


def resolve_cleared(db: Session, *, field_id: int, keep: set[str]) -> None:
    """Auto-resolve open alerts whose condition is no longer present."""
    stmt = select(Alert).where(
        Alert.field_id == field_id,
        Alert.status.in_([AlertStatus.OPEN.value, AlertStatus.ACKNOWLEDGED.value]),
    )
    for alert in db.execute(stmt).scalars():
        if alert.fingerprint not in keep:
            alert.status = AlertStatus.RESOLVED.value
            alert.resolved_at = datetime.now(UTC)
            logger.debug("Auto-resolved alert %s (condition cleared)", alert.id)


def alert_evidence(db: Session, farm_id: int, limit: int = 50) -> list[Alert]:
    stmt = select(Alert).where(Alert.farm_id == farm_id).order_by(Alert.last_observed_at.desc()).limit(limit)
    return list(db.execute(stmt).scalars())


def evidence_from_value(label: str, value: Any, unit: str | None, source: str) -> dict[str, Any]:
    return {
        "label": label,
        "value": value,
        "unit": unit,
        "kind": SourceKind.OBSERVED.value,
        "source": source,
    }


_ALERT_TYPE_FOR_RISK = {
    "heat_stress": "high_temperature",
    "water_stress": "water_stress",
    "excessive_rainfall": "heavy_rainfall",
    "extended_dry_period": "water_stress",
    "disease_favourable_environment": "disease_risk_environment",
    "sensor_fault": "sensor_malfunction",
}

_ALERT_TITLE = {
    "high_temperature": "High temperature warning",
    "heavy_rainfall": "Heavy rainfall warning",
    "water_stress": "Water stress warning",
    "disease_risk_environment": "Disease-favourable conditions",
    "sensor_malfunction": "Sensor malfunction",
    "low_soil_moisture": "Low soil moisture",
}
