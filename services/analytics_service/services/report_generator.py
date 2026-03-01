"""
ZenSensei Analytics Service - Report Generator

Generates personal weekly/monthly reports and platform daily KPI reports.
All reports include chart data structures ready for frontend rendering.
In dev mode, realistic sample data is synthesised deterministically.
"""

from __future__ import annotations

import hashlib
import random
import uuid
from datetime import datetime, timedelta, timezone

import structlog

from services.analytics_service.schemas import (
    ChartData,
    ChartDataset,
    CohortAnalysisResponse,
    CohortMetric,
    MonthlyReportResponse,
    PatternItem,
    PlatformDailyReportResponse,
    TrendItem,
    WeeklyReportResponse,
)
from services.analytics_service.services.metrics_service import MetricsService
from services.analytics_service.services.pattern_detector import PatternDetector

logger = structlog.get_logger(__name__)


def _rng(key: str) -> random.Random:
    seed = int(hashlib.md5(key.encode()).hexdigest(), 16) % (2**31)
    return random.Random(seed)


def _week_bounds(now: datetime) -> tuple[str, str]:
    monday = now - timedelta(days=now.weekday())
    sunday = monday + timedelta(days=6)
    return monday.strftime("%Y-%m-%d"), sunday.strftime("%Y-%m-%d")


class ReportGenerator:
    """Assembles weekly, monthly, and platform reports."""

    def __init__(self, metrics: MetricsService | None = None, detector: PatternDetector | None = None) -> None:
        self._metrics = metrics or MetricsService()
        self._detector = detector or PatternDetector()

    def generate_weekly_report(self, user_id: str) -> WeeklyReportResponse:
        now = datetime.now(tz=timezone.utc)
        week_start, week_end = _week_bounds(now)
        rng = _rng(f"weekly:{user_id}:{week_start}")
        user_metrics = self._metrics.get_user_metrics(user_id)
        patterns = self._detector.detect_patterns(user_id)
        sessions = rng.randint(4, 14)
        goals_completed = rng.randint(0, 4)
        tasks_completed = rng.randint(3, 25)
        insights_acted = rng.randint(1, 8)
        engagement = user_metrics.engagement_score
        engagement_change = round(rng.uniform(-8.0, 12.0), 1)
        day_labels = [(now - timedelta(days=6 - i)).strftime("%a") for i in range(7)]
        daily_sessions = [rng.randint(0, 4) for _ in range(7)]
        daily_tasks = [rng.randint(0, 8) for _ in range(7)]
        activity_chart = ChartData(
            chart_type="bar", title="Daily Activity This Week", labels=day_labels,
            datasets=[
                ChartDataset(label="Sessions", data=daily_sessions, color="#6366f1"),
                ChartDataset(label="Tasks Completed", data=daily_tasks, color="#22c55e"),
            ], unit="count",
        )
        goals_active = rng.randint(1, 5)
        goals_not_started = rng.randint(0, 2)
        goal_progress_chart = ChartData(
            chart_type="doughnut", title="Goal Status This Week",
            labels=["Completed", "In Progress", "Not Started"],
            datasets=[ChartDataset(label="Goals", data=[goals_completed, goals_active, goals_not_started], color="#6366f1")],
        )
        achievements = _pick_achievements(rng, goals_completed, tasks_completed, sessions)
        improvement_areas = _pick_improvement_areas(rng, engagement_change)
        streak = user_metrics.current_streak_days
        summary = (
            f"This week you completed {tasks_completed} tasks and {goals_completed} goal"
            f"{'s' if goals_completed != 1 else ''}, with {sessions} sessions. "
            f"Your engagement score is {engagement:.0f}."
        )
        return WeeklyReportResponse(
            user_id=user_id, report_id=str(uuid.uuid4()),
            week_start=week_start, week_end=week_end,
            sessions_this_week=sessions,
            avg_session_duration_minutes=user_metrics.avg_session_duration_minutes,
            streak_days=streak, goals_completed=goals_completed,
            tasks_completed=tasks_completed, insights_acted_on=insights_acted,
            engagement_score=engagement, engagement_score_change=engagement_change,
            achievements=achievements, improvement_areas=improvement_areas,
            top_patterns=patterns[:2], activity_chart=activity_chart,
            goal_progress_chart=goal_progress_chart, summary_text=summary,
        )

    def generate_monthly_report(self, user_id: str) -> MonthlyReportResponse:
        now = datetime.now(tz=timezone.utc)
        month_str = now.strftime("%Y-%m")
        rng = _rng(f"monthly:{user_id}:{month_str}")
        user_metrics = self._metrics.get_user_metrics(user_id)
        patterns = self._detector.detect_patterns(user_id)
        trends = self._detector.detect_trends(user_id)
        sessions = rng.randint(18, 55)
        active_days = rng.randint(12, 28)
        goals_created = rng.randint(2, 10)
        goals_completed = int(goals_created * rng.uniform(0.3, 0.7))
        tasks_created = rng.randint(25, 120)
        tasks_completed = int(tasks_created * rng.uniform(0.45, 0.85))
        insights_viewed = rng.randint(15, 60)
        insights_acted = int(insights_viewed * rng.uniform(0.25, 0.55))
        engagement = user_metrics.engagement_score
        engagement_change = round(rng.uniform(-10.0, 18.0), 1)
        heatmap_labels = [(now - timedelta(days=27 - i)).strftime("%b %d") for i in range(28)]
        heatmap_values = [round(rng.uniform(0, 10), 1) for _ in range(28)]
        activity_heatmap = ChartData(
            chart_type="bar", title="Daily Activity — Last 28 Days",
            labels=heatmap_labels,
            datasets=[ChartDataset(label="Activity Score", data=heatmap_values, color="#6366f1")],
            unit="score",
        )
        week_labels = [f"Week {i + 1}" for i in range(4)]
        base_eng = engagement - engagement_change
        eng_values = [round(base_eng + engagement_change * (i / 3) + rng.gauss(0, 1.5), 1) for i in range(4)]
        engagement_trend_chart = ChartData(
            chart_type="line", title="Engagement Score Trend", labels=week_labels,
            datasets=[ChartDataset(label="Engagement Score", data=eng_values, color="#6366f1")],
            unit="score",
        )
        from services.analytics_service.services.metrics_service import _GOAL_CATEGORIES
        goal_cats = rng.sample(_GOAL_CATEGORIES, min(5, len(_GOAL_CATEGORIES)))
        goal_counts = [rng.randint(1, 4) for _ in goal_cats]
        goal_breakdown_chart = ChartData(
            chart_type="pie", title="Goals by Category", labels=goal_cats,
            datasets=[ChartDataset(label="Goals Created", data=[float(c) for c in goal_counts])],
        )
        top_features = rng.sample(["Goals", "AI Insights", "Tasks", "Daily Summary", "Decision Analyzer"], 3)
        achievements = _pick_achievements(rng, goals_completed, tasks_completed, sessions)
        highlights = [
            f"Completed {goals_completed} goals this month.",
            f"Acted on {insights_acted} AI insights.",
            f"Maintained a {user_metrics.longest_streak_days}-day active streak.",
        ]
        action_recs = [
            "Review your abandoned goals and reactivate the most relevant one.",
            "Set a specific completion date for each active goal.",
            "Connect an additional integration to enrich your knowledge graph.",
        ]
        goal_completion_rate = round(goals_completed / goals_created, 3) if goals_created > 0 else 0.0
        task_completion_rate = round(tasks_completed / tasks_created, 3) if tasks_created > 0 else 0.0
        summary = (
            f"In {now.strftime('%B %Y')} you were active {active_days} days with {sessions} sessions. "
            f"You completed {goals_completed}/{goals_created} goals and {tasks_completed} tasks."
        )
        return MonthlyReportResponse(
            user_id=user_id, report_id=str(uuid.uuid4()), month=month_str,
            sessions_this_month=sessions, total_active_days=active_days,
            avg_session_duration_minutes=user_metrics.avg_session_duration_minutes,
            goals_created=goals_created, goals_completed=goals_completed,
            goal_completion_rate=goal_completion_rate,
            tasks_created=tasks_created, tasks_completed=tasks_completed,
            task_completion_rate=task_completion_rate,
            insights_viewed=insights_viewed, insights_acted_on=insights_acted,
            longest_streak_days=user_metrics.longest_streak_days,
            engagement_score=engagement, engagement_score_change=engagement_change,
            achievements=achievements, top_features_used=top_features,
            top_patterns=patterns[:3], key_trends=trends[:3],
            activity_heatmap=activity_heatmap,
            engagement_trend_chart=engagement_trend_chart,
            goal_breakdown_chart=goal_breakdown_chart,
            summary_text=summary, highlights=highlights,
            action_recommendations=action_recs,
        )

    def generate_platform_daily(self) -> PlatformDailyReportResponse:
        now = datetime.now(tz=timezone.utc)
        today_str = now.strftime("%Y-%m-%d")
        rng = _rng(f"platform_daily:{today_str}")
        platform = self._metrics.get_platform_metrics()
        dau = platform.dau
        new_signups = platform.new_users_today
        churned = rng.randint(8, 35)
        total_sessions = platform.sessions_today
        events_total = rng.randint(total_sessions * 18, total_sessions * 32)
        events_by_type = {
            "page_view": rng.randint(events_total // 4, events_total // 3),
            "feature_use": rng.randint(events_total // 6, events_total // 5),
            "task_complete": rng.randint(events_total // 10, events_total // 8),
            "goal_complete": rng.randint(100, 400),
            "insight_view": rng.randint(events_total // 8, events_total // 6),
            "session_start": total_sessions,
        }
        hours = [f"{h:02d}:00" for h in range(24)]
        hourly_base = [2, 1, 1, 1, 2, 4, 7, 11, 14, 13, 11, 10, 9, 9, 10, 11, 12, 13, 14, 13, 11, 8, 5, 3]
        hourly_dau_values = [max(1, int(dau * (b / sum(hourly_base)) * rng.uniform(0.85, 1.15))) for b in hourly_base]
        hourly_dau_chart = ChartData(
            chart_type="line", title="Hourly Active Users", labels=hours,
            datasets=[ChartDataset(label="Active Users", data=[float(v) for v in hourly_dau_values], color="#6366f1")],
            unit="users",
        )
        event_breakdown_chart = ChartData(
            chart_type="bar", title="Events by Type Today",
            labels=list(events_by_type.keys()),
            datasets=[ChartDataset(label="Event Count", data=[float(v) for v in events_by_type.values()], color="#22c55e")],
            unit="events",
        )
        return PlatformDailyReportResponse(
            report_id=str(uuid.uuid4()), date=today_str,
            dau=dau, new_signups=new_signups, churned_users=churned,
            net_user_growth=new_signups - churned,
            total_sessions=total_sessions,
            avg_session_duration_minutes=platform.avg_session_duration_minutes,
            total_events=events_total, events_by_type=events_by_type,
            goals_created=rng.randint(180, 420), goals_completed=rng.randint(60, 180),
            tasks_created=rng.randint(800, 2200), tasks_completed=rng.randint(600, 1800),
            insights_generated=rng.randint(300, 900), insights_acted_on=rng.randint(80, 300),
            new_integrations_connected=rng.randint(20, 80),
            active_integrations=rng.randint(int(dau * 0.4), int(dau * 0.65)),
            hourly_dau_chart=hourly_dau_chart, event_breakdown_chart=event_breakdown_chart,
        )

    def generate_cohort_report(self, cohort_id: str) -> CohortAnalysisResponse:
        rng = _rng(f"cohort:{cohort_id}")
        initial_users = rng.randint(800, 2400)
        raw_rates = [1.0, 0.70, 0.52, 0.41, 0.35, 0.31, 0.28]
        retention_data: list[CohortMetric] = []
        for period, rate in enumerate(raw_rates):
            jittered = round(rate * rng.uniform(0.92, 1.08), 3)
            jittered = min(jittered, 1.0)
            retention_data.append(CohortMetric(
                period=period,
                retained_users=int(initial_users * jittered),
                retention_rate=jittered,
            ))
        period_labels = [f"Week {i}" if i > 0 else "Signup" for i in range(7)]
        retention_values = [m.retention_rate * 100 for m in retention_data]
        chart = ChartData(
            chart_type="line", title=f"Cohort {cohort_id} Retention",
            labels=period_labels,
            datasets=[ChartDataset(label="Retention %", data=retention_values, color="#6366f1")],
            unit="%",
        )
        signup_period = cohort_id if len(cohort_id) == 7 else "2026-01"
        return CohortAnalysisResponse(
            cohort_id=cohort_id, cohort_name=f"Cohort {cohort_id}",
            signup_period=signup_period, initial_users=initial_users,
            retention_data=retention_data,
            avg_engagement_score=round(rng.uniform(48.0, 72.0), 1),
            avg_goals_per_user=round(rng.uniform(2.5, 6.8), 1),
            avg_session_duration_minutes=round(rng.uniform(12.0, 22.0), 1),
            top_features=random.Random(rng.randint(0, 9999)).sample(
                ["Goals", "AI Insights", "Tasks", "Daily Summary", "Integrations"], 3
            ),
            chart=chart,
        )


def _pick_achievements(rng: random.Random, goals_completed: int, tasks_completed: int, sessions: int) -> list[str]:
    pool = [
        f"Completed {goals_completed} goal{'s' if goals_completed != 1 else ''} this week",
        f"Finished {tasks_completed} tasks",
        f"Logged in {sessions} days",
        "Acted on 3 AI insights in one day",
        "Reached a 7-day active streak",
        "Connected your first integration",
    ]
    n = rng.randint(1, min(3, len(pool)))
    return rng.sample(pool, n)


def _pick_improvement_areas(rng: random.Random, engagement_change: float) -> list[str]:
    pool = [
        "Re-engage with goals you haven't touched in over a week",
        "Act on at least one AI insight per day this week",
        "Connect Notion or Google Calendar for more personalised insights",
        "Schedule a weekly review session on Sunday evening",
    ]
    n = rng.randint(1, 3)
    areas = rng.sample(pool, n)
    if engagement_change < -3:
        areas.insert(0, "Your engagement dipped — try a 5-minute daily check-in")
    return areas


report_generator = ReportGenerator()


def get_report_generator() -> ReportGenerator:
    return report_generator
