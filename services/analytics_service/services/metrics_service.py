"""
ZenSensei Analytics Service - Metrics Service

Computes platform-wide and per-user engagement metrics.
In dev mode all numbers are generated from realistic seeded sample data.
"""

from __future__ import annotations

import hashlib
import random
from datetime import datetime, timedelta, timezone
from typing import Optional

import structlog

from shared.config import get_config
from services.analytics_service.schemas import (
    FeatureMetric,
    GoalMetrics,
    IntegrationUsageMetric,
    PlatformMetricsResponse,
    RetentionData,
    TrendDirection,
    UserMetricsResponse,
)

logger = structlog.get_logger(__name__)
cfg = get_config()


def _seed_for(key: str) -> int:
    return int(hashlib.md5(key.encode()).hexdigest(), 16) % (2**31)


def _seeded_rng(key: str) -> random.Random:
    return random.Random(_seed_for(key))


_TOTAL_REGISTERED_USERS = 18_420

_FEATURE_DEFINITIONS = [
    ("Goals", "goals"),
    ("Tasks", "tasks"),
    ("AI Insights", "ai_insights"),
    ("Decision Analyzer", "decision_analyzer"),
    ("Relationship Tracker", "relationship_tracker"),
    ("Knowledge Graph", "knowledge_graph"),
    ("Daily Summary", "daily_summary"),
    ("Pattern Detection", "pattern_detection"),
    ("Integrations Hub", "integrations_hub"),
    ("Weekly Reports", "weekly_reports"),
]

_INTEGRATION_DEFINITIONS = [
    ("Google Calendar", "google_calendar"),
    ("Gmail", "gmail"),
    ("Notion", "notion"),
    ("Spotify", "spotify"),
    ("Plaid (Finance)", "plaid"),
]

_GOAL_CATEGORIES = [
    "career",
    "health",
    "finance",
    "relationships",
    "personal_growth",
    "education",
    "creativity",
]


class MetricsService:
    """Computes platform and user engagement metrics."""

    def calculate_dau(self) -> int:
        rng = _seeded_rng(f"dau:{datetime.now(tz=timezone.utc).strftime('%Y-%m-%d')}")
        return int(_TOTAL_REGISTERED_USERS * rng.uniform(0.08, 0.14))

    def calculate_wau(self) -> int:
        rng = _seeded_rng(f"wau:{datetime.now(tz=timezone.utc).strftime('%Y-%W')}")
        return int(_TOTAL_REGISTERED_USERS * rng.uniform(0.28, 0.38))

    def calculate_mau(self) -> int:
        rng = _seeded_rng(f"mau:{datetime.now(tz=timezone.utc).strftime('%Y-%m')}")
        return int(_TOTAL_REGISTERED_USERS * rng.uniform(0.52, 0.62))

    def calculate_retention(self, period: Optional[str] = None) -> RetentionData:
        return RetentionData(day_1=0.71, day_7=0.48, day_30=0.32, day_90=0.21)

    def feature_adoption_rates(self) -> list[FeatureMetric]:
        mau = self.calculate_mau()
        metrics: list[FeatureMetric] = []
        adoption_rates = [0.82, 0.79, 0.63, 0.41, 0.38, 0.29, 0.56, 0.22, 0.45, 0.31]
        trends = [
            TrendDirection.UP, TrendDirection.UP, TrendDirection.UP,
            TrendDirection.STABLE, TrendDirection.UP, TrendDirection.STABLE,
            TrendDirection.DOWN, TrendDirection.UP, TrendDirection.STABLE,
            TrendDirection.UP,
        ]
        for (name, key), rate, trend in zip(_FEATURE_DEFINITIONS, adoption_rates, trends):
            rng = _seeded_rng(f"feature:{key}")
            users_tried = int(_TOTAL_REGISTERED_USERS * rate * rng.uniform(0.95, 1.05))
            active = int(mau * rate * rng.uniform(0.6, 0.8))
            metrics.append(FeatureMetric(
                feature_name=name,
                feature_key=key,
                users_tried=users_tried,
                users_active_last_30_days=active,
                adoption_rate=round(rate, 3),
                avg_uses_per_active_user=round(rng.uniform(3.0, 14.0), 1),
                trend=trend,
            ))
        return metrics

    def goal_completion_rates(self) -> GoalMetrics:
        total_created = 94_250
        total_completed = 31_200
        total_abandoned = 18_600
        total_active = total_created - total_completed - total_abandoned
        category_rates = {
            cat: round(_seeded_rng(f"goal_cat:{cat}").uniform(0.25, 0.48), 3)
            for cat in _GOAL_CATEGORIES
        }
        return GoalMetrics(
            total_goals_created=total_created,
            total_goals_completed=total_completed,
            total_goals_active=total_active,
            total_goals_abandoned=total_abandoned,
            overall_completion_rate=round(total_completed / total_created, 3),
            avg_days_to_complete=28.4,
            completion_by_category=category_rates,
            most_common_goal_categories=["career", "health", "personal_growth"],
        )

    def integration_usage(self) -> list[IntegrationUsageMetric]:
        mau = self.calculate_mau()
        results: list[IntegrationUsageMetric] = []
        conn_rates = [0.44, 0.41, 0.22, 0.14, 0.18]
        trends = [
            TrendDirection.STABLE, TrendDirection.UP, TrendDirection.UP,
            TrendDirection.DOWN, TrendDirection.UP,
        ]
        for (name, key), rate, trend in zip(_INTEGRATION_DEFINITIONS, conn_rates, trends):
            rng = _seeded_rng(f"integration:{key}")
            connected = int(_TOTAL_REGISTERED_USERS * rate)
            active = int(mau * rate * rng.uniform(0.65, 0.85))
            results.append(IntegrationUsageMetric(
                integration_name=name,
                integration_key=key,
                connected_users=connected,
                adoption_rate=round(connected / _TOTAL_REGISTERED_USERS, 3),
                active_last_30_days=active,
                avg_syncs_per_user_per_week=round(rng.uniform(2.5, 9.0), 1),
                trend=trend,
            ))
        return results

    def user_engagement_score(self, user_id: str) -> float:
        rng = _seeded_rng(f"engagement:{user_id}")
        session_score = rng.uniform(40, 95)
        streak_score = rng.uniform(20, 100)
        goal_score = rng.uniform(30, 85)
        insight_score = rng.uniform(25, 90)
        feature_score = rng.uniform(35, 80)
        weights = [0.30, 0.20, 0.25, 0.15, 0.10]
        scores = [session_score, streak_score, goal_score, insight_score, feature_score]
        return round(sum(w * s for w, s in zip(weights, scores)), 1)

    def get_platform_metrics(self) -> PlatformMetricsResponse:
        dau = self.calculate_dau()
        mau = self.calculate_mau()
        wau = self.calculate_wau()
        rng = _seeded_rng(f"platform_daily:{datetime.now(tz=timezone.utc).strftime('%Y-%m-%d')}")
        return PlatformMetricsResponse(
            dau=dau, mau=mau, wau=wau,
            dau_mau_ratio=round(dau / mau, 4) if mau > 0 else 0.0,
            retention=self.calculate_retention(),
            new_users_today=rng.randint(85, 220),
            new_users_this_month=rng.randint(2_400, 3_800),
            total_registered_users=_TOTAL_REGISTERED_USERS,
            avg_session_duration_minutes=round(rng.uniform(12.0, 22.0), 1),
            sessions_today=rng.randint(dau, int(dau * 2.4)),
        )

    def get_user_metrics(self, user_id: str) -> UserMetricsResponse:
        rng = _seeded_rng(f"user_metrics:{user_id}")
        goals_created = rng.randint(3, 24)
        goals_completed = int(goals_created * rng.uniform(0.3, 0.7))
        tasks_created = rng.randint(12, 120)
        tasks_completed = int(tasks_created * rng.uniform(0.4, 0.85))
        insights_viewed = rng.randint(10, 80)
        insights_acted = int(insights_viewed * rng.uniform(0.2, 0.55))
        sessions_30d = rng.randint(8, 45)
        sessions_7d = int(sessions_30d * rng.uniform(0.2, 0.4))
        streak = rng.randint(0, 42)
        days_ago = rng.randint(90, 540)
        member_since = datetime.now(tz=timezone.utc) - timedelta(days=days_ago)
        last_active = datetime.now(tz=timezone.utc) - timedelta(hours=rng.randint(0, 72))
        return UserMetricsResponse(
            user_id=user_id,
            total_sessions=rng.randint(sessions_30d * 2, sessions_30d * 8),
            sessions_last_7_days=sessions_7d,
            sessions_last_30_days=sessions_30d,
            avg_session_duration_minutes=round(rng.uniform(8.0, 28.0), 1),
            engagement_score=self.user_engagement_score(user_id),
            current_streak_days=streak,
            longest_streak_days=max(streak, rng.randint(streak, streak + 21)),
            goals_created=goals_created,
            goals_completed=goals_completed,
            goal_completion_rate=round(goals_completed / goals_created, 3) if goals_created > 0 else 0.0,
            tasks_created=tasks_created,
            tasks_completed=tasks_completed,
            task_completion_rate=round(tasks_completed / tasks_created, 3) if tasks_created > 0 else 0.0,
            insights_viewed=insights_viewed,
            insights_acted_on=insights_acted,
            insight_action_rate=round(insights_acted / insights_viewed, 3) if insights_viewed > 0 else 0.0,
            integrations_connected=rng.randint(1, 4),
            last_active_at=last_active,
            member_since=member_since,
        )


metrics_service = MetricsService()


def get_metrics_service() -> MetricsService:
    return metrics_service
