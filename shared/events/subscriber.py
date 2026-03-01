"""
ZenSensei Shared Events - Pub/Sub Subscriber Base

Base class for building Google Cloud Pub/Sub push and pull subscribers.
Each microservice that consumes events extends ``EventSubscriber`` and
implements ``handle_message``.

Pull-subscriber example (for long-running background tasks)::

    class UserEventSubscriber(EventSubscriber):
        async def handle_message(self, event_type: str, data: dict, raw: dict) -> None:
            if event_type == "user.created":
                await self._on_user_created(data)

    sub = UserEventSubscriber(subscription="user-events-user-service-sub")
    await sub.start()   # blocks; listens indefinitely
    await sub.stop()    # graceful shutdown

Push-subscriber example (for Cloud Run HTTP push endpoints)::

    sub = UserEventSubscriber(subscription="...")
    message_dict = sub.decode_push_message(request_body_bytes)
    await sub.handle_message(...)
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import signal
from abc import ABC, abstractmethod
from typing import Any

from google.cloud import pubsub_v1
from google.cloud.pubsub_v1 import SubscriberClient
from google.cloud.pubsub_v1.types import PubsubMessage

from shared.config import ZenSenseiConfig, get_config

logger = logging.getLogger(__name__)


class EventSubscriber(ABC):
    """
    Abstract base class for Pub/Sub event consumers.

    Subclasses must implement :meth:`handle_message`.
    """

    def __init__(
        self,
        subscription: str,
        config: ZenSenseiConfig | None = None,
        max_messages: int = 10,
        ack_deadline_seconds: int = 60,
    ) -> None:
        """
        Args:
            subscription: Short subscription name
                (e.g. ``"user-events-user-service-sub"``). The full resource path
                ``projects/<project>/subscriptions/<name>`` is built automatically.
            config: Optional config override for testing.
            max_messages: Maximum messages to pull per batch.
            ack_deadline_seconds: ACK deadline extension in seconds.
        """
        self._config = config or get_config()
        self._subscription = subscription
        self._max_messages = max_messages
        self._ack_deadline_seconds = ack_deadline_seconds
        self._client: SubscriberClient | None = None
        self._running = False

    @property
    def subscription_path(self) -> str:
        """Full Pub/Sub subscription resource path."""
        if self._client is None:
            tmp = pubsub_v1.SubscriberClient()
            path = tmp.subscription_path(self._config.gcp_project_id, self._subscription)
            tmp.close()
            return path
        return self._client.subscription_path(
            self._config.gcp_project_id, self._subscription
        )

    @abstractmethod
    async def handle_message(
        self,
        event_type: str,
        data: dict[str, Any],
        raw_envelope: dict[str, Any],
    ) -> None:
        """
        Process a single decoded event.

        This method is called once per successfully decoded message.
        If an exception is raised the message will **not** be acknowledged
        and will be redelivered after the ACK deadline.

        Args:
            event_type: The ``event_type`` field from the envelope
                (e.g. ``"user.created"``).
            data: The ``data`` field from the envelope dict.
            raw_envelope: The full decoded envelope dict for advanced use.
        """

    # ─── Pull subscription loop ─────────────────────────────────────────────────

    async def start(self) -> None:
        """
        Start the pull subscription loop.

        Registers ``SIGTERM`` and ``SIGINT`` handlers for graceful shutdown.
        Blocks until :meth:`stop` is called.
        """
        self._client = pubsub_v1.SubscriberClient()
        self._running = True

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda: asyncio.ensure_future(self.stop()))

        logger.info("Starting subscriber on %s", self.subscription_path)

        try:
            while self._running:
                await self._pull_and_process()
                await asyncio.sleep(0.1)
        finally:
            await self.stop()

    async def stop(self) -> None:
        """Gracefully stop the pull loop and close the client."""
        self._running = False
        if self._client:
            self._client.close()
            self._client = None
        logger.info("Subscriber stopped")

    async def _pull_and_process(self) -> None:
        """Pull a batch of messages and process each one."""
        if self._client is None:
            return

        response = await asyncio.to_thread(
            self._client.pull,
            request={
                "subscription": self.subscription_path,
                "max_messages": self._max_messages,
            },
            timeout=5.0,
        )

        if not response.received_messages:
            return

        ack_ids: list[str] = []

        for received in response.received_messages:
            msg: PubsubMessage = received.message
            try:
                envelope = self._decode_message(msg)
                event_type: str = envelope.get("event_type", "unknown")
                data: dict[str, Any] = envelope.get("data", {})
                await self.handle_message(event_type, data, envelope)
                ack_ids.append(received.ack_id)
            except Exception as exc:
                logger.error(
                    "Failed to process message %s: %s",
                    msg.message_id,
                    exc,
                    exc_info=True,
                )
                # Do not ACK — message will be redelivered

        if ack_ids:
            await asyncio.to_thread(
                self._client.acknowledge,
                request={
                    "subscription": self.subscription_path,
                    "ack_ids": ack_ids,
                },
            )

    # ─── Push endpoint helper ───────────────────────────────────────────────────

    def decode_push_message(self, body: bytes) -> dict[str, Any]:
        """
        Decode a Pub/Sub HTTP push webhook body.

        The push envelope looks like::

            {
                "message": {
                    "data": "<base64-encoded JSON>",
                    "messageId": "...",
                    "attributes": {}
                },
                "subscription": "projects/.../subscriptions/..."
            }

        Args:
            body: Raw HTTP request body bytes.

        Returns:
            Decoded event envelope dict.
        """
        push_envelope: dict[str, Any] = json.loads(body)
        message = push_envelope["message"]
        return self._decode_message_dict(message)

    # ─── Internal helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _decode_message(msg: PubsubMessage) -> dict[str, Any]:
        """Decode a ``PubsubMessage`` protobuf into an envelope dict."""
        raw_data = base64.b64decode(msg.data).decode("utf-8")
        return json.loads(raw_data)

    @staticmethod
    def _decode_message_dict(message: dict[str, Any]) -> dict[str, Any]:
        """Decode a raw Pub/Sub message dict (from push webhook)."""
        raw_data = base64.b64decode(message["data"]).decode("utf-8")
        return json.loads(raw_data)
