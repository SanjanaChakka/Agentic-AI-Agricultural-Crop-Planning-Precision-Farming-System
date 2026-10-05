"""Router registry."""

from app.api.routers.analysis_router import (
    irrigation_router,
    ml_router,
    risk_router,
    suitability_router,
)
from app.api.routers.farm_router import router as farm_router
from app.api.routers.health_router import router as health_router
from app.api.routers.knowledge_router import router as knowledge_router
from app.api.routers.operations_router import activity_router, alert_router, approval_router
from app.api.routers.report_router import router as report_router
from app.api.routers.sensor_router import router as sensor_router
from app.api.routers.soil_router import router as soil_router
from app.api.routers.weather_router import router as weather_router
from app.api.routers.workflow_router import router as workflow_router

ALL_ROUTERS = (
    health_router,
    farm_router,
    soil_router,
    sensor_router,
    weather_router,
    suitability_router,
    irrigation_router,
    risk_router,
    ml_router,
    workflow_router,
    approval_router,
    activity_router,
    alert_router,
    report_router,
    knowledge_router,
)

__all__ = [
    "ALL_ROUTERS",
    "activity_router",
    "alert_router",
    "approval_router",
    "farm_router",
    "health_router",
    "irrigation_router",
    "knowledge_router",
    "ml_router",
    "report_router",
    "risk_router",
    "sensor_router",
    "soil_router",
    "suitability_router",
    "weather_router",
    "workflow_router",
]
