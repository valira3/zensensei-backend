"""
ZenSensei AI Reasoning Service - Insight Engine

Generates daily personalised insights by:
1. Querying the knowledge graph for user context
2. Fetching historical patterns from the analytics service
3. Calling the LLM to produce structured InsightItems
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Optional

import structlog

from services.ai_reasoning_service.schemas import InsightItem
from services.ai_reasoning_service.services.llm_client import LLMClient
from services.ai_reasoning_service.services.prompt_templates import (
    INSIGHT_GENERATION_PROMPT,
)
from shared.models.insights import InsightImpact, InsightType

logger = structlog.get_logger(__name__)


class InsightEngine:
    """Orchestrates the daily insight generation pipeline."""

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm = llm_client

    # ─── Public API ──────────────────────────────────────────────────────────────

    async def generate_daily_insights(
        self,
        user_id: str,
        max_insights: int = 5,
        focus_areas: Optional[list[InsightType]] = None,
    ) -> list[InsightItem]:
        """Run the full insight generation pipeline for a user."""
        # 1. Build graph context summary (stubbed – replace with real graph call)
        graph_context = await self._fetch_graph_context(user_id)

        # 2. Build historical pattern summary (stubbed – replace with analytics call)
        patterns = await self._fetch_historical_patterns(user_id)

        # 3. Format and submit prompt
        focus_str = (
            ", ".join(focus_areas) if focus_areas else "all areas"
        )
        prompt = INSIGHT_GENERATION_PROMPT.format(
            user_id=user_id,
            max_insights=max_insights,
            focus_areas=focus_str,
            graph_context=json.dumps(graph_context, indent=2),
            pattern_summary=json.dumps(patterns, indent=2),
        )

        raw = await self._llm.generate(prompt)
        insights_data = self._parse_insights(raw)

        items = []
        for entry in insights_data[:max_insights]:
            try:
                item = InsightItem(
                    insight_id=str(uuid.uuid4()),
                    insight_type=InsightType(entry.get("insight_type", "PRIORITY")),
                    title=entry["title"],
                    description=entry["description"],
                    action=entry.get("action", ""),
                    confidence=float(entry.get("confidence", 0.75)),
                    impact=InsightImpact(entry.get("impact", "MEDIUM")),
                    related_node_ids=entry.get("related_node_ids", []),
                    metadata=entry.get("metadata", {}),
                )
                items.append(item)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "insight_parse_error", entry=entry, error=str(exc)
                )

        logger.info(
            "insights_generated",
            user_id=user_id,
            count=len(items),
            max_requested=max_insights,
        )
        return items

    # ─── Internal helpers ─────────────────────────────────────────────────────

    async def _fetch_graph_context(self, user_id: str) -> dict[str, Any]:
        """Stub: fetch user's knowledge-graph context."""
        return {
            "user_id": user_id,
            "active_goals": [],
            "recent_events": [],
            "key_relationships": [],
            "habits": [],
        }

    async def _fetch_historical_patterns(
        self, user_id: str
    ) -> dict[str, Any]:
        """Stub: fetch analytics patterns for the user."""
        return {
            "productivity_trend": "stable",
            "energy_peaks": ["09:00", "15:00"],
            "common_blockers": [],
            "mood_trend": "neutral",
        }

    @staticmethod
    def _parse_insights(raw: str) -> list[dict[str, Any]]:
        """Extract a JSON array from the LLM response."""
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1])
        return json.loads(text)
