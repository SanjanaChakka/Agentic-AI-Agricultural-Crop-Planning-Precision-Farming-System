"""Deterministic demonstration data.

Seeding creates a realistic but entirely clearly-labelled demo estate so that a
fresh clone shows a working system on first load.  Everything it writes is
marked with ``data_source='demo_seed'`` or ``is_simulated=True`` so it can never
be confused with real observations.

The data set is realistic for a semi-arid Indian farming district (Karnataka /
Telangana black-cotton region): two farms, five fields, a lab-style soil test
per field, a week of simulated sensor telemetry and the reference-document
registry for the RAG corpus.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.data.crop_catalog import resolve_soil_type
from app.models.farm import Farm, Field
from app.models.soil import SoilObservation
from app.services.sensor_service import simulate_readings
from app.services.soil_service import interpret_observation, register_reference_documents

logger = get_logger(__name__)

SEED_SENSOR_SEED = 20240517


def seed_if_empty(db: Session) -> dict[str, int]:
    """Populate the database only when no farm exists yet.  Safe to call on boot."""
    farm_count = db.scalar(select(func.count()).select_from(Farm)) or 0
    if farm_count:
        return {"seeded": 0, "reason": "database already contains farms"}

    counts = _seed(db)
    logger.info("Seeded demonstration data: %s", counts)
    return counts


def _seed(db: Session) -> dict[str, int]:
    now = datetime.now(UTC)

    farms: list[Farm] = [
        Farm(
            name="Ravi Kisan Farms",
            owner_name="Ravi Kumar",
            location_name="Raichur, Karnataka",
            latitude=16.21,
            longitude=77.36,
            village="Gowribiddanahal",
            district="Raichur",
            state="Karnataka",
            total_area_ha=10.4,
            notes="Demonstration farm. Soil and telemetry values are simulated unless stated as measured.",
        ),
        Farm(
            name="Sanjana Agro Estate",
            owner_name="Sanjana Reddy",
            location_name="Jangaon, Telangana",
            latitude=17.51,
            longitude=78.79,
            village="Cheepurupalli",
            district="Vikarabad",
            state="Telangana",
            total_area_ha=6.8,
            notes="Demonstration farm used for the sandy-loam / tank-irrigated scenario.",
        ),
    ]
    db.add_all(farms)
    db.flush()

    fields: list[Field] = [
        Field(
            farm_id=farms[0].id,
            field_code="RKF-01",
            name="North Black Cotton Plot",
            area_ha=4.2,
            soil_type="black_soil",
            previous_crop="cotton",
            proposed_crop="cotton",
            crop_stage="flowering",
            irrigation_source="borewell",
            water_availability="moderate",
            water_availability_m3_per_day=180.0,
            notes="Vertisol with high clay content; irrigate only on measured depletion.",
        ),
        Field(
            farm_id=farms[0].id,
            field_code="RKF-02",
            name="Tank-fed Red Laterite Plot",
            area_ha=2.6,
            soil_type="red_laterite",
            previous_crop="groundnut",
            proposed_crop="sorghum",
            crop_stage="vegetative",
            irrigation_source="tank",
            water_availability="limited",
            water_availability_m3_per_day=70.0,
            notes="Low water-holding capacity; sorghum chosen for drought tolerance.",
        ),
        Field(
            farm_id=farms[0].id,
            field_code="RKF-03",
            name="Canal-fed Wheat Plot",
            area_ha=3.6,
            soil_type="alluvial",
            previous_crop="rice",
            proposed_crop="wheat",
            crop_stage="maturity",
            irrigation_source="canal",
            water_availability="abundant",
            water_availability_m3_per_day=260.0,
            notes="Post-ri rabi plot receiving canal water.",
        ),
        Field(
            farm_id=farms[1].id,
            field_code="SAE-01",
            name="Sandy Loam Onion Plot",
            area_ha=2.2,
            soil_type="sandy_loam",
            previous_crop="onion",
            proposed_crop="groundnut",
            crop_stage="sowing",
            irrigation_source="drip",
            water_availability="seasonal",
            water_availability_m3_per_day=95.0,
            notes="Drip irrigated; sandy loam drains fast and needs frequent short cycles.",
        ),
        Field(
            farm_id=farms[1].id,
            field_code="SAE-02",
            name="Loam Pigeonpea Plot",
            area_ha=2.1,
            soil_type="loam",
            previous_crop="maize",
            proposed_crop="pigeonpea",
            crop_stage="vegetative",
            irrigation_source="rainfed",
            water_availability="none",
            notes="Fully rainfed intercrop plot.",
        ),
    ]
    db.add_all(fields)
    db.flush()

    # ------------------------------------------------------------------
    # Soil observations - values chosen to exercise every branch of the
    # soil / suitability agents.  Stored as measured values with an explicit
    # demo data source.
    # ------------------------------------------------------------------
    soil_specs = {
        "RKF-01": {
            "ph": 7.9,
            "n": 248.0,
            "p": 22.0,
            "k": 312.0,
            "oc": 0.62,
            "moisture": 23.5,
            "ec": 0.42,
            "depth": 15.0,
        },
        "RKF-02": {
            "ph": 5.6,
            "n": 176.0,
            "p": 11.0,
            "k": 148.0,
            "oc": 0.41,
            "moisture": 15.2,
            "ec": 0.31,
            "depth": 15.0,
        },
        "RKF-03": {
            "ph": 7.2,
            "n": 312.0,
            "p": 28.0,
            "k": 196.0,
            "oc": 0.55,
            "moisture": 31.4,
            "ec": 0.24,
            "depth": 20.0,
        },
        "SAE-01": {
            "ph": 6.8,
            "n": 205.0,
            "p": 44.0,
            "k": 132.0,
            "oc": 0.38,
            "moisture": 18.7,
            "ec": 0.19,
            "depth": 15.0,
        },
        "SAE-02": {"ph": 6.5, "n": 96.0, "p": 9.0, "k": 74.0, "oc": 0.29, "moisture": 27.9, "ec": 0.27, "depth": 20.0},
    }
    observation_count = 0
    for field in fields:
        spec = soil_specs[field.field_code]
        observation = SoilObservation(
            field_id=field.id,
            observed_at=now - timedelta(days=12),
            sample_depth_cm=spec["depth"],
            soil_type=field.soil_type,
            ph=spec["ph"],
            nitrogen_available_kg_ha=spec["n"],
            phosphorus_available_kg_ha=spec["p"],
            potassium_available_kg_ha=spec["k"],
            organic_carbon_percent=spec["oc"],
            soil_moisture_percent=spec["moisture"],
            electrical_conductivity_ds_m=spec["ec"],
            data_source="demo_seed",
            lab_name="District Agricultural Laboratory (demonstration record)",
            notes="Demonstration soil test generated by the application seed, not a real laboratory report.",
        )
        db.add(observation)
        db.flush()
        interpret_observation(observation, crop=field.proposed_crop, persist=True)
        observation_count += 1

    # ------------------------------------------------------------------
    # Sensor telemetry (clearly flagged as simulated)
    # ------------------------------------------------------------------
    reading_count = 0
    for index, field in enumerate(fields):
        bands = resolve_soil_type(field.soil_type)
        start_moisture = min(
            max(soil_specs[field.field_code]["moisture"], bands["refill_trigger"] - 4.0), bands["field_capacity"] - 6.0
        )
        readings = simulate_readings(
            db,
            field,
            hours=72,
            interval_hours=2.0,
            sensor_id=f"SM-{index + 1:02d}",
            seed=SEED_SENSOR_SEED + index,
            initial_soil_moisture_percent=round(start_moisture, 2),
            rainfall_events=index != 2,
            inject_fault=index == 1,
        )
        reading_count += len(readings)

    documents = register_reference_documents(db)
    db.flush()

    return {
        "seeded": 1,
        "farms": len(farms),
        "fields": len(fields),
        "soil_observations": observation_count,
        "sensor_readings": reading_count,
        "reference_documents": documents,
    }
