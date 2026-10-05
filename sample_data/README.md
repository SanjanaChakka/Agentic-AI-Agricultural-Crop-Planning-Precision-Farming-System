# Sample dataset

Synthetic-but-realistic demonstration data, exported from a running instance by
`scripts/export_sample_data.py`. It is not hand-written: the script drives the
real API (simulate sensors → assess suitability → run the six-agent workflow →
plan activities) against a disposable backend, then reads the rows back out. So
every file here is exactly what the application stores.

Regenerate with:

```bash
python scripts/export_sample_data.py   # expects a backend on :8123
```

| File | Rows | Demonstrates |
|---|---|---|
| `fields.csv` | 5 | Five distinct soil conditions (black cotton, red laterite, alluvial, sandy loam, loam) with differing area, water availability and proposed crop |
| `soil_nutrient_thresholds.csv` | 5 | The configured N/P/K interpretation bands used to classify soil tests |
| `crop_catalog.csv` | 14 | Multiple crops with aliases, each carrying its own pH/temperature/moisture requirements |
| `weather_forecast_sample.csv` | 21 | Weather variation across three agro-climates (Hyderabad, Warangal, Kochi), 7 days each |
| `sensor_readings_sample.csv` | 273 | Soil-moisture change over time, including rain events and dry-down periods, with full provenance |
| `crop_suitability_sample.csv` | 15 | 5 fields × 3 proposed crops, each scored with per-factor verdicts and evidence |
| `crop_risk_findings_sample.csv` | 5 | Environmental-risk scenarios (water stress and heat) with severity, impact and evidence |
| `farm_activities_sample.csv` | 64 | The activity planner's output, including irrigation, soil testing, scouting, sowing and harvest planning |
| `open_alerts.csv` | 7 | Alerts generated for low moisture, water stress and heat conditions |
| `workflow_runs.csv` | 30 | Multi-agent executions with agent roster, status and duration |

## Why the provenance columns matter

`is_simulated`, `quality_flags` and `notes` are carried through from
`sensor_readings_sample.csv` deliberately. The system's data-honesty contract
depends on a reader being able to tell a measurement from a generated value
without trusting prose, so the export keeps those columns rather than the
measurement-only view that `/sensors/fields/{id}/trend` returns.

Every row in this snapshot is `is_simulated=true`, because it was produced by the
simulator. A live deployment additionally stores Open-Meteo soil-model rows with
`is_simulated=false` and `quality_flags=["third_party_model"]` — that feed is a
third-party *model*, not an in-field probe, and is labelled as such.

## Note on empty plans

Not every workflow run produces activities. The planner only emits work when the
agents found an actual signal — a risk finding, or water being proposed or
withheld. A field assessed as `review_required` with no risk findings correctly
yields no activities rather than invented ones, so gaps in
`farm_activities_sample.csv` are expected and are themselves evidence of the
system not fabricating work.