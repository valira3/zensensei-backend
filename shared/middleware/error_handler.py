"""
ZenSensei Shared Middleware - Global Error Handler

Registers FastAPI exception handlers that convert all unhandled exceptions
into structured ``ErrorResponse`` JSON payloads so that clients always
receive a consistent error schema.

Handled cases
-------------
RequestValidationError  → 422 with per-field validation details
HTTPException           → passthrough with original status code
ValueError              → 400 Bad Request
PermissionError         → 403 Forbidden
Exception (catch-all)   → 500 Internal Server Error (details hidden in prod)

Usage::

    app = FastAPI()
    add_error_handler(app)
"""

from __future__ import annotations

import logging
import traceback
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import ORJSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from shared.config import ZenSenseiConfig, get_config

logger = logging.getLogger(__name__)


def _error_response(
    error_code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "success": False,
        "error_code": error_code,
        "message": message,
        "details": details,
    }


def add_error_handler(
    app: FastAPI,
    config: ZenSenseiConfig | None = None,
) -> None:
    """
    Register global exception handlers on *app*.

    Args:
        app: The FastAPI application instance.
        config: Optional config override (used to toggle detail visibility).
    """
    cfg = config or get_config()

    # ─── Pydantic validation errors ─────────────────────────────────────────────
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> ORJSONResponse:
        details: list[dict[str, Any]] = []
        for error in exc.errors():
            details.append(
                {
                    "field": " -> ".join(str(loc) for loc in error.get("loc", [])),
                    "message": error.get("msg"),
                    "type": error.get("type"),
                }
            )
        logger.warning("Validation error on %s %s", request.method, request.url.path)
        return ORJSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_error_response(
                error_code="VALIDATION_ERROR",
                message="Request validation failed",
                details={"errors": details},
            ),
        )

    # ─── HTTP exceptions ─────────────────────────────────────────────────────
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request,
        exc: StarletteHTTPException,
    ) -> ORJSONResponse:
        error_code_map: dict[int, str] = {
            400: "BAD_REQUEST",
            401: "UNAUTHORIZED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            405: "METHOD_NOT_ALLOWED",
            409: "CONFLICT",
            410: "GONE",
            429: "RATE_LIMIT_EXCEEDED",
            500: "INTERNAL_SERVER_ERROR",
            502: "BAD_GATEWAY",
            503: "SERVICE_UNAVAILABLE",
        }
        error_code = error_code_map.get(exc.status_code, f"HTTP_{exc.status_code}")
        logger.warning(
            "HTTP %d on %s %s",
            exc.status_code,
            request.method,
            request.url.path,
        )
        return ORJSONResponse(
            status_code=exc.status_code,
            content=_error_response(
                error_code=error_code,
                message=str(exc.detail),
            ),
        )

    # ─── ValueError → 400 ──────────────────────────────────────────────────────
    @app.exception_handler(ValueError)
    async def value_error_handler(
        request: Request,
        exc: ValueError,
    ) -> ORJSONResponse:
        logger.warning("ValueError on %s %s: %s", request.method, request.url.path, exc)
        return ORJSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=_error_response(
                error_code="BAD_REQUEST",
                message=str(exc),
            ),
        )

    # ─── PermissionError → 403 ─────────────────────────────────────────────────────
    @app.exception_handler(PermissionError)
    async def permission_error_handler(
        request: Request,
        exc: PermissionError,
    ) -> ORJSONResponse:
        logger.warning("PermissionError on %s %s: %s", request.method, request.url.path, exc)
        return ORJSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=_error_response(
                error_code="FORBIDDEN",
                message="You do not have permission to perform this action.",
            ),
        )

    # ─── Catch-all → 500 ──────────────────────────────────────────────────────
    @app.exception_handler(Exception)
    async def generic_exception_handler(
        request: Request,
        exc: Exception,
    ) -> ORJSONResponse:
        logger.error(
            "Unhandled exception on %s %s",
            request.method,
            request.url.path,
            exc_info=True,
        )
        details: dict[str, Any] | None = None
        if cfg.is_development:
            details = {"traceback": traceback.format_exc()}

        return ORJSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_response(
                error_code="INTERNAL_SERVER_ERROR",
                message="An unexpected error occurred. Please try again later.",
                details=details,
            ),
        )
