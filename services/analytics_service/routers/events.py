"""
ZenSensei Analytics Service - Events Router

Endpoints
---------
POST /analytics/events               Track a single event
POST /analytics/events/batch         Batch event ingestion (max 500)
GET  /analytics/events/{user_id}     Get paginated event history for a user
"""

from __future__ import annotations

import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import ORJSONResponse

from shared.auth import get_current_user
from shared.models.base import BaseResponse

from services.analytics_service.schemas import (
    BatchEventRequest,
    EventRequest,
    EventHistoryResponse,
)
from services.analytics_service.services.analytics_service import (
    AnalyticsService,
    get_analytics_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics/events", tags=["events"])


# ─── Dependency helpers ───────────────────────────────────────────────────────


def _svc() -> AnalyticsService:
    return get_analytics_service()


CurrentUser = Annotated[dict, Depends(get_current_user)]
Svc = Annotated[AnalyticsService, Depends(_svc)]


# ─── Routes ─────────────────────────────────────────────────────────────────


@router.post("", response_class=ORJSONResponse, status_code=status.HTTP_202_ACCEPTED)
async def track_event(
    payload: EventRequest,
    current_user: CurrentUser,
    svc: Svc,
) -> ORJSONResponse:
    """Track a single analytics event for the authenticated user."""
    await svc.track_event(
        user_id=current_user["uid"],
        event=payload,
    )
    return ORJSONResponse(
        BaseResponse(data={"queued": True}).model_dump(),
        status_code=status.HTTP_202_ACCEPTED,
    )


@router.post("/batch", response_class=ORJSONResponse, status_code=status.HTTP_202_ACCEPTED)
async def batch_track_events(
    payload: BatchEventRequest,
    current_user: CurrentUser,
    svc: Svc,
) -> ORJSONResponse:
    """Batch-ingest analytics events (max 500). Scoped to the authenticated user."""
    await svc.batch_track_events(
        user_id=current_user["uid"],
        events=payload,
    )
    return ORJSONResponse(
        BaseResponse(data={"queued": True, "count": len(payload.events)}).model_dump(),
        status_code=status.HTTP_202_ACCEPTED,
    )


@router.get(
    "/{user_id}",
    response_class=ORJSONResponse,
    status_code=status.HTTP_200_OK,
)
async def get_event_history(
    user_id: str,
    current_user: CurrentUser,
    svc: Svc,
    limit: Optional[int] = Query(50, ge=1, le=500),
    offset: Optional[int] = Query(0, ge=0),
    event_type: Optional[str] = Query(None),
) -> ORJSONResponse:
    """Return paginated event history. Users can only access their own events."""
    if current_user["uid"] != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    result: EventHistoryResponse = await svc.get_event_history(
        user_id=user_id,
        limit=limit or 50,
        offset=offset or 0,
        event_type=event_type,
    )
    return ORJSONResponse(BaseResponse(data=result.model_dump()).model_dump())
