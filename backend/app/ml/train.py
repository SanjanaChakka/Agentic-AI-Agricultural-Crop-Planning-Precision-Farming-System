"""Reproducible training entry point for both ML tasks.

Usage::

    python -m app.ml.train                 # train with the default seed
    python -m app.ml.train --seed 7 --seasons 200

Artifacts written to ``app/ml/artifacts``:
* ``soil_moisture_forecast.joblib`` - regression pipeline + feature names
* ``environmental_risk_classifier.joblib`` - classification pipeline + classes
* ``metrics.json`` - dataset statistics, metrics and evaluation notes
* ``feature_importance.json`` - permutation-free impurity importances

Model selection
---------------
Grouped (by simulated season) 80/20 train/test split, evaluated with MAE, RMSE
and R^2 for the regressor and accuracy / macro-F1 / per-class report plus a
confusion matrix for the classifier.  Whole seasons are held out so that
near-identical consecutive days from the same season cannot leak across the
split.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)

from app.core.config import settings
from app.core.logging import get_logger
from app.ml.dataset import HORIZON, generate_datasets
from app.ml.features import MOISTURE_FORECAST_FEATURES, RISK_CLASSES, RISK_FEATURES

logger = get_logger(__name__)

MODEL_VERSION = "1.0.0"
ARTIFACTS = Path(settings.ml_artifacts_dir)


def _grouped_split(season_ids: np.ndarray, *, test_fraction: float, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Split whole seasons, never individual rows, so no season leaks across sets."""
    unique = np.unique(season_ids)
    rng = np.random.default_rng(seed)
    shuffled = rng.permutation(unique)
    n_test = max(1, int(len(shuffled) * test_fraction))
    test_seasons = set(shuffled[:n_test].tolist())
    test_mask = np.array([sid in test_seasons for sid in season_ids], dtype=bool)
    return ~test_mask, test_mask


def train_all(seed: int, seasons: int, test_fraction: float = 0.2) -> dict:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    logger.info("Generating simulated dataset (seed=%s, seasons=%s)", seed, seasons)
    data = generate_datasets(seed=seed, n_seasons=seasons)
    metadata = data["metadata"]
    logger.info("Dataset: %d moisture rows, %d risk rows", metadata["moisture_rows"], metadata["risk_rows"])

    train_mask, test_mask = _grouped_split(data["season_id"], test_fraction=test_fraction, seed=seed)

    # --- Task 1: 7-day soil moisture forecast (regression) ------------------
    x_m = data["moisture_x"]
    y_m = data["moisture_y"]
    regressor = RandomForestRegressor(
        n_estimators=90,
        max_depth=12,
        min_samples_leaf=6,
        max_features="sqrt",
        random_state=seed,
        n_jobs=-1,
    )
    regressor.fit(x_m[train_mask], y_m[train_mask])
    predictions = regressor.predict(x_m[test_mask])
    moisture_metrics = {
        "mae": float(mean_absolute_error(y_m[test_mask], predictions)),
        "rmse": float(np.sqrt(mean_squared_error(y_m[test_mask], predictions))),
        "r2": float(r2_score(y_m[test_mask], predictions)),
        "train_samples": int(train_mask.sum()),
        "test_samples": int(test_mask.sum()),
    }
    logger.info(
        "Moisture forecast: MAE=%.3f RMSE=%.3f R2=%.3f",
        moisture_metrics["mae"],
        moisture_metrics["rmse"],
        moisture_metrics["r2"],
    )

    joblib.dump(
        {
            "model": regressor,
            "features": MOISTURE_FORECAST_FEATURES,
            "target": f"soil_moisture_percent_volumetric_day_{HORIZON}",
            "horizon_days": HORIZON,
            "model_version": MODEL_VERSION,
            "trained_at": datetime.now(UTC).isoformat(),
        },
        ARTIFACTS / "soil_moisture_forecast.joblib",
        compress=3,
    )

    # --- Task 2: environmental risk severity (multi-class) -----------------
    x_r = data["risk_x"]
    y_r = data["risk_y"]
    classifier = RandomForestClassifier(
        n_estimators=110,
        max_depth=12,
        min_samples_leaf=6,
        max_features="sqrt",
        class_weight="balanced",
        random_state=seed,
        n_jobs=-1,
    )
    classifier.fit(x_r[train_mask], y_r[train_mask])
    risk_predictions = classifier.predict(x_r[test_mask])
    risk_report = classification_report(
        y_r[test_mask],
        risk_predictions,
        labels=list(range(len(RISK_CLASSES))),
        target_names=list(RISK_CLASSES),
        output_dict=True,
        zero_division=0,
    )
    risk_metrics = {
        "accuracy": float(accuracy_score(y_r[test_mask], risk_predictions)),
        "macro_f1": float(f1_score(y_r[test_mask], risk_predictions, average="macro", zero_division=0)),
        "train_samples": int(train_mask.sum()),
        "test_samples": int(test_mask.sum()),
        "classification_report": {
            label: (
                {metric: float(value) for metric, value in scores.items() if isinstance(value, int | float)}
                if isinstance(scores, dict)
                else float(scores)
            )
            for label, scores in risk_report.items()
        },
        "confusion_matrix": {
            "labels": list(RISK_CLASSES),
            "matrix": confusion_matrix(
                y_r[test_mask], risk_predictions, labels=list(range(len(RISK_CLASSES)))
            ).tolist(),
        },
    }
    logger.info("Risk classifier: accuracy=%.3f macro-F1=%.3f", risk_metrics["accuracy"], risk_metrics["macro_f1"])

    joblib.dump(
        {
            "model": classifier,
            "features": RISK_FEATURES,
            "classes": list(RISK_CLASSES),
            "target": "environmental_risk_severity_bucket",
            "model_version": MODEL_VERSION,
            "trained_at": datetime.now(UTC).isoformat(),
        },
        ARTIFACTS / "environmental_risk_classifier.joblib",
        compress=3,
    )

    importance = {
        "soil_moisture_forecast": dict(
            zip(MOISTURE_FORECAST_FEATURES, [float(v) for v in regressor.feature_importances_], strict=True)
        ),
        "environmental_risk_classifier": dict(
            zip(RISK_FEATURES, [float(v) for v in classifier.feature_importances_], strict=True)
        ),
    }
    (ARTIFACTS / "feature_importance.json").write_text(json.dumps(importance, indent=2), encoding="utf-8")

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "seed": seed,
        "model_version": MODEL_VERSION,
        "dataset": {
            "type": "physically simulated soil water balance (FAO-56 style)",
            "seasons": seasons,
            "grouped_split": "whole seasons held out (20%)",
            **metadata,
        },
        "models": [
            {
                "task": "soil_moisture_forecast",
                "model_name": "RandomForestRegressor",
                "algorithm": "Random forest regression ensemble",
                "target": f"soil_moisture_percent_volumetric_day_{HORIZON}",
                "features": MOISTURE_FORECAST_FEATURES,
                "hyperparameters": {
                    "n_estimators": 90,
                    "max_depth": 12,
                    "min_samples_leaf": 6,
                    "max_features": "sqrt",
                },
                "metrics": dict(moisture_metrics.items()),
                "documentation": (
                    "Predicts root-zone volumetric soil moisture seven days ahead from current moisture, "
                    "recent rainfall, reference evapotranspiration, weather and crop-stage features. "
                    "Used by the irrigation planning agent to estimate how long the current profile lasts."
                ),
            },
            {
                "task": "environmental_risk_classification",
                "model_name": "RandomForestClassifier",
                "algorithm": "Random forest classification ensemble (class_weight=balanced)",
                "target": "environmental_risk_severity_bucket (none/low/moderate/high)",
                "features": RISK_FEATURES,
                "hyperparameters": {
                    "n_estimators": 110,
                    "max_depth": 12,
                    "min_samples_leaf": 6,
                    "max_features": "sqrt",
                },
                "metrics": dict(risk_metrics.items()),
                "documentation": (
                    "Aggregates heat, water-deficit, heavy-rain and disease-favourability hazards, including "
                    "their interactions (heat amplifying water stress, wet weather amplifying disease risk), "
                    "into a single severity bucket that complements the explicit threshold rules."
                ),
            },
        ],
        "limitations": [
            "Training data is simulated with an FAO-56 style water balance model, so reported metrics measure "
            "how well the model reproduces that process, not real-world field accuracy.",
            "The risk classifier learns an explicit severity formula from the simulator; it generalises across "
            "crop and soil combinations but cannot add information that is absent from its inputs.",
            "Field calibration against real sensor logs remains necessary before operational irrigation control.",
        ],
    }
    (ARTIFACTS / "metrics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    logger.info("Artifacts written to %s", ARTIFACTS)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the soil-moisture and risk models")
    parser.add_argument("--seed", type=int, default=settings.ml_random_seed)
    parser.add_argument("--seasons", type=int, default=420, help="Number of simulated seasons")
    parser.add_argument("--test-fraction", type=float, default=0.2)
    args = parser.parse_args()

    train_all(seed=args.seed, seasons=args.seasons, test_fraction=args.test_fraction)


if __name__ == "__main__":
    main()
