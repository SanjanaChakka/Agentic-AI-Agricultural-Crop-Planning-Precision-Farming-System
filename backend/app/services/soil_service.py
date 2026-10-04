"""Soil interpretation.

Hard rule of this module: it *reads* measured values and *writes* an
interpretation.  It never writes back to ``SoilObservation``.  Every conclusion
is accompanied by the measurement that produced it plus a citation to the
knowledge document that defines the threshold band.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.data.crop_catalog import (
    NUTRIENT_THRESHOLDS,
    PH_CLASS_LABELS,
    nutrient_status_for,
    ph_class_for,
    resolve_crop,
)
from app.models.enums import NutrientStatus, PhClass, SourceKind
from app.models.soil import SoilInterpretation, SoilObservation
from app.rag.retriever import get_retriever
from app.schemas.common import Evidence, SourceReference, sources_as_dicts

PH_DOC = "soil.soil_ph_and_fertility"
TEXTURE_DOC = "soil.texture_and_water_holding"

NUTRIENT_LABELS = {
    "nitrogen_available_kg_ha": "Available nitrogen (kg/ha)",
    "phosphorus_available_kg_ha": "Available phosphorus P2O5 (kg/ha)",
    "potassium_available_kg_ha": "Available potassium K2O (kg/ha)",
    "organic_carbon_percent": "Organic carbon (%)",
}

PH_ADVICE = {
    PhClass.STRONGLY_ACIDIC: (
        "Strongly acidic soil. Phosphorus is largely fixed and aluminium/manganese toxicity can limit roots. "
        "Plan a lime application based on a buffer capacity test and re-test after 4-6 months."
    ),
    PhClass.MODERATELY_ACIDIC: (
        "Moderately acidic soil - acceptable for most field crops. Confirm that the proposed crop tolerates "
        "this pH before deciding."
    ),
    PhClass.NEUTRAL: "Neutral soil - the most favourable reaction for the majority of field crops.",
    PhClass.MODERATELY_ALKALINE: (
        "Moderately alkaline soil. Iron, zinc and manganese availability falls; watch for micronutrient "
        "deficiency symptoms and avoid further liming."
    ),
    PhClass.STRONGLY_ALKALINE: (
        "Strongly alkaline soil - a major constraint. Most field crops are limited; plan gypsum or sulphur "
        "amendment only after a specialist review and confirm whether the field should move to a "
        "tolerant crop."
    ),
}

NUTRIENT_ADVICE = {
    NutrientStatus.LOW: "Apply the crop-recommended dose, split across the season for nitrogen.",
    NutrientStatus.MEDIUM: "Maintain with a maintenance dose; no corrective action is required.",
    NutrientStatus.HIGH: "Sufficient - do not apply additional doses without a fresh soil test.",
}


def _ph_class(ph: float | None) -> str:
    return ph_class_for(ph)


def _nutrient_status(parameter: str, value: float | None) -> str:
    return nutrient_status_for(parameter, value)


def soil_thresholds_payload() -> dict:
    """Transparent export of every rating band the system applies."""
    return {
        "nitrogen_available_kg_ha": NUTRIENT_THRESHOLDS["nitrogen_available_kg_ha"],
        "phosphorus_available_kg_ha": NUTRIENT_THRESHOLDS["phosphorus_available_kg_ha"],
        "potassium_available_kg_ha": NUTRIENT_THRESHOLDS["potassium_available_kg_ha"],
        "organic_carbon_percent": NUTRIENT_THRESHOLDS["organic_carbon_percent"],
        "ph_classes": PH_CLASS_LABELS,
    }


def missing_parameters(observation: SoilObservation, *, crop: str | None = None) -> list[str]:
    """Parameters that are not present in this measurement."""
    measured = observation.measured_payload()
    missing = [name for name, value in measured.items() if value is None]
    if crop and observation.ph is None:
        missing.append("ph (required to confirm crop pH tolerance)")
    return missing


def interpret_observation(
    observation: SoilObservation,
    *,
    crop: str | None = None,
    persist: bool = False,
) -> SoilInterpretation:
    """Build (and optionally persist) an interpretation of a measured observation."""
    ph_value = observation.ph
    ph_class = _ph_class(ph_value)

    nutrient_status: dict[str, str] = {}
    evidence: list[Evidence] = []
    limitations: list[str] = []
    recommendations: list[dict] = []
    sources: list[SourceReference] = []

    retriever = get_retriever()
    for reference in retriever.retrieve_document(PH_DOC):
        sources.append(reference)

    # --- pH -------------------------------------------------------------
    if ph_value is None:
        limitations.append("Soil pH was not measured, so reaction class and nutrient availability cannot be judged.")
    else:
        evidence.append(
            Evidence(
                label="Measured soil pH",
                value=ph_value,
                kind=SourceKind.MEASURED,
                source=observation.data_source,
                reference=PH_DOC,
                note=PH_CLASS_LABELS.get(ph_class),
                observed_at=observation.observed_at,
            )
        )
        requirements = resolve_crop(crop)
        if requirements is not None:
            low, high = requirements.ph_optimal
            if not (low - 0.5 <= ph_value <= high + 0.5):
                limitations.append(
                    f"Measured pH {ph_value} sits outside the optimal {low}-{high} band for {requirements.name}."
                )
                evidence.append(
                    Evidence(
                        label=f"{requirements.name} optimal pH band",
                        value=f"{low}-{high}",
                        kind=SourceKind.RETRIEVED_REFERENCE,
                        source=requirements.doc(),
                        reference=requirements.doc(),
                    )
                )
        if ph_class != PhClass.NEUTRAL:
            recommendations.append(
                {
                    "action": "Amend soil reaction",
                    "detail": PH_ADVICE.get(ph_class, ""),
                    "priority": "high"
                    if ph_class in {PhClass.STRONGLY_ACIDIC, PhClass.STRONGLY_ALKALINE}
                    else "medium",
                    "basis": "soil pH class",
                }
            )

    # --- nutrients ------------------------------------------------------
    for parameter, label in NUTRIENT_LABELS.items():
        value = getattr(observation, parameter, None)
        status = _nutrient_status(parameter, value)
        nutrient_status[parameter] = status
        if value is None:
            limitations.append(f"{label} was not measured.")
            continue

        bands = NUTRIENT_THRESHOLDS[parameter]
        evidence.append(
            Evidence(
                label=f"Measured {label}",
                value=value,
                kind=SourceKind.MEASURED,
                source=observation.data_source,
                reference=PH_DOC,
                note=f"rated {status} (low below {bands['low_max']}, high above {bands['medium_max']})",
                observed_at=observation.observed_at,
            )
        )
        if status == NutrientStatus.LOW:
            recommendations.append(
                {
                    "action": f"Address low {label.split(' (')[0].lower()}",
                    "detail": NUTRIENT_ADVICE[NutrientStatus.LOW],
                    "priority": "high" if parameter == "organic_carbon_percent" else "medium",
                    "basis": f"soil test rating: {status}",
                }
            )
        elif status == NutrientStatus.HIGH:
            recommendations.append(
                {
                    "action": f"Skip additional {label.split(' (')[0].lower()}",
                    "detail": NUTRIENT_ADVICE[NutrientStatus.HIGH],
                    "priority": "low",
                    "basis": f"soil test rating: {status}",
                }
            )

    if (
        observation.organic_carbon_percent is not None
        and nutrient_status.get("organic_carbon_percent") == NutrientStatus.LOW
    ):
        for reference in retriever.retrieve_document(TEXTURE_DOC):
            sources.append(reference)
        recommendations.append(
            {
                "action": "Build organic matter",
                "detail": "Low organic carbon reduces water-holding capacity and nutrient buffering. "
                "Incorporate compost or crop residue and consider a green manure.",
                "priority": "medium",
                "basis": "organic carbon rating: low",
            }
        )

    if observation.soil_moisture_percent is None:
        limitations.append("Soil moisture was not measured, so current water status is unknown.")
    else:
        evidence.append(
            Evidence(
                label="Measured soil moisture",
                value=observation.soil_moisture_percent,
                unit="% VWC",
                kind=SourceKind.MEASURED,
                source=observation.data_source,
                reference=TEXTURE_DOC,
                observed_at=observation.observed_at,
            )
        )

    if observation.electrical_conductivity_ds_m is not None:
        evidence.append(
            Evidence(
                label="Measured electrical conductivity",
                value=observation.electrical_conductivity_ds_m,
                unit="dS/m",
                kind=SourceKind.MEASURED,
                source=observation.data_source,
                note="Salinity indicator; values above 2 dS/m begin to restrict most field crops.",
                observed_at=observation.observed_at,
            )
        )
    else:
        limitations.append("Electrical conductivity was not measured, so salinity status is unknown.")

    summary = _build_summary(observation, ph_class, nutrient_status, limitations)
    present = sum(1 for value in observation.measured_payload().values() if value is not None)
    confidence = round(present / 7.0, 2)

    interpretation = SoilInterpretation(
        soil_observation_id=observation.id,
        agent_name="soil_nutrient_analysis_agent",
        generated_by="rule+retrieval",
        ph_class=ph_class,
        nutrient_status=nutrient_status,
        organic_matter_status=nutrient_status.get("organic_carbon_percent", "unknown"),
        summary=summary,
        limitations=limitations,
        recommendations=recommendations,
        missing_parameters=missing_parameters(observation, crop=crop),
        evidence=[item.model_dump() for item in evidence],
        sources=sources_as_dicts(sources),
        confidence=confidence,
    )

    if persist:
        existing = observation.interpretation
        if existing is not None:
            for key, value in (
                ("ph_class", interpretation.ph_class),
                ("nutrient_status", interpretation.nutrient_status),
                ("organic_matter_status", interpretation.organic_matter_status),
                ("summary", interpretation.summary),
                ("limitations", interpretation.limitations),
                ("recommendations", interpretation.recommendations),
                ("missing_parameters", interpretation.missing_parameters),
                ("evidence", interpretation.evidence),
                ("sources", interpretation.sources),
                ("confidence", interpretation.confidence),
            ):
                setattr(existing, key, value)
            interpretation = existing
        else:
            observation.interpretation = interpretation

    return interpretation


def _build_summary(
    observation: SoilObservation,
    ph_class: str,
    nutrient_status: dict[str, str],
    limitations: list[str],
) -> str:
    parts: list[str] = []
    if observation.ph is not None:
        parts.append(f"Measured pH is {observation.ph} ({PH_CLASS_LABELS.get(ph_class, ph_class)}).")
    else:
        parts.append("Soil pH was not measured.")

    lows = [label for parameter, label in NUTRIENT_LABELS.items() if nutrient_status.get(parameter) == "low"]
    if lows:
        parts.append("Low: " + ", ".join(lows) + ".")
    mediums = [label for parameter, label in NUTRIENT_LABELS.items() if nutrient_status.get(parameter) == "medium"]
    if mediums:
        parts.append("Medium: " + ", ".join(mediums) + ".")

    if observation.ph is not None and ph_class in PH_ADVICE:
        parts.append(PH_ADVICE[ph_class])

    if limitations:
        parts.append(f"{len(limitations)} parameter(s) are missing, so this interpretation is partial.")
    return " ".join(part for part in parts if part)


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------


def get_observation(db: Session, observation_id: int) -> SoilObservation:
    observation = db.get(SoilObservation, observation_id)
    if observation is None:
        raise NotFoundError(message=f"Soil observation {observation_id} was not found.")
    return observation


def latest_observation(db: Session, field_id: int) -> SoilObservation | None:
    statement = (
        select(SoilObservation)
        .where(SoilObservation.field_id == field_id)
        .order_by(SoilObservation.observed_at.desc(), SoilObservation.id.desc())
    )
    return db.execute(statement).scalars().first()


def latest_observation_before(db: Session, field_id: int, *, before: datetime) -> SoilObservation | None:
    statement = (
        select(SoilObservation)
        .where(SoilObservation.field_id == field_id, SoilObservation.observed_at <= before)
        .order_by(SoilObservation.observed_at.desc(), SoilObservation.id.desc())
    )
    return db.execute(statement).scalars().first()


def observation_evidence(observation: SoilObservation) -> list[Evidence]:
    """Evidence block for a raw measurement, used across agent outputs."""
    labels = {
        "ph": "Measured soil pH",
        "nitrogen_available_kg_ha": "Measured available nitrogen",
        "phosphorus_available_kg_ha": "Measured available phosphorus (P2O5)",
        "potassium_available_kg_ha": "Measured available potassium (K2O)",
        "organic_carbon_percent": "Measured organic carbon",
        "soil_moisture_percent": "Measured soil moisture",
        "electrical_conductivity_ds_m": "Measured electrical conductivity",
    }
    units = {"soil_moisture_percent": "% VWC", "electrical_conductivity_ds_m": "dS/m"}
    evidence: list[Evidence] = []
    for key, label in labels.items():
        value = getattr(observation, key, None)
        if value is None:
            continue
        evidence.append(
            Evidence(
                label=label,
                value=value,
                unit=units.get(key),
                kind=SourceKind.MEASURED,
                source=observation.data_source,
                observed_at=observation.observed_at,
            )
        )
    return evidence


def register_reference_documents(db: Session) -> int:
    """Persist the ingested corpus so /knowledge/sources can list it."""
    from app.models.operations import ReferenceDocument

    retriever = get_retriever()
    documents = retriever.documents
    existing = {doc.doc_key: doc for doc in db.execute(select(ReferenceDocument)).scalars()}
    count = 0
    for meta in documents:
        row = existing.get(meta.doc_key)
        if row is None:
            db.add(
                ReferenceDocument(
                    doc_key=meta.doc_key,
                    title=meta.title,
                    category=meta.category,
                    organisation=meta.organisation,
                    source_url=meta.source_url,
                    region=meta.region,
                    chunk_count=0,
                    checksum=meta.checksum,
                    is_active=True,
                )
            )
            count += 1
        elif row.checksum != meta.checksum or row.title != meta.title:
            row.title = meta.title
            row.category = meta.category
            row.organisation = meta.organisation
            row.source_url = meta.source_url
            row.region = meta.region
            row.checksum = meta.checksum
            count += 1

    chunk_counts: dict[str, int] = {}
    for chunk in retriever.chunks:
        chunk_counts[chunk.doc_key] = chunk_counts.get(chunk.doc_key, 0) + 1
    for row in db.execute(select(ReferenceDocument)).scalars():
        row.chunk_count = chunk_counts.get(row.doc_key, 0)

    return count
