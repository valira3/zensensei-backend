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

from collections import defaultdict, deque

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
    try:
        from jose import JWTError, jwt as jose_jwt
        payload = jose_jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
            options={"verify_aud": False},
        )
        return payload
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}") from exc


proxy_router = ProxyRouter()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    log.info("Starting ZenSensei API Gateway on port 4000 ...")
    await proxy_router.start()
    log.info("Registered %d upstream routes", sum(len(r.path_prefixes) for r in ROUTES))
    yield
    log.info("Shutting down ZenSensei API Gateway ...")
    await proxy_router.stop()


app = FastAPI(
    title="ZenSensei API Gateway",
    description="Unified API entry point that routes requests to the appropriate ZenSensei microservice with JWT validation, rate limiting, and CORS.",
    version="1.0.0",
    docs_url="/gateway/docs",
    redoc_url="/gateway/redoc",
    openapi_url="/gateway/openapi.json",
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
)

ALLOWED_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:3000,http://localhost:5173,http://localhost:8080",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-RateLimit-Limit", "X-RateLimit-Remaining"],
)


@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    start_ts = time.monotonic()
    request.state.request_id = request_id
    log.info("-> %s %s", request.method, request.url.path, request_id=request_id, client=request.client.host if request.client else "unknown")
    response: Response = await call_next(request)
    duration_ms = round((time.monotonic() - start_ts) * 1000, 1)
    log.info("<- %s %s %d  %.1fms", request.method, request.url.path, response.status_code, duration_ms, request_id=request_id)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time"] = f"{duration_ms}ms"
    return response


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if request.url.path in ("/health", "/api/v1/status"):
        return await call_next(request)
    client_ip = request.headers.get("X-Forwarded-For") or (request.client.host if request.client else "unknown")
    if _is_rate_limited(client_ip):
        return ORJSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded - 100 requests per minute"},
            headers={"Retry-After": "60", "X-RateLimit-Limit": str(_RATE_LIMIT_MAX_REQUESTS), "X-RateLimit-Remaining": "0"},
        )
    response: Response = await call_next(request)
    remaining = max(0, _RATE_LIMIT_MAX_REQUESTS - len(_ip_request_times[client_ip]))
    response.headers["X-RateLimit-Limit"] = str(_RATE_LIMIT_MAX_REQUESTS)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    return response


@app.get("/health", tags=["Gateway"], summary="Gateway health check")
async def gateway_health() -> ORJSONResponse:
    upstream_health = await check_all_services()
    status_code = 200 if upstream_health["status"] != "unhealthy" else 503
    return ORJSONResponse(status_code=status_code, content={"status": upstream_health["status"], "service": "api-gateway", "version": "1.0.0", "timestamp": datetime.now(timezone.utc).isoformat(), "upstreams": upstream_health})


@app.get("/api/v1/status", tags=["Gateway"], summary="All services status")
async def services_status() -> ORJSONResponse:
    health = await check_all_services()
    return ORJSONResponse(content=health)


@app.get("/api/v1/docs", tags=["Gateway"], summary="Aggregate API documentation")
async def aggregate_docs() -> RedirectResponse:
    return RedirectResponse(url="/gateway/docs", status_code=302)


@app.api_route(
    "/api/v1/{full_path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    tags=["Proxy"],
    summary="Proxy to microservices",
    include_in_schema=False,
)
async def proxy_request(full_path: str, request: Request) -> Response:
    path = request.url.path
    route = resolve_route(path)
    if route is None:
        raise HTTPException(status_code=404, detail=f"No route found for {path}")
    is_public = any(path.startswith(p) for p in PUBLIC_PATHS)
    if route.requires_auth and not is_public:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")
        token = auth_header.removeprefix("Bearer ").strip()
        jwt_payload = _validate_jwt(token)
        request.state.user_id = jwt_payload.get("sub")
    return await proxy_router.proxy(request, route)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "4000"))
    uvicorn.run("gateway.main:app", host="0.0.0.0", port=port, reload=os.getenv("ENVIRONMENT", "development") == "development", log_config=None, access_log=False)
