"""Generate a complete sample dataset from an isolated, throwaway backend.

The submission needs demonstration data covering varied soil conditions,
multiple crops, weather variation, soil-moisture change, irrigation events and
environmental-risk scenarios. Activity planning only runs against a completed
workflow, so the data has to be produced by driving the real pipeline - but on a
disposable SQLite container rather than the live deployment.
"""

from __future__ import annotations

import csv
import json
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://localhost:8123/api/v1"
OUT = Path(__file__).resolve().parents[1] / "sample_data"


def call(path: str, payload: dict | None = None) -> object:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
        method="POST" if data else "GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        print(f"  ! {exc.code} {path}: {exc.read()[:160].decode('utf-8', 'replace')}")
        return None


def write(name: str, rows: list[dict], header: list[str] | None = None) -> None:
    if not rows:
        print(f"  skip {name} (no rows)")
        return
    OUT.mkdir(exist_ok=True)
    cols = header or sorted({k for row in rows for k in row})
    with (OUT / name).open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"  {name}: {len(rows)} rows")


def main() -> None:
    print(f"generating sample data from {BASE}")

    fields = call("/fields?limit=100") or []
    write("fields.csv", fields)
    write("crop_catalog.csv", (call("/suitability/crops") or {}).get("crops", []) or [])

    soil = call("/soil/thresholds") or {}
    write("soil_nutrient_thresholds.csv", [{"parameter": k, **v} for k, v in soil.items()])

    # Weather variation across three distinct agro-climates.
    weather_rows: list[dict] = []
    for name, (lat, lon) in {
        "Hyderabad_IN": (17.38, 78.48),
        "Warangal_IN": (17.97, 79.5),
        "Kochi_IN": (9.93, 76.27),
    }.items():
        bundle = ((call(f"/weather/lookup?latitude={lat}&longitude={lon}&days=7") or {}).get("bundle")) or {}
        for day in bundle.get("daily") or []:
            weather_rows.append({"location": name, **day})
    write("weather_forecast_sample.csv", weather_rows)

    # Drive the real pipeline per field: sensors -> suitability -> agents ->
    # risk -> activity plan. This is what produces irrigation events.
    suitability_rows: list[dict] = []
    risk_rows: list[dict] = []
    activity_rows: list[dict] = []
    sensor_rows: list[dict] = []

    for field in fields:
        fid = field.get("id")
        if not fid:
            continue
        print(f"  field {fid} ({field.get('name')})")

        call(f"/sensors/fields/{fid}/simulate", {"days": 3, "replace_existing": True})

        trend = call(f"/sensors/readings?field_id={fid}&limit=200") or []
        for point in trend:
            # Keep the provenance columns: the data-honesty contract is only
            # demonstrable if is_simulated/quality_flags travel with the data.
            sensor_rows.append(
                {
                    "field_id": fid,
                    **point,
                    "quality_flags": "|".join(point.get("quality_flags") or []),
                }
            )

        for crop in ("Maize", "Cotton", "Groundnut"):
            # field_id is a *query* parameter here, not part of the body.
            result = call(
                f"/suitability/assess?field_id={fid}",
                {"crop": crop, "include_evidence": True},
            )
            if isinstance(result, dict):
                suitability_rows.append({"field_id": fid, "proposed_crop": crop, **result})

        risk = call(f"/risk/fields/{fid}") or {}
        for finding in risk.get("findings") or []:
            risk_rows.append({"field_id": fid, "risk_level": risk.get("risk_level"), **finding})

        run = call("/workflow/runs", {"field_id": fid})
        run_id = run.get("id") if isinstance(run, dict) else None

    # Plan for every run, not just the ones just created: whether a plan is
    # emitted depends on the agents having found a real signal in *that* run, so
    # earlier runs may hold the irrigation/risk examples this dataset needs.
    for run in call("/workflow/runs?limit=100") or []:
        run_id = run.get("id")
        if not run_id:
            continue
        # The planner only emits activities when the agents actually found a
        # signal (a risk finding, or water proposed/withheld). It never invents
        # work, so an empty plan is a legitimate result rather than a failure.
        for activity in call(
            "/activities/plan",
            {"workflow_run_id": run_id, "include_approved_only": False},
        ) or []:
            activity_rows.append(
                {"field_id": run.get("field_id"), "workflow_run_id": run_id, **activity}
            )

    write("sensor_readings_sample.csv", sensor_rows)
    write("crop_suitability_sample.csv", suitability_rows)
    write("crop_risk_findings_sample.csv", risk_rows)
    write("farm_activities_sample.csv", activity_rows)

    alerts = call("/alerts/open") or []
    write("open_alerts.csv", alerts)
    write("workflow_runs.csv", call("/workflow/runs?limit=100") or [])

    print("done")


if __name__ == "__main__":
    main()