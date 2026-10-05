"""Inference facade for the trained models.

Design contract:

* A missing or unloadable artifact is **not** an error.  Every prediction call
  returns ``status="unavailable"`` with an explanation so that callers (agents,
  APIs) can degrade to rule-only reasoning and surface a warning instead of
  failing.
* Predictions always state which features were imputed because they were
  missing, so an imputed prediction is never presented as a full-evidence one.
* ``model_version`` travels with every prediction.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np

from app.core.config import settings
from app.core.logging import get_logger
from app.ml.features import (
    MOISTURE_FORECAST_FEATURES,
    RISK_CLASSES,
    RISK_FEATURES,
    build_moisture_feature_vector,
    build_risk_feature_vector,
)

logger = get_logger(__name__)

MOISTURE_ARTIFACT = "soil_moisture_forecast.joblib"
RISK_ARTIFACT = "environmental_risk_classifier.joblib"
METRICS_FILE = "metrics.json"

UNAVAILABLE = "unavailable"
OK = "ok"


class MLRegistry:
    """Loads the trained artifacts once and serves predictions."""

    def __init__(self, artifacts_dir: Path | None = None) -> None:
        self._dir = artifacts_dir or Path(settings.ml_artifacts_dir)
        self._moisture: dict[str, Any] | None = None
        self._risk: dict[str, Any] | None = None
        self._metrics: dict[str, Any] | None = None
        self._errors: list[str] = []
        self._loaded = False

    # -- lifecycle -------------------------------------------------------
    def load(self, *, force: bool = False) -> None:
        if self._loaded and not force:
            return
        self._loaded = True
        self._errors = []
        self._moisture = self._load_bundle(MOISTURE_ARTIFACT)
        self._risk = self._load_bundle(RISK_ARTIFACT)
        self._metrics = self._load_metrics()
        if self._moisture is None or self._risk is None:
            logger.warning(
                "ML artifacts unavailable in %s - the system will run rule-only. Run `python -m app.ml.train`.",
                self._dir,
            )
        else:
            logger.info("ML models loaded from %s", self._dir)

    def _load_bundle(self, name: str) -> dict[str, Any] | None:
        path = self._dir / name
        if not path.exists():
            self._errors.append(f"Missing artifact {name}")
            return None
        try:
            return joblib.load(path)
        except Exception as exc:  # pragma: no cover - corrupt artifact
            self._errors.append(f"Failed to load {name}: {exc}")
            logger.exception("Could not load ML artifact %s", name)
            return None

    def _load_metrics(self) -> dict[str, Any] | None:
        path = self._dir / METRICS_FILE
        if not path.exists():
            return None
        try:
            import json

            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - a missing or corrupt metrics file means 'no metrics'
            return None

    # -- status ----------------------------------------------------------
    @property
    def moisture_available(self) -> bool:
        return self._moisture is not None

    @property
    def risk_available(self) -> bool:
        return self._risk is not None

    @property
    def available(self) -> bool:
        return self.moisture_available or self.risk_available

    @property
    def errors(self) -> list[str]:
        return list(self._errors)

    def describe_models(self) -> list[dict[str, Any]]:
        """Model cards for the API, sourced from ``metrics.json``."""
        if not self._metrics:
            return [
                {
                    "task": "soil_moisture_forecast",
                    "model_name": "not trained",
                    "available": False,
                    "detail": "No metrics.json found. Run `python -m app.ml.train` to build the models.",
                },
                {
                    "task": "environmental_risk_classification",
                    "model_name": "not trained",
                    "available": False,
                    "detail": "No metrics.json found. Run `python -m app.ml.train` to build the models.",
                },
            ]

        cards = []
        for model in self._metrics.get("models", []):
            task = model.get("task", "unknown")
            card = dict(model)
            metrics = dict(card.get("metrics", {}))
            # ``train_samples``/``test_samples`` are recorded next to the scores
            # in metrics.json; hoist them so the API can present the split.
            card["train_samples"] = int(metrics.pop("train_samples", 0) or 0)
            card["test_samples"] = int(metrics.pop("test_samples", 0) or 0)
            card["metrics"] = metrics
            card["model_version"] = self._metrics.get("model_version", "unknown")
            card["split"] = self._metrics.get("dataset", {}).get("split", {})
            card["dataset_summary"] = {
                key: value for key, value in self._metrics.get("dataset", {}).items() if key not in {"description"}
            }
            card["limitations"] = self._metrics.get("limitations", [])
            card["available"] = self.moisture_available if task == "soil_moisture_forecast" else self.risk_available
            card["trained_at"] = _parse_dt(self._metrics.get("generated_at"))
            cards.append(card)
        return cards

    # -- predictions -----------------------------------------------------
    def predict_soil_moisture(self, **features: Any) -> dict[str, Any]:
        """7-day-ahead soil moisture forecast (% VWC)."""
        if self._moisture is None:
            return {
                "status": UNAVAILABLE,
                "task": "soil_moisture_forecast",
                "model_name": "RandomForestRegressor",
                "model_version": "not-trained",
                "message": "Soil moisture forecast model is unavailable; irrigation used rule logic only.",
            }
        vector, missing = build_moisture_feature_vector(**features)
        model = self._moisture["model"]
        value = float(model.predict(np.asarray([vector], dtype="float32"))[0])
        return {
            "status": OK,
            "task": "soil_moisture_forecast",
            "model_name": "RandomForestRegressor",
            "model_version": self._moisture.get("model_version", "unknown"),
            "prediction_value": round(value, 2),
            "unit": "% VWC",
            "horizon_days": self._moisture.get("horizon_days", 7),
            "features": dict(zip(self._moisture.get("features", MOISTURE_FORECAST_FEATURES), vector, strict=True)),
            "imputed_features": missing,
            "message": (
                f"Predicted root-zone soil moisture {value:.1f} % VWC seven days ahead."
                + (f" Imputed features: {', '.join(missing)}." if missing else "")
            ),
        }

    def predict_risk_severity(self, **features: Any) -> dict[str, Any]:
        """Environmental risk severity bucket."""
        if self._risk is None:
            return {
                "status": UNAVAILABLE,
                "task": "environmental_risk_classification",
                "model_name": "RandomForestClassifier",
                "model_version": "not-trained",
                "message": "Risk classification model is unavailable; risk rules were applied alone.",
            }
        vector, missing = build_risk_feature_vector(**features)
        model = self._risk["model"]
        probabilities = model.predict_proba(np.asarray([vector], dtype="float32"))[0]
        classes = list(self._risk.get("classes", RISK_CLASSES))
        best_index = int(np.argmax(probabilities))
        label = classes[best_index] if best_index < len(classes) else str(best_index)
        confidence = float(probabilities[best_index])
        distribution = {cls: round(float(prob), 4) for cls, prob in zip(classes, probabilities, strict=True)}
        return {
            "status": OK,
            "task": "environmental_risk_classification",
            "model_name": "RandomForestClassifier",
            "model_version": self._risk.get("model_version", "unknown"),
            "prediction_label": label,
            "prediction_value": confidence,
            "confidence": round(confidence, 4),
            "class_distribution": distribution,
            "features": dict(zip(self._risk.get("features", RISK_FEATURES), vector, strict=True)),
            "imputed_features": missing,
            "message": (
                f"Model-classified environmental risk severity '{label}' with {confidence * 100:.0f}% confidence."
                + (f" Imputed features: {', '.join(missing)}." if missing else "")
            ),
        }


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:  # pragma: no cover - defensive
        return None


_registry: MLRegistry | None = None


def get_ml_registry() -> MLRegistry:
    global _registry  # noqa: PLW0603 - documented lazy singleton
    if _registry is None:
        _registry = MLRegistry()
        if settings.ml_autoload:
            _registry.load()
    return _registry
