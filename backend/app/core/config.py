"""Centralised configuration.

All runtime configuration is read from environment variables (optionally seeded
from a ``.env`` file).  Secrets (API keys, database passwords) are never given
hard-coded defaults and are never written to logs.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# ``backend/app/core/config.py`` -> ``backend``
BACKEND_ROOT = Path(__file__).resolve().parents[2]
# repository root (contains ``.env`` for docker-compose style deployments)
REPO_ROOT = BACKEND_ROOT.parent

_ENV_FILES = (
    BACKEND_ROOT / ".env",
    REPO_ROOT / ".env",
)


def _strip_inline_comment(value: str) -> str:
    """Remove a trailing ``# comment`` from an unquoted ``.env`` value.

    A ``#`` only opens a comment when it is preceded by whitespace or starts the
    value, so tokens that legitimately contain ``#`` survive intact.
    """
    for position, char in enumerate(value):
        if char == "#" and (position == 0 or value[position - 1].isspace()):
            return value[:position].rstrip()
    return value


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return _strip_inline_comment(value)


def _load_dotenv_files(paths: tuple[Path, ...] = _ENV_FILES) -> list[str]:
    """Seed ``os.environ`` from simple ``KEY=VALUE`` files.

    Real process environment variables always win, so container/CI injected
    secrets are never overwritten.  Returns the list of files that were read.
    """
    loaded: list[str] = []
    for path in paths:
        if not path.is_file():
            continue
        try:
            for raw_line in path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = _unquote(value.strip())
                if key and key not in os.environ and value:
                    os.environ[key] = value
            loaded.append(str(path))
        except OSError:  # pragma: no cover - unreadable env file must not crash boot
            logger.warning("Unable to read environment file %s", path)
    return loaded


class Settings(BaseSettings):
    """Runtime settings.  Every field maps to an upper-case env var."""

    model_config = SettingsConfigDict(
        env_file=None,
        extra="ignore",
        case_sensitive=False,
    )

    # --- Application -----------------------------------------------------
    app_name: str = "Agentic AI Agricultural Crop Planning & Precision Farming System"
    app_version: str = "1.0.0"
    environment: str = "development"
    debug: bool = False
    log_level: str = "INFO"
    api_v1_prefix: str = "/api/v1"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # --- Persistence -----------------------------------------------------
    # SQLite by default so the project runs with zero infrastructure.
    # Set DATABASE_URL to a PostgreSQL DSN for production (see .env.example).
    database_url: str = f"sqlite:///{(BACKEND_ROOT / 'agri.db').as_posix()}"
    sql_echo: bool = False
    db_pool_size: int = 5
    db_max_overflow: int = 10

    # --- LLM provider (optional) ----------------------------------------
    # Absent key -> the system runs fully on deterministic, evidence-based
    # narratives instead.  Never logged.
    openai_api_key: str | None = None
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_timeout_seconds: float = 20.0
    llm_enabled: bool = True

    # --- Weather ---------------------------------------------------------
    # Primary: OpenWeatherMap (requires key).  Secondary: Open-Meteo (keyless).
    weather_api_key: str | None = None
    weather_api_base_url: str = "https://api.openweathermap.org/data/2.5"
    open_meteo_base_url: str = "https://api.open-meteo.com/v1/forecast"
    weather_timeout_seconds: float = 10.0
    weather_forecast_days: int = 7
    # When every upstream fails, a clearly-labelled offline estimate may be
    # returned instead of hard-failing the workflow.
    allow_offline_weather_fallback: bool = True

    # --- Retrieval (agricultural RAG) -----------------------------------
    rag_top_k: int = 4
    rag_min_score: float = 0.05
    rag_relative_score_ratio: float = 0.4
    rag_rebuild_on_startup: bool = False

    # --- Machine learning ------------------------------------------------
    ml_artifacts_dir: str = str(BACKEND_ROOT / "app" / "ml" / "artifacts")
    ml_autoload: bool = True
    ml_random_seed: int = 20240517

    # --- Behaviour -------------------------------------------------------
    seed_demo_data_on_startup: bool = True
    reports_dir: str = str(BACKEND_ROOT / "reports")

    @field_validator("cors_origins")
    @classmethod
    def _normalise_origins(cls, value: str) -> str:
        cleaned = [item.strip().rstrip("/") for item in value.split(",") if item.strip()]
        if not cleaned:
            return ""
        return ",".join(cleaned)

    @property
    def cors_origin_list(self) -> list[str]:
        return [item for item in self.cors_origins.split(",") if item]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_enabled and self.openai_api_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    _load_dotenv_files()
    settings = Settings()
    # Never print secrets - only report *presence*.
    logger.debug(
        "Settings loaded (env=%s, db=%s, llm_configured=%s, weather_key_present=%s)",
        settings.environment,
        "sqlite" if settings.is_sqlite else "postgres/other",
        settings.llm_configured,
        bool(settings.weather_api_key),
    )
    return settings


settings = get_settings()
