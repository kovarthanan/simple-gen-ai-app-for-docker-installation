"""Application exceptions and their HTTP mapping."""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.logging import get_logger

logger = get_logger(__name__)


class AppError(Exception):
    status_code = 500
    code = "internal_error"

    def __init__(self, message: str, details: Any | None = None):
        super().__init__(message)
        self.message = message
        self.details = details


class GuardrailViolation(AppError):
    status_code = 422
    code = "guardrail_violation"


class IngestionError(AppError):
    status_code = 400
    code = "ingestion_error"


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class RetrievalError(AppError):
    status_code = 502
    code = "retrieval_error"


class StoreError(AppError):
    status_code = 503
    code = "store_unavailable"


class LLMError(AppError):
    status_code = 502
    code = "llm_error"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        if exc.status_code >= 500:
            logger.error("%s: %s", exc.code, exc.message)
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.code, "message": exc.message, "details": exc.details},
        )
