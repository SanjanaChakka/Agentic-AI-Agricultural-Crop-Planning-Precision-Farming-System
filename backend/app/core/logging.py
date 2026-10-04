"""Application logging configuration."""

from __future__ import annotations

import logging
import logging.config
import sys

from app.core.config import settings

_CONFIGURED = False


class _SafeFormatter(logging.Formatter):
    """Formatter that never emits values of secret-ish settings."""

    _redactions = (
        (settings.openai_api_key or "\0", "***"),
        (settings.weather_api_key or "\0", "***"),
    )

    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        for configured_key, placeholder in self._redactions:
            if configured_key != "\0" and configured_key in message:
                message = message.replace(configured_key, placeholder)
        return message


def configure_logging() -> None:
    """Idempotently configure root logging with a single console handler."""
    global _CONFIGURED  # noqa: PLW0603 - module-level idempotency flag
    if _CONFIGURED:
        return

    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(_SafeFormatter("%(asctime)s %(levelname)-8s [%(name)s] %(message)s", datefmt="%H:%M:%S"))

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "app": {
                    "()": _SafeFormatter,
                    "format": "%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
                    "datefmt": "%H:%M:%S",
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "app",
                    "stream": "ext://sys.stdout",
                }
            },
            "root": {"handlers": ["console"], "level": level},
            "loggers": {
                "uvicorn": {"handlers": ["console"], "level": level, "propagate": False},
                "uvicorn.access": {"handlers": ["console"], "level": level, "propagate": False},
                "sqlalchemy.engine": {"handlers": ["console"], "level": "WARNING", "propagate": False},
            },
        }
    )
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)
