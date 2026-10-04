"""ORM model registry.

Importing this package registers every mapper on ``Base.metadata`` which is
required by ``create_all`` and by Alembic autogeneration.
"""

from app.models.assessment import IrrigationAssessment, MLPrediction, RiskFinding, SuitabilityAssessment
from app.models.base import Base, TimestampMixin, UTCDateTime, utcnow
from app.models.enums import (
    ActivityStatus,
    ActivityType,
    AlertStatus,
    AlertType,
    ApprovalStatus,
    CropStage,
    IrrigationRecommendation,
    MLTask,
    NutrientStatus,
    PhClass,
    RiskType,
    Severity,
    SourceKind,
    SuitabilityStatus,
    WorkflowStatus,
)
from app.models.farm import Farm, Field
from app.models.operations import Alert, FarmActivity, ReferenceDocument, Report, WaterBalanceRecord
from app.models.sensor import SensorReading
from app.models.soil import SoilInterpretation, SoilObservation
from app.models.weather import WeatherSnapshot
from app.models.workflow import AgentTrace, ApprovalRequest, WorkflowRun

__all__ = [
    "ActivityStatus",
    "ActivityType",
    "AgentTrace",
    "Alert",
    "AlertStatus",
    "AlertType",
    "ApprovalRequest",
    "ApprovalStatus",
    "Base",
    "CropStage",
    "Farm",
    "FarmActivity",
    "Field",
    "IrrigationAssessment",
    "IrrigationRecommendation",
    "MLPrediction",
    "MLTask",
    "NutrientStatus",
    "PhClass",
    "ReferenceDocument",
    "Report",
    "RiskFinding",
    "RiskType",
    "SensorReading",
    "Severity",
    "SoilInterpretation",
    "SoilObservation",
    "SourceKind",
    "SuitabilityAssessment",
    "SuitabilityStatus",
    "TimestampMixin",
    "UTCDateTime",
    "WaterBalanceRecord",
    "WeatherSnapshot",
    "WorkflowRun",
    "WorkflowStatus",
    "utcnow",
]
