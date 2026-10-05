"""Enumerations shared by ORM models, schemas and services."""

from __future__ import annotations

from enum import Enum


class SuitabilityStatus(str, Enum):
    SUITABLE = "suitable"
    SUITABLE_WITH_CONDITIONS = "suitable_with_conditions"
    ADDITIONAL_INFORMATION_REQUIRED = "additional_information_required"
    AGRONOMIC_REVIEW_REQUIRED = "agronomic_review_required"


class IrrigationRecommendation(str, Enum):
    IRRIGATE_SOON = "consider_irrigation"
    POSTPONE_IRRIGATION = "consider_postponing_irrigation"
    NO_IRRIGATION_NEEDED = "no_irrigation_needed"
    REVIEW_REQUIRED = "review_required"
    INSUFFICIENT_INFORMATION = "insufficient_information"


class RiskType(str, Enum):
    HEAT_STRESS = "heat_stress"
    WATER_STRESS = "water_stress"
    EXCESSIVE_RAINFALL = "excessive_rainfall"
    EXTENDED_DRY_PERIOD = "extended_dry_period"
    DISEASE_FAVOURABLE_ENVIRONMENT = "disease_favourable_environment"
    SENSOR_FAULT = "sensor_fault"


class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class WorkflowStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_HUMAN_REVIEW = "awaiting_human_review"
    COMPLETED = "completed"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"
    FAILED = "failed"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFIED = "modified"


class ActivityStatus(str, Enum):
    PLANNED = "planned"
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ActivityType(str, Enum):
    FIELD_PREPARATION = "field_preparation"
    SOWING = "sowing"
    IRRIGATION = "irrigation"
    SOIL_TESTING = "soil_testing"
    CROP_OBSERVATION = "crop_observation"
    NUTRIENT_APPLICATION = "nutrient_application"
    HARVEST_PLANNING = "harvest_planning"
    FIELD_SCROUTING = "field_scouting"


class AlertStatus(str, Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class AlertType(str, Enum):
    LOW_SOIL_MOISTURE = "low_soil_moisture"
    HEAVY_RAINFALL = "heavy_rainfall"
    HIGH_TEMPERATURE = "high_temperature"
    SENSOR_MALFUNCTION = "sensor_malfunction"
    WATER_STRESS = "water_stress"
    DISEASE_RISK_ENVIRONMENT = "disease_risk_environment"


class SourceKind(str, Enum):
    """Provenance tag for every piece of evidence in the system."""

    MEASURED = "measured"
    OBSERVED = "observed"
    FORECAST = "forecast"
    RETRIEVED_REFERENCE = "retrieved_reference"
    RULE = "rule"
    ML_PREDICTION = "ml_prediction"
    LLM_NARRATIVE = "llm_narrative"
    DETERMINISTIC_NARRATIVE = "deterministic_narrative"
    USER_INPUT = "user_input"
    SIMULATED = "simulated"


class NutrientStatus(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


class PhClass(str, Enum):
    STRONGLY_ACIDIC = "strongly_acidic"
    MODERATELY_ACIDIC = "moderately_acidic"
    NEUTRAL = "neutral"
    MODERATELY_ALKALINE = "moderately_alkaline"
    STRONGLY_ALKALINE = "strongly_alkaline"
    UNKNOWN = "unknown"


class MLTask(str, Enum):
    SOIL_MOISTURE_FORECAST = "soil_moisture_forecast"
    ENVIRONMENTAL_RISK_CLASSIFICATION = "environmental_risk_classification"
    IRRIGATION_DEMAND = "irrigation_demand"


class CropStage(str, Enum):
    SOWING = "sowing"
    EMERGENCE = "emergence"
    VEGETATIVE = "vegetative"
    FLOWERING = "flowering"
    FRUITING = "fruiting"
    MATURITY = "maturity"
    POST_HARVEST = "post_harvest"
    UNKNOWN = "unknown"
