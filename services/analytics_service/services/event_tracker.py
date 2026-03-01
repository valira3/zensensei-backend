"""
ZenSensei Analytics Service - Event Tracker

Handles storage of analytics events. In production this writes to
BigQuery via batch inserts; in development mode it uses an in-memory
store so the service runs without any GCP credentials.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

import structlog

from shared.config import get_config
from services.analytics_service.schemas import (
    EventRecord,
    EventTrackRequest,
    EventType,
)

logger = structlog.get_logger(__name__)
cfg = get_config()


class EventTracker:
    """Tracks analytics events."""

    def __init__(self) -> None:
        self._store: dict[str, list[EventRecord]] = {}
        self._all_events: list[EventRecord] = []

    async def track_event(
        self,
        user_id: str,
        event_type: EventType,
        properties: dict | None = None,
        session_id: Optional[str] = None,
        timestamp: Optional[datetime] = None,
    ) -> EventRecord:
        event = EventRecord(
            event_id=str(uuid.uuid4()),
            user_id=user_id,
            event_type=event_type,
            properties=properties or {},
            session_id=session_id,
            timestamp=timestamp or datetime.now(tz=timezone.utc),
            ingested_at=datetime.now(tz=timezone.utc),
        )

        if cfg.is_development:
            self._store.setdefault(user_id, []).insert(0, event)
            self._all_events.insert(0, event)
        else:
            await self._persist_to_bigquery([event])

        logger.info(
            "event_tracked",
            event_id=event.event_id,
            user_id=user_id,
            event_type=event_type,
        )
        return event

    async def batch_track(
        self, requests: list[EventTrackRequest]
    ) -> tuple[int, int, list[str]]:
        accepted = 0
        failed = 0
        event_ids: list[str] = []
        records: list[EventRecord] = []

        for req in requests:
            try:
                record = EventRecord(
                    event_id=str(uuid.uuid4()),
                    user_id=req.user_id,
                    event_type=req.event_type,
                    properties=req.properties,
                    session_id=req.session_id,
                    timestamp=req.timestamp or datetime.now(tz=timezone.utc),
                    ingested_at=datetime.now(tz=timezone.utc),
                )
                records.append(record)
                event_ids.append(record.event_id)
                accepted += 1
            except Exception as exc:
                logger.warning("batch_event_parse_error", error=str(exc))
                failed += 1

        if cfg.is_development:
            for record in records:
                self._store.setdefault(record.user_id, []).insert(0, record)
                self._all_events.insert(0, record)
        else:
            await self._persist_to_bigquery(records)

        logger.info(
            "batch_events_tracked",
            accepted=accepted,
            failed=failed,
            total=len(requests),
        )
        return accepted, failed, event_ids

    async def get_events(
        self,
        user_id: str,
        page: int = 1,
        page_size: int = 50,
        event_type_filter: Optional[EventType] = None,
    ) -> tuple[list[EventRecord], int]:
        events = self._store.get(user_id, [])
        if event_type_filter:
            events = [e for e in events if e.event_type == event_type_filter]
        total = len(events)
        offset = (page - 1) * page_size
        return events[offset : offset + page_size], total

    async def _persist_to_bigquery(self, records: list[EventRecord]) -> None:
        logger.info(
            "bigquery_insert_stub",
            count=len(records),
            note="Replace with real BigQuery insert in production",
        )


event_tracker = EventTracker()


def get_event_tracker() -> EventTracker:
    return event_tracker
