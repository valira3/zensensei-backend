"""
ZenSensei Shared Middleware - Structured Logging

Starlette ASGI middleware that emits a structured log record for every
HTTP request/response using structlog.

Log record fields
-----------------
method          HTTP method (GET, POST, …)
path            Request path
status_code     HTTP response status
duration_ms     Round-trip duration in milliseconds
request_id      UUID assigned per request (also injected as X-Request-ID header)
user_agent      Value of the User-Agent header
remote_addr     Client IP address
"""

from __future__ import annotations

import time
import uuid
from typing import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

# Configure structlog once at import time.
# Individual services can call structlog.configure() again to override.
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(20),  # INFO
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)

logger = structlog.get_logger("zensensei.middleware.logging")


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    ASGI middleware that logs every request/response as a structured JSON record.

    Usage::

        app.add_middleware(LoggingMiddleware, service_name="user-service")
    """

    def __init__(self, app: ASGIApp, service_name: str = "zensensei") -> None:
        super().__init__(app)
        self._service_name = service_name

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = str(uuid.uuid4())
        start = time.perf_counter()

        # Bind request context so all log records within this request carry it
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            service=self._service_name,
        )

        response = await call_next(request)

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        response.headers["X-Request-ID"] = request_id

        logger.info(
            "request",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
            remote_addr=request.client.host if request.client else "-",
            user_agent=request.headers.get("user-agent", "-"),
        )

        return response
