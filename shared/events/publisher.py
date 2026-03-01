"""
ZenSensei Shared Events - Pub/Sub Publisher

Async Google Cloud Pub/Sub event publisher used by all services
to emit domain events onto the shared event bus.

Supported event types
---------------------
user.created          user.updated         user.deleted
goal.created          goal.updated         goal.completed
task.created          task.completed       task.cancelled
insight.generated
integration.synced    integration.error
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from google.cloud import pubsub_v1
from google.cloud.pubsub_v1 import PublisherClient
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from shared.config import ZenSenseiConfig, get_config

logger = logging.getLogger(__name__)


class EventType(StrEnum):
    """All domain events published onto the ZenSensei event bus."""

    # User lifecycle
    USER_CREATED = "user.created"
    USER_UPDATED = "user.updated"
    USER_DELETED = "user.deleted"

    # Goals
    GOAL_CREATED = "goal.created"
    GOAL_UPDATED = "goal.updated"
    GOAL_COMPLETED = "goal.completed"

    # Tasks
    TASK_CREATED = "task.created"
    TASK_COMPLETED = "task.completed"
    TASK_CANCELLED = "task.cancelled"

    # AI
    INSIGHT_GENERATED = "insight.generated"

    # Integrations
    INTEGRATION_SYNCED = "integration.synced"
    INTEGRATION_ERROR = "integration.error"


def _topic_path(publisher: PublisherClient, project_id: str, topic: str) -> str:
    return publisher.topic_path(project_id, topic)


class EventPublisher:
    """
    Async-compatible Google Cloud Pub/Sub publisher.

    The underlying ``PublisherClient`` is synchronous but wraps the
    network call in ``asyncio.to_thread`` to avoid blocking the event loop.

    Usage::

        publisher = EventPublisher()
        await publisher.connect()

        await publisher.publish(
            topic=config.pubsub_user_events_topic,
            event_type=EventType.USER_CREATED,
            data={"user_id": "uid-123", "email": "alice@example.com"},
        )

        await publisher.close()
    """

    def __init__(self, config: ZenSenseiConfig | None = None) -> None:
        self._config = config or get_config()
        self._client: PublisherClient | None = None

    async def connect(self) -> None:
        """Initialise the Pub/Sub publisher client."""
        if self._client is not None:
            return
        self._client = pubsub_v1.PublisherClient()
        logger.info("Pub/Sub publisher initialised")

    async def close(self) -> None:
        """Flush any pending messages and close the publisher."""
        if self._client:
            self._client.stop()
            self._client = None
            logger.info("Pub/Sub publisher closed")

    def _assert_connected(self) -> PublisherClient:
        if self._client is None:
            raise RuntimeError("EventPublisher.connect() must be called first")
        return self._client

    @retry(
        retry=retry_if_exception_type(Exception),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
        stop=stop_after_attempt(3),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    async def publish(
        self,
        topic: str,
        event_type: EventType | str,
        data: dict[str, Any],
        attributes: dict[str, str] | None = None,
    ) -> str:
        """
        Publish an event to a Pub/Sub topic.

        A standard envelope is added around *data*::

            {
                "event_id": "<uuid>",
                "event_type": "<event_type>",
                "published_at": "<ISO-8601>",
                "data": { ... }
            }

        Args:
            topic: Short topic name (e.g. ``"user-events"``); the full
                   ``projects/<project>/topics/<topic>`` path is built automatically.
            event_type: Domain event type string or ``EventType`` enum member.
            data: Arbitrary event payload dict.
            attributes: Optional Pub/Sub message attributes for filtering.

        Returns:
            The published message ID.
        """
        import asyncio

        client = self._assert_connected()
        topic_path = _topic_path(client, self._config.gcp_project_id, topic)

        envelope: dict[str, Any] = {
            "event_id": str(uuid.uuid4()),
            "event_type": str(event_type),
            "published_at": datetime.now(tz=timezone.utc).isoformat(),
            "data": data,
        }
        payload = json.dumps(envelope, default=str).encode("utf-8")
        msg_attributes = attributes or {}
        msg_attributes.setdefault("event_type", str(event_type))

        # Run the synchronous publish call in a thread to avoid blocking
        future = await asyncio.to_thread(
            client.publish, topic_path, payload, **msg_attributes
        )
        message_id: str = await asyncio.to_thread(future.result)

        logger.debug(
            "Published event",
            extra={
                "event_type": str(event_type),
                "topic": topic,
                "message_id": message_id,
            },
        )
        return message_id

    # ─── Convenience helpers ─────────────────────────────────────────────────────

    async def publish_user_event(
        self,
        event_type: EventType,
        user_data: dict[str, Any],
    ) -> str:
        """Publish an event to the user-events topic."""
        return await self.publish(
            topic=self._config.pubsub_user_events_topic,
            event_type=event_type,
            data=user_data,
        )

    async def publish_graph_update(
        self,
        event_type: EventType,
        graph_data: dict[str, Any],
    ) -> str:
        """Publish an event to the graph-updates topic."""
        return await self.publish(
            topic=self._config.pubsub_graph_updates_topic,
            event_type=event_type,
            data=graph_data,
        )

    async def publish_ai_job(
        self,
        job_data: dict[str, Any],
    ) -> str:
        """Publish an AI processing job to the ai-jobs topic."""
        return await self.publish(
            topic=self._config.pubsub_ai_jobs_topic,
            event_type="ai.job.queued",
            data=job_data,
        )


# ─── Module-level singleton ────────────────────────────────────────────────────────────

_event_publisher: EventPublisher | None = None


def get_event_publisher() -> EventPublisher:
    """Return the module-level EventPublisher singleton."""
    global _event_publisher
    if _event_publisher is None:
        _event_publisher = EventPublisher()
    return _event_publisher
