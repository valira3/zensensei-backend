"""
ZenSensei Graph Query Service - Pydantic Schemas

Service-specific request/response models.  Shared graph primitives
(GraphNode, GraphRelationship, SubgraphResponse) are re-exported from
shared.models.graph for convenience.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import Field, field_validator

from shared.models.base import BaseModel, BaseResponse
from shared.models.graph import (
    GraphNode,
    GraphRelationship,
    NodeType,
    RelationshipType,
    SubgraphResponse,
)

__all__ = [
    # Re-exports
    "GraphNode",
    "GraphRelationship",
    "SubgraphResponse",
    # Node
    "NodeCreateRequest",
    "NodeUpdateRequest",
    "NodeResponse",
    "NodeListResponse",
    "NodeTypeCount",
    "NodeTypeListResponse",
    # Relationship
    "RelationshipCreateRequest",
    "RelationshipUpdateRequest",
    "RelationshipResponse",
    "NodeRelationshipsResponse",
    # Complex Queries
    "CypherQueryRequest",
    "CypherQueryResponse",
    "UserContextResponse",
    "GoalImpactResponse",
    "SimilarPatternEntry",
    "SimilarPatternsResponse",
    "PathResponse",
    "RecommendationEntry",
    "RecommendationsResponse",
    # Schema
    "SchemaStatusResponse",
    "SchemaInitResponse",
    "SeedDataResponse",
    "FixtureDeleteResponse",
]

# ─── Node Schemas ─────────────────────────────────────────────────────────────────


class NodeCreateRequest(BaseModel):
    """Payload to create a new graph node."""

    type: NodeType = Field(description="Node label / type")
    properties: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary properties to store on the node",
    )
    schema_scope: Optional[str] = Field(
        default=None,
        description="Optional scope tag (e.g. 'user:<uid>', 'global', 'fixtures:demo')",
        max_length=128,
    )


class NodeUpdateRequest(BaseModel):
    """Payload to update properties on an existing node."""

    properties: dict[str, Any] = Field(
        description="Properties to merge onto the node (partial update)",
    )


class NodeResponse(BaseModel):
    """API representation of a single graph node."""

    id: str
    type: str = Field(description="Primary label")
    labels: list[str] = Field(default_factory=list)
    properties: dict[str, Any] = Field(default_factory=dict)
    schema_scope: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class NodeListResponse(BaseModel):
    """Paginated list of nodes."""

    items: list[NodeResponse]
    total: int
    page: int = 1
    page_size: int = 20


class NodeTypeCount(BaseModel):
    type: str
    count: int


class NodeTypeListResponse(BaseModel):
    """All node types present in the graph with their counts."""

    types: list[NodeTypeCount]
    total_nodes: int = 0


# ─── Relationship Schemas ─────────────────────────────────────────────────────────


class RelationshipCreateRequest(BaseModel):
    """Payload to create a directed relationship between two existing nodes."""

    source_id: str = Field(description="ID of the source (start) node")
    target_id: str = Field(description="ID of the target (end) node")
    type: RelationshipType = Field(description="Relationship type / label")
    properties: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional properties stored on the relationship",
    )

    @field_validator("source_id", "target_id")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Node ID must not be empty")
        return v.strip()


class RelationshipUpdateRequest(BaseModel):
    """Payload to update properties on an existing relationship."""

    properties: dict[str, Any] = Field(
        description="Properties to merge onto the relationship",
    )


class RelationshipResponse(BaseModel):
    """API representation of a single graph relationship."""

    id: str
    type: str
    source_id: str
    target_id: str
    properties: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class NodeRelationshipsResponse(BaseModel):
    """All relationships for a node, plus neighbour info."""

    node_id: str
    relationships: list[RelationshipResponse]
    total: int


# ─── Cypher Query Schemas ─────────────────────────────────────────────────────────


class CypherQueryRequest(BaseModel):
    """Admin-only arbitrary Cypher execution payload."""

    cypher: str = Field(
        description="Parameterised Cypher query",
        min_length=3,
        max_length=4096,
    )
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Named parameters for the query",
    )
    database: str = Field(
        default="neo4j",
        description="Target Neo4j database",
        max_length=64,
    )


class CypherQueryResponse(BaseModel):
    """Result of an arbitrary Cypher query."""

    records: list[dict[str, Any]]
    row_count: int
    execution_time_ms: float


# ─── Complex Query Response Schemas ──────────────────────────────────────────────


class UserContextStats(BaseModel):
    goal_count: int = 0
    task_count: int = 0
    event_count: int = 0
    insight_count: int = 0
    milestone_count: int = 0
    habit_count: int = 0
    relationship_count: int = 0


class UserContextResponse(BaseModel):
    """Full user subgraph context, assembled from multi-hop traversal."""

    user_id: str
    user: Optional[dict[str, Any]] = None
    goals: list[dict[str, Any]] = Field(default_factory=list)
    tasks: list[dict[str, Any]] = Field(default_factory=list)
    events: list[dict[str, Any]] = Field(default_factory=list)
    insights: list[dict[str, Any]] = Field(default_factory=list)
    milestones: list[dict[str, Any]] = Field(default_factory=list)
    habits: list[dict[str, Any]] = Field(default_factory=list)
    relationships: list[RelationshipResponse] = Field(default_factory=list)
    stats: UserContextStats = Field(default_factory=UserContextStats)
    cached: bool = False


class GoalImpactResponse(BaseModel):
    """Analysed impact of a single goal across the graph."""

    goal_id: str
    goal: Optional[dict[str, Any]] = None
    tasks: list[dict[str, Any]] = Field(default_factory=list)
    milestones: list[dict[str, Any]] = Field(default_factory=list)
    sub_goals: list[dict[str, Any]] = Field(default_factory=list)
    insights: list[dict[str, Any]] = Field(default_factory=list)
    dependent_goals: list[dict[str, Any]] = Field(default_factory=list)
    owner_ids: list[str] = Field(default_factory=list)
    affected_nodes: list[str] = Field(default_factory=list)
    impact_score: float = Field(
        default=0.0,
        description="Computed impact score based on downstream node count",
    )
    cached: bool = False


class SimilarPatternEntry(BaseModel):
    user_id: str
    display_name: Optional[str] = None
    shared_categories: int
    shared_goal_count: int
    shared_task_pattern_count: int
    similarity_score: float


class SimilarPatternsResponse(BaseModel):
    """Users with similar behaviour patterns."""

    user_id: str
    patterns: list[SimilarPatternEntry] = Field(default_factory=list)
    cached: bool = False


class PathNode(BaseModel):
    id: str
    labels: list[str] = Field(default_factory=list)
    name: Optional[str] = None


class PathRelationship(BaseModel):
    id: Optional[str] = None
    type: str
    source_id: str
    target_id: str


class PathResponse(BaseModel):
    """Shortest path between two nodes."""

    source_id: str
    target_id: str
    found: bool
    path_length: Optional[int] = None
    path_nodes: list[PathNode] = Field(default_factory=list)
    path_relationships: list[PathRelationship] = Field(default_factory=list)
    cached: bool = False


class RecommendationEntry(BaseModel):
    id: str
    title: str
    category: Optional[str] = None
    endorsement_count: int
    supporting_insights: list[str] = Field(default_factory=list)
    recommendation_type: str = "goal"
    score: float = 0.0


class RecommendationsResponse(BaseModel):
    """Graph-based personalised recommendations."""

    user_id: str
    recommendations: list[RecommendationEntry] = Field(default_factory=list)
    cached: bool = False


# ─── Schema / Admin Schemas ───────────────────────────────────────────────────────


class LabelCount(BaseModel):
    label: str
    count: int


class RelTypeCount(BaseModel):
    type: str
    count: int


class SchemaStatusResponse(BaseModel):
    """Current state of the graph schema — counts per node type and rel type."""

    node_counts: list[LabelCount] = Field(default_factory=list)
    relationship_counts: list[RelTypeCount] = Field(default_factory=list)
    total_nodes: int = 0
    total_relationships: int = 0
    indexes_initialized: bool = False
    constraints_initialized: bool = False


class SchemaInitResponse(BaseModel):
    """Result of schema initialisation (index + constraint creation)."""

    indexes_created: int = 0
    constraints_created: int = 0
    errors: list[str] = Field(default_factory=list)
    success: bool = True


class SeedDataResponse(BaseModel):
    """Result of seeding sample graph data."""

    nodes_created: int = 0
    relationships_created: int = 0
    scope: str = "fixtures:demo"
    success: bool = True


class FixtureDeleteResponse(BaseModel):
    """Result of deleting fixture data by scope tag."""

    scope: str
    deleted: int
    success: bool = True
