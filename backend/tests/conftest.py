"""Shared pytest fixtures.

Every test runs against a *throwaway* SQLite database in a temporary directory
and uses the real, committed ML artifacts so the suite exercises the same
production code paths.  Network credentials are forced off: the weather agent
must prove that it either reaches the keyless live provider or falls back with an
explicit ``is_simulated`` label - it must never be handed a fabricated "API"
result, and a test must never depend on somebody's API key being present.

Environment variables are set *before* ``app`` is imported because
``app.core.config`` builds its settings singleton at import time.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

_TMP_ROOT = Path(tempfile.mkdtemp(prefix="agri-pytest-"))

# --- environment ------------------------------------------------------------
os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP_ROOT / 'test.db').as_posix()}"
os.environ["REPORTS_DIR"] = str(_TMP_ROOT / "reports")
os.environ["SEED_DEMO_DATA_ON_STARTUP"] = "true"
os.environ["ALLOW_OFFLINE_WEATHER_FALLBACK"] = "true"
os.environ["LOG_LEVEL"] = "WARNING"
os.environ["RAG_REBUILD_ON_STARTUP"] = "false"
# Never inherit a developer's personal keys into the test run.
for _secret in ("OPENAI_API_KEY", "WEATHER_API_KEY", "DATABASE_URL"):
    if _secret == "DATABASE_URL":  # noqa: S105 - environment variable name, not a secret
        continue
    os.environ.pop(_secret, None)
os.environ["OPENAI_API_KEY"] = ""
os.environ["WEATHER_API_KEY"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.main import app  # noqa: E402
from app.ml.registry import get_ml_registry  # noqa: E402
from app.rag.retriever import get_retriever  # noqa: E402

API = settings.api_v1_prefix


def pytest_sessionfinish(session, exitstatus) -> None:
    shutil.rmtree(_TMP_ROOT, ignore_errors=True)


@pytest.fixture(scope="session")
def client() -> Iterator[TestClient]:
    """A ``TestClient`` with the real lifespan (schema, index, models, seed)."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def field_id(client: TestClient) -> int:
    """The primary seeded field used by the acceptance tests."""
    fields = client.get(f"{API}/fields", params={"limit": 50}).json()
    assert fields, "the seed service must create at least one field"
    return int(fields[0]["id"])


@pytest.fixture(scope="session")
def retriever():  # type: ignore[no-untyped-def]
    return get_retriever()


@pytest.fixture(scope="session")
def ml_registry():  # type: ignore[no-untyped-def]
    return get_ml_registry()


@pytest.fixture(scope="session")
def run_summary(client: TestClient, field_id: int) -> dict:
    """One real multi-agent workflow run, shared by the acceptance cases."""
    response = client.post(
        f"{API}/workflow/runs",
        json={"field_id": field_id, "crop": "cotton", "force_refresh_weather": True},
    )
    assert response.status_code == 201, response.text
    return response.json()
