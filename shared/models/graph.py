"""
ZenSensei Shared Models - Knowledge Graph

Pydantic schemas for the graph domain objects used by the AI reasoning
layer to represent entities and their relationships.

Core concepts
-------------
``Node``
    A vertex in the knowledge graph.  Every node has a ``kind`` (e.g.
    ``"goal"``, ``"task"``, ``"user"``) and an opaque ``properties`` bag
    for domain-specific attributes.

``Edge``
    A directed relationship between two nodes.  The ``relation`` field
    carries a human-readable predicate (e.g. ``"blocks"``,
    ``"assigned_to"``, ``"sub_goal_of"``).

``GraphSnapshot``
    A point-in-time capture of a sub-graph returned by the reasoning
    service.  Consumers should treat this as read-only.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from pydantic import Field

from .base import TimestampedModel, UUIDModel


class Node(UUIDModel):
    """A vertex in the ZenSensei knowledge graph."""

    kind: str = Field(
        ...,
        description="Ontological type of the node (e.g. 'goal', 'task', 'user').",
    )
    label: str = Field(
        ...,
        description="Human-readable display name for the node.",
    )
    properties: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary domain-specific attributes.",
    )


class Edge(UUIDModel):
    """A directed relationship between two ``Node`` instances."""

    source_id: uuid.UUID = Field(..., description="UUID of the originating node.")
    target_id: uuid.UUID = Field(..., description="UUID of the destination node.")
    relation: str = Field(
        ...,
        description="Human-readable predicate (e.g. 'blocks', 'assigned_to').",
    )
    weight: float = Field(
        default=1.0,
        ge=0.0,
        description="Edge weight; higher values indicate stronger relationships.",
    )
    properties: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary metadata attached to this relationship.",
    )


class GraphSnapshot(TimestampedModel):
    """Immutable point-in-time view of a knowledge-graph sub-graph."""

    nodes: List[Node] = Field(default_factory=list)
    edges: List[Edge] = Field(default_factory=list)
    context: Optional[str] = Field(
        None,
        description="Free-text description of what this snapshot represents.",
    )
