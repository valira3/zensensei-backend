"""
ZenSensei Analytics Service - Pattern Detector

Identifies recurring behavioral patterns, upward/downward trends,
statistical anomalies, and predicts likely next actions for a user.

All computations use deterministic seeded sample data in dev mode.
"""

from __future__ import annotations

import hashlib
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import structlog

from services.analytics_service.schemas import (
    AnomalyItem,
    PatternItem,
    PatternType,
    PredictionItem,
    TrendDirection,
    TrendItem,
)

logger = structlog.get_logger(__name__)


def _rng(key: str) -> random.Random:
    seed = int(hashlib.md5(key.encode()).hexdigest(), 16) % (2**31)
    return random.Random(seed)


_PATTERN_TEMPLATES = [
    {
        "pattern_type": PatternType.TIME_OF_DAY,
        "title": "Morning Power User",
        "description": (
            "You complete the majority of your tasks and goals between 7–9 AM. "
            "Your engagement score is 34% higher during this window."
        ),
        "supporting_key": "morning_peak",
    },
    {
        "pattern_type": PatternType.TIME_OF_DAY,
        "title": "Late-Night Reflection Window",
        "description": (
            "You tend to review insights and log reflections between 9–11 PM, "
            "suggesting an evening wind-down habit."
        ),
        "supporting_key": "evening_review",
    },
    {
        "pattern_type": PatternType.DAY_OF_WEEK,
        "title": "Sunday Planning Ritual",
        "description": (
            "Your goal and task creation spikes on Sunday evenings — "
            "you set intentions 2.8× more than any other day."
        ),
        "supporting_key": "sunday_planning",
    },
    {
        "pattern_type": PatternType.DAY_OF_WEEK,
        "title": "Mid-Week Productivity Dip",
        "description": (
            "Task completions drop 28% on Wednesdays compared to your weekly average. "
            "Consider scheduling lighter work on this day."
        ),
        "supporting_key": "wednesday_dip",
    },
    {
        "pattern_type": PatternType.STREAK,
        "title": "Consistent Daily Check-in Streak",
        "description": (
            "You have opened the app every day for the past 14 days. "
            "Users with streaks of 14+ days retain 61% more goals."
        ),
        "supporting_key": "streak_14",
    },
    {
        "pattern_type": PatternType.SURGE,
        "title": "Goal Completion Surge After Insights",
        "description": (
            "Within 24 hours of acting on an AI insight, your goal completion "
            "rate surges by 47%."
        ),
        "supporting_key": "post_insight_surge",
    },
    {
        "pattern_type": PatternType.CORRELATION,
        "title": "Fitness Goals Boost Productivity",
        "description": (
            "On days you log a health/fitness activity, your task completion "
            "rate is 39% higher."
        ),
        "supporting_key": "fitness_productivity_correlation",
    },
    {
        "pattern_type": PatternType.DECLINE,
        "title": "Finance Goal Engagement Declining",
        "description": (
            "Interactions with finance-related goals have dropped 22% over the "
            "last 30 days."
        ),
        "supporting_key": "finance_decline",
    },
]

_TREND_TEMPLATES = [
    {
        "metric": "daily_task_completions",
        "direction_options": [TrendDirection.UP, TrendDirection.STABLE],
        "insights": [
            "Your task completion rate has grown steadily over the past 4 weeks.",
            "Task completions are holding steady.",
        ],
    },
    {
        "metric": "engagement_score",
        "direction_options": [TrendDirection.UP, TrendDirection.DOWN],
        "insights": [
            "Your engagement score has risen 12 points over 30 days.",
            "Engagement dipped slightly this month.",
        ],
    },
    {
        "metric": "goal_completion_rate",
        "direction_options": [TrendDirection.STABLE, TrendDirection.UP],
        "insights": [
            "Goal completion rate is stable at around 38%.",
            "Goal completion has improved; your rate is now in the top 25% of users.",
        ],
    },
    {
        "metric": "session_duration_minutes",
        "direction_options": [TrendDirection.UP, TrendDirection.DOWN],
        "insights": [
            "Average session length grew from 14 to 19 minutes.",
            "Session duration shortened slightly.",
        ],
    },
    {
        "metric": "insight_action_rate",
        "direction_options": [TrendDirection.UP, TrendDirection.STABLE],
        "insights": [
            "You acted on 43% of insights last month, up from 31%.",
            "Insight action rate is steady.",
        ],
    },
]


class PatternDetector:
    """Detects behavioral patterns, trends, anomalies, and predicts actions."""

    def detect_patterns(self, user_id: str) -> list[PatternItem]:
        rng = _rng(f"patterns:{user_id}")
        n_patterns = rng.randint(3, 5)
        selected = rng.sample(_PATTERN_TEMPLATES, n_patterns)
        now = datetime.now(tz=timezone.utc)
        items: list[PatternItem] = []
        for tmpl in selected:
            first_observed = now - timedelta(days=rng.randint(7, 90))
            items.append(PatternItem(
                pattern_id=str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{user_id}:{tmpl['supporting_key']}")),
                pattern_type=tmpl["pattern_type"],
                title=tmpl["title"],
                description=tmpl["description"],
                confidence=round(rng.uniform(0.65, 0.94), 3),
                strength=round(rng.uniform(0.55, 0.90), 3),
                supporting_data={"key": tmpl["supporting_key"], "sample_size": rng.randint(20, 120)},
                first_observed_at=first_observed,
                last_observed_at=now - timedelta(hours=rng.randint(0, 48)),
            ))
        return items

    def detect_trends(self, user_id: str) -> list[TrendItem]:
        rng = _rng(f"trends:{user_id}")
        now = datetime.now(tz=timezone.utc)
        trends: list[TrendItem] = []
        for tmpl in _TREND_TEMPLATES:
            direction = rng.choice(tmpl["direction_options"])
            insight = tmpl["insights"][0 if direction != TrendDirection.DOWN else 1]
            period_days = 30
            base = rng.uniform(30.0, 70.0)
            if direction == TrendDirection.UP:
                delta = rng.uniform(0.5, 2.5)
            elif direction == TrendDirection.DOWN:
                delta = -rng.uniform(0.5, 2.5)
            else:
                delta = 0.0
            data_points = []
            for i in range(14):
                day = now - timedelta(days=period_days - i * 2)
                val = max(0.0, base + delta * i + rng.gauss(0, 1.2))
                data_points.append({"date": day.strftime("%Y-%m-%d"), "value": round(val, 2)})
            change_pct = round(
                (data_points[-1]["value"] - data_points[0]["value"])
                / max(data_points[0]["value"], 0.001) * 100, 1,
            )
            trends.append(TrendItem(
                metric=tmpl["metric"],
                direction=direction,
                change_percent=change_pct,
                period_days=period_days,
                data_points=data_points,
                insight=insight,
            ))
        return trends

    def detect_anomalies(self, user_id: str) -> list[AnomalyItem]:
        rng = _rng(f"anomalies:{user_id}")
        now = datetime.now(tz=timezone.utc)
        candidate_anomalies = [
            {"metric": "task_completions", "description": "Task completions jumped to 18 today — 2.4× above your 30-day average.", "severity": "low", "observed": 18.0, "expected": 7.5},
            {"metric": "session_duration_minutes", "description": "Your session lasted 58 minutes — 3.1× your typical 19-minute average.", "severity": "low", "observed": 58.0, "expected": 19.0},
            {"metric": "goal_creation", "description": "5 goals created in a single day, versus your baseline of 0.4/day.", "severity": "medium", "observed": 5.0, "expected": 0.4},
            {"metric": "engagement_score", "description": "Engagement score dropped 18 points in 48 hours.", "severity": "medium", "observed": 42.0, "expected": 60.0},
            {"metric": "login_frequency", "description": "No app activity for 9 consecutive days.", "severity": "high", "observed": 9.0, "expected": 1.2},
        ]
        n = rng.randint(0, 2)
        selected = rng.sample(candidate_anomalies, min(n, len(candidate_anomalies)))
        return [
            AnomalyItem(
                anomaly_id=str(uuid.uuid4()),
                metric=a["metric"],
                description=a["description"],
                severity=a["severity"],
                observed_value=a["observed"],
                expected_value=a["expected"],
                deviation_percent=round((a["observed"] - a["expected"]) / max(a["expected"], 0.001) * 100, 1),
                detected_at=now - timedelta(hours=rng.randint(0, 24)),
            )
            for a in selected
        ]

    def predict_behavior(self, user_id: str) -> list[PredictionItem]:
        rng = _rng(f"predictions:{user_id}")
        candidates = [
            {"predicted_action": "Complete a pending task", "timeframe": "next 24h", "rationale": "You complete tasks at a high rate on weekday mornings.", "suggested_nudge": "Tap to see your overdue tasks."},
            {"predicted_action": "Review and act on an AI insight", "timeframe": "next 24h", "rationale": "You typically review new insights within 18 hours.", "suggested_nudge": "Your daily insights are ready."},
            {"predicted_action": "Create a new goal", "timeframe": "this week", "rationale": "You tend to create goals on Sunday evenings.", "suggested_nudge": "You're at 2 active goals. Add one?"},
            {"predicted_action": "Connect an integration", "timeframe": "this week", "rationale": "You've been active for 64 days without Notion connected.", "suggested_nudge": "Connect Notion to automatically sync your tasks."},
            {"predicted_action": "Log a reflection", "timeframe": "tonight", "rationale": "Your evening engagement window is approaching.", "suggested_nudge": None},
            {"predicted_action": "Start a new streak", "timeframe": "tomorrow", "rationale": "Your current streak is 3 days.", "suggested_nudge": "Just 4 more days to hit the 7-day milestone!"},
        ]
        n = rng.randint(3, 5)
        selected = rng.sample(candidates, n)
        return [
            PredictionItem(
                prediction_id=str(uuid.uuid4()),
                predicted_action=c["predicted_action"],
                probability=round(rng.uniform(0.45, 0.88), 3),
                timeframe=c["timeframe"],
                rationale=c["rationale"],
                suggested_nudge=c.get("suggested_nudge"),
            )
            for c in selected
        ]


pattern_detector = PatternDetector()


def get_pattern_detector() -> PatternDetector:
    return pattern_detector
