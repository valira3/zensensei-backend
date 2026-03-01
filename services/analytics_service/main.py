"""
ZenSensei Analytics Service - FastAPI Application Entry Point
"""

from __future__ import annotations

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from services.analytics_service.routers import events, metrics, patterns, reports
from shared.middleware.logging import setup_logging

setup_logging()
logger = structlog.get_logger(__name__)

app = FastAPI(
    title="ZenSensei Analytics Service",
    description="User behavior tracking, metric aggregation, and pattern detection.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(events.router, prefix="/events", tags=["events"])
app.include_router(metrics.router, prefix="/metrics", tags=["metrics"])
app.include_router(patterns.router, prefix="/patterns", tags=["patterns"])
app.include_router(reports.router, prefix="/reports", tags=["reports"])


@app.get("/health")
async def health() -> dict:
    return {"status": "healthy", "service": "analytics-service"}
