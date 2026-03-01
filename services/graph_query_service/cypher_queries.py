"""
ZenSensei Graph Query Service - Cypher Query Templates

All Cypher queries are parameterised to prevent injection and bounded
to prevent runaway traversals.  Constants are imported by graph_service.py
and used as-is; never interpolate user input directly into Cypher strings.
"""

from __future__ import annotations

# ─── Index / Constraint DDL ───────────────────────────────────────────────────

CREATE_INDEXES: list[str] = [
    # PERSON indexes
    "CREATE INDEX person_email_idx IF NOT EXISTS FOR (n:PERSON) ON (n.email)",
    "CREATE INDEX person_id_idx    IF NOT EXISTS FOR (n:PERSON) ON (n.id)",
    # GOAL indexes
    "CREATE INDEX goal_user_idx    IF NOT EXISTS FOR (n:GOAL)   ON (n.user_id)",
    "CREATE INDEX goal_id_idx      IF NOT EXISTS FOR (n:GOAL)   ON (n.id)",
    "CREATE INDEX goal_status_idx  IF NOT EXISTS FOR (n:GOAL)   ON (n.status)",
    # TASK indexes
    "CREATE INDEX task_user_idx    IF NOT EXISTS FOR (n:TASK)   ON (n.user_id)",
    "CREATE INDEX task_due_idx     IF NOT EXISTS FOR (n:TASK)   ON (n.due_date)",
    "CREATE INDEX task_goal_idx    IF NOT EXISTS FOR (n:TASK)   ON (n.goal_id)",
    "CREATE INDEX task_id_idx      IF NOT EXISTS FOR (n:TASK)   ON (n.id)",
    # EVENT indexes
    "CREATE INDEX event_start_idx  IF NOT EXISTS FOR (n:EVENT)  ON (n.start_time)",
    "CREATE INDEX event_user_idx   IF NOT EXISTS FOR (n:EVENT)  ON (n.user_id)",
    "CREATE INDEX event_id_idx     IF NOT EXISTS FOR (n:EVENT)  ON (n.id)",
    # INSIGHT indexes
    "CREATE INDEX insight_user_idx IF NOT EXISTS FOR (n:INSIGHT) ON (n.user_id)",
    "CREATE INDEX insight_id_idx   IF NOT EXISTS FOR (n:INSIGHT) ON (n.id)",
    # MILESTONE indexes
    "CREATE INDEX milestone_id_idx IF NOT EXISTS FOR (n:MILESTONE) ON (n.id)",
    # HABIT indexes
    "CREATE INDEX habit_user_idx   IF NOT EXISTS FOR (n:HABIT)   ON (n.user_id)",
    "CREATE INDEX habit_id_idx     IF NOT EXISTS FOR (n:HABIT)   ON (n.id)",
]

CREATE_CONSTRAINTS: list[str] = [
    "CREATE CONSTRAINT person_id_unique    IF NOT EXISTS FOR (n:PERSON)   REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT goal_id_unique      IF NOT EXISTS FOR (n:GOAL)     REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT task_id_unique      IF NOT EXISTS FOR (n:TASK)     REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT event_id_unique     IF NOT EXISTS FOR (n:EVENT)    REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT insight_id_unique   IF NOT EXISTS FOR (n:INSIGHT)  REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT milestone_id_unique IF NOT EXISTS FOR (n:MILESTONE) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT habit_id_unique     IF NOT EXISTS FOR (n:HABIT)    REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT content_id_unique   IF NOT EXISTS FOR (n:CONTENT)  REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT service_id_unique   IF NOT EXISTS FOR (n:SERVICE)  REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT asset_id_unique     IF NOT EXISTS FOR (n:ASSET)    REQUIRE n.id IS UNIQUE",
]

# ─── Node CRUD ────────────────────────────────────────────────────────────────

# $id, $type (label injected at call site), $properties, $schema_scope
CREATE_NODE = """
CALL apoc.create.node([$type], apoc.map.merge({id: $id, schema_scope: $schema_scope, created_at: $created_at}, $properties))
YIELD node
RETURN node
"""

# Fallback when APOC is unavailable — caller substitutes label
CREATE_NODE_TYPED = """
MERGE (n:{label} {{id: $id}})
ON CREATE SET n += $properties, n.created_at = $created_at, n.schema_scope = $schema_scope
RETURN n AS node
"""

GET_NODE_BY_ID = """
MATCH (n {id: $id})
RETURN n AS node,
       labels(n) AS labels,
       elementId(n) AS element_id
LIMIT 1
"""

UPDATE_NODE = """
MATCH (n {id: $id})
SET n += $properties, n.updated_at = $updated_at
RETURN n AS node, labels(n) AS labels
"""

DELETE_NODE = """
MATCH (n {id: $id})
DETACH DELETE n
RETURN count(n) AS deleted
"""

# ─── Search ───────────────────────────────────────────────────────────────────

# Bounded search by type + property map — type label substituted safely
SEARCH_NODES_BY_TYPE = """
MATCH (n:{label})
WHERE all(k IN keys($props) WHERE n[k] = $props[k])
RETURN n AS node, labels(n) AS labels
ORDER BY n.created_at DESC
SKIP $skip LIMIT $limit
"""

SEARCH_NODES_FULLTEXT = """
CALL db.index.fulltext.queryNodes('node_fulltext', $query)
YIELD node, score
WHERE $type = '' OR $type IN labels(node)
RETURN node, labels(node) AS labels, score
ORDER BY score DESC
SKIP $skip LIMIT $limit
"""

LIST_NODE_TYPES = """
CALL db.labels() YIELD label
CALL apoc.cypher.run('MATCH (n:' + label + ') RETURN count(n) AS cnt', {}) YIELD value
RETURN label AS type, value.cnt AS count
ORDER BY count DESC
"""

# Fallback — no APOC
LIST_NODE_TYPES_SIMPLE = """
MATCH (n)
UNWIND labels(n) AS lbl
RETURN lbl AS type, count(*) AS count
ORDER BY count DESC
"""

# ─── Relationship CRUD ────────────────────────────────────────────────────────

CREATE_RELATIONSHIP = """
MATCH (a {id: $source_id}), (b {id: $target_id})
CALL apoc.create.relationship(a, $type, apoc.map.merge({id: $id, created_at: $created_at}, $properties), b)
YIELD rel
RETURN rel, elementId(rel) AS element_id,
       a.id AS source_id, b.id AS target_id, type(rel) AS rel_type
"""

# Fallback without APOC — rel_type injected by caller only after validation
CREATE_RELATIONSHIP_TYPED = """
MATCH (a {{id: $source_id}}), (b {{id: $target_id}})
MERGE (a)-[r:{rel_type} {{id: $id}}]->(b)
ON CREATE SET r += $properties, r.created_at = $created_at
RETURN r AS rel, a.id AS source_id, b.id AS target_id, type(r) AS rel_type
"""

GET_RELATIONSHIP_BY_ID = """
MATCH ()-[r {id: $id}]->()
RETURN r AS rel, startNode(r).id AS source_id, endNode(r).id AS target_id,
       type(r) AS rel_type, elementId(r) AS element_id
LIMIT 1
"""

UPDATE_RELATIONSHIP = """
MATCH ()-[r {id: $id}]->()
SET r += $properties, r.updated_at = $updated_at
RETURN r AS rel, startNode(r).id AS source_id, endNode(r).id AS target_id,
       type(r) AS rel_type
"""

DELETE_RELATIONSHIP = """
MATCH ()-[r {id: $id}]->()
DELETE r
RETURN count(r) AS deleted
"""

GET_NODE_RELATIONSHIPS = """
MATCH (n {id: $node_id})-[r]-(m)
WHERE $direction = 'BOTH'
   OR ($direction = 'OUT' AND startNode(r).id = n.id)
   OR ($direction = 'IN'  AND endNode(r).id   = n.id)
RETURN r AS rel,
       startNode(r).id AS source_id,
       endNode(r).id   AS target_id,
       type(r) AS rel_type,
       m AS neighbour, labels(m) AS neighbour_labels
ORDER BY r.created_at DESC
SKIP $skip LIMIT $limit
"""

# ─── Complex Graph Queries ────────────────────────────────────────────────────

USER_CONTEXT_QUERY = """
// Full 2-hop user subgraph — bounded at depth 2
MATCH (user:PERSON {id: $user_id})

// Direct relationships
OPTIONAL MATCH (user)-[r1]-(n1)
WHERE NOT n1.id IS NULL

// Second-hop relationships (bounded)
OPTIONAL MATCH (n1)-[r2]-(n2)
WHERE NOT n2.id IS NULL
  AND n2.id <> user.id

WITH user,
     collect(DISTINCT {node: n1, rel: r1}) AS first_hop,
     collect(DISTINCT {node: n2, rel: r2}) AS second_hop

RETURN user,
       first_hop,
       second_hop,
       size(first_hop)  AS first_hop_count,
       size(second_hop) AS second_hop_count
"""

# Structured user context query — returns typed buckets
USER_CONTEXT_STRUCTURED = """
MATCH (user:PERSON {id: $user_id})

// Goals
OPTIONAL MATCH (user)-[:HAS_GOAL]->(g:GOAL)

// Tasks linked through goals
OPTIONAL MATCH (g)-[:INCLUDES]->(t:TASK)

// Events
OPTIONAL MATCH (user)-[:ATTENDED|:HAS_GOAL]->(e:EVENT)

// Insights
OPTIONAL MATCH (user)-[:DERIVES|:HAS_GOAL|:HAS_INSIGHT]->(i:INSIGHT)

// Milestones
OPTIONAL MATCH (g)-[:HAS_MILESTONE]->(m:MILESTONE)

// Habits
OPTIONAL MATCH (user)-[:HAS_HABIT]->(h:HABIT)

RETURN user,
       collect(DISTINCT properties(g))  AS goals,
       collect(DISTINCT properties(t))  AS tasks,
       collect(DISTINCT properties(e))  AS events,
       collect(DISTINCT properties(i))  AS insights,
       collect(DISTINCT properties(m))  AS milestones,
       collect(DISTINCT properties(h))  AS habits,
       count(DISTINCT g)  AS goal_count,
       count(DISTINCT t)  AS task_count,
       count(DISTINCT e)  AS event_count,
       count(DISTINCT i)  AS insight_count
"""

GOAL_IMPACT_QUERY = """
// What does this goal affect? — max depth 3, bounded
MATCH (g:GOAL {id: $goal_id})

// Tasks the goal drives
OPTIONAL MATCH (g)-[:INCLUDES]->(t:TASK)

// Milestones under the goal
OPTIONAL MATCH (g)-[:HAS_MILESTONE]->(ms:MILESTONE)

// Sub-goals
OPTIONAL MATCH (g)-[:INCLUDES|:HAS_GOAL]->(sg:GOAL)

// Insights derived from the goal
OPTIONAL MATCH (g)-[:CONTRIBUTES_TO|:TRIGGERS]->(ins:INSIGHT)

// Users owning the goal
OPTIONAL MATCH (u:PERSON)-[:HAS_GOAL]->(g)

// Goals that depend on this one (dependents)
OPTIONAL MATCH (dep_g:GOAL)-[:DEPENDS_ON]->(g)

// Paths of causal influence (depth-2 cap)
OPTIONAL MATCH (g)-[:AFFECTS|:SUPPORTS|:CONTRIBUTES_TO*1..2]->(affected)

RETURN g AS goal,
       collect(DISTINCT properties(t))   AS tasks,
       collect(DISTINCT properties(ms))  AS milestones,
       collect(DISTINCT properties(sg))  AS sub_goals,
       collect(DISTINCT properties(ins)) AS insights,
       collect(DISTINCT u.id)            AS owner_ids,
       collect(DISTINCT properties(dep_g)) AS dependent_goals,
       collect(DISTINCT labels(affected)[0] + ':' + affected.id) AS affected_nodes
"""

SIMILAR_PATTERNS_QUERY = """
// Users who share goal categories and task patterns with $user_id
MATCH (user:PERSON {id: $user_id})-[:HAS_GOAL]->(g:GOAL)

// Find other users with goals in the same categories
MATCH (other:PERSON)-[:HAS_GOAL]->(og:GOAL)
WHERE other.id <> user.id
  AND og.category = g.category

// Compute overlap score
WITH user, other,
     count(DISTINCT og.category) AS shared_categories,
     count(DISTINCT og)          AS shared_goal_count

WHERE shared_categories >= 1

// Task pattern similarity
OPTIONAL MATCH (user)-[:HAS_GOAL]->(ug:GOAL)-[:INCLUDES]->(ut:TASK)
OPTIONAL MATCH (other)-[:HAS_GOAL]->(xg:GOAL)-[:INCLUDES]->(xt:TASK)
WHERE ut.status = xt.status

WITH other, shared_categories, shared_goal_count,
     count(DISTINCT xt) AS shared_task_pattern_count

RETURN other.id AS user_id, other.display_name AS display_name,
       shared_categories, shared_goal_count, shared_task_pattern_count,
       (shared_categories * 2 + shared_goal_count + shared_task_pattern_count) AS similarity_score
ORDER BY similarity_score DESC
LIMIT $limit
"""

SHORTEST_PATH_QUERY = """
// Bounded shortest path — max depth 6 hops
MATCH (source {id: $source_id}), (target {id: $target_id})
MATCH path = shortestPath((source)-[*1..6]-(target))
RETURN path,
       length(path) AS path_length,
       [n IN nodes(path) | {id: n.id, labels: labels(n), name: coalesce(n.name, n.title, n.id)}]
           AS path_nodes,
       [r IN relationships(path) | {id: r.id, type: type(r), source: startNode(r).id, target: endNode(r).id}]
           AS path_relationships
LIMIT 5
"""

RECOMMENDATION_QUERY = """
// Graph-based recommendations for a user
MATCH (user:PERSON {id: $user_id})-[:HAS_GOAL]->(g:GOAL)

// Users with similar goals
MATCH (similar:PERSON)-[:HAS_GOAL]->(sg:GOAL)
WHERE similar.id <> user.id
  AND sg.category = g.category

// What those similar users are doing that this user is not
MATCH (similar)-[:HAS_GOAL]->(rec_g:GOAL)
WHERE NOT (user)-[:HAS_GOAL]->(rec_g)
  AND rec_g.status = 'ACTIVE'

// Insights from similar users
OPTIONAL MATCH (similar)-[:HAS_INSIGHT|:DERIVES]->(ins:INSIGHT)

WITH rec_g, count(DISTINCT similar) AS endorsement_count,
     collect(DISTINCT ins.content)[..3] AS supporting_insights

WHERE endorsement_count >= 1

RETURN rec_g.id          AS id,
       rec_g.title       AS title,
       rec_g.category    AS category,
       endorsement_count,
       supporting_insights,
       'goal' AS recommendation_type
ORDER BY endorsement_count DESC
LIMIT $limit
"""

SUBGRAPH_QUERY = """
// Variable-depth subgraph — depth bounded by caller ($depth, max 5)
MATCH (root {id: $root_id})
MATCH path = (root)-[*0..$depth]-(connected)
WHERE connected.id IS NOT NULL

WITH collect(DISTINCT connected) AS all_nodes,
     collect(DISTINCT relationships(path)) AS all_rels_nested

UNWIND all_rels_nested AS rel_list
UNWIND rel_list AS r

WITH all_nodes, collect(DISTINCT r) AS all_rels

RETURN [n IN all_nodes | {
    id:         n.id,
    labels:     labels(n),
    properties: properties(n)
}] AS nodes,
[r IN all_rels | {
    id:         r.id,
    type:       type(r),
    source_id:  startNode(r).id,
    target_id:  endNode(r).id,
    properties: properties(r)
}] AS relationships
"""

# ─── Schema / Statistics ──────────────────────────────────────────────────────

GET_GRAPH_STATISTICS = """
CALL apoc.meta.stats()
YIELD labels, relTypesCount, nodeCount, relCount
RETURN labels, relTypesCount, nodeCount, relCount
"""

GET_GRAPH_STATISTICS_SIMPLE = """
MATCH (n)
UNWIND labels(n) AS lbl
WITH lbl, count(n) AS cnt
RETURN collect({label: lbl, count: cnt}) AS node_counts,
       (MATCH (n) RETURN count(n)) AS total_nodes,
       (MATCH ()-[r]->() RETURN count(r)) AS total_rels
"""

# Separate simpler queries used for schema status
COUNT_NODES_BY_LABEL = """
MATCH (n)
UNWIND labels(n) AS lbl
RETURN lbl AS label, count(*) AS count
ORDER BY count DESC
"""

COUNT_RELS_BY_TYPE = """
MATCH ()-[r]->()
RETURN type(r) AS type, count(*) AS count
ORDER BY count DESC
"""

DELETE_FIXTURES_BY_SCOPE = """
MATCH (n {schema_scope: $scope})
DETACH DELETE n
RETURN count(n) AS deleted
"""
