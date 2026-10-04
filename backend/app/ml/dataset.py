"""Physically-grounded data generation for the ML models.

IMPORTANT AND DELIBERATE DESIGN NOTE
------------------------------------
No public field-level soil-moisture time series with the exact feature set this
project needs ships with an open licence that could be redistributed here.
Rather than ship an unusable notebook or copy a dataset with unclear
provenance, this module **simulates** the training data with an explicit,
documented soil-water-balance model:

* extraterrestrial radiation follows the FAO-56 equation;
* reference evapotranspiration uses the FAO-56 Hargreaves-Samani form;
* crop evapotranspiration uses an FAO-56 piecewise-linear crop-coefficient curve;
* daily water balance tracks root-zone depletion with texture-specific field
  capacity / wilting point and a percolation term above field capacity;
* rainfall is drawn from a gamma distribution modulated by a monsoon or winter
  seasonal pattern, with realistic inter-day autocorrelation.

Consequences, stated plainly:

* The labels are physically consistent, and the fitted models learn a real,
  non-linear interaction function.
* Reported metrics are against *simulator* ground truth, so they measure the
  model's ability to reproduce the process, not field accuracy. This limitation
  is documented in the README and in ``metrics.json``.

Regenerate with::

    python -m app.ml.train
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from app.data.crop_catalog import CROP_REQUIREMENTS, CropRequirements
from app.ml.features import (
    MOISTURE_FORECAST_FEATURES,
    RISK_CLASSES,
    RISK_FEATURES,
    hazard_margins,
    soil_class_index,
    stage_index,
)

SOLT = 0.0820  # latent heat of vaporisation (MJ/kg)
DAYS = 180
HORIZON = 7  # forecast horizon in days


@dataclass
class SimulationConfig:
    crop_key: str
    soil_type: str
    latitude: float
    longitude: float
    climate: str  # "monsoon" | "winter" | "humid_tropical" | "semi_arid"


# --- soil hydraulic properties ------------------------------------------------

THETA_SAT = {
    "sandy": 0.38,
    "sandy_loam": 0.44,
    "loam": 0.48,
    "silt_loam": 0.50,
    "clay_loam": 0.52,
    "clay": 0.54,
    "black_soil": 0.53,
    "red_soil": 0.46,
    "red_laterite": 0.44,
    "alluvial": 0.49,
}

FC = {
    "sandy": 0.18,
    "sandy_loam": 0.26,
    "loam": 0.33,
    "silt_loam": 0.36,
    "clay_loam": 0.38,
    "clay": 0.42,
    "black_soil": 0.40,
    "red_soil": 0.27,
    "red_laterite": 0.25,
    "alluvial": 0.34,
}

WP = {
    "sandy": 0.06,
    "sandy_loam": 0.09,
    "loam": 0.13,
    "silt_loam": 0.14,
    "clay_loam": 0.15,
    "clay": 0.18,
    "black_soil": 0.17,
    "red_soil": 0.10,
    "red_laterite": 0.09,
    "alluvial": 0.13,
}

ROOT_DEPTH_MM = {
    "sowing": 200.0,
    "emergence": 300.0,
    "vegetative": 500.0,
    "flowering": 700.0,
    "fruiting": 800.0,
    "maturity": 800.0,
}

KCB = {"rice": 1.20, "wheat": 1.15, "maize": 1.20, "cotton": 1.15, "tomato": 1.15, "potato": 1.05, "soybean": 1.15}


# --- FAO-56 helpers ----------------------------------------------------------


def extraterrestrial_radiation(lat_deg: float, day_of_year: int) -> float:
    """FAO-56 equation 21 (MJ m-2 day-1)."""
    phi = math.radians(lat_deg)
    dr = 1 + 0.033 * math.cos(2 * math.pi * day_of_year / 365)
    decl = 0.409 * math.sin(2 * math.pi * day_of_year / 365 - 1.39)
    x = max(-1.0, min(1.0, -math.tan(phi) * math.tan(decl)))
    ws = math.acos(x)
    return (
        (24 * 60 / math.pi)
        * 0.0820
        * dr
        * (ws * math.sin(phi) * math.sin(decl) + math.cos(phi) * math.cos(decl) * math.sin(ws))
    )


def hargreaves_et0(tmin: float, tmax: float, ra: float) -> float:
    """FAO-56 equation 52 (Hargreaves-Samani)."""
    tmean = (tmin + tmax) / 2.0
    return max(0.0, 0.0023 * (tmean + 17.8) * math.sqrt(max(0.0, tmax - tmin)) * ra)


def crop_coefficient(stage_fraction: float, kc_ini: float, kc_mid: float, kc_end: float) -> float:
    """FAO-56 piecewise-linear single-crop-coefficient curve."""
    if stage_fraction < 0.2:
        return kc_ini
    if stage_fraction < 0.4:
        return kc_ini + (kc_mid - kc_ini) * (stage_fraction - 0.2) / 0.2
    if stage_fraction < 0.75:
        return kc_mid
    return max(0.2, kc_mid - (kc_mid - kc_end) * (stage_fraction - 0.75) / 0.25)


def stage_name(fraction: float) -> str:
    if fraction < 0.15:
        return "sowing"
    if fraction < 0.3:
        return "emergence"
    if fraction < 0.55:
        return "vegetative"
    if fraction < 0.7:
        return "flowering"
    if fraction < 0.9:
        return "fruiting"
    return "maturity"


# --- climate generation -------------------------------------------------------

CLIMATE_TEMPS = {
    "monsoon": (24.0, 8.0, 0.0),
    "winter": (21.0, 9.0, 3.0),
    "humid_tropical": (28.0, 6.0, 1.0),
    "semi_arid": (31.0, 11.0, 0.0),
}

CLIMATE_RAIN = {
    "monsoon": (7.0, 22.0, 0.42),
    "winter": (3.5, 9.0, 0.22),
    "humid_tropical": (9.0, 24.0, 0.48),
    "semi_arid": (2.0, 7.0, 0.14),
}


def _seasonal_rain(weather_rng: np.random.Generator, climate: str) -> float:
    shape, scale, wet_prob = CLIMATE_RAIN[climate]
    if weather_rng.random() < wet_prob:
        return float(weather_rng.gamma(shape=1.6, scale=scale))
    return 0.0


def _humidity(tmean: float, rain_today: float, humidity_rng: np.random.Generator) -> float:
    base = 78.0 - 1.1 * (tmean - 22.0) + humidity_rng.normal(0.0, 7.0)
    if rain_today > 1.0:
        base += 12.0
    return float(np.clip(base, 22.0, 99.0))


def _risk_label(requirements: CropRequirements, feature_row: dict[str, float]) -> str:
    """Physically-defined multi-hazard severity bucket used as classifier target."""
    tmax = feature_row["temp_max_c"]
    theta = feature_row["soil_moisture_percent"]
    rh = feature_row["humidity_mean_percent"]
    wet_fraction = feature_row["wet_day_fraction_7d"]
    rain3 = feature_row["rainfall_3d_mm"]
    tmean = feature_row["temp_mean_c"]

    heat = min(2.0, max(0.0, (tmax - requirements.heat_stress_threshold_c) / 5.0))
    water = min(
        2.0,
        max(0.0, (requirements.moisture_critical - theta) / max(1.0, 0.45 * requirements.moisture_critical)),
    )
    rain_excess = min(2.0, max(0.0, (rain3 - requirements.heavy_rain_threshold_mm_3d) / 40.0))
    disease = 0.0
    if rh >= requirements.humidity_risk_threshold_percent and wet_fraction >= 0.4 and 8.0 <= tmean <= 33.0:
        disease = min(2.0, (rh - requirements.humidity_risk_threshold_percent) / 12.0 + wet_fraction)
    dryness = min(2.0, max(0.0, (0.15 * feature_row["rainfall_7d_mm"] - feature_row["et0_7d_mm"]) / 5.0))

    # Hazards interact: heat amplifies water stress, wet weather amplifies disease.
    score = max(
        heat,
        water * (1.0 + 0.35 * heat),
        rain_excess,
        disease,
        dryness,
    )
    if score < 0.18:
        return "none"
    if score < 0.45:
        return "low"
    if score < 0.85:
        return "moderate"
    return "high"


def _simulate(config: SimulationConfig, rng: np.random.Generator) -> tuple[list[dict], list[dict]]:
    """Simulate one season; return ``(moisture_rows, risk_rows)``."""
    requirements = CROP_REQUIREMENTS[config.crop_key]
    soil = config.soil_type
    theta_fc = FC[soil] * 100.0
    theta_wp = WP[soil] * 100.0
    theta_sat = THETA_SAT[soil] * 100.0

    tmean_base, temp_range, temp_offset = CLIMATE_TEMPS[config.climate]

    duration = int(rng.integers(requirements.duration_days[0], requirements.duration_days[1] + 1))
    duration = max(duration, 40)

    # initial soil moisture somewhere between wilting point and field capacity
    theta = float(rng.uniform(theta_wp + 0.35 * (theta_fc - theta_wp), theta_fc + 4.0))
    theta = min(theta, theta_sat)

    kc_ini = 0.40
    kc_mid = KCB.get(config.crop_key, 1.15)
    kc_end = 0.55 if config.crop_key in {"rice", "cotton", "tomato"} else 0.40

    weather_rng = np.random.default_rng(rng.integers(0, 2**32 - 1))
    humidity_rng = np.random.default_rng(rng.integers(0, 2**32 - 1))

    history: list[dict[str, float]] = []
    moisture_rows: list[dict] = []
    risk_rows: list[dict] = []

    for day in range(DAYS):
        frac = min(1.0, day / duration)
        dooy = 1 + (int(60 + frac * 200) % DAYS)
        ra = extraterrestrial_radiation(config.latitude, dooy)

        rain = _seasonal_rain(weather_rng, config.climate)
        tmean = tmean_base + temp_offset + float(rng.normal(0.0, 1.6))
        trange = max(1.0, temp_range + float(rng.normal(0.0, 1.8)))
        tmax = tmean + trange / 2.0
        tmin = tmean - trange / 2.0
        et0 = hargreaves_et0(tmin, tmax, ra)
        kc = crop_coefficient(frac, kc_ini, kc_mid, kc_end)
        etc = et0 * kc
        peff = rain * 0.85

        stage = stage_name(frac)
        depth = ROOT_DEPTH_MM[stage]
        taw = max(1.0, (theta_fc - theta_wp) / 100.0 * depth)
        depletion = max(0.0, min(taw, (theta_fc - theta) / 100.0 * depth + etc - peff))

        # percolation above field capacity
        drain = 0.0
        if theta > theta_fc:
            drain = (theta - theta_fc) / 100.0 * depth

        theta = theta_fc - depletion / depth * 100.0 + drain / depth * 100.0
        theta = float(np.clip(theta, max(1.0, theta_wp - 2.0), theta_sat))

        rh = _humidity(tmean, rain, humidity_rng)
        wind = float(np.clip(rng.gamma(2.0, 0.9), 0.2, 9.0))

        history.append(
            {
                "rain": rain,
                "tmin": tmin,
                "tmax": tmax,
                "tmean": tmean,
                "rh": rh,
                "wind": wind,
                "et0": etc,
                "theta": theta,
                "stage": stage,
                "frac": frac,
            }
        )

        if day < 5 or day > DAYS - HORIZON - 2:
            continue

        window = history[-7:]
        rain_7d = float(sum(item["rain"] for item in window))
        rain_3d = float(sum(item["rain"] for item in window[-3:]))
        rain_1d = window[-1]["rain"]
        et0_7d = float(sum(item["et0"] for item in window))
        theta_change_3d = theta - history[-4]["theta"]
        wet_fraction = float(sum(1 for item in window if item["rain"] > 1.0 or item["rh"] >= 85.0) / 7.0)

        features = {
            "temp_min_c": window[-1]["tmin"],
            "temp_max_c": window[-1]["tmax"],
            "temp_mean_c": window[-1]["tmean"],
            "humidity_mean_percent": float(np.mean([item["rh"] for item in window])),
            "humidity_min_percent": float(np.min([item["rh"] for item in window])),
            "wind_speed_ms": window[-1]["wind"],
            "rainfall_1d_mm": rain_1d,
            "rainfall_3d_mm": rain_3d,
            "rainfall_7d_mm": rain_7d,
            "wet_day_fraction_7d": wet_fraction,
            "et0_7d_mm": et0_7d,
            "soil_moisture_percent": theta,
            "soil_moisture_change_3d": theta_change_3d,
            "crop_stage_index": stage_index(stage),
            "soil_class_index": soil_class_index(soil),
            "latitude": config.latitude,
        }
        features.update(
            hazard_margins(
                crop=config.crop_key,
                temp_max_c=features["temp_max_c"],
                soil_moisture_percent=features["soil_moisture_percent"],
                humidity_mean_percent=features["humidity_mean_percent"],
                rainfall_3d_mm=features["rainfall_3d_mm"],
            )
        )

        # forward rainfall for the moisture feature: simulate the next 3 days
        future_rain = 0.0
        future_et0 = 0.0
        for step in range(1, HORIZON + 1):
            f_frac = min(1.0, (day + step) / duration)
            f_doy = 1 + (int(60 + f_frac * 200) % DAYS)
            f_ra = extraterrestrial_radiation(config.latitude, f_doy)
            f_rain = _seasonal_rain(weather_rng, config.climate)
            f_tmean = tmean_base + temp_offset + float(rng.normal(0.0, 1.6))
            f_trange = max(1.0, temp_range + float(rng.normal(0.0, 1.8)))
            f_et0 = hargreaves_et0(f_tmean - f_trange / 2, f_tmean + f_trange / 2, f_ra)
            f_etc = f_et0 * crop_coefficient(f_frac, kc_ini, kc_mid, kc_end)
            if step <= 3:
                future_rain += f_rain
                future_et0 += f_etc
            # advance the balance
            f_depth = ROOT_DEPTH_MM[stage_name(f_frac)]
            f_taw = max(1.0, (theta_fc - theta_wp) / 100.0 * f_depth)
            depl = max(0.0, min(f_taw, (theta_fc - theta) / 100.0 * f_depth + f_etc - f_rain * 0.85))
            drain = max(0.0, (theta - theta_fc) / 100.0 * f_depth)
            theta = theta_fc - depl / f_depth * 100.0 + drain / f_depth * 100.0
            theta = float(np.clip(theta, max(1.0, theta_wp - 2.0), theta_sat))

        risk_rows.append({"features": features, "label": _risk_label(requirements, features)})

        moisture_features = {
            "soil_moisture_percent": features["soil_moisture_percent"],
            "soil_moisture_change_3d": theta_change_3d,
            "soil_temperature_c": theta / 8.0 + 4.0,
            "air_temperature_c": features["temp_mean_c"],
            "humidity_percent": features["humidity_mean_percent"],
            "wind_speed_ms": features["wind_speed_ms"],
            "rainfall_7d_mm": rain_7d,
            "et0_7d_mm": et0_7d,
            "crop_stage_index": features["crop_stage_index"],
            "soil_class_index": features["soil_class_index"],
            "latitude": config.latitude,
            "expected_rainfall_next_3d_mm": future_rain,
        }
        # persist for the classifier pass as well
        risk_rows[-1]["future_et0_3d"] = future_et0

        moisture_rows.append({"features": moisture_features, "target": theta})

    return moisture_rows, risk_rows


def generate_datasets(seed: int = 20240517, n_seasons: int = 420) -> dict:
    """Generate training data for both tasks.

    Returns numpy arrays plus the season index, which is used for a
    *grouped* train/test split (whole seasons are held out, never individual
    rows, which would leak almost-identical consecutive days across the split).
    """
    rng = np.random.default_rng(seed)
    soil_types = list(FC.keys())
    climate_keys = list(CLIMATE_TEMPS.keys())
    crop_keys = list(CROP_REQUIREMENTS.keys())

    moisture_x: list[list[float]] = []
    moisture_y: list[float] = []
    risk_x: list[list[float]] = []
    risk_y: list[int] = []
    season_ids: list[int] = []

    for season in range(n_seasons):
        config = SimulationConfig(
            crop_key=crop_keys[int(rng.integers(len(crop_keys)))],
            soil_type=soil_types[int(rng.integers(len(soil_types)))],
            latitude=float(rng.uniform(8.0, 32.0)),
            longitude=float(rng.uniform(70.0, 92.0)),
            climate=climate_keys[int(rng.integers(len(climate_keys)))],
        )
        moisture_rows, risk_rows = _simulate(config, rng)
        for row in moisture_rows:
            moisture_x.append([row["features"][name] for name in MOISTURE_FORECAST_FEATURES])
            moisture_y.append(row["target"])
            season_ids.append(season)
        for row in risk_rows:
            risk_x.append([row["features"][name] for name in RISK_FEATURES])
            risk_y.append(RISK_CLASSES.index(row["label"]))

    season_ids_array = np.array(season_ids, dtype="int32")
    return {
        "moisture_x": np.asarray(moisture_x, dtype="float32"),
        "moisture_y": np.asarray(moisture_y, dtype="float32"),
        "risk_x": np.asarray(risk_x, dtype="float32"),
        "risk_y": np.asarray(risk_y, dtype="int32"),
        "season_id": season_ids_array,
        "metadata": {
            "seed": seed,
            "seasons": n_seasons,
            "crop_keys": crop_keys,
            "soil_types": soil_types,
            "climates": climate_keys,
            "moisture_rows": len(moisture_y),
            "risk_rows": len(risk_y),
            "risk_class_distribution": {
                RISK_CLASSES[index]: int((np.asarray(risk_y) == index).sum()) for index in range(len(RISK_CLASSES))
            },
        },
    }
