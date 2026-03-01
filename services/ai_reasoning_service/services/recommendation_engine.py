"""
ZenSensei AI Reasoning Service - Recommendation Engine

Generates personalised, prioritised action recommendations across
three primary domains:
  - Goals  : based on goal progress, blockers, and deadlines
  - Relationships : who to reach out to and why
  - Wellness : health, balance, and habit suggestions

All endpoints share a common generate_recommendations() entry point
that can be filtered by focus area.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import structlog

from shared.config import get_config
from shared.models.insights import InsightImpact

from services.ai_reasoning_service.schemas import (
    RecommendationItem,
    RecommendationPriority,
    RecommendationResponse,
    RecommendationType,
)
from services.ai_reasoning_service.services.insight_engine import InsightEngine
from services.ai_reasoning_service.services.llm_client import LLMClient
from services.ai_reasoning_service.services.prompt_templates import RECOMMENDATION_PROMPT

logger = structlog.get_logger(__name__)
_cfg = get_config()

# ─── In-memory store for acted-upon recommendations ───────────────────────────────
_acted_recs: dict[str, dict[str, Any]] = {}


class RecommendationEngine:
    """
    Generates personalised recommendations from user knowledge-graph context.

    Usage::

        engine = RecommendationEngine()
        response = await engine.generate_recommendations(user_id, context)
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        insight_engine: Optional[InsightEngine] = None,
    ) -> None:
        self._llm = llm_client or LLMClient()
        self._engine = insight_engine or InsightEngine(llm_client=self._llm)

    async def generate_recommendations(
        self,
        user_id: str,
        context: Optional[dict[str, Any]] = None,
        focus_area: str = "ALL",
        count: int = 5,
    ) -> RecommendationResponse:
        start = time.perf_counter()
        logger.info(
            "recommendation_engine.generate.start",
            user_id=user_id,
            focus_area=focus_area,
        )

        if context is None:
            context = {"habits": [], "goals": [], "relationships": []}

        habits = context.get("habits", [])
        wellness_summary = "\n".join(
            f"- {h.get('title', '?')}: streak={h.get('streak', 0)}, "
            f"last done {h.get('last_completed_days_ago', '?')}d ago"
            for h in habits
        ) or "No wellness data available."

        behaviour_patterns = "No patterns available."

        prompt = RECOMMENDATION_PROMPT.format(
            user_id=user_id,
            current_date=datetime.now(tz=timezone.utc).strftime("%Y-%m-%d"),
            focus_area=focus_area,
            goals_summary="No goals data.",
            relationship_summary="No relationship data.",
            wellness_summary=wellness_summary,
            behaviour_patterns=behaviour_patterns,
            count=count,
        )

        raw = await self._llm.generate(prompt)
        try:
            import json
            text = raw.strip()
            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(lines[1:-1])
            raw_list = json.loads(text)
        except Exception:
            raw_list = []

        if not isinstance(raw_list, list):
            raw_list = []

        if focus_area != "ALL":
            raw_list = [
                r for r in raw_list
                if str(r.get("rec_type", "")).upper() == focus_area.upper()
            ]

        recs = [self._parse_rec(r) for r in raw_list[:count]]

        if not recs:
            recs = self._fallback_recs(user_id, focus_area, context)

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.info(
            "recommendation_engine.generate.complete",
            user_id=user_id,
            count=len(recs),
            duration_ms=duration_ms,
        )

        return RecommendationResponse(
            user_id=user_id,
            recommendations=recs,
            focus_area=focus_area,
        )

    async def goal_recommendations(self, user_id: str) -> RecommendationResponse:
        return await self.generate_recommendations(
            user_id, context=None, focus_area="GOAL", count=5
        )

    async def relationship_recommendations(self, user_id: str) -> RecommendationResponse:
        return await self.generate_recommendations(
            user_id, context=None, focus_area="RELATIONSHIP", count=5
        )

    async def wellness_recommendations(self, user_id: str) -> RecommendationResponse:
        return await self.generate_recommendations(
            user_id, context=None, focus_area="WELLNESS", count=5
        )

    async def mark_acted(self, rec_id: str, notes: Optional[str] = None) -> None:
        _acted_recs[rec_id] = {
            "rec_id": rec_id,
            "acted_at": datetime.now(tz=timezone.utc).isoformat(),
            "notes": notes,
        }
        logger.info("recommendation_engine.mark_acted", rec_id=rec_id)

    @staticmethod
    def _parse_rec(raw: dict[str, Any]) -> RecommendationItem:
        try:
            rec_type = RecommendationType(str(raw.get("rec_type", "GOAL")).upper())
        except ValueError:
            rec_type = RecommendationType.GOAL

        try:
            priority = RecommendationPriority(str(raw.get("priority", "MEDIUM")).upper())
        except ValueError:
            priority = RecommendationPriority.MEDIUM

        impact_str = str(raw.get("estimated_impact", "MEDIUM")).upper()
        try:
            impact = InsightImpact(impact_str)
        except ValueError:
            impact = InsightImpact.MEDIUM

        return RecommendationItem(
            rec_id=str(uuid.uuid4()),
            rec_type=rec_type,
            title=str(raw.get("title", "Recommendation"))[:256],
            description=str(raw.get("description", ""))[:1000],
            rationale=str(raw.get("rationale", ""))[:500],
            priority=priority,
            effort=str(raw.get("effort", "medium")).lower(),
            estimated_impact=impact,
            related_entity_id=raw.get("related_entity_id"),
        )

    @staticmethod
    def _fallback_recs(
        user_id: str,
        focus_area: str,
        context: dict[str, Any],
    ) -> list[RecommendationItem]:
        return [
            RecommendationItem(
                rec_id=str(uuid.uuid4()),
                rec_type=RecommendationType.TASK,
                title="Review your priorities for today",
                description=(
                    "Take 5 minutes to review your open tasks and goals. "
                    "Identify the single most impactful action you can take today."
                ),
                rationale="Fallback recommendation — daily priority review.",
                priority=RecommendationPriority.MEDIUM,
                effort="low",
                estimated_impact=InsightImpact.MEDIUM,
            )
        ]
