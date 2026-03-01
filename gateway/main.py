"""
ZenSensei API Gateway - Application Entry Point

FastAPI application that:
  - Validates JWT tokens before forwarding requests
  - Enforces per-IP rate limiting (100 req / min)
  - Adds CORS headers for browser clients
  - Proxies all /api/v1/* traffic to the correct microservice
  - Exposes /health, /api/v1/status, and /api/v1/docs endpoints

Port: 4000
"""

from __future__ import annotations

import logging
import os
import sys
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncGenerator
from collections import defaultdict, deque

import structlog
import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse, RedirectResponse

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_SERVICES_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for _p in (_REPO_ROOT, _SERVICES_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from gateway.health import check_all_services
from gateway.proxy import ProxyRouter
from gateway.routes import ROUTES, resolve_route

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)
log = structlog.get_logger("gateway.main")

JWT_SECRET = os.getenv("SECRET_KEY", "change-me-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_ISSUER = os.getenv("JWT_ISSUER", "zensensei-user-service")

PUBLIC_PATHS: set[str] = {
    "/health",
    "/api/v1/status",
    "/api/v1/docs",
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/refresh",
    "/api/v1/auth/forgot-password",
    "/api/v1/auth/reset-password",
    "/api/v1/webhooks",
}

_RATE_LIMIT_WINDOW = 60
_RATE_LIMIT_MAX_REQUESTS = 100
_ip_request_times: dict[str, deque] = defaultdict(deque)


def _is_rate_limited(ip: str) -> bool:
    now = time.monotonic()
    window_start = now - _RATE_LIMIT_WINDOW
    dq = _ip_request_times[ip]
    while dq and dq[0] < window_start:
        dq.popleft()
    if len(dq) >= _RATE_LIMIT_MAX_REQUESTS:
        return True
    dq.append(now)
    return False


def _validate_jwt(token: str) -> dict[str, Any]:
    """Decode and validate a JWT. Returns the payload dict on success."""
    try:
        from jose import JWTError, jwt as jose_jwt
        payload = jose_jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
        )
        return payload
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}") from exc


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    log.info("gateway.startup", version="1.0.0")
    yield
    log.info("gateway.shutdown")


app = FastAPI(
    title="ZenSensei API Gateway",
    version="1.0.0",
    docs_url="/api/v1/docs",
    redoc_url=None,
    lifespan=lifespan,
    default_response_class=ORJSONResponse,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

proxy_router = ProxyRouter()


@app.get("/health", tags=["ops"])
async def health() -> ORJSONResponse:
    return ORJSONResponse({"status": "ok", "service": "api-gateway", "version": "1.0.0"})


@app.get("/api/v1/status", tags=["ops"])
async def status() -> ORJSONResponse:
    result = await check_all_services()
    status_code = 200 if result["status"] == "healthy" else 207
    return ORJSONResponse(result, status_code=status_code)


@app.api_route("/api/v1/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy(path: str, request: Request) -> Response:
    full_path = f"/api/v1/{path}"

    if _is_rate_limited(request.client.host if request.client else "unknown"):
        raise HTTPException(status_code=429, detail="Too many requests")

    if full_path not in PUBLIC_PATHS:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing Authorization header")
        token = auth_header[len("Bearer "):]
        _validate_jwt(token)

    route = resolve_route(full_path)
    if route is None:
        raise HTTPException(status_code=404, detail=f"No route found for {full_path}")

    return await proxy_router.forward(request, route)


if __name__ == "__main__":
    uvicorn.run("gateway.main:app", host="0.0.0.0", port=int(os.getenv("PORT", 4000)), reload=True)
