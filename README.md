# Agentic AI Agricultural Crop Planning & Precision Farming System

An end-to-end precision-farming decision-support platform. A LangGraph
multi-agent workflow analyses a field's soil, sensors, weather and agronomic
knowledge base, produces crop-suitability / irrigation / risk assessments,
scores them with a trained ML model, raises de-duplicated alerts, plans farm
activities, and gates every consequential action behind human approval.
Advisory reports are exportable as PDF.

> Safety stance: this system **never** claims a disease is confirmed, never
> actuates physical equipment, and never silently fabricates weather data.
> Environmental findings are always phrased as *"Environmental conditions
> favourable for X"* with a non-diagnostic disclaimer.

---

## 1. Problem statement

Smallholder and precision growers juggle fragmented data — lab soil tests,
weather forecasts, soil-moisture probes, and agronomic extension literature —
with no integrated way to turn it into a defensible plan for a specific field.
This system integrates those sources into one auditable workflow whose every
number is traceable to a measurement, a forecast, a rule, an ML model, or a
cited reference document.

## 2. Architecture

```
┌──────────────┐   HTTPS / JSON    ┌─────────────────────────────────────────┐
│ React + TS   │ ────────────────► │ FastAPI (app/api/routers)               │
│ Tailwind UI  │   (Axios client)  │  - validation (Pydantic v2)             │
└──────────────┘                   │  - services (app/services)              │
                                   │  - LangGraph orchestration (app/agents) │
                                   │  - RAG over FAISS (app/rag)             │
                                   │  - ML registry (app/ml)                 │
                                   │  - SQLAlchemy 2 + Alembic               │
                                   └───────┬───────────────────┬─────────────┘
                                           │                   │
                                     SQLite/Postgres     Open-Meteo /
                                     (agri.db default)   OpenWeatherMap
```

- **Backend**: Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic,
  LangGraph, FAISS, scikit-learn, reportlab.
- **Frontend**: React 18, TypeScript, Tailwind, TanStack Query, axios,
  react-router, recharts.
- **Database**: SQLite by default (zero-infra demo), PostgreSQL supported via
  `DATABASE_URL` + `alembic upgrade head`.

## 3. Database design

Tables (see `backend/app/models`): `farm`, `field`, `soil_observation`,
`soil_interpretation`, `sensor_reading`, `sensor_device`, `weather_snapshot`,
`suitability_assessment`, `irrigation_assessment`, `risk_finding`,
`ml_prediction`, `alert`, `farm_activity`, `approval_request`,
`workflow_run`, `agent_trace`, `advisory_report`, `reference_document`.
All rows carry timestamps; fingerprinting indexes de-duplicate alerts;
`workflow_run.state` + `agent_trace.evidence` form the audit ledger.

## 4. Agents (12, all used)

Defined in `backend/app/agents`, executed as LangGraph nodes:

| Agent | Responsibility |
|---|---|
| `farm_field_profile_agent` | Field identity, crop history, water context |
| `soil_nutrient_agent` | Soil test → measured/interpretation split |
| `sensor_telemetry_agent` | Latest readings + trend + sanity flags |
| `weather_climate_agent` | Live provider chain, labelled fallback |
| `weather_bundle_bridge` | Store summary → typed `WeatherBundle` |
| `knowledge_retrieval_agent` | FAISS search over 23 agronomy docs |
| `crop_suitability_agent` | Weighted factor score + citations |
| `ml_forecast_agent` | Both trained models, persisted predictions |
| `irrigation_agent` | Rule-based irrigation proposal (never actuates) |
| `crop_risk_advisory_agent` | Favourability-only risk findings |
| `activity_planner_agent` | Dated activity plan from all findings |
| `advisory_narrative_agent` | Deterministic (or LLM) explanation |

Workflow (`graph.py`) is an explicit state machine; each node's evidence and
citations are merged into a shared `WorkflowState`, persisted as
`agent_trace` rows, and finally surfaced in the run summary, the UI and the PDF.

## 5. Weather integration

Provider chain: **OpenWeatherMap → Open-Meteo → offline climatology**.
The Open-Meteo branch needs no API key and is genuinely live. Every response
carries `source`, `provider`, `is_simulated`, `fallback_used`; any offline
estimate is labelled `source="offline-climatology"`, `is_simulated=true`
either in the API payload, the persisted snapshot, the UI banner, or the PDF.

## 6. Agricultural RAG

- Corpus: 23 curated markdown documents (`app/data/knowledge/*.md`) covering
  crop requirements, soil conditions, irrigation, crop stages and
  environmental risks.
- Store: FAISS `IndexFlatIP` + normalised bag/hashed embeddings (deterministic,
  reproducible, no download), persisted under `app/rag/index`.
- Retrieval results carry `doc_key`, `title`, `category`, cosine `score` and
  are cited by every downstream agent result; low-score hits are suppressed
  via `RAG_MIN_SCORE`/`RAG_RELATIVE_SCORE_RATIO`.

## 7. ML component

Two RandomForest models (`backend/app/ml`), trained by
`python -m app.ml.train` on a simulated FAO-56-style soil-water-balance
dataset (grouped season-wise 80/20 split, no season leakage):

1. `soil_moisture_forecast` — 7-day-ahead root-zone moisture regression
   (MAE ≈ 0.35 %VWC, R² per `metrics.json`).
2. `environmental_risk_classification` — 4-class severity bucket
   (none/low/moderate/high, accuracy ≈ 0.97).

Both are integrated into the workflow (via `MLForecastAgent`) **and** exposed
through `POST /api/v1/ml/predict`. All predictions persist with features,
imputed-feature lists, model version and confidence. Missing artifacts degrade
to a recorded rule-only run; a first boot auto-trains both models.

## 8. Suitability, irrigation, risk logic

- **Suitability** (`suitability_service`): transparent weighted factors
  (pH 0.22, soil moisture 0.18, temperature 0.16, rainfall/water 0.14,
  soil type 0.12, fertility 0.10, crop history 0.08), every factor carrying
  verdict, measured value, required range, weight and detail. Missing inputs
  reduce confidence and force `additional_information_required`.
- **Irrigation** (`irrigation_service`): rules over measured soil moisture,
  crop stage, 3-day forecast rainfall and ET₀. Low moisture **but** significant
  forecast rain → "consider postponing", never blind "irrigate now". Every
  recommendation is `requires_human_authorisation=true`.
- **Risk** (`risk_service`): threshold rules for heat stress, water stress,
  excessive rainfall, dry spells, and humidity/rain disease-favourable
  environments; cross-checked by the ML severity classifier; findings always
  worded as environmental favourability with a scouting recommendation.

## 9. Sensor pipeline

Simulated or real `sensor_reading` rows (soil moisture, temperature, humidity;
`sensor_device` association), trend statistics over windows, outlier/missing
handling, and a simulator service for demos (`POST /api/v1/sensors/simulate`).

## 10. Human-in-the-loop

`approval_request` rows gate irrigation/activity plans: reviewer must approve,
reject, modify or request re-analysis. Approvals are persisted with reviewer
name, note and timestamp and move activities `planned → scheduled`. A safety
contract endpoint documents that no code path actuates hardware.

## 11. Alerts

`alert_service` raises/syncs alerts keyed by a fingerprint
(`sha1(field|alert_type|discriminator)`); duplicates only re-open on severity
escalation; cleared conditions auto-resolve.

## 12. Reports

`POST /api/v1/reports?field_id=N` renders an 8+-section PDF (farm/field,
soil, weather, suitability, irrigation, risk, ML, activities, alerts,
approvals, sources, limitations) via reportlab; verified openable with pypdf.

## 13. Environment variables

See [`.env.example`](.env.example) — every value is optional and safe by
default. `OPENAI_API_KEY`/`WEATHER_API_KEY` blank → deterministic advisory
text and Open-Meteo weather. Frontend secrets: none (`VITE_API_BASE_URL` only).

## 14. Local setup

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp ../.env.example .env                              # optional
uvicorn app.main:app --reload --port 8000

# Frontend (new terminal)
cd frontend
npm ci
npm run dev                                          # http://localhost:5173
```

First boot seeds a demo database, warms FAISS, compiles the LangGraph, and
auto-trains the two ML models if artifacts are missing.

Useful commands:

```bash
python -m app.ml.train          # retrain + rewrite metrics.json
alembic upgrade head            # when using PostgreSQL
scripts/smoke.py                # HTTP smoke check against a running server
```

## 15. Testing

```bash
cd backend && python -m pytest tests -q     # 7 acceptance suites, incl. TC-01..TC-06 recorder
cd backend && ruff check . && ruff format --check .
cd frontend && npm run lint && npx vitest run && npm run build
```

TC-01…TC-06 are recorded (inputs/expected/actual/agents/evidence/pass-fail) by
`tests/test_acceptance_tc01_tc06.py` into an acceptance report.

## 16. API documentation

Interactive OpenAPI docs at `http://localhost:8000/docs`. Route inventory in
[`api-routes.txt`](api-routes.txt); full schema in `api-contract.json`.

## 17. Deployment

- **Backend → Render**: root [`render.yaml`](render.yaml) is a blueprint;
  set `DATABASE_URL` (Postgres), `CORS_ORIGINS`, optional weather/LLM keys.
- **Frontend → Vercel**: [`frontend/vercel.json`](frontend/vercel.json);
  set `VITE_API_BASE_URL=https://<your-render-app>/api/v1` and allow that
  origin in the backend `CORS_ORIGINS`.
- Remaining manual step: create the Render/Vercel projects and set the two
  environment variables above (needs your accounts/credentials).

## 18. CI

GitHub Actions (`.github/workflows/ci.yml`) runs, on every push/PR: ruff
lint + format check + pytest for the backend, and eslint + vitest +
`tsc`/`vite build` for the frontend.

## 19. Troubleshooting

| Symptom | Fix |
|---|---|
| `No module named ...` | recreate the venv, `pip install -r requirements-dev.txt` |
| ML "unavailable" warnings | `python -m app.ml.train` |
| Weather says "offline-climatology" | no internet or rate-limited; labelled by design |
| CORS errors in dev | victim calls should use the Vite proxy (`/api/v1`) |
| DB schema errors | `alembic upgrade head` or delete `agri.db` to re-seed |

## 20. Limitations & safety notes

- ML training data is simulated (FAO-56-style); metrics measure fidelity to
  that simulation, not field-level accuracy.
- Sensor data is simulated unless real devices POST to the ingestion API.
- The advisory narrative is LLM-composed only when `OPENAI_API_KEY` is set;
  all numbers still originate from the analysis services.
- The system gives decision support only — it is not an agronomic prescription
  and never a diagnosis.
