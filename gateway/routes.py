"""
ZenSensei API Gateway - Route Definitions

Maps URL path prefixes to upstream microservice base URLs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import os


@dataclass
class ServiceRoute:
    name: str
    base_url: str
    path_prefixes: list[str]
    requires_auth: bool = True
    timeout_seconds: float = 30.0
    health_path: str = "/health"


_ON_RAILWAY = bool(os.getenv("RAILWAY_ENVIRONMENT"))

if _ON_RAILWAY:
    _USER_SERVICE_URL = os.getenv("USER_SERVICE_URL", "http://user-service.railway.internal:8001")
    _GRAPH_QUERY_SERVICE_URL = os.getenv("GRAPH_QUERY_SERVICE_URL", "http://graph-query-service.railway.internal:8002")
    _AI_REASONING_SERVICE_URL = os.getenv("AI_REASONING_SERVICE_URL", "http://ai-reasoning-service.railway.internal:8003")
    _INTEGRATION_SERVICE_URL = os.getenv("INTEGRATION_SERVICE_URL", "http://integration-service.railway.internal:8004")
    _NOTIFICATION_SERVICE_URL = os.getenv("NOTIFICATION_SERVICE_URL", "http://notification-service.railway.internal:8005")
    _ANALYTICS_SERVICE_URL = os.getenv("ANALYTICS_SERVICE_URL", "http://analytics-service.railway.internal:8006")
else:
    _USER_SERVICE_URL = os.getenv("USER_SERVICE_URL", "http://localhost:8001")
    _GRAPH_QUERY_SERVICE_URL = os.getenv("GRAPH_QUERY_SERVICE_URL", "http://localhost:8002")
    _AI_REASONING_SERVICE_URL = os.getenv("AI_REASONING_SERVICE_URL", "http://localhost:8003")
    _INTEGRATION_SERVICE_URL = os.getenv("INTEGRATION_SERVICE_URL", "http://localhost:8004")
    _NOTIFICATION_SERVICE_URL = os.getenv("NOTIFICATION_SERVICE_URL", "http://localhost:8005")
    _ANALYTICS_SERVICE_URL = os.getenv("ANALYTICS_SERVICE_URL", "http://localhost:8006")


ROUTES: list[ServiceRoute] = [
    ServiceRoute(
        name="user-service",
        base_url=_USER_SERVICE_URL,
        path_prefixes=["/api/v1/auth", "/api/v1/users", "/api/v1/onboarding"],
        requires_auth=False,
        timeout_seconds=20.0,
    ),
    ServiceRoute(
        name="graph-query-service",
        base_url=_GRAPH_QUERY_SERVICE_URL,
        path_prefixes=["/api/v1/nodes", "/api/v1/relationships", "/api/v1/graph", "/api/v1/schema"],
        requires_auth=True,
        timeout_seconds=45.0,
    ),
    ServiceRoute(
        name="ai-reasoning-service",
        base_url=_AI_REASONING_SERVICE_URL,
        path_prefixes=["/api/v1/insights", "/api/v1/decisions", "/api/v1/recommendations"],
        requires_auth=True,
        timeout_seconds=60.0,
    ),
    ServiceRoute(
        name="integration-service",
        base_url=_INTEGRATION_SERVICE_URL,
        path_prefixes=["/api/v1/integrations", "/api/v1/webhooks"],
        requires_auth=True,
        timeout_seconds=30.0,
    ),
    ServiceRoute(
        name="notification-service",
        base_url=_NOTIFICATION_SERVICE_URL,
        path_prefixes=["/api/v1/notifications"],
        requires_auth=True,
        timeout_seconds=15.0,
    ),
    ServiceRoute(
        name="analytics-service",
        base_url=_ANALYTICS_SERVICE_URL,
        path_prefixes=["/api/v1/analytics"],
        requires_auth=True,
        timeout_seconds=30.0,
    ),
]

ROUTES_BY_NAME: dict[str, ServiceRoute] = {r.name: r for r in ROUTES}


def resolve_route(path: str) -> Optional[ServiceRoute]:
    for route in ROUTES:
        for prefix in route.path_prefixes:
            if path == prefix or path.startswith(prefix + "/"):
                return route
    return None
