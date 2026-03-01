"""
ZenSensei Shared Middleware - CORS

Configures CORS (Cross-Origin Resource Sharing) for FastAPI apps
using the origins specified in ZenSenseiConfig.

Usage::

    app = FastAPI()
    add_cors_middleware(app)

    # Or with a custom config:
    add_cors_middleware(app, config=my_config)
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from shared.config import ZenSenseiConfig, get_config


def add_cors_middleware(
    app: FastAPI,
    config: ZenSenseiConfig | None = None,
) -> None:
    """
    Add CORSMiddleware to *app* using settings from *config*.

    In development mode all origins are allowed (``allow_origins=["*"]``)
    to avoid friction when running locally.  In staging/production only
    the origins listed in ``cors_origins`` are permitted.

    Args:
        app: The FastAPI application instance.
        config: Optional config override; defaults to ``get_config()``.
    """
    cfg = config or get_config()

    if cfg.is_development:
        origins = ["*"]
    else:
        origins = cfg.cors_origins

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-Request-ID",
            "X-Api-Key",
            "Accept",
            "Origin",
        ],
        expose_headers=["X-Request-ID"],
        max_age=600,  # preflight cache in seconds
    )
