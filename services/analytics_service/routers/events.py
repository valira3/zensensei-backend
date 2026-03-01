"""
ZenSensei Analytics Service - Events Router

Endpoints
---------
POST /analytics/events               Track a single event
POST /analytics/events/batch         Batch event ingestion (max 500)
GET  /analytics/events/{user_id}     Get paginated event history for a user
"""

from __future__ import annotations

from typing import Annotated, Optional

import structlog
from fastapi import APIRouter, Depends, Query, status

from services.analytics_service.schemas import (
    EventBatchRequest,
    EventBatchResponse,
    EventHistoryResponse,
    EventResponse,
    EventTrackRequest,
    EventType,
)
from services.analytics_service.services.event_tracker import (
    EventTracker,
    get_event_tracker,
)

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.post(
    "",
    response_model=EventResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Track an event",
    description=(
        "Ingest a single analytics event for a user. "
        "Supported event types: page_view, feature_use, goal_create, goal_complete, "
        "task_create, task_complete, insight_view, insight_act, "
        "integration_connect, session_start, session_end."
    ),
)
async def track_event(
    request: EventTrackRequest,
    tracker: EventTracker = Depends(get_event_tracker),
) -> EventResponse:
    record = await tracker.track_event(
        user_id=request.user_id,
        event_type=request.event_type,
        properties=request.properties,
        session_id=request.session_id,
        timestamp=request.timestamp,
    )

    logger.info(
        "event_ingested",
        event_id=record.event_id,
        user_id=record.user_id,
        event_type=record.event_type,
    )

    return EventResponse(
        event_id=record.event_id,
        status="accepted",
        ingested_at=record.ingested_at,
    )


@router.post(
    "/batch",
    response_model=EventBatchResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Batch event ingestion",
    description=(
        "Ingest up to 500 analytics events in a single request. "
        "Returns the count of accepted and failed events along with the "
        "generated event IDs for accepted records."
    ),
)
async def batch_track_events(
    request: EventBatchRequest,
    tracker: EventTracker = Depends(get_event_tracker),
) -> EventBatchResponse:
    accepted, failed, event_ids = await tracker.batch_track(request.events)

    logger.info(
        "batch_events_ingested",
        accepted=accepted,
        failed=failed,
        total=len(request.events),
    )

    from datetime import datetime, timezone

    return EventBatchResponse(
        accepted=accepted,
        failed=failed,
        event_ids=event_ids,
        ingested_at=datetime.now(tz=timezone.utc),
    )


@router.get(
    "/{user_id}",
    response_model=EventHistoryResponse,
    summary="Get user's event history",
    description=(
        "Retrieve paginated event history for a specific user. "
        "Optionally filter by event type. Returns newest events first."
    ),
)
async def get_user_events(
    user_id: str,
    page: Annotated[int, Query(ge=1, description="Page number (1-based)")] = 1,
    page_size: Annotated[int, Query(ge=1, le=200, description="Events per page")] = 50,
    event_type: Optional[EventType] = Query(
        default=None, description="Filter by event type"
    ),
    tracker: EventTracker = Depends(get_event_tracker),
) -> EventHistoryResponse:
    events, total = await tracker.get_events(
        user_id=user_id,
        page=page,
        page_size=page_size,
        event_type_filter=event_type,
    )

    return EventHistoryResponse(
        user_id=user_id,
        events=events,
        total=total,
        page=page,
        page_size=page_size,
    )
