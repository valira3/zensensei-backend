"""
ZenSensei Graph Query Service - Schema Service

Manages Neo4j indexes, constraints, and sample data seeding.
Also collects graph statistics for the /schema/status endpoint.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from services.graph_query_service import cypher_queries as Q
from services.graph_query_service.services.graph_service import (
    GraphService,
    get_graph_service,
)

logger = logging.getLogger(__name__)

SEED_SCOPE = "fixtures:demo"


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _days(delta: int) -> str:
    return (datetime.now(tz=timezone.utc) + timedelta(days=delta)).isoformat()


class SchemaService:
    """
    Handles schema initialisation (indexes + constraints) and data seeding.
    Works via GraphService so it benefits from the in-memory fallback.
    """

    def __init__(self, graph: GraphService | None = None) -> None:
        self._graph = graph or get_graph_service()
        self._indexes_initialized: bool = False
        self._constraints_initialized: bool = False

    # ─── Init ─────────────────────────────────────────────────────────────────────

    async def initialize_schema(self) -> dict[str, Any]:
        """Create all Neo4j indexes and uniqueness constraints."""
        errors: list[str] = []
        indexes_created = 0
        constraints_created = 0

        if not self._graph._neo4j_ok or not self._graph._neo4j:
            logger.warning("SchemaService: Neo4j unavailable — skipping DDL, marking initialized")
            self._indexes_initialized = True
            self._constraints_initialized = True
            return {
                "indexes_created": 0,
                "constraints_created": 0,
                "errors": ["Neo4j unavailable — operating in in-memory mode"],
                "success": True,
            }

        # Create constraints first (they implicitly create an index in Neo4j 4+)
        for stmt in Q.CREATE_CONSTRAINTS:
            try:
                await self._graph._neo4j.run_query(stmt)
                constraints_created += 1
            except Exception as exc:
                msg = f"Constraint DDL failed: {exc}"
                logger.warning(msg)
                errors.append(msg)

        # Create explicit indexes
        for stmt in Q.CREATE_INDEXES:
            try:
                await self._graph._neo4j.run_query(stmt)
                indexes_created += 1
            except Exception as exc:
                msg = f"Index DDL failed: {exc}"
                logger.warning(msg)
                errors.append(msg)

        self._indexes_initialized = True
        self._constraints_initialized = True
        logger.info(
            "Schema init complete: %d indexes, %d constraints, %d errors",
            indexes_created,
            constraints_created,
            len(errors),
        )
        return {
            "indexes_created": indexes_created,
            "constraints_created": constraints_created,
            "errors": errors,
            "success": len(errors) == 0,
        }

    # ─── Status ──────────────────────────────────────────────────────────────────

    async def get_status(self) -> dict[str, Any]:
        """Collect graph statistics for the status endpoint."""
        node_counts = await self._graph.count_nodes_by_label()
        rel_counts = await self._graph.count_rels_by_type()
        total_nodes = sum(c.get("count", 0) for c in node_counts)
        total_rels = sum(c.get("count", 0) for c in rel_counts)
        return {
            "node_counts": node_counts,
            "relationship_counts": rel_counts,
            "total_nodes": total_nodes,
            "total_relationships": total_rels,
            "indexes_initialized": self._indexes_initialized,
            "constraints_initialized": self._constraints_initialized,
        }

    # ─── Seed ────────────────────────────────────────────────────────────────────

    async def seed_sample_data(self) -> dict[str, Any]:
        """
        Seed a comprehensive sample dataset covering all 10 node types.

        All seeded nodes carry schema_scope = 'fixtures:demo' so they can
        be cleanly removed via DELETE /schema/fixtures/fixtures:demo.
        """
        nodes_created = 0
        rels_created = 0
        scope = SEED_SCOPE

        # ── PERSON nodes ────────────────────────────────────────────────────────────
        user1_id = "seed-person-alice"
        user2_id = "seed-person-bob"
        user3_id = "seed-person-carol"

        people = [
            (user1_id, {"display_name": "Alice Chen", "email": "alice@demo.local", "life_stage": "EARLY_CAREER"}),
            (user2_id, {"display_name": "Bob Russo", "email": "bob@demo.local", "life_stage": "MID_CAREER"}),
            (user3_id, {"display_name": "Carol Kim", "email": "carol@demo.local", "life_stage": "COLLEGE"}),
        ]
        person_ids = []
        for pid, props in people:
            n = await self._graph.create_node("PERSON", props, scope, node_id=pid)
            if n:
                person_ids.append(pid)
                nodes_created += 1

        # ── GOAL nodes ─────────────────────────────────────────────────────────────
        goals = [
            ("seed-goal-fitness", user1_id, {
                "title": "Run a half-marathon", "category": "HEALTH",
                "status": "ACTIVE", "priority": "HIGH",
                "target_date": _days(90), "user_id": user1_id,
            }),
            ("seed-goal-career", user1_id, {
                "title": "Get promoted to senior engineer", "category": "CAREER",
                "status": "ACTIVE", "priority": "CRITICAL",
                "target_date": _days(180), "user_id": user1_id,
            }),
            ("seed-goal-finance", user2_id, {
                "title": "Build 6-month emergency fund", "category": "FINANCIAL",
                "status": "ACTIVE", "priority": "HIGH",
                "target_date": _days(120), "user_id": user2_id,
            }),
            ("seed-goal-learning", user3_id, {
                "title": "Complete ML specialization", "category": "ACADEMIC",
                "status": "ACTIVE", "priority": "MEDIUM",
                "target_date": _days(60), "user_id": user3_id,
            }),
        ]
        goal_ids = []
        for gid, uid, props in goals:
            n = await self._graph.create_node("GOAL", props, scope, node_id=gid)
            if n:
                goal_ids.append((gid, uid))
                nodes_created += 1

        # ── TASK nodes ─────────────────────────────────────────────────────────────
        tasks = [
            ("seed-task-run-plan", "seed-goal-fitness", user1_id, {
                "title": "Create 12-week training plan", "status": "DONE",
                "priority": 4, "due_date": _days(-5), "user_id": user1_id,
                "goal_id": "seed-goal-fitness",
            }),
            ("seed-task-run-shoes", "seed-goal-fitness", user1_id, {
                "title": "Buy running shoes", "status": "DONE",
                "priority": 3, "due_date": _days(-10), "user_id": user1_id,
                "goal_id": "seed-goal-fitness",
            }),
            ("seed-task-run-5k", "seed-goal-fitness", user1_id, {
                "title": "Complete first 5K run", "status": "IN_PROGRESS",
                "priority": 4, "due_date": _days(7), "user_id": user1_id,
                "goal_id": "seed-goal-fitness",
            }),
            ("seed-task-pr-review", "seed-goal-career", user1_id, {
                "title": "Lead team code review process", "status": "TODO",
                "priority": 5, "due_date": _days(14), "user_id": user1_id,
                "goal_id": "seed-goal-career",
            }),
            ("seed-task-budget", "seed-goal-finance", user2_id, {
                "title": "Set up automatic savings transfer", "status": "DONE",
                "priority": 5, "due_date": _days(-3), "user_id": user2_id,
                "goal_id": "seed-goal-finance",
            }),
            ("seed-task-course", "seed-goal-learning", user3_id, {
                "title": "Complete Week 4 Neural Networks module", "status": "IN_PROGRESS",
                "priority": 4, "due_date": _days(3), "user_id": user3_id,
                "goal_id": "seed-goal-learning",
            }),
        ]
        task_ids = []
        for tid, gid, uid, props in tasks:
            n = await self._graph.create_node("TASK", props, scope, node_id=tid)
            if n:
                task_ids.append((tid, gid, uid))
                nodes_created += 1

        # ── MILESTONE nodes ──────────────────────────────────────────────────────────
        milestones = [
            ("seed-ms-10k", "seed-goal-fitness", {
                "title": "Run 10K without stopping", "target_date": _days(30),
                "achieved": False, "goal_id": "seed-goal-fitness",
            }),
            ("seed-ms-savings", "seed-goal-finance", {
                "title": "Save first $1,000", "target_date": _days(30),
                "achieved": True, "goal_id": "seed-goal-finance",
            }),
        ]
        milestone_ids = []
        for mid, gid, props in milestones:
            n = await self._graph.create_node("MILESTONE", props, scope, node_id=mid)
            if n:
                milestone_ids.append((mid, gid))
                nodes_created += 1

        # ── EVENT nodes ─────────────────────────────────────────────────────────────
        events = [
            ("seed-event-race", user1_id, {
                "title": "City Half-Marathon 2026", "start_time": _days(90),
                "end_time": _days(90), "location": "Downtown", "user_id": user1_id,
            }),
            ("seed-event-hackathon", user3_id, {
                "title": "ML Hackathon", "start_time": _days(14),
                "end_time": _days(15), "user_id": user3_id,
            }),
        ]
        event_ids = []
        for eid, uid, props in events:
            n = await self._graph.create_node("EVENT", props, scope, node_id=eid)
            if n:
                event_ids.append((eid, uid))
                nodes_created += 1

        # ── INSIGHT nodes ────────────────────────────────────────────────────────────
        insights = [
            ("seed-insight-morning", user1_id, {
                "content": "Morning workouts correlate with higher task completion rates",
                "confidence": 0.82, "source": "AI_ANALYSIS", "user_id": user1_id,
            }),
            ("seed-insight-savings", user2_id, {
                "content": "Automated savings transfers reduce financial anxiety",
                "confidence": 0.91, "source": "PATTERN_MATCH", "user_id": user2_id,
            }),
        ]
        insight_ids = []
        for iid, uid, props in insights:
            n = await self._graph.create_node("INSIGHT", props, scope, node_id=iid)
            if n:
                insight_ids.append((iid, uid))
                nodes_created += 1

        # ── HABIT nodes ────────────────────────────────────────────────────────────
        habits = [
            ("seed-habit-run", user1_id, {
                "title": "Daily 30-min run", "frequency": "DAILY",
                "streak": 12, "user_id": user1_id,
            }),
            ("seed-habit-study", user3_id, {
                "title": "Study ML for 2h", "frequency": "WEEKDAYS",
                "streak": 5, "user_id": user3_id,
            }),
        ]
        habit_ids = []
        for hid, uid, props in habits:
            n = await self._graph.create_node("HABIT", props, scope, node_id=hid)
            if n:
                habit_ids.append((hid, uid))
                nodes_created += 1

        # ── CONTENT nodes ────────────────────────────────────────────────────────────
        contents = [
            ("seed-content-book", {
                "title": "Atomic Habits", "type": "BOOK",
                "author": "James Clear", "tags": ["habits", "productivity"],
            }),
            ("seed-content-course", {
                "title": "Deep Learning Specialization", "type": "COURSE",
                "platform": "Coursera", "tags": ["ml", "ai"],
            }),
        ]
        content_ids = []
        for cid, props in contents:
            n = await self._graph.create_node("CONTENT", props, scope, node_id=cid)
            if n:
                content_ids.append(cid)
                nodes_created += 1

        # ── SERVICE nodes ────────────────────────────────────────────────────────────
        services = [
            ("seed-service-strava", {
                "name": "Strava", "category": "FITNESS_TRACKER",
                "integration_status": "CONNECTED",
            }),
            ("seed-service-plaid", {
                "name": "Plaid", "category": "FINANCIAL_DATA",
                "integration_status": "CONNECTED",
            }),
        ]
        service_ids = []
        for sid, props in services:
            n = await self._graph.create_node("SERVICE", props, scope, node_id=sid)
            if n:
                service_ids.append(sid)
                nodes_created += 1

        # ── ASSET nodes ────────────────────────────────────────────────────────────
        assets = [
            ("seed-asset-plan", user1_id, {
                "title": "12-Week Training Plan PDF",
                "asset_type": "DOCUMENT", "user_id": user1_id,
            }),
        ]
        asset_ids = []
        for aid, uid, props in assets:
            n = await self._graph.create_node("ASSET", props, scope, node_id=aid)
            if n:
                asset_ids.append((aid, uid))
                nodes_created += 1

        # ── HEALTH_METRIC nodes ─────────────────────────────────────────────────────
        health_metrics = [
            ("seed-hm-rhr", user1_id, {
                "metric_type": "RESTING_HEART_RATE", "value": 58,
                "unit": "bpm", "recorded_at": _now(), "user_id": user1_id,
            }),
        ]
        for hmid, uid, props in health_metrics:
            n = await self._graph.create_node("HEALTH_METRIC", props, scope, node_id=hmid)
            if n:
                nodes_created += 1

        # ── FINANCIAL_ARTIFACT nodes ────────────────────────────────────────────────────
        fin_artifacts = [
            ("seed-fa-budget", user2_id, {
                "title": "Monthly Budget Q1 2026", "artifact_type": "BUDGET",
                "currency": "USD", "user_id": user2_id,
            }),
        ]
        for faid, uid, props in fin_artifacts:
            n = await self._graph.create_node("FINANCIAL_ARTIFACT", props, scope, node_id=faid)
            if n:
                nodes_created += 1

        # ── TIME_BLOCK nodes ──────────────────────────────────────────────────────────
        time_blocks = [
            ("seed-tb-morning", user1_id, {
                "label": "Morning Training Block",
                "start_time": "06:00", "end_time": "07:00",
                "recurrence": "DAILY", "user_id": user1_id,
            }),
        ]
        for tbid, uid, props in time_blocks:
            n = await self._graph.create_node("TIME_BLOCK", props, scope, node_id=tbid)
            if n:
                nodes_created += 1

        # ── PLAN nodes ────────────────────────────────────────────────────────────────
        plans = [
            ("seed-plan-career", user1_id, {
                "title": "Career Advancement 2026 Plan",
                "horizon": "YEARLY", "user_id": user1_id,
            }),
        ]
        for planid, uid, props in plans:
            n = await self._graph.create_node("PLAN", props, scope, node_id=planid)
            if n:
                nodes_created += 1

        # ── ACTIVITY nodes ────────────────────────────────────────────────────────────
        activities = [
            ("seed-act-run1", user1_id, {
                "activity_type": "RUN", "duration_minutes": 32,
                "distance_km": 5.1, "date": _days(-1), "user_id": user1_id,
            }),
        ]
        for actid, uid, props in activities:
            n = await self._graph.create_node("ACTIVITY", props, scope, node_id=actid)
            if n:
                nodes_created += 1

        # ─── RELATIONSHIPS ────────────────────────────────────────────────────────────

        rel_defs: list[tuple[str, str, str, dict[str, Any]]] = [
            # Person -> Goal
            (user1_id, "seed-goal-fitness", "HAS_GOAL", {}),
            (user1_id, "seed-goal-career", "HAS_GOAL", {}),
            (user2_id, "seed-goal-finance", "HAS_GOAL", {}),
            (user3_id, "seed-goal-learning", "HAS_GOAL", {}),
            # Goal -> Task
            ("seed-goal-fitness", "seed-task-run-plan", "INCLUDES", {}),
            ("seed-goal-fitness", "seed-task-run-shoes", "INCLUDES", {}),
            ("seed-goal-fitness", "seed-task-run-5k", "INCLUDES", {}),
            ("seed-goal-career", "seed-task-pr-review", "INCLUDES", {}),
            ("seed-goal-finance", "seed-task-budget", "INCLUDES", {}),
            ("seed-goal-learning", "seed-task-course", "INCLUDES", {}),
            # Goal -> Milestone
            ("seed-goal-fitness", "seed-ms-10k", "HAS_MILESTONE", {}),
            ("seed-goal-finance", "seed-ms-savings", "HAS_MILESTONE", {}),
            # Person -> Event
            (user1_id, "seed-event-race", "ATTENDED", {}),
            (user3_id, "seed-event-hackathon", "ATTENDED", {}),
            # Goal -> Event (race supports fitness goal)
            ("seed-goal-fitness", "seed-event-race", "SUPPORTS", {}),
            # Person -> Insight
            (user1_id, "seed-insight-morning", "HAS_INSIGHT", {}),
            (user2_id, "seed-insight-savings", "HAS_INSIGHT", {}),
            # Insight -> Goal (supports)
            ("seed-insight-morning", "seed-goal-fitness", "CONTRIBUTES_TO", {}),
            ("seed-insight-savings", "seed-goal-finance", "CONTRIBUTES_TO", {}),
            # Person -> Habit
            (user1_id, "seed-habit-run", "HAS_HABIT", {}),
            (user3_id, "seed-habit-study", "HAS_HABIT", {}),
            # Habit -> Goal
            ("seed-habit-run", "seed-goal-fitness", "CONTRIBUTES_TO", {}),
            ("seed-habit-study", "seed-goal-learning", "CONTRIBUTES_TO", {}),
            # Person -> Content (consumed)
            (user1_id, "seed-content-book", "CONSUMED", {}),
            (user3_id, "seed-content-course", "CONSUMED", {}),
            # Person -> Service (subscribed)
            (user1_id, "seed-service-strava", "SUBSCRIBED_TO", {}),
            (user2_id, "seed-service-plaid", "SUBSCRIBED_TO", {}),
            # Social connections
            (user1_id, user2_id, "KNOWS", {"context": "colleagues"}),
            (user1_id, user3_id, "KNOWS", {"context": "mentorship"}),
            # Asset
            (user1_id, "seed-asset-plan", "HAS_ASSET", {}),
            ("seed-asset-plan", "seed-goal-fitness", "SUPPORTS", {}),
            # Health metric
            (user1_id, "seed-hm-rhr", "HAS_METRIC", {}),
            # Financial artifact
            (user2_id, "seed-fa-budget", "HAS_ARTIFACT", {}),
        ]

        for src, tgt, rtype, props in rel_defs:
            try:
                r = await self._graph.create_relationship(
                    src, tgt, rtype, props, rel_id=f"seed-rel-{uuid.uuid4().hex[:8]}"
                )
                if r:
                    rels_created += 1
            except Exception as exc:
                logger.warning("Seed relationship %s->%s (%s) failed: %s", src, tgt, rtype, exc)

        logger.info("Seeded %d nodes and %d relationships", nodes_created, rels_created)
        return {
            "nodes_created": nodes_created,
            "relationships_created": rels_created,
            "scope": scope,
            "success": True,
        }

    # ─── Delete fixtures ───────────────────────────────────────────────────────────

    async def delete_fixtures(self, scope: str) -> dict[str, Any]:
        deleted = await self._graph.delete_by_scope(scope)
        return {"scope": scope, "deleted": deleted, "success": True}


# ─── Module-level singleton ─────────────────────────────────────────────────────────

_schema_service: SchemaService | None = None


def get_schema_service() -> SchemaService:
    """Return the module-level SchemaService singleton."""
    global _schema_service
    if _schema_service is None:
        _schema_service = SchemaService()
    return _schema_service
