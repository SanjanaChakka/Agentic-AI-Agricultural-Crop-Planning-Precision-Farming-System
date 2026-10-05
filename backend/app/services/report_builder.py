"""Builds the structured section list the PDF renderer consumes.

This is the bridge between the workflow state (JSON) and
:mod:`app.services.report_service`.  It performs no analysis of its own - every
value it prints was computed by an agent or a service.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from reportlab.lib.units import mm

from app.core.logging import get_logger
from app.models.farm import Farm, Field
from app.models.workflow import WorkflowRun
from app.services import risk_service

logger = get_logger(__name__)


def build_sections(
    *,
    field: Field,
    farm: Farm | None,
    run: WorkflowRun | None,
    state: dict[str, Any],
    generated_at: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Return ``(header_context, sections)`` for the PDF renderer."""
    soil = state.get("soil") or {}
    weather = state.get("weather") or {}
    suitability = state.get("suitability") or {}
    irrigation = state.get("irrigation") or {}
    risk = state.get("risk") or {}
    telemetry = state.get("telemetry") or {}
    advisory = state.get("advisory") or {}
    approval = state.get("approval") or {}
    ml_predictions = state.get("ml_predictions") or []
    activities = state.get("activities") or []
    alerts = state.get("alerts") or []

    context: dict[str, Any] = {
        "farm_name": farm.name if farm else "-",
        "field_name": field.name,
        "field_code": field.field_code,
        "crop": (run.crop if run else None) or field.proposed_crop or "-",
        "area_ha": field.area_ha,
        "soil_type": field.soil_type,
        "location_name": farm.location_name if farm else "-",
        "latitude": field.effective_latitude,
        "longitude": field.effective_longitude,
        "workflow_run_id": run.id if run else "not applicable",
        "status": run.status if run else "not applicable",
        "agents_invoked": list(run.agents_invoked) if run else [],
        "weather_source": weather.get("provider") or "not fetched",
        "weather_simulated": weather.get("is_simulated"),
        "generated_at": generated_at or datetime.now(UTC).isoformat(timespec="seconds"),
    }

    sections: list[dict[str, Any]] = [
        _executive_section(state, advisory, approval, risk, irrigation, suitability, weather),
        _soil_section(soil, suitability),
        _weather_section(weather, telemetry),
        _suitability_section(suitability),
        _irrigation_section(irrigation),
        _risk_section(risk),
        _ml_section(ml_predictions),
        _operations_section(activities, alerts, approval),
        _evidence_section(state),
    ]
    return context, sections


# ----------------------------------------------------------------------
def _executive_section(state, advisory, approval, risk, irrigation, suitability, weather) -> dict[str, Any]:  # noqa: ANN001
    rows = [["Item", "Outcome"]]
    rows.append(["Crop suitability", f"{suitability.get('status', 'not assessed')} (score {suitability.get('score')})"])
    rows.append(
        [
            "Irrigation proposal",
            f"{irrigation.get('recommendation', 'not assessed')} - "
            f"{irrigation.get('estimated_water_mm')} mm, urgency {irrigation.get('urgency')}",
        ]
    )
    rows.append(
        ["Environmental risk", f"{risk.get('risk_level', 'unknown')} ({len(risk.get('findings') or [])} finding(s))"]
    )
    rows.append(["Weather source", f"{weather.get('provider', '-')} (simulated: {weather.get('is_simulated')})"])
    rows.append(["Human approval", f"{approval.get('status', 'no approval request')} - {approval.get('title', '-')}"])
    rows.append(["Agents invoked", ", ".join(state.get("agents_invoked") or []) or "-"])

    blocks: list[dict[str, Any]] = [
        {
            "kind": "paragraph",
            "text": str(advisory.get("advisory") or "No advisory narrative was produced for this field."),
        },
        {"kind": "table", "rows": rows, "header": True, "widths": [42 * mm, None]},
    ]
    if approval.get("status") == "pending":
        blocks.append(
            {
                "kind": "callout",
                "text": (
                    "AWAITING HUMAN APPROVAL. This report is a proposal. No irrigation or other physical "
                    "action may be carried out until a reviewer approves the plan in the system."
                ),
            }
        )
    if state.get("warnings"):
        blocks.append({"kind": "h2", "text": "Run warnings"})
        blocks.append({"kind": "bullets", "items": [str(item) for item in state["warnings"]]})

    return {"title": "1. Executive summary", "blocks": blocks}


def _soil_section(soil: dict[str, Any], suitability: dict[str, Any]) -> dict[str, Any]:
    if not soil.get("available"):
        return {
            "title": "2. Measured soil values",
            "blocks": [
                {
                    "kind": "paragraph",
                    "text": (
                        "No soil observation is on record for this field. No soil values have been inferred or "
                        "invented; the assessments above rely on soil-texture defaults and are flagged accordingly."
                    ),
                }
            ],
        }

    measured = soil.get("measured") or {}
    interpretation = soil.get("interpretation") or {}
    measured_rows = [
        ["Parameter", "Measured value", "Unit", "Data source"],
        ["pH", measured.get("ph"), "pH units", soil.get("data_source")],
        ["Available nitrogen", measured.get("nitrogen_available_kg_ha"), "kg/ha", soil.get("data_source")],
        ["Available phosphorus", measured.get("phosphorus_available_kg_ha"), "kg/ha", soil.get("data_source")],
        ["Available potassium", measured.get("potassium_available_kg_ha"), "kg/ha", soil.get("data_source")],
        ["Organic carbon", measured.get("organic_carbon_percent"), "%", soil.get("data_source")],
        ["Soil moisture at sampling", measured.get("soil_moisture_percent"), "% VWC", soil.get("data_source")],
        ["Electrical conductivity", measured.get("electrical_conductivity_ds_m"), "dS/m", soil.get("data_source")],
        ["Sample depth", soil.get("sample_depth_cm"), "cm", soil.get("data_source")],
        ["Observed at", soil.get("observed_at"), "", soil.get("lab_name") or soil.get("data_source")],
    ]

    blocks: list[dict[str, Any]] = [
        {
            "kind": "callout",
            "text": (
                "MEASURED VALUES - reproduced exactly as supplied by "
                f"{soil.get('data_source')}. The AI layer never modifies these numbers; everything in the next "
                "block is interpretation."
            ),
        },
        {"kind": "table", "rows": measured_rows, "header": True, "widths": [52 * mm, 26 * mm, 20 * mm, None]},
        {"kind": "h2", "text": "AI interpretation (separate from the measurements above)"},
        {"kind": "paragraph", "text": str(interpretation.get("summary") or "No interpretation recorded.")},
        {
            "kind": "table",
            "rows": [
                ["Interpretation item", "Result"],
                ["pH reaction class", interpretation.get("ph_class")],
                ["Organic matter status", interpretation.get("organic_matter_status")],
                *[
                    [f"Nutrient status: {key}", value]
                    for key, value in (interpretation.get("nutrient_status") or {}).items()
                ],
                ["Confidence", interpretation.get("confidence")],
            ],
            "header": True,
            "widths": [60 * mm, None],
        },
    ]
    if interpretation.get("recommendations"):
        blocks.append({"kind": "h2", "text": "Interpretation-driven recommendations"})
        blocks.append(
            {
                "kind": "bullets",
                "items": [
                    f"[{item.get('parameter', 'soil')}] {item.get('detail', '')}".strip()
                    for item in interpretation["recommendations"]
                ],
            }
        )
    if interpretation.get("limitations"):
        blocks.append({"kind": "h2", "text": "Limitations of this interpretation"})
        blocks.append({"kind": "bullets", "items": [str(item) for item in interpretation["limitations"]]})
    if suitability.get("missing_information"):
        blocks.append({"kind": "h2", "text": "Missing soil inputs"})
        blocks.append({"kind": "bullets", "items": [str(item) for item in suitability["missing_information"]]})

    return {"title": "2. Soil and nutrient analysis", "blocks": blocks}


def _weather_section(weather: dict[str, Any], telemetry: dict[str, Any]) -> dict[str, Any]:
    if not weather.get("available"):
        return {
            "title": "3. Weather and climate context",
            "blocks": [
                {
                    "kind": "paragraph",
                    "text": (
                        "No weather context could be obtained for this field"
                        + (f" ({weather.get('reason')})." if weather.get("reason") else ".")
                        + " Rainfall and heat rules in this report are therefore based on incomplete information."
                    ),
                }
            ],
        }

    daily_rows = [["Date", "Min degC", "Max degC", "Rain mm", "Rain %", "ET0 mm", "Humidity %"]]
    for day in weather.get("daily") or []:
        daily_rows.append(
            [
                str(day.get("forecast_date"))[:10],
                day.get("temp_min_c"),
                day.get("temp_max_c"),
                day.get("precipitation_mm"),
                day.get("precipitation_probability_percent"),
                day.get("et0_mm"),
                day.get("humidity_percent"),
            ]
        )

    summary_rows = [
        ["Metric", "Value", "Source"],
        ["Provider", weather.get("provider"), weather.get("source")],
        ["Simulated", weather.get("is_simulated"), weather.get("source")],
        ["Rainfall next 3 days", f"{weather.get('rainfall_next_3_days_mm')} mm", weather.get("source")],
        ["Rainfall over window", f"{weather.get('total_precipitation_mm')} mm", weather.get("source")],
        ["Reference ET0 over window", f"{weather.get('total_et0_mm')} mm", weather.get("source")],
        ["Max temperature", f"{weather.get('max_temp_c')} deg C", weather.get("source")],
        ["Min temperature", f"{weather.get('min_temp_c')} deg C", weather.get("source")],
        ["Mean humidity", f"{weather.get('mean_humidity_percent')} %", weather.get("source")],
    ]

    blocks: list[dict[str, Any]] = []
    if weather.get("is_simulated"):
        blocks.append(
            {
                "kind": "callout",
                "text": (
                    "SIMULATED WEATHER. This forecast came from the offline climatology fallback, not from a "
                    "live weather API. Every rainfall, heat and humidity rule in this report is indicative "
                    "only and must be verified against a live forecast before it is acted on."
                ),
            }
        )
    blocks.extend(
        [
            {"kind": "table", "rows": summary_rows, "header": True, "widths": [56 * mm, 34 * mm, None]},
            {"kind": "h2", "text": "Daily forecast"},
            {
                "kind": "table",
                "rows": daily_rows,
                "header": True,
                "widths": [24 * mm, 20 * mm, 20 * mm, 20 * mm, 18 * mm, 20 * mm, None],
            },
        ]
    )
    if weather.get("notes"):
        blocks.append({"kind": "h2", "text": "Provider notes"})
        blocks.append({"kind": "bullets", "items": [str(item) for item in weather["notes"]]})
    if telemetry.get("latest"):
        latest = telemetry["latest"]
        blocks.append({"kind": "h2", "text": "Latest soil telemetry"})
        blocks.append(
            {
                "kind": "table",
                "rows": [
                    ["Metric", "Value", "Note"],
                    ["Recorded at", latest.get("recorded_at"), f"sensor {latest.get('sensor_id')}"],
                    ["Soil moisture", f"{latest.get('soil_moisture_percent')} % VWC", ""],
                    ["Soil temperature", f"{latest.get('soil_temperature_c')} deg C", ""],
                    ["Air temperature", f"{latest.get('air_temperature_c')} deg C", ""],
                    ["Air humidity", f"{latest.get('air_humidity_percent')} %", ""],
                    [
                        "Quality flags",
                        ", ".join(latest.get("quality_flags") or []),
                        "simulated" if latest.get("is_simulated") else "measured",
                    ],
                ],
                "header": True,
                "widths": [40 * mm, 34 * mm, None],
            }
        )

    return {"title": "3. Weather and climate context", "blocks": blocks}


def _suitability_section(suitability: dict[str, Any]) -> dict[str, Any]:
    if not suitability:
        return {"title": "4. Crop suitability", "blocks": [{"kind": "paragraph", "text": "Not assessed in this run."}]}

    factor_rows = [["Factor", "Weight", "Verdict", "Score", "Measured", "Detail"]]
    for factor in suitability.get("factor_scores") or []:
        factor_rows.append(
            [
                factor.get("label"),
                factor.get("weight"),
                factor.get("verdict"),
                factor.get("score"),
                factor.get("measured_value") or "-",
                factor.get("detail"),
            ]
        )

    blocks: list[dict[str, Any]] = [
        {
            "kind": "paragraph",
            "text": str(suitability.get("narrative") or ""),
        },
        {
            "kind": "table",
            "rows": [
                ["Assessment item", "Result"],
                ["Crop", suitability.get("crop")],
                ["Status", suitability.get("status")],
                ["Weighted score", suitability.get("score")],
                ["Confidence", suitability.get("confidence")],
                ["Evaluated weight", suitability.get("evaluated_weight")],
            ],
            "header": True,
            "widths": [56 * mm, None],
        },
        {"kind": "h2", "text": "Factor-by-factor assessment"},
        {
            "kind": "table",
            "rows": factor_rows,
            "header": True,
            "widths": [30 * mm, 14 * mm, 20 * mm, 14 * mm, 22 * mm, None],
        },
    ]
    if suitability.get("limiting_factors"):
        blocks.append({"kind": "h2", "text": "Limiting factors"})
        blocks.append({"kind": "bullets", "items": [str(item) for item in suitability["limiting_factors"]]})
    if suitability.get("favorable_factors"):
        blocks.append({"kind": "h2", "text": "Favourable factors"})
        blocks.append({"kind": "bullets", "items": [str(item) for item in suitability["favorable_factors"]]})

    return {"title": "4. Crop suitability assessment", "blocks": blocks}


def _irrigation_section(irrigation: dict[str, Any]) -> dict[str, Any]:
    if not irrigation:
        return {
            "title": "5. Irrigation assessment",
            "blocks": [{"kind": "paragraph", "text": "Not assessed in this run."}],
        }

    rule_rows = [["Rule", "Outcome", "Detail"]]
    for rule in irrigation.get("rules_evaluated") or []:
        rule_rows.append([rule.get("rule"), rule.get("outcome"), rule.get("detail")])

    blocks: list[dict[str, Any]] = [
        {
            "kind": "table",
            "rows": [
                ["Item", "Value"],
                ["Recommendation", irrigation.get("recommendation")],
                ["Urgency", irrigation.get("urgency")],
                [
                    "Estimated depth",
                    f"{irrigation.get('estimated_water_mm')} mm" if irrigation.get("estimated_water_mm") else "-",
                ],
                [
                    "Estimated volume",
                    f"{irrigation.get('estimated_volume_m3')} m3" if irrigation.get("estimated_volume_m3") else "-",
                ],
                ["Human authorisation required", irrigation.get("requires_human_authorisation")],
            ],
            "header": True,
            "widths": [56 * mm, None],
        },
        {"kind": "paragraph", "text": str(irrigation.get("rationale") or "")},
        {
            "kind": "callout",
            "text": (
                "This is a proposal only. The system has no mechanism to apply water: irrigation requires explicit "
                "human authorisation, and approved plans are recorded as documentation."
            ),
        },
        {"kind": "h2", "text": "Rules evaluated (in order)"},
        {"kind": "table", "rows": rule_rows, "header": True, "widths": [38 * mm, 24 * mm, None]},
    ]

    sensor_context = irrigation.get("sensor_context") or {}
    if sensor_context:
        blocks.append({"kind": "h2", "text": "Sensor context"})
        blocks.append(
            {
                "kind": "table",
                "rows": [
                    ["Attribute", "Value"],
                    ["Latest reading at", sensor_context.get("latest_reading_at")],
                    ["Sensor", sensor_context.get("sensor_id")],
                    ["Simulated", sensor_context.get("is_simulated")],
                    ["Soil moisture", f"{sensor_context.get('soil_moisture_percent')} % VWC"],
                    ["Refill trigger", f"{sensor_context.get('refill_trigger_percent')} % VWC"],
                    ["Field capacity", f"{sensor_context.get('field_capacity_percent')} % VWC"],
                    ["Quality flags", ", ".join(sensor_context.get("quality_flags") or [])],
                ],
                "header": True,
                "widths": [56 * mm, None],
            }
        )

    return {"title": "5. Irrigation assessment", "blocks": blocks}


def _risk_section(risk: dict[str, Any]) -> dict[str, Any]:
    if not risk:
        return {
            "title": "6. Environmental risk findings",
            "blocks": [{"kind": "paragraph", "text": "Not assessed in this run."}],
        }

    blocks: list[dict[str, Any]] = [
        {"kind": "callout", "text": risk_service.DISCLAIMER},
        {
            "kind": "table",
            "rows": [
                ["Attribute", "Value"],
                ["Overall environmental risk level", risk.get("risk_level")],
                ["Findings", len(risk.get("findings") or [])],
            ],
            "header": True,
            "widths": [56 * mm, None],
        },
    ]
    for finding in risk.get("findings") or []:
        blocks.append(
            {
                "kind": "h2",
                "text": f"{str(finding.get('risk_type', '')).replace('_', ' ').title()} - {finding.get('severity')}",
            }
        )
        blocks.append({"kind": "paragraph", "text": str(finding.get("statement", ""))})
        if finding.get("potential_impact"):
            blocks.append(
                {
                    "kind": "bullets",
                    "items": [f"Potential impact: {finding['potential_impact']}"],
                }
            )
        if finding.get("recommended_investigation"):
            blocks.append(
                {
                    "kind": "bullets",
                    "items": [f"Recommended investigation: {finding['recommended_investigation']}"],
                }
            )
    if risk.get("review_notes"):
        blocks.append({"kind": "h2", "text": "Reviewer notes"})
        blocks.append({"kind": "bullets", "items": [str(item) for item in risk["review_notes"]]})

    return {"title": "6. Environmental risk findings (favourability, not diagnosis)", "blocks": blocks}


def _ml_section(ml_predictions: list[dict[str, Any]]) -> dict[str, Any]:
    if not ml_predictions:
        return {
            "title": "7. Machine-learning models",
            "blocks": [
                {
                    "kind": "paragraph",
                    "text": (
                        "No trained model output is available for this run; "
                        "the decisions above rest on rule logic only."
                    ),
                }
            ],
        }

    rows = [["Task", "Model", "Version", "Prediction", "Confidence", "Message"]]
    for prediction in ml_predictions:
        value = prediction.get("prediction_label") or prediction.get("prediction_value")
        rows.append(
            [
                str(prediction.get("task")).replace("_", " "),
                prediction.get("model_name"),
                prediction.get("model_version"),
                value,
                prediction.get("confidence"),
                prediction.get("message"),
            ]
        )

    return {
        "title": "7. Machine-learning models",
        "blocks": [
            {
                "kind": "callout",
                "text": (
                    "Training data provenance: the models were trained on simulated seasons generated by an "
                    "FAO-56 style soil-water-balance simulation. Their metrics describe how well they reproduce "
                    "that simulation; they are not validated against field yield or disease outcomes."
                ),
            },
            {
                "kind": "table",
                "rows": rows,
                "header": True,
                "widths": [30 * mm, 30 * mm, 16 * mm, 18 * mm, 16 * mm, None],
            },
        ],
    }


def _operations_section(
    activities: list[dict[str, Any]], alerts: list[dict[str, Any]], approval: dict[str, Any]
) -> dict[str, Any]:
    blocks: list[dict[str, Any]] = []

    if approval:
        blocks.append({"kind": "h2", "text": "Human approval record"})
        blocks.append(
            {
                "kind": "table",
                "rows": [
                    ["Attribute", "Value"],
                    ["Approval id", approval.get("id")],
                    ["Title", approval.get("title")],
                    ["Status", approval.get("status")],
                    ["Reviewer", approval.get("reviewer_name")],
                    ["Decision note", approval.get("decision_note")],
                    ["Reviewer observation", approval.get("observation")],
                    ["Decided at", approval.get("decided_at")],
                ],
                "header": True,
                "widths": [46 * mm, None],
            }
        )

    blocks.append({"kind": "h2", "text": "Planned activities"})
    if activities:
        rows = [["Type", "Title", "Scheduled", "Status", "Priority", "Reason"]]
        for item in activities:
            rows.append(
                [
                    str(item.get("activity_type", "")).replace("_", " "),
                    item.get("title"),
                    str(item.get("scheduled_date"))[:16] if item.get("scheduled_date") else "-",
                    item.get("status"),
                    item.get("priority"),
                    item.get("reason"),
                ]
            )
        blocks.append(
            {
                "kind": "table",
                "rows": rows,
                "header": True,
                "widths": [26 * mm, 34 * mm, 22 * mm, 16 * mm, 14 * mm, None],
            }
        )
    else:
        blocks.append({"kind": "paragraph", "text": "No activities were planned for this run."})

    blocks.append({"kind": "h2", "text": "Alerts raised"})
    if alerts:
        rows = [["Type", "Severity", "Status", "Occurrences", "Message"]]
        for item in alerts:
            rows.append(
                [
                    str(item.get("alert_type", "")).replace("_", " "),
                    item.get("severity"),
                    item.get("status"),
                    item.get("occurrence_count"),
                    item.get("message"),
                ]
            )
        blocks.append(
            {"kind": "table", "rows": rows, "header": True, "widths": [28 * mm, 18 * mm, 18 * mm, 18 * mm, None]}
        )
    else:
        blocks.append({"kind": "paragraph", "text": "No alerts were raised for this run."})

    return {"title": "8. Activity plan, alerts and approval", "blocks": blocks}


def _evidence_section(state: dict[str, Any]) -> dict[str, Any]:
    """Every fact the report relies on, with its provenance tag."""
    evidence = state.get("evidence") or []
    rows = [["#", "Label", "Value", "Unit", "Provenance", "Source"]]
    for index, item in enumerate(evidence, start=1):
        value = item.get("value")
        unit = item.get("unit") or ""
        rows.append(
            [
                index,
                item.get("label"),
                "not available" if value is None else value,
                unit,
                str(item.get("kind", "measured")),
                item.get("source") or item.get("reference") or "-",
            ]
        )

    blocks: list[dict[str, Any]] = [
        {
            "kind": "paragraph",
            "text": (
                "Provenance tags: MEASURED is a laboratory, device or human value; OBSERVED is a value derived "
                "from stored measurements; FORECAST is a weather provider value; SIMULATED is generated "
                "demonstration data; ML_PREDICTION is model output; RULE and RETRIEVED_REFERENCE are rule "
                "thresholds and cited guidance."
            ),
        }
    ]
    if rows:
        blocks.append(
            {
                "kind": "table",
                "rows": rows,
                "header": True,
                "widths": [8 * mm, 48 * mm, 26 * mm, 14 * mm, 26 * mm, None],
            }
        )
    else:
        blocks.append({"kind": "paragraph", "text": "No evidence items were recorded for this run."})

    return {"title": "9. Evidence ledger", "blocks": blocks}
