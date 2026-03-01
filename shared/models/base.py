"""
ZenSensei Shared Models - Base Classes

Provides abstract Pydantic base models used as building blocks for every
domain model in the ZenSensei platform.

Design goals
------------
* Consistent ``id``, ``created_at``, and ``updated_at`` fields across all
  entities.
* Immutable read models (``model_config = ConfigDict(frozen=True)``) so that
  API response objects cannot be mutated accidentally after deserialisation.
* A shared ``from_orm`` helper that accepts any SQLAlchemy-compatible ORM
  model instance without requiring callers to set ``from_attributes=True`` on
  every individual schema.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    """Return the current UTC time as a timezone-aware datetime."""
    return datetime.now(tz=timezone.utc)


# ---------------------------------------------------------------------------
# Abstract base models
# ---------------------------------------------------------------------------

class UUIDModel(BaseModel):
    """
    Abstract base model that adds a UUID primary key.

    All ZenSensei domain models derive from this class so that every entity
    has a globally unique, stable identifier.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        description="Globally unique entity identifier (UUID v4).",
    )


class TimestampedModel(UUIDModel):
    """
    Abstract base model with ``id``, ``created_at``, and ``updated_at`` fields.

    ``created_at`` defaults to the moment the Python object is constructed;
    ``updated_at`` is initialised to the same value and should be refreshed
    by the persistence layer on every write.
    """

    created_at: datetime = Field(
        default_factory=_utcnow,
        description="UTC timestamp when the record was first persisted.",
    )
    updated_at: datetime = Field(
        default_factory=_utcnow,
        description="UTC timestamp of the most recent update.",
    )

    def touch(self) -> None:
        """
        Refresh ``updated_at`` to the current UTC time.

        Call this before persisting changes to an existing record.
        """
        # Pydantic v2 models are not frozen by default; subclasses that
        # opt-in to ``frozen=True`` should use ``model_copy(update={...})``
        # instead.
        object.__setattr__(self, "updated_at", _utcnow())
