"""Structured agronomic reference data used by the rule layer.

Every numeric band in this module is a *project-configured agronomic threshold*
whose provenance is recorded in :data:`THRESHOLD_SOURCES` and mirrored in the
retrievable knowledge corpus under ``app/data/knowledge``.  Agents never invent
values: they look them up here and cite the corresponding document.

Soil-test rating bands follow the widely used ICAR-style "available nutrient"
classification for medium black soils (kg/ha of available N, P2O5 and K2O) and
the standard soil pH classes.  Volumetric soil-moisture bands are expressed as
percent volumetric water content (% VWC).
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------

THRESHOLD_SOURCES: dict[str, str] = {
    "soil_ph": "soil.soil_ph_and_fertility",
    "soil_nutrients": "soil.soil_ph_and_fertility",
    "soil_texture": "soil.texture_and_water_holding",
    "crop_requirements": "crops.*",
    "irrigation": "irrigation.scheduling_principles",
    "stage_water": "irrigation.water_requirements_by_stage",
    "heat_risk": "climate.heat_and_water_stress",
    "rain_risk": "climate.rainfall_extremes_and_waterlogging",
    "disease_risk": "risk.disease_favourable_environment",
    "crop_stages": "practices.crop_stages_and_practices",
}

# ---------------------------------------------------------------------------
# Soil pH classes
# ---------------------------------------------------------------------------

PH_CLASSES: dict[str, tuple[float, float]] = {
    "strongly_acidic": (0.0, 5.5),
    "moderately_acidic": (5.5, 6.5),
    "neutral": (6.5, 7.5),
    "moderately_alkaline": (7.5, 8.5),
    "strongly_alkaline": (8.5, 14.0),
}

PH_CLASS_LABELS: dict[str, str] = {
    "strongly_acidic": "strongly acidic (pH < 5.5)",
    "moderately_acidic": "moderately acidic (pH 5.5-6.5)",
    "neutral": "neutral (pH 6.5-7.5)",
    "moderately_alkaline": "moderately alkaline (pH 7.5-8.5)",
    "strongly_alkaline": "strongly alkaline (pH > 8.5)",
}

# ---------------------------------------------------------------------------
# Soil-test rating bands (kg/ha available nutrient; organic carbon in %)
# ---------------------------------------------------------------------------

NUTRIENT_THRESHOLDS: dict[str, dict[str, float]] = {
    "nitrogen_available_kg_ha": {"low_max": 110.0, "medium_max": 280.0},
    "phosphorus_available_kg_ha": {"low_max": 10.0, "medium_max": 25.0},
    "potassium_available_kg_ha": {"low_max": 110.0, "medium_max": 280.0},
    "organic_carbon_percent": {"low_max": 0.5, "medium_max": 0.75},
}

# ---------------------------------------------------------------------------
# Volumetric soil moisture bands by texture (approximate plant-available water)
# ---------------------------------------------------------------------------

TEXTURE_WATER_BANDS: dict[str, dict[str, float]] = {
    # field capacity / refill trigger / wilting point  (% VWC)
    "sandy": {"field_capacity": 18.0, "refill_trigger": 10.0, "wilting_point": 6.0, "available_water_mm_per_10cm": 8.0},
    "sandy_loam": {
        "field_capacity": 26.0,
        "refill_trigger": 15.0,
        "wilting_point": 9.0,
        "available_water_mm_per_10cm": 12.0,
    },
    "loam": {
        "field_capacity": 33.0,
        "refill_trigger": 21.0,
        "wilting_point": 13.0,
        "available_water_mm_per_10cm": 17.0,
    },
    "silt_loam": {
        "field_capacity": 36.0,
        "refill_trigger": 23.0,
        "wilting_point": 14.0,
        "available_water_mm_per_10cm": 19.0,
    },
    "clay_loam": {
        "field_capacity": 38.0,
        "refill_trigger": 25.0,
        "wilting_point": 15.0,
        "available_water_mm_per_10cm": 20.0,
    },
    "clay": {
        "field_capacity": 42.0,
        "refill_trigger": 27.0,
        "wilting_point": 18.0,
        "available_water_mm_per_10cm": 18.0,
    },
    "black_soil": {
        "field_capacity": 40.0,
        "refill_trigger": 26.0,
        "wilting_point": 17.0,
        "available_water_mm_per_10cm": 20.0,
    },
    "red_soil": {
        "field_capacity": 27.0,
        "refill_trigger": 17.0,
        "wilting_point": 10.0,
        "available_water_mm_per_10cm": 13.0,
    },
    "red_laterite": {
        "field_capacity": 25.0,
        "refill_trigger": 15.0,
        "wilting_point": 9.0,
        "available_water_mm_per_10cm": 11.0,
    },
    "alluvial": {
        "field_capacity": 34.0,
        "refill_trigger": 22.0,
        "wilting_point": 13.0,
        "available_water_mm_per_10cm": 17.0,
    },
}

DEFAULT_TEXTURE_BANDS = TEXTURE_WATER_BANDS["loam"]

# ---------------------------------------------------------------------------
# Crop requirements
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CropRequirements:
    """Agronomic requirement envelope for one crop."""

    name: str
    aliases: tuple[str, ...]
    ph_optimal: tuple[float, float]
    ph_tolerable: tuple[float, float]
    temp_optimal: tuple[float, float]
    temp_absolute_max: float
    season_rainfall_mm: tuple[float, float]
    water_requirement_mm: tuple[float, float]
    moisture_optimal: tuple[float, float]
    moisture_critical: float
    season: str
    duration_days: tuple[int, int]
    critical_stages: tuple[str, ...]
    frost_sensitive: bool = True
    waterlogged_sensitive: bool = True
    notes: str = ""
    heavy_rain_threshold_mm_3d: float = 50.0
    heat_stress_threshold_c: float = 35.0
    humidity_risk_threshold_percent: float = 85.0
    suitable_soils: tuple[str, ...] = ()
    doc_key: str = field(default="")

    def doc(self) -> str:
        return self.doc_key or f"crops.{self.name.lower().replace(' ', '_')}"


CROP_REQUIREMENTS: dict[str, CropRequirements] = {
    "rice": CropRequirements(
        name="Rice",
        aliases=("paddy", "oryza sativa"),
        ph_optimal=(5.5, 7.0),
        ph_tolerable=(5.0, 7.5),
        temp_optimal=(24.0, 32.0),
        temp_absolute_max=38.0,
        season_rainfall_mm=(1000.0, 3000.0),
        water_requirement_mm=(600.0, 1200.0),
        moisture_optimal=(45.0, 90.0),
        moisture_critical=25.0,
        season="kharif / rabi (transplanted or direct seeded)",
        duration_days=(110, 150),
        critical_stages=("panicle initiation", "booting", "flowering", "grain filling"),
        frost_sensitive=True,
        waterlogged_sensitive=False,
        heavy_rain_threshold_mm_3d=80.0,
        heat_stress_threshold_c=35.0,
        humidity_risk_threshold_percent=92.0,
        suitable_soils=("clay", "clay_loam", "black_soil", "alluvial"),
        notes=(
            "Rice tolerates standing water and responds strongly to assured water supply; "
            "alternating wetting and drying reduces methane emissions and water use."
        ),
    ),
    "wheat": CropRequirements(
        name="Wheat",
        aliases=("bread wheat", "durum wheat", "triticum aestivum"),
        ph_optimal=(6.0, 7.5),
        ph_tolerable=(5.5, 8.0),
        temp_optimal=(15.0, 22.0),
        temp_absolute_max=30.0,
        season_rainfall_mm=(400.0, 750.0),
        water_requirement_mm=(400.0, 650.0),
        moisture_optimal=(45.0, 65.0),
        moisture_critical=30.0,
        season="rabi (cool season)",
        duration_days=(100, 135),
        critical_stages=("crown root initiation", "tillering", "jointing", "flowering", "grain filling"),
        frost_sensitive=True,
        waterlogged_sensitive=True,
        heavy_rain_threshold_mm_3d=40.0,
        heat_stress_threshold_c=30.0,
        humidity_risk_threshold_percent=85.0,
        suitable_soils=("loam", "silt_loam", "clay_loam", "alluvial", "black_soil"),
        notes=(
            "Terminal heat above 30 C during grain filling sharply reduces grain weight; "
            "an irrigation timed around crown root initiation is usually the highest priority."
        ),
    ),
    "maize": CropRequirements(
        name="Maize",
        aliases=("corn", "zea mays"),
        ph_optimal=(5.5, 7.5),
        ph_tolerable=(5.0, 8.0),
        temp_optimal=(21.0, 27.0),
        temp_absolute_max=35.0,
        season_rainfall_mm=(600.0, 1200.0),
        water_requirement_mm=(500.0, 800.0),
        moisture_optimal=(50.0, 75.0),
        moisture_critical=35.0,
        season="kharif / spring",
        duration_days=(90, 130),
        critical_stages=("tasselling", "silking", "grain filling"),
        frost_sensitive=True,
        waterlogged_sensitive=True,
        heavy_rain_threshold_mm_3d=50.0,
        heat_stress_threshold_c=33.0,
        humidity_risk_threshold_percent=85.0,
        suitable_soils=("loam", "sandy_loam", "clay_loam", "alluvial", "silt_loam"),
        notes=(
            "Maize is most sensitive to water shortage at tasselling and silking; a single missed "
            "irrigation in this window can dominate season yield."
        ),
    ),
    "sorghum": CropRequirements(
        name="Sorghum",
        aliases=("jowar", "great millet", "sorghum bicolor"),
        ph_optimal=(5.5, 7.5),
        ph_tolerable=(5.0, 8.0),
        temp_optimal=(25.0, 32.0),
        temp_absolute_max=40.0,
        season_rainfall_mm=(400.0, 700.0),
        water_requirement_mm=(350.0, 550.0),
        moisture_optimal=(35.0, 55.0),
        moisture_critical=25.0,
        season="kharif / rabi",
        duration_days=(95, 130),
        critical_stages=("emergence", "booting", "flowering", "grain filling"),
        frost_sensitive=False,
        waterlogged_sensitive=True,
        heavy_rain_threshold_mm_3d=50.0,
        heat_stress_threshold_c=40.0,
        humidity_risk_threshold_percent=85.0,
        suitable_soils=("sandy_loam", "loam", "red_soil", "black_soil", "sandy"),
        notes="Sorghum is a drought-resilient crop suited to semi-arid tracts with erratic rainfall.",
    ),
    "cotton": CropRequirements(
        name="Cotton",
        aliases=("gossypium", "cottonseed"),
        ph_optimal=(6.0, 7.5),
        ph_tolerable=(5.5, 8.5),
        temp_optimal=(21.0, 30.0),
        temp_absolute_max=38.0,
        season_rainfall_mm=(600.0, 1200.0),
        water_requirement_mm=(700.0, 1100.0),
        moisture_optimal=(45.0, 70.0),
        moisture_critical=30.0,
        season="kharif",
        duration_days=(150, 210),
        critical_stages=("squaring", "flowering", "boll development"),
        frost_sensitive=False,
        waterlogged_sensitive=True,
        heavy_rain_threshold_mm_3d=60.0,
        heat_stress_threshold_c=37.0,
        humidity_risk_threshold_percent=88.0,
        suitable_soils=("black_soil", "alluvial", "clay_loam", "loam", "red_soil"),
        notes=(
            "Square and boll development stages are highly sensitive to both moisture deficit and boll rot "
            "after wet spells."
        ),
    ),
    "groundnut": CropRequirements(
        name="Groundnut",
        aliases=("peanut", "arachis hypogaea"),
        ph_optimal=(6.0, 7.5),
        ph_tolerable=(5.5, 8.0),
        temp_optimal=(25.0, 32.0),
        temp_absolute_max=38.0,
        season_rainfall_mm=(400.0, 600.0),
        water_requirement_mm=(350.0, 500.0),
        moisture_optimal=(40.0, 60.0),
        moisture_critical=25.0,
        season="kharif",
        duration_days=(100, 140),
        critical_stages=("germination", "flowering", "pod development", "pod filling"),
        frost_sensitive=False,
        waterlogged_sensitive=True,
        heavy_rain_threshold_mm_3d=45.0,
        heat_stress_threshold_c=36.0,
        humidity_risk_threshold_percent=88.0,
        suitable_soils=("sandy_loam", "red_soil", "sandy", "loam", "laterite"),
        notes="Excess water around the root zone causes red rot; a well-drained sandy loam is preferred.",
    ),
    "chickpea": CropRequirements(
        name="Chickpea",
        aliases=("gram", "garbanzo", "cicer arietinum"),
        ph_optimal=(6.0, 7.5),
        ph_tolerable=(5.5, 8.0),
        temp_optimal=(15.0, 25.0),
        temp_absolute_max=32.0,
        season_rainfall_mm=(300.0, 500.0),
        water_requirement_mm=(300.0, 450.0),
        moisture_optimal=(40.0, 60.0),
        moisture_critical=28.0,
        season="rabi",
        duration_days=(95, 125),
        critical_stages=("emergence", "branching", "flowering", "pod filling"),
        frost_sensitive=True,
        waterlogged_sensitive=True,
        heavy_rain_threshold_mm_3d=35.0,
        heat_stress_threshold_c=32.0,
        humidity_risk_threshold_percent=85.0,
        suitable_soils=("loam", "silt_loam", "clay_loam", "black_soil", "alluvial"),
        notes="Chickpea is largely grown on residual moisture; excess water causes damping off and wilt.",
    ),
    "tomato": CropRequirements(
        name="Tomato",
        aliases=("lycopersicon esculentum", "tamatar"),
        ph_optimal=(6.0, 7.0),
        ph_tolerable=(5.5, 7.5),
        temp_optimal=(18.0, 27.0),
        temp_absolute_max=35.0,
        season_rainfall_mm=(600.0, 1250.0),
        water_requirement_mm=(450.0, 700.0),
        moisture_optimal=(55.0, 75.0),
        moisture_critical=38.0,
        season="kharif / rabi / summer",
        duration_days=(110, 150),
        critical_stages=("establishment", "flowering", "fruit set", "fruit development"),
        frost_sensitive=True,
        waterlogged_sensitive=True,
        heavy_rain_threshold_mm_3d=30.0,
        heat_stress_threshold_c=33.0,
        humidity_risk_threshold_percent=88.0,
        suitable_soils=("loam", "sandy_loam", "silt_loam", "alluvial", "red_soil"),
        notes="Irregular moisture plus high humidity favours fruit rot; avoid overhead irrigation late in the day.",
    ),
    "soybean": CropRequirements(
        name="Soybean",
        aliases=("soya", "glycine max"),
        ph_optimal=(6.0, 7.5),
        ph_tolerable=(5.5, 8.0),
        temp_optimal=(22.0, 30.0),
        temp_absolute_max=36.0,
        season_rainfall_mm=(600.0, 1000.0),
        water_requirement_mm=(450.0, 700.0),
        moisture_optimal=(50.0, 70.0),
        moisture_critical=33.0,
        season="kharif",
        duration_days=(90, 120),
        critical_stages=("emergence", "flowering", "pod filling"),
        frost_sensitive=True,
        waterlogged_sensitive=True,
        heavy_rain_threshold_mm_3d=45.0,
        heat_stress_threshold_c=34.0,
        humidity_risk_threshold_percent=88.0,
        suitable_soils=("black_soil", "loam", "clay_loam", "alluvial", "silt_loam"),
        notes="Soybean fixes its own nitrogen but still needs a reliable supply of water at pod filling.",
    ),
    "pearl_millet": CropRequirements(
        name="Pearl Millet",
        aliases=("bajra", "pennisetum glaucum"),
        ph_optimal=(6.0, 7.5),
        ph_tolerable=(5.5, 8.5),
        temp_optimal=(25.0, 32.0),
        temp_absolute_max=42.0,
        season_rainfall_mm=(300.0, 600.0),
        water_requirement_mm=(250.0, 400.0),
        moisture_optimal=(30.0, 50.0),
        moisture_critical=20.0,
        season="kharif",
        duration_days=(75, 100),
        critical_stages=("emergence", "tillering", "grain filling"),
        frost_sensitive=False,
        waterlogged_sensitive=True,
        heavy_rain_threshold_mm_3d=50.0,
        heat_stress_threshold_c=40.0,
        humidity_risk_threshold_percent=85.0,
        suitable_soils=("sandy", "sandy_loam", "red_soil", "red_laterite", "loam"),
        notes="Highly heat and drought tolerant; grows on light soils with low fertility.",
    ),
    "finger_millet": CropRequirements(
        name="Finger Millet",
        aliases=("ragi", "mandua", "eleusine coracana"),
        ph_optimal=(5.5, 7.5),
        ph_tolerable=(5.0, 8.0),
        temp_optimal=(20.0, 30.0),
        temp_absolute_max=36.0,
        season_rainfall_mm=(400.0, 600.0),
        water_requirement_mm=(300.0, 450.0),
        moisture_optimal=(40.0, 60.0),
        moisture_critical=25.0,
        season="kharif / summer",
        duration_days=(85, 110),
        critical_stages=("emergence", "tillering", "grain filling"),
        frost_sensitive=True,
        waterlogged_sensitive=True,
        heavy_rain_threshold_mm_3d=45.0,
        heat_stress_threshold_c=35.0,
        humidity_risk_threshold_percent=85.0,
        suitable_soils=("red_soil", "sandy_loam", "loam", "laterite", "sandy"),
        notes="Finger millet is a staple in rainfed tracts and stores well as grain.",
    ),
    "pigeonpea": CropRequirements(
        name="Pigeonpea",
        aliases=("tur", "arhar", "cajanus cajan"),
        ph_optimal=(6.0, 7.5),
        ph_tolerable=(5.5, 8.0),
        temp_optimal=(24.0, 33.0),
        temp_absolute_max=38.0,
        season_rainfall_mm=(500.0, 800.0),
        water_requirement_mm=(350.0, 500.0),
        moisture_optimal=(40.0, 60.0),
        moisture_critical=27.0,
        season="kharif",
        duration_days=(150, 200),
        critical_stages=("flowering", "pod development", "pod filling"),
        frost_sensitive=True,
        waterlogged_sensitive=True,
        heavy_rain_threshold_mm_3d=45.0,
        heat_stress_threshold_c=36.0,
        humidity_risk_threshold_percent=85.0,
        suitable_soils=("black_soil", "red_soil", "loam", "clay_loam", "laterite"),
        notes="Pigeonpea is deep rooted and drought tolerant once established.",
    ),
    "mustard": CropRequirements(
        name="Mustard",
        aliases=("rapeseed", "canola", "brassica juncea"),
        ph_optimal=(6.0, 7.5),
        ph_tolerable=(5.5, 8.0),
        temp_optimal=(15.0, 25.0),
        temp_absolute_max=30.0,
        season_rainfall_mm=(300.0, 450.0),
        water_requirement_mm=(250.0, 400.0),
        moisture_optimal=(40.0, 60.0),
        moisture_critical=28.0,
        season="rabi",
        duration_days=(100, 130),
        critical_stages=("establishment", "rosette", "flowering", "pod filling"),
        frost_sensitive=True,
        waterlogged_sensitive=True,
        heavy_rain_threshold_mm_3d=30.0,
        heat_stress_threshold_c=30.0,
        humidity_risk_threshold_percent=88.0,
        suitable_soils=("loam", "silt_loam", "clay_loam", "alluvial", "black_soil"),
        notes="Terminal heat and moisture stress at pod filling cause severe yield loss.",
    ),
    "potato": CropRequirements(
        name="Potato",
        aliases=("aloo", "solanum tuberosum"),
        ph_optimal=(5.0, 6.5),
        ph_tolerable=(4.5, 7.0),
        temp_optimal=(15.0, 22.0),
        temp_absolute_max=30.0,
        season_rainfall_mm=(500.0, 750.0),
        water_requirement_mm=(350.0, 550.0),
        moisture_optimal=(55.0, 75.0),
        moisture_critical=40.0,
        season="rabi / kharif",
        duration_days=(80, 120),
        critical_stages=("sprout development", "stolon growth", "tuber initiation", "bulking"),
        frost_sensitive=True,
        waterlogged_sensitive=True,
        heavy_rain_threshold_mm_3d=30.0,
        heat_stress_threshold_c=28.0,
        humidity_risk_threshold_percent=90.0,
        suitable_soils=("sandy_loam", "loam", "silt_loam", "red_soil", "alluvial"),
        notes=(
            "Potato prefers a slightly acidic, well-aerated soil; tuber quality falls sharply when soil pH "
            "exceeds 7.0 (tuber blotch)."
        ),
    ),
}

CROP_ALIAS_INDEX: dict[str, str] = {
    alias: key for key, req in CROP_REQUIREMENTS.items() for alias in (key, req.name.lower(), *req.aliases)
}

CROP_NAMES: list[str] = [req.name for req in CROP_REQUIREMENTS.values()]


def resolve_crop(name: str | None) -> CropRequirements | None:
    """Resolve a free-text crop name to its requirement envelope."""
    if not name:
        return None
    key = CROP_ALIAS_INDEX.get(name.strip().lower())
    return CROP_REQUIREMENTS.get(key) if key else None


def resolve_soil_type(soil_type: str | None) -> dict[str, float]:
    """Return the moisture/water-holding bands for a soil texture."""
    if not soil_type:
        return DEFAULT_TEXTURE_BANDS
    key = soil_type.strip().lower().replace(" ", "_").replace("-", "_")
    return TEXTURE_WATER_BANDS.get(key, DEFAULT_TEXTURE_BANDS)


def ph_class_for(ph: float | None) -> str:
    """Map a measured pH to its agronomic class."""
    if ph is None:
        return "unknown"
    for name, (low, high) in PH_CLASSES.items():
        if low <= ph < high:
            return name
    return "strongly_alkaline" if ph >= 8.5 else "strongly_acidic"


def nutrient_status_for(parameter: str, value: float | None) -> str:
    """Rate an available-nutrient measurement as low / medium / high."""
    if value is None:
        return "unknown"
    bands = NUTRIENT_THRESHOLDS.get(parameter)
    if bands is None:
        return "unknown"
    if value < bands["low_max"]:
        return "low"
    if value < bands["medium_max"]:
        return "medium"
    return "high"


# ---------------------------------------------------------------------------
# Risk thresholds (climate driven)
# ---------------------------------------------------------------------------

HEAT_STRESS_TEMP_C = 35.0
SEVERE_HEAT_TEMP_C = 40.0
EXTENDED_DRY_DAYS = 14
LOW_MOISTURE_CRITICAL = 30.0
HIGH_HUMIDITY_DISEASE_RISK = 85.0
DISEASE_RISK_LEAF_WETNESS_PROXY = 0.75  # fraction of forecast days with rain or high humidity
HEAVY_RAINFALL_MM_3D = 50.0
SEVERE_RAINFALL_MM_3D = 100.0
WATERLOGGING_RISK_MM_3D = 80.0
