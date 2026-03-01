"""
ZenSensei Shared Database - Firestore Client

Async Firestore client wrapper providing standard CRUD operations
over Google Cloud Firestore (or the local emulator).
"""

from __future__ import annotations

import logging
from typing import Any

from google.cloud import firestore
from google.cloud.firestore_v1.async_client import AsyncClient
from google.cloud.firestore_v1.base_document import DocumentSnapshot

from shared.config import ZenSenseiConfig, get_config

logger = logging.getLogger(__name__)


class FirestoreClient:
    """
    Thin async Firestore wrapper.

    Usage::

        client = FirestoreClient()
        await client.connect()

        await client.create("users", "uid-123", {"display_name": "Alice"})
        user = await client.get("users", "uid-123")
        await client.update("users", "uid-123", {"display_name": "Alice B."})
        await client.delete("users", "uid-123")
    """

    def __init__(self, config: ZenSenseiConfig | None = None) -> None:
        self._config = config or get_config()
        self._db: AsyncClient | None = None

    async def connect(self) -> None:
        """Initialise the Firestore async client. Call once on service startup."""
        if self._db is not None:
            return

        self._db = firestore.AsyncClient(project=self._config.gcp_project_id)
        logger.info(
            "Firestore client initialised",
            extra={"project": self._config.gcp_project_id},
        )

    async def close(self) -> None:
        """Close the Firestore client. Call on service shutdown."""
        if self._db:
            self._db.close()
            self._db = None
            logger.info("Firestore client closed")

    def _assert_connected(self) -> AsyncClient:
        if self._db is None:
            raise RuntimeError("FirestoreClient.connect() must be called first")
        return self._db

    # ─── CRUD operations ─────────────────────────────────────────────────────────

    async def create(
        self,
        collection: str,
        document_id: str,
        data: dict[str, Any],
    ) -> str:
        """
        Create a document with the given ID. Raises if it already exists.

        Returns:
            The document ID.
        """
        db = self._assert_connected()
        doc_ref = db.collection(collection).document(document_id)
        await doc_ref.create(data)
        logger.debug("Created Firestore document %s/%s", collection, document_id)
        return document_id

    async def set(
        self,
        collection: str,
        document_id: str,
        data: dict[str, Any],
        merge: bool = False,
    ) -> str:
        """
        Create or overwrite a document. If *merge* is True, performs a partial update.

        Returns:
            The document ID.
        """
        db = self._assert_connected()
        doc_ref = db.collection(collection).document(document_id)
        await doc_ref.set(data, merge=merge)
        logger.debug("Set Firestore document %s/%s (merge=%s)", collection, document_id, merge)
        return document_id

    async def get(
        self,
        collection: str,
        document_id: str,
    ) -> dict[str, Any] | None:
        """
        Fetch a document by ID.

        Returns:
            Document data dict or ``None`` if the document does not exist.
        """
        db = self._assert_connected()
        doc_ref = db.collection(collection).document(document_id)
        snapshot: DocumentSnapshot = await doc_ref.get()
        if not snapshot.exists:
            return None
        return snapshot.to_dict()

    async def update(
        self,
        collection: str,
        document_id: str,
        data: dict[str, Any],
    ) -> None:
        """
        Partially update specific fields on an existing document.

        Raises:
            google.api_core.exceptions.NotFound if the document does not exist.
        """
        db = self._assert_connected()
        doc_ref = db.collection(collection).document(document_id)
        await doc_ref.update(data)
        logger.debug("Updated Firestore document %s/%s", collection, document_id)

    async def delete(
        self,
        collection: str,
        document_id: str,
    ) -> None:
        """Delete a document. Silently succeeds if it does not exist."""
        db = self._assert_connected()
        doc_ref = db.collection(collection).document(document_id)
        await doc_ref.delete()
        logger.debug("Deleted Firestore document %s/%s", collection, document_id)

    async def list_collection(
        self,
        collection: str,
        limit: int = 100,
        order_by: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Retrieve up to *limit* documents from a top-level collection.

        Args:
            collection: Collection name.
            limit: Maximum number of documents to return.
            order_by: Optional field to order results by.

        Returns:
            List of document data dicts (document ID injected as ``"_id"``).
        """
        db = self._assert_connected()
        query = db.collection(collection).limit(limit)
        if order_by:
            query = query.order_by(order_by)

        docs = []
        async for snapshot in query.stream():
            doc_data = snapshot.to_dict() or {}
            doc_data["_id"] = snapshot.id
            docs.append(doc_data)
        return docs

    async def query_collection(
        self,
        collection: str,
        filters: list[tuple[str, str, Any]],
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Query documents matching the provided WHERE-style filters.

        Args:
            collection: Collection name.
            filters: List of ``(field, operator, value)`` tuples,
                e.g. ``[("status", "==", "ACTIVE"), ("priority", ">", 2)]``.
            limit: Maximum number of documents to return.

        Returns:
            List of matching document data dicts.
        """
        db = self._assert_connected()
        query = db.collection(collection)
        for field, op, value in filters:
            query = query.where(field, op, value)
        query = query.limit(limit)

        docs = []
        async for snapshot in query.stream():
            doc_data = snapshot.to_dict() or {}
            doc_data["_id"] = snapshot.id
            docs.append(doc_data)
        return docs

    async def health_check(self) -> bool:
        """Return True if Firestore is reachable."""
        try:
            db = self._assert_connected()
            # List collections is a lightweight probe
            async for _ in db.collections():
                break
            return True
        except Exception:
            return False


# ─── Singleton helper ────────────────────────────────────────────────────────────

_firestore_client: FirestoreClient | None = None


def get_firestore_client() -> FirestoreClient:
    """Return a module-level singleton FirestoreClient."""
    global _firestore_client
    if _firestore_client is None:
        _firestore_client = FirestoreClient()
    return _firestore_client
