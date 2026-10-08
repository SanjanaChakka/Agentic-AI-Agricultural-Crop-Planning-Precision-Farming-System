# Technical Guide

Everything you need to explain, run and defend this project: how the two
services talk to each other, what every route does, how backend changes reach
the frontend, and what the agent code is actually doing.

Companion to `README.md`. This file is the deep dive.

---

## 1. How the backend and frontend connect

### 1.1 Local development

The browser never imports a backend hostname. `frontend/src/api/client.ts`
creates one axios instance whose `baseURL` is a **relative** path:

```ts
// frontend/src/api/client.ts
export const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim() || '/api/v1';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: { Accept: 'application/json' },
  timeout: 120_000,
});
```

Vite then forwards `/api` to Python during development:

```ts
// frontend/vite.config.ts
const proxyTarget = process.env.VITE_DEV_PROXY_TARGET ?? 'http://127.0.0.1:8000';

server: {
  proxy: {
    '/api': { target: proxyTarget, changeOrigin: true },
  },
}
```

So the request path is:

```
browser  ── GET /api/v1/fields ──►  Vite :5173
                                        │ proxy /api
                                        ▼
                                   uvicorn :8000
                                   FastAPI router
                                   service layer
                                   SQLAlchemy
```

Same origin from the browser's point of view, so **CORS never enters the
picture locally**. Two processes, one origin, no preflight.

**To run it:**

```bash
# Backend (port 8000)
python -m venv .venv
.venv\Scripts\activate              # Windows — source .venv/bin/activate on macOS/Linux
pip install -r backend/requirements.txt -r backend/requirements-dev.txt
cd backend && uvicorn app.main:app --reload --port 8000

# Frontend (port 5173)
cd frontend && npm install && npm run dev
```

**Or the whole stack in Docker:**

```bash
cp .env.example .env
docker compose up --build
```

`docker-compose.yml` maps `${BACKEND_PORT:-8000}:8000` and
`${FRONTEND_PORT:-8080}:80`. Override if those ports are taken:

```bash
FRONTEND_PORT=8090 BACKEND_PORT=8001 docker compose up --build
```

In the container, nginx serves the SPA on `:80` and reverse-proxies `/api` to
the backend — the same single-origin arrangement as dev, just with nginx instead
of Vite.

### 1.2 Production (Render + Vercel)

There is no reverse proxy. Two separate hosts means two **separate origins**,
so both a CORS header and an absolute API URL are required:

```
browser ── GET https://agri-backend-644q.onrender.com/api/v1/fields
          Origin: https://agentic-ai-agricultural-crop-planni.vercel.app
                       │
                       ▼
        Render checks CORS_ORIGINS before responding
```

| Where | Variable | Value |
|---|---|---|
| Vercel | `VITE_API_BASE_URL` | `https://agri-backend-644q.onrender.com/api/v1` |
| Render | `CORS_ORIGINS` | `https://agentic-ai-agricultural-crop-planni.vercel.app` |
| Render | `DATABASE_URL` | `postgresql://…` from the Render Postgres instance |

Three rules that silently break if missed:

1. **`/api/v1` is mandatory** in `VITE_API_BASE_URL`. Drop it and every call
   goes to `/health`, `/fields`, `/alerts/open` — all `404`, because FastAPI
   mounts its routers under that prefix.
2. **The two origins must match exactly** — scheme + host, no trailing slash,
   no `/api`. A mismatch turns the 404s into CORS errors.
3. **`VITE_` variables are inlined at build time.** Changing one in the Vercel
   dashboard needs a *redeploy*, not a restart.

### 1.3 Diagnosing a connection problem

| Symptom | Cause | Fix |
|---|---|---|
| Every request `404` with paths like `/health` | `VITE_API_BASE_URL` missing `/api/v1` | Append the suffix, redeploy Vercel |
| Requests `404` on the **right** path | Backend has no such route | Check `api-contract.json`; the router may be unmounted |
| `CORS policy` error in console | `CORS_ORIGINS` ≠ the real Vercel origin | Set Render's value to the exact origin, deploy |
| `cors_origin_list` ignores your setting | Value has a trailing slash or comma | `Settings.cors_origin_list` splits on `,` only |
| 502 / `unhealthy` on Render | Container ignoring `$PORT` | Image must bind `--port ${PORT:-8000}`; healthcheck must probe the same port |
| `database: down`, `ml`/`rag` up | `DATABASE_URL` malformed or wrong dialect | A bare `postgresql://` is normalised to `postgresql+psycopg://` automatically |
| Works locally, empty on Render | No `SEED_DEMO_DATA_ON_STARTUP` | Set to `true` and deploy |

---

## 2. What a backend change does to the frontend

The two halves are decoupled by the JSON contract in `api-contract.json`.
That contract is generated from the FastAPI app, so the frontend does **not**
need to be told when a route appears — it does need to be changed when a shape
it reads changes.

| Backend change | Frontend effect | What you must do |
|---|---|---|
| **Add a new route** | Nothing breaks | Add `src/api/<domain>.ts` function + `src/hooks/use<X>.ts` if you want to render it |
| **Delete or rename a route** | Immediate `404` on that call | Update the matching `src/api/*.ts` function; grep for the path |
| **Add an optional field** to a response | Nothing breaks; field is simply absent | Add it to `src/api/types.ts` to use it |
| **Remove or rename a field** in a response | Type mismatch at build time, `undefined` at runtime | Update `types.ts` first, then any component reading it |
| **Change an enum's values** (e.g. `severity: "low"`) | UI maps by string, so unknown values render blank | Update the frontend's label/colour lookup tables |
| **Tighten validation** (rejects what used to pass) | Submit form now shows 422 | `client.ts` already normalises FastAPI `detail` into `ApiError.issues`; surface them |
| **Change a status string** (`awaiting_human_review`) | Workflow UI branch stops matching | Update the status guards in `src/api/workflow.ts` |
| **Add a required field to a POST body** | Frontend request now 422s | Send the new field from `src/api/*.ts` |
| **Change pagination shape** | Lists come back empty | Check `limit`/`offset` handling in the hook |
| **Change the API base path prefix** | Everything 404s | Update `VITE_API_BASE_URL` (and rebuild) |
| **Enable a new CORS origin** | Blanket CORS failure for that host | Add the origin to `CORS_ORIGINS` in Render |
| **Upgrade the API version** (`/api/v1` → `/api/v2`) | All calls fail | Update `client.ts` default and the deploy env var together |

**The safe order for any contract change:** update backend → run
`api-contract.json` regeneration → update `src/api/types.ts` → run
`npm run build` (TypeScript will point at every consumer) → run the backend test
suite.

`src/api/client.ts` is the single choke point. Because every request goes
through `apiClient`, there is no second place where a base URL or header can
drift.

---

## 3. Complete API surface

71 paths, 83 HTTP operations. FastAPI also serves its own
`/docs`, `/redoc` and `/openapi.json` — those three plus
`GET /` are the 87 route objects the app registers; the 83 below are the
application's.

### System

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Service banner |
| GET | `/api/v1/health` | Component health: `database`, `ml`, `rag`, providers |
| GET | `/api/v1/health/live` | Liveness probe — is the process up |
| GET | `/api/v1/health/ready` | Readiness probe — will it serve; used by Render's health check |
| GET | `/api/v1/dashboard` | Cross-farm dashboard aggregates |

### Farms and fields

| Method | Path | Purpose |
|---|---|---|
| GET | `/farms` | List farms (`search`, `limit`, `offset`) |
| POST | `/farms` | Register a farm |
| GET | `/farms/{farm_id}` | One farm with its fields |
| PATCH | `/farms/{farm_id}` | Update a farm |
| DELETE | `/farms/{farm_id}` | Delete a farm and its fields |
| GET | `/farms/{farm_id}/summary` | Dashboard summary for one farm |
| GET | `/fields` | List fields (`farm_id`, `soil_type`, `limit`, `offset`) |
| POST | `/fields?farm_id=` | Add a field to a farm |
| GET | `/fields/counts` | Field counts and total area |
| GET | `/fields/{field_id}` | One field |
| PATCH | `/fields/{field_id}` | Update a field |
| DELETE | `/fields/{field_id}` | Delete a field |

### Soil

| Method | Path | Purpose |
|---|---|---|
| POST | `/soil/observations` | Record a **measured** soil test and generate its interpretation |
| GET | `/soil/observations` | List soil observations |
| GET | `/soil/observations/{observation_id}` | Measured values **and** AI interpretation, kept separate |
| GET | `/soil/observations/{observation_id}/evidence` | Provenance-tagged evidence for one observation |
| POST | `/soil/observations/{observation_id}/reinterpret?crop=` | Re-run interpretation for a measured observation |
| GET | `/soil/fields/{field_id}/latest` | Latest soil test for a field |
| GET | `/soil/thresholds` | Agronomic rating bands in use |

### Weather

| Method | Path | Purpose |
|---|---|---|
| GET | `/weather/lookup?latitude=&longitude=` | Forecast for any coordinate |
| GET | `/weather/fields/{field_id}?days=` | Forecast for a registered field |
| GET | `/weather/fields/{field_id}/evidence?days=` | Provenance-tagged weather evidence |
| GET | `/weather/snapshots` | Persisted weather snapshots |
| GET | `/weather/snapshots/{snapshot_id}` | One snapshot |

### Sensors

| Method | Path | Purpose |
|---|---|---|
| GET | `/sensors/fields/{field_id}/latest?sensor_id=` | Latest reading |
| GET | `/sensors/fields/{field_id}/trend?hours=&sensor_id=` | Trend plus summary statistics |
| GET | `/sensors/fields/{field_id}/quality` | Data-quality audit for the latest telemetry |
| GET | `/sensors/readings?field_id=&limit=&offset=` | Raw readings with provenance columns |
| POST | `/sensors/readings` | Ingest a device reading |
| POST | `/sensors/fields/{field_id}/simulate` | Generate simulated telemetry (every row flagged) |
| POST | `/sensors/fields/{field_id}/sync-live-soil` | Ingest live Open-Meteo soil telemetry |

### Crop suitability

| Method | Path | Purpose |
|---|---|---|
| POST | `/suitability/assess?field_id=` | Assess a crop against the field (**`field_id` is a query param, `crop` is the body**) |
| GET | `/suitability/crops` | Supported crops and their agronomic thresholds |
| GET | `/suitability/fields/{field_id}` | Assessment history |

### Irrigation

| Method | Path | Purpose |
|---|---|---|
| POST | `/irrigation/assess?field_id=` | Irrigation decision support — proposal only, never auto-applied |
| GET | `/irrigation/fields/{field_id}` | Assessment history |

### Crop risk

| Method | Path | Purpose |
|---|---|---|
| GET | `/risk/fields/{field_id}?crop=` | Scan environmental risk for a field |
| GET | `/risk/fields/{field_id}/history` | Persisted findings |
| GET | `/risk/disclaimer` | The non-diagnostic disclaimer the system enforces |

### Machine learning

| Method | Path | Purpose |
|---|---|---|
| GET | `/ml/status` | Model availability and load errors |
| GET | `/ml/models` | Trained models with their metrics |
| POST | `/ml/predict?field_id=` | Run both models against current conditions |
| GET | `/ml/fields/{field_id}/predictions` | Prediction history |

### Knowledge base (RAG)

| Method | Path | Purpose |
|---|---|---|
| GET | `/knowledge/status` | Retrieval index status |
| GET | `/knowledge/documents` | Indexed reference documents |
| GET | `/knowledge/documents/{doc_key}` | Citations for one known document |
| POST | `/knowledge/search` | Semantic search over the corpus |
| POST | `/knowledge/rebuild` | Rebuild the retrieval index from disk |

### Workflow and agents

| Method | Path | Purpose |
|---|---|---|
| GET | `/agents` | The specialised agents in this workflow |
| GET | `/agents/graph` | Compiled LangGraph topology |
| POST | `/workflow/runs` | Execute the full multi-agent cycle for a field |
| GET | `/workflow/runs` | List runs |
| GET | `/workflow/runs/count` | Count runs |
| GET | `/workflow/runs/{run_id}` | Run detail with agent traces |
| GET | `/workflow/runs/{run_id}/summary` | Condensed result |
| GET | `/workflow/runs/{run_id}/traces` | Per-agent audit trail |
| POST | `/workflow/runs/{run_id}/reanalyse` | Re-run carrying the reviewer's observations |
| POST | `/workflow/runs/{run_id}/report` | Generate the PDF report |
| GET | `/workflow/runs/field/{field_id}/latest` | Most recent run for a field |

### Approvals (human-in-the-loop)

| Method | Path | Purpose |
|---|---|---|
| GET | `/approvals` | List approval requests |
| GET | `/approvals/pending?limit=` | Pending human review |
| GET | `/approvals/{approval_id}` | One approval request |
| POST | `/approvals/{approval_id}/decision` | Approve, reject, modify or request re-analysis |
| GET | `/approvals/safety-contract` | What approval does and does not do |

### Activities

| Method | Path | Purpose |
|---|---|---|
| GET | `/activities` | List farm activities |
| POST | `/activities` | Add a manual activity |
| GET | `/activities/fields/{field_id}/upcoming?days=` | Activities inside a time window |
| POST | `/activities/plan` | Plan activities from a completed workflow run |
| PATCH | `/activities/{activity_id}` | Update an activity |

### Alerts

| Method | Path | Purpose |
|---|---|---|
| GET | `/alerts` | List alerts by farm/field/status/severity |
| GET | `/alerts/open?farm_id=` | Open and acknowledged alerts |
| GET | `/alerts/dedup-policy` | How duplicate suppression works |
| PATCH | `/alerts/{alert_id}` | Acknowledge or resolve an alert |

### Reports

| Method | Path | Purpose |
|---|---|---|
| GET | `/reports` | List generated reports |
| POST | `/reports?field_id=` | Generate a PDF report |
| GET | `/reports/{report_id}` | Report metadata |
| GET | `/reports/{report_id}/download` | Download the PDF |
| DELETE | `/reports/{report_id}` | Delete a report |

---

## 4. Frontend

### 4.1 Pages and which API modules they use

| Route | Page | API module |
|---|---|---|
| `/` | `DashboardPage` | `farms`, `health` |
| `/farms` | `FarmsFieldsPage` | `farms`, `suitability` |
| `/fields/:fieldId` | `FieldDetailPage` | `farms`, `soil`, `weather`, `risk` |
| `/fields/:fieldId/edit` | `FieldEditPage` | `farms` |
| `/soil` | `SoilPage` | `soil` |
| `/weather` | `WeatherPage` | `weather` |
| `/planner` | `CropPlannerPage` | `suitability`, `crops` |
| `/sensors` | `SensorsPage` | `sensors` |
| `/irrigation` | `IrrigationPage` | `irrigation` |
| `/risk` | `CropRiskPage` | `risk`, `approvals` |
| `/activities` | `ActivitiesPage` | `activities`, `approvals` |
| `/advisory` | `AdvisoryPage` | `workflow`, `approvals` |
| `/reports` | `ReportsPage` | `reports` |
| `/dashboard` | redirect → `/` | — |
| `*` | `NotFoundPage` | — |

Defined in `frontend/src/AppRoutes.tsx`.

### 4.2 Layering

```
src/pages/<X>Page.tsx          UI only: renders, forms, charts
        │  uses
src/hooks/use<X>.ts            TanStack Query: cache, loading, invalidation
        │  calls
src/api/<x>.ts                 Typed request/response functions
        │  via
src/api/client.ts              axios instance, baseURL, error normalisation
        │
   FastAPI
```

A page never constructs a URL. It calls a hook, the hook calls `client.ts`,
`client.ts` applies `API_BASE_URL`. That is why changing the base URL is a
one-line change.

### 4.3 Error normalisation

`client.ts` converts FastAPI's `detail` payload into one `ApiError` carrying
`status`, `url` and a list of field-level `issues`, so pages show readable
messages instead of raw axios output.

### 4.4 Frontend commands

```bash
npm run dev      # Vite dev server
npm run build    # tsc -b && vite build
npm run lint     # eslint .
npm test         # vitest
```

---

## 5. Backend

### 5.1 Layering rule

```
api/         → routers, HTTP, status codes
  └ services/ → business logic, no HTTP concerns
       └ models/  → SQLAlchemy ORM
agents/      → LangGraph workflow (calls services)
ml/          → training + inference, joblib artifacts
rag/         → FAISS index + keyfact retrieval
```

`api/` depends on `services/`, **never the reverse**. Services never import
FastAPI request objects. That is what makes the test suite fast and the logic
reusable from scripts.

### 5.2 Key modules

| Path | Role |
|---|---|
| `backend/app/main.py` | App factory, router mounting, startup |
| `backend/app/core/config.py` | `Settings`, env parsing, `sqlalchemy_url`, `cors_origin_list` |
| `backend/app/core/database.py` | Engine creation, `_engine_kwargs`, `Base`, `init_db()` |
| `backend/app/api/routers/*.py` | One router per domain |
| `backend/app/services/*.py` | Business logic |
| `backend/app/agents/*.py` | The six agents and the graph |
| `backend/app/ml/` | Model training and prediction |
| `backend/app/rag/` | FAISS index construction |
| `backend/app/data/crop_catalog.py` | Crop requirements |
| `backend/app/data/knowledge/*.md` | The RAG corpus |

### 5.3 Database handling

```python
# backend/app/core/database.py
def _engine_kwargs(database_url: str) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"echo": settings.sql_echo, "future": True}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
    else:
        kwargs.update(
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_pre_ping=True,
            pool_recycle=1800,
        )
    return kwargs
```

The SQLite-only arguments are guarded by the scheme, so PostgreSQL gets a
proper pooled engine instead.

### 5.4 The DSN normalisation (why PostgreSQL works at all)

```python
# backend/app/core/config.py
@property
def sqlalchemy_url(self) -> str:
    url = self.database_url
    if url.startswith(("postgresql://", "postgres://")):
        return "postgresql+psycopg://" + url.split("://", 1)[1]
    return url
```

The project installs psycopg **3**. SQLAlchemy maps a bare `postgresql://` DSN
to the psycopg**2** dialect, which raises
`ModuleNotFoundError: No module named 'psycopg2'` during `create_engine` — at
import time, before a port is bound. PaaS providers hand out the bare form, so
the driver is pinned here rather than requiring operators to remember a
`+psycopg` suffix.

### 5.5 Settings worth knowing

| Env var | Default | Effect |
|---|---|---|
| `DATABASE_URL` | `sqlite:///…/agri.db` | PostgreSQL in production |
| `CORS_ORIGINS` | — | Comma-separated, split by `Settings.cors_origin_list` |
| `SEED_DEMO_DATA_ON_STARTUP` | `false` | Create the 5 demo fields |
| `ALLOW_OFFLINE_WEATHER_FALLBACK` | `false` | Fall back to climatology when the provider is unreachable |
| `LLM_ENABLED` | `false` | Uses a deterministic provider unless a key is present |
| `REPORTS_DIR` | `/data/reports` | PDF output location |
| `LOG_LEVEL` | `INFO` | |
| `TRAIN_AT_BUILD` (build arg) | `false` | If `true`, retrains ML at image build |

---

## 6. The agents

### 6.1 Six orchestration nodes, fourteen classes

`AGENT_ORDER` contains **six** entries. Three are `CompositeAgent` wrappers
holding sub-steps, so the published count of six is honoured while keeping each
specialised class single-purpose:

| Node | Composite | Sub-steps |
|---|---|---|
| `agent_profile` | `FarmFieldProfileAgent` | `FarmFieldProfileAgent`, `SensorTelemetryAgent` |
| `agent_soil` | — | `SoilNutrientAgent` |
| `agent_weather` | `WeatherClimateAgent` | `WeatherClimateAgent`, `TelemetryBridgeAgent` |
| `agent_suitability` | `CropSuitabilityAgent` | `KnowledgeRetrievalAgent`, `CropSuitabilityAgent` |
| `agent_irrigation` | `IrrigationAgent` | `MLForecastAgent`, `IrrigationAgent` |
| `agent_risk` | `CropRiskAdvisoryAgent` | `CropRiskAdvisoryAgent`, `ActivityPlannerAgent`, `AdvisoryNarrativeAgent` |

### 6.2 The graph is a straight line

```
__start__ → agent_profile → agent_soil → agent_weather
         → agent_suitability → agent_irrigation → agent_risk → __end__
```

No fan-out and no cycle. Each node reads the shared state written by the
previous one. That makes the run deterministic and easy to trace, and it means
an agent that fails leaves an explicit `error` in state rather than hanging the
workflow.

### 6.3 Shared state

Every agent receives one `AgentContext`:

```python
# backend/app/agents/base.py
@dataclass
class AgentContext:
    db: Session
    field: Field
    farm: Farm
    crop: str
    requirements: CropRequirements
    workflow_run_id: int
    retriever: KnowledgeRetriever = field(default_factory=get_retriever)
    ml: MLRegistry = field(default_factory=get_ml_registry)
    options: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    sources: list[SourceReference] = field(default_factory=list)
```

`evidence` and `sources` are **accumulated** as agents run, so the final
advisory report can show every claim with where it came from.

### 6.4 Result contract and error containment

```python
# backend/app/agents/base.py
class BaseAgent:
    name: str = "base_agent"
    responsibility: str = "abstract base agent"

    def execute(self, ctx: AgentContext) -> AgentResult:
        started = time.perf_counter()
        try:
            result = self.run(ctx)
        except Exception as exc:
            logger.exception("Agent %s failed on workflow %s", self.name, ctx.workflow_run_id)
            result = AgentResult(
                name=self.name,
                responsibility=self.responsibility,
                status="failed",
                error=f"{type(exc).__name__}: {exc}",
                reasoning=f"The {self.name} aborted; downstream steps treat its output as unavailable.",
            )
        result.duration_ms = round((time.perf_counter() - started) * 1000, 2)
        result.sources = [SourceReference.model_validate(item) for item in result.sources]
        ctx.add_evidence(*result.evidence)
        ctx.add_sources(*result.sources)
        if result.error:
            ctx.warn(f"{self.name}: {result.error}")
        return result
```

**Why this matters:** a crashing agent does not take down the request. It
records `status="failed"` with the exception text, warns the context, and the
run continues. The trace then shows *which* agent failed and why.

It also means a defect can hide. `_model_finding` once declared three
parameters while its call site passed two; the risk agent raised `TypeError`,
`execute` caught it, and a risk-monitoring run finished with zero alerts. The
static check in `tests/test_risk_model_finding.py` now asserts every call site's
argument count matches the signature.

### 6.5 What each agent does

**1 — Farm & Field Profile** (`context_agents.py`)
Registers farms and fields, records area, location, crop history, irrigation
source and water availability, then **names what is missing** rather than
filling it in. Output is a structured profile; the frontend renders it on
`/farms`.

**2 — Soil & Nutrient Analysis** (`context_agents.py::SoilNutrientAgent`)
Reads the measured soil observation, compares it against the retrieved crop
requirements, and produces a condition summary. Measured values are passed
through untouched; only the interpretation layer is generated. The
`/soil/observations/{id}` endpoint returns both, separately.

**3 — Weather & Climate Analysis** (`context_agents.py::WeatherClimateAgent`)
Calls Open-Meteo for current and forecast temperature, rainfall, probability,
humidity and wind, then derives heat-stress, heavy-rainfall and dry-period
findings. If the provider is unreachable and
`ALLOW_OFFLINE_WEATHER_FALLBACK` is set, it falls back and **labels** the result
`is_simulated=true`. It never presents generated weather as measured weather —
this is asserted in acceptance TC-02.

**4 — Crop Planning & Suitability** (`decision_agents.py::CropSuitabilityAgent`,
preceded by `KnowledgeRetrievalAgent`)
Retrieves the crop's reference requirements, then scores seven factors:
`soil_ph`, `soil_texture`, `soil_moisture`, `temperature`,
`rainfall_and_water`, `soil_fertility`, `crop_history`. Each factor carries a
verdict, a score, a weight, the measured value and the retrieved range. Missing
inputs go to `missing_information` instead of being scored as passes.

**5 — Irrigation Planning** (`decision_agents.py::IrrigationAgent`,
preceded by `MLForecastAgent`)
Combines soil moisture, crop stage, forecast rainfall and water availability
into one of `irrigate_soon`, `postpone_irrigation`, `consider_irrigation` or
`review_required`. When significant rain is forecast it proposes postponement.
The recommendation is a **proposal**: it is written to state, not to the field,
and an irrigation activity only appears after a human approves.

**6 — Crop Risk & Farm Advisory** (`decision_agents.py`)
Three sub-steps:
- `CropRiskAdvisoryAgent` — produces environmental risk findings and
  cross-checks the rule-based severity against the ML classifier.
- `ActivityPlannerAgent` — turns findings into farm activities.
- `AdvisoryNarrativeAgent` — writes the plain-language advisory.

The rule that governs everything here: report *conditions favourable to* a
problem, never that the problem exists. Findings are worded as
favourability statements and carry a disclaimer that the system has no
diagnostic capability.

### 6.6 Explainability: measured vs interpreted

```python
# backend/app/agents/base.py
def evidence_from_measurement(
    label: str,
    value: Any,
    *,
    unit: str | None = None,
    kind: str = "measured",
    source: str | None = None,
    reference: str | None = None,
    note: str | None = None,
    observed_at: datetime | None = None,
) -> Evidence:
    return Evidence(label=label, value=value, unit=unit, kind=kind, ...)
```

`kind` is the discriminator that runs all the way to the UI. The full enum is
`SourceKind` in `backend/app/models/enums.py`:

| `kind` | Meaning |
|---|---|
| `measured` | A value taken from a lab report or entered measurement — never altered |
| `observed` | A value read off a device or observed in the field |
| `forecast` | Weather model output, with provider and timestamp |
| `retrieved_reference` | Quoted from the knowledge base, with the document reference |
| `rule` | Derived by configured agronomic logic |
| `ml_prediction` | A model output, with its confidence |
| `llm_narrative` | Generated text from an LLM, when one is configured |
| `deterministic_narrative` | Generated text from the fallback template provider |
| `user_input` | Something a person typed in |
| `simulated` | Synthetic telemetry, flagged as such |

Every evidence item carries its `kind` all the way to the client, so measured
facts, retrieved references, model output and generated text stay visibly
apart. The frontend groups them (`groupByKind` in `AdvisoryPage`,
`CropPlannerPage`, `IrrigationPage`) and badges them with `EvidenceKindBadge`;
the PDF report prints it inline, so a line reads
`soil pH: 5.4 [measured]`.

### 6.7 Signature-consistency guard

```python
# backend/tests/test_risk_model_finding.py
def test_every_call_site_matches_the_signature() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    target = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_model_finding"
    )
    declared, calls = _call_arity(target)

    assert calls, "expected at least one call site to check"
    for count in calls:
        assert count == declared, (
            f"_model_finding declares {declared} parameters but a call site passes {count}; "
            "the data-dependent ML-escalation branch would raise TypeError at runtime"
        )
```

This parses the module and compares declared vs passed arity. It fails on the
mismatch itself rather than waiting for a fixture that happens to exercise the
branch — which is exactly how the original bug stayed latent across runs.

---

## 7. Data honesty rules

These are enforced in code, not just documented.

| Rule | Where |
|---|---|
| Measured values are never rewritten by interpretation | Soil service stores the observation; interpretation is a separate row |
| Simulated telemetry is flagged on every row | `is_simulated=true`, `quality_flags=["simulated"]` |
| Third-party soil data is labelled a model, not a probe | `quality_flags=["third_party_model"]` |
| Weather fallback is labelled | `is_simulated=true` plus a fallback marker |
| Live data is not injected with future timestamps | `sync_live_soil_telemetry` discards future hours |
| Risk is never phrased as a diagnosis | `risk/disclaimer` endpoint, `confirmed_as_favourability_statement` |
| Nothing actuates without a human | Approval gate; activities stay `planned` and awaiting authorisation |
| Empty plans are not padded | The planner emits work only when the agents found a signal |

---

## 8. Demonstration walkthrough

Use this for a live run. Two options first.

**Option A — Docker (recommended):**

```bash
cp .env.example .env
docker compose up --build
```

**Option B — source:**

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r backend/requirements.txt -r backend/requirements-dev.txt
cd backend && uvicorn app.main:app --reload --port 8000
# then, in another terminal:
cd frontend && npm install && npm run dev
```

Then load `http://localhost:8080` (Docker) or `http://localhost:5173` (source).

### The eight steps

**Step 1 — Health.**
Open `http://localhost:8000/api/v1/health`. Expect `database: up`,
`ml: up`, `rag: up`, and `weather_provider: open-meteo`. This proves the DB,
the committed ML artifacts and the FAISS index all loaded.

**Step 2 — Register a farm and a field.**
`/farms` page → create a farm, then add a field with area, soil type,
location and proposed crop. *(Functional Requirement 1.)*

**Step 3 — Record a soil test.**
`/soil` page → record pH, N, P, K, moisture. The response returns the
**measured** values and the **AI interpretation** separately, and the original
pH is unchanged. Open the evidence view to see `kind: measured` alongside the
retrieved reference range. *(Requirements 2, 11.)*

**Step 4 — Retrieve weather.**
`/weather` page → pick a field. Shows temperature, rainfall, rain probability,
humidity and the forecast period with provider and timestamp. Explain the
honesty rule: if the provider were unreachable, the UI would label the data
`simulated` rather than pass it off as live. *(Requirements 3, 4.)*

**Step 5 — Analyse sensors.**
`/sensors` page → **Sync live data** for a field, then generate simulated
telemetry. Show the trend chart and point out `is_simulated` on every row. Note
the three-month soil case: `sync-live-soil` stores Open-Meteo model output with
`quality_flags=["third_party_model"]` — a model, not an in-field probe.
*(Requirement 8.)*

**Step 6 — Run the agents.**
`/planner` → select a field and crop, then trigger the workflow. Walk the six
nodes in order: profile → soil → weather → suitability → irrigation → risk.
Show the trace per agent, including the citation each one retrieved.
*(Requirements 4, 5, 10, 11.)*

On the advisory page, the result is one of:
- **Suitable** — every factor favourable
- **Suitable with Conditions** — some factors limiting but workable
- **Additional Information Required** — inputs missing; the gaps are named
- **Agronomic Review Required** — a limitation needing a human

**Step 7 — ML predictions.**
From the same run, show the two models: the 7-day soil moisture forecast
(MAE 0.35, R² 0.997) and the environmental risk classifier (accuracy 0.974,
macro-F1 0.959). Emphasise the **grouped split** — whole seasons held out — and
that both models are consumed by the agents, not shown in isolation.
*(Requirement 10.)*

**Step 8 — Human review and the report.**
`/advisory` → approve or reject. Approve an irrigation and only then does the
activity become `scheduled`. Reject and it stays `planned` with a note. Then
`/reports` → generate and download the PDF. Point out that it lists source
references and the review status. *(Requirements 12, 13, 15.)*

### The six acceptance cases

Run `pytest` in `backend/` — the recorder writes
`backend/artifacts/acceptance_report.md`.

Each case carries a `requirement` field, so the brief's scenarios are traced to
a named test:

| Brief scenario | Verified by |
|---|---|
| Suitable conditions → evidence-based suitability | TC-03 |
| pH outside the crop range → limitation identified | `tests/test_ph_suitability.py` |
| Low moisture → water-stress / irrigation review | TC-04, `tests/test_alerts_and_approvals.py` |
| Rainfall forecast → irrigation adapts | `tests/test_irrigation_service.py` |
| Missing soil info → information requested | TC-01, `tests/test_soil_service.py` |
| High humidity, disease-favourable → alert not diagnosis | TC-05, `tests/test_risk_model_finding.py` |

> TC-01…TC-06 are this project's own identifiers from
> `backend/artifacts/acceptance_report.json`, **not** the brief's scenario
> numbers. TC-02 (weather labelling) and TC-06 (full orchestration + PDF) cover
> the remaining requirements.

Expected: **6/6 cases, 147/147 checks.** Backend suite: **145 tests**, ruff
clean. Frontend: 60 tests, `tsc` and eslint clean.

---

## 9. Troubleshooting

| Symptom | Likely cause |
|---|---|
| `ModuleNotFoundError: No module named 'psycopg2'` | `DATABASE_URL` not normalised — should not happen since `sqlalchemy_url` |
| Agent shows `status: failed` in the trace | Its exception was caught by `execute`; check `reasoning` for the message |
| Empty activity plan | Correct — the planner emits work only when there is a real signal |
| `422` on `/suitability/assess` | `field_id` is a **query** parameter, not part of the body |
| `422` on `/activities/plan` | `workflow_run_id` is required |
| Frontend shows 0 sensors | No telemetry for that field; run **Sync live data** or simulate |
| Model not loaded | Check `/ml/status`; artifacts are committed so this indicates a build problem |
| Report download 404 | `REPORTS_DIR` is ephemeral on a free tier without an attached disk |

---

## 10. Commands reference

```bash
# Backend
cd backend && uvicorn app.main:app --reload --port 8000
cd backend && python -m pytest -q
cd backend && python -m ruff check app tests
cd backend && python -m ruff format app tests

# Frontend
cd frontend && npm run dev
cd frontend && npm run build && npm run lint && npm test

# Contract regeneration
# (run the contract writer — output lands in api-contract.json / api-routes.txt)

# Sample data export (expects a backend on :8123)
python scripts/export_sample_data.py

# Full stack
cp .env.example .env
docker compose up --build
FRONTEND_PORT=8090 BACKEND_PORT=8001 docker compose up --build   # ports taken
```

---

## 11. Project layout

```
agri-mini/
├── backend/
│   ├── app/
│   │   ├── main.py              app factory, router mounting
│   │   ├── core/                config, database, settings
│   │   ├── api/routers/         one router per domain
│   │   ├── services/            business logic, no HTTP
│   │   ├── agents/              the six agents and the LangGraph
│   │   ├── models/              SQLAlchemy ORM
│   │   ├── schemas/             Pydantic request/response models
│   │   ├── ml/                  training, inference, metrics.json
│   │   ├── rag/                 FAISS index construction
│   │   └── data/                crop_catalog, knowledge/*.md
│   ├── tests/                   145 tests incl. acceptance recorder
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── pages/               14 pages
│   │   ├── api/                 typed client per domain
│   │   ├── hooks/               TanStack Query hooks
│   │   ├── components/
│   │   ├── AppRoutes.tsx        route table
│   │   └── vite.config.ts       dev proxy
│   └── vercel.json              SPA rewrite config
├── sample_data/                 exported demonstration dataset
├── scripts/export_sample_data.py
├── api-contract.json            generated OpenAPI contract (71 paths / 83 ops)
├── api-routes.txt               route listing
├── render.yaml                  Render Blueprint
├── docker-compose.yml
├── Dockerfile.backend
└── README.md                    overview, architecture diagram
```