"""
ZenSensei AI Reasoning Service - Decision Analyzer

Orchestrates multi-factor decision analysis using the LLM client.
Factors analysed
----------------
1. Goal impact
2. Relationship effect
3. Financial implications
4. Historical patterns
5. Opportunity cost
6. Risk assessment
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Optional

import structlog

from services.ai_reasoning_service.schemas import (
    DecisionAnalysis,
    DecisionCompareRequest,
    DecisionCompareResponse,
    DecisionContext,
    DecisionHistoryItem,
    FactorAnalysis,
    OptionComparison,
)
from services.ai_reasoning_service.services.llm_client import LLMClient
from services.ai_reasoning_service.services.prompt_templates import (
    DECISION_ANALYSIS_PROMPT,
    DECISION_COMPARE_PROMPT,
)

logger = structlog.get_logger(__name__)

# In-memory history store (swap for Firestore in production)
_history_store: dict[str, list[DecisionAnalysis]] = {}


class DecisionAnalyzer:
    """Performs multi-factor AI decision analysis."""

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm = llm_client

    # ─── Public API ──────────────────────────────────────────────────────────────

    async def analyze_decision(
        self,
        user_id: str,
        decision_context: DecisionContext,
    ) -> DecisionAnalysis:
        """Run a full multi-factor analysis on the supplied decision context."""
        prompt = DECISION_ANALYSIS_PROMPT.format(
            title=decision_context.title,
            description=decision_context.description,
            category=decision_context.category,
            options=json.dumps(
                [o.model_dump() for o in decision_context.options], indent=2
            ),
            constraints=json.dumps(decision_context.constraints),
            related_goal_ids=json.dumps(decision_context.related_goal_ids),
            urgency_days=decision_context.urgency_days or "unspecified",
        )

        raw = await self._llm.generate(prompt)
        data = self._parse_json(raw)

        analysis = DecisionAnalysis(
            decision_id=str(uuid.uuid4()),
            user_id=user_id,
            title=decision_context.title,
            summary=data.get("summary", ""),
            recommended_option=data.get("recommended_option"),
            confidence=float(data.get("confidence", 0.7)),
            goal_impact=FactorAnalysis(**data["goal_impact"]),
            relationship_effect=FactorAnalysis(**data["relationship_effect"]),
            financial_implications=FactorAnalysis(**data["financial_implications"]),
            historical_patterns=FactorAnalysis(**data["historical_patterns"]),
            opportunity_cost=FactorAnalysis(**data["opportunity_cost"]),
            risk_assessment=FactorAnalysis(**data["risk_assessment"]),
            overall_score=float(data.get("overall_score", 5.0)),
            action_steps=data.get("action_steps", []),
            risks=data.get("risks", []),
            upsides=data.get("upsides", []),
            model_used=self._llm.primary_model,
        )

        # Persist
        _history_store.setdefault(user_id, []).insert(0, analysis)

        logger.info(
            "decision_analyzed",
            user_id=user_id,
            decision_id=analysis.decision_id,
            score=analysis.overall_score,
        )
        return analysis

    async def compare_options(
        self,
        request: DecisionCompareRequest,
    ) -> DecisionCompareResponse:
        """Side-by-side comparison of multiple options."""
        prompt = DECISION_COMPARE_PROMPT.format(
            context_description=request.context_description,
            options=json.dumps(
                [o.model_dump() for o in request.options], indent=2
            ),
            related_goal_ids=json.dumps(request.related_goal_ids),
        )

        raw = await self._llm.generate(prompt)
        data = self._parse_json(raw)

        option_comparisons = [
            OptionComparison(**opt) for opt in data.get("options", [])
        ]

        return DecisionCompareResponse(
            user_id=request.user_id,
            context_description=request.context_description,
            options=option_comparisons,
            recommended=data.get("recommended", ""),
            reasoning=data.get("reasoning", ""),
        )

    async def get_history(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[DecisionHistoryItem], int]:
        """Return paginated decision history for a user."""
        all_analyses = _history_store.get(user_id, [])
        total = len(all_analyses)
        page_items = all_analyses[offset : offset + limit]
        history_items = [
            DecisionHistoryItem(
                decision_id=a.decision_id,
                title=a.title,
                category=a.category if hasattr(a, "category") else "OTHER",
                recommended_option=a.recommended_option,
                overall_score=a.overall_score,
                analyzed_at=a.analyzed_at,
            )
            for a in page_items
        ]
        return history_items, total

    # ─── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_json(raw: str) -> dict[str, Any]:
        """Extract JSON from LLM response, stripping markdown fences if needed."""
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1])
        return json.loads(text)
