"""Structured application errors and FastAPI exception handlers."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.core.logging import get_logger

logger = get_logger(__name__)


class AppError(Exception):
    """Base class for expected, reportable application errors."""

    status_code: int = 500
    code: str = "internal_error"
    message: str = "An unexpected error occurred."

    def __init__(self, message: str | None = None, *, code: str | None = None, **context: Any) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.context: dict[str, Any] = {k: v for k, v in context.items() if v is not None}
        super().__init__(self.message)

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"error": {"code": self.code, "message": self.message}}
        if self.context:
            payload["error"]["context"] = self.context
        return payload


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"
    message = "The requested resource was not found."


class ConflictError(AppError):
    status_code = 409
    code = "conflict"
    message = "The request conflicts with the current state."


class UnprocessableEntityError(AppError):
    status_code = 422
    code = "unprocessable_entity"
    message = "The request could not be processed with the supplied data."


class UpstreamServiceError(AppError):
    """A third-party service (weather API, LLM, ...) failed."""

    status_code = 502
    code = "upstream_service_error"
    message = "An upstream service could not be reached."


class ServiceUnavailableError(AppError):
    status_code = 503
    code = "service_unavailable"
    message = "A required component is currently unavailable."


def _json_error(status_code: int, code: str, message: str, context: Any = None) -> JSONResponse:
    body: dict[str, Any] = {"error": {"code": code, "message": message}}
    if context:
        body["error"]["context"] = context
    return JSONResponse(status_code=status_code, content=body)


def register_exception_handlers(app: FastAPI) -> None:
    """Attach handlers that convert every error into a consistent JSON shape."""

    @app.exception_handler(AppError)
    async def _app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        if exc.status_code >= 500:
            logger.error("Application error %s: %s", exc.code, exc.message)
        else:
            logger.info("Application error %s: %s", exc.code, exc.message)
        return JSONResponse(status_code=exc.status_code, content=exc.to_payload())

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {
                "field": ".".join(str(part) for part in err.get("loc", []) if part != "body"),
                "message": err.get("msg", "invalid value"),
                "type": err.get("type", "value_error"),
            }
            for err in exc.errors()
        ]
        return _json_error(422, "request_validation_error", "Request payload validation failed.", details)

    @app.exception_handler(SQLAlchemyError)
    async def _db_handler(_: Request, exc: SQLAlchemyError) -> JSONResponse:
        logger.exception("Database failure", exc_info=exc)
        return _json_error(503, "database_unavailable", "A database error occurred. Please retry shortly.")

    @app.exception_handler(Exception)
    async def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
        return _json_error(500, "internal_error", "An unexpected error occurred.")
