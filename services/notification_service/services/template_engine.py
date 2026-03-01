"""
ZenSensei Notification Service - Template Engine

Provides built-in templates for each NotificationType with
channel-specific formatting (push = short, email = detailed,
in-app = medium) and {{variable}} substitution.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

from shared.models.notifications import NotificationChannel, NotificationType

logger = logging.getLogger(__name__)

# ─── Template registry ─────────────────────────────────────────────────────────────

# Structure: {template_id: {channel: {title, body}, variables: [...], ...}}
_BUILTIN_TEMPLATES: dict[str, dict[str, Any]] = {
    # ── INSIGHT ────────────────────────────────────────────────────────────────────
    "insight_new": {
        "notification_type": NotificationType.INSIGHT,
        "name": "New Insight Available",
        "description": "Sent when ZenSensei generates a new insight for the user.",
        "variables": ["user_name", "insight_title", "insight_preview", "insight_url"],
        "push": {
            "title": "New insight for you ✨",
            "body": "{{insight_title}} — tap to explore.",
        },
        "in_app": {
            "title": "New Insight: {{insight_title}}",
            "body": "{{insight_preview}} Discover what this means for your goals.",
        },
        "email": {
            "title": "ZenSensei found a new insight for you",
            "body": (
                "Hi {{user_name}},\n\n"
                "We've uncovered a new insight based on your recent activity:\n\n"
                "**{{insight_title}}**\n\n"
                "{{insight_preview}}\n\n"
                "Visit {{insight_url}} to explore this insight in depth and take action."
            ),
        },
    },
    "insight_digest": {
        "notification_type": NotificationType.INSIGHT,
        "name": "Weekly Insight Digest",
        "description": "Weekly summary of insights generated for the user.",
        "variables": ["user_name", "insight_count", "top_insight", "digest_url"],
        "push": {
            "title": "Your weekly ZenSensei digest",
            "body": "{{insight_count}} new insights this week. Tap to review.",
        },
        "in_app": {
            "title": "Weekly Digest: {{insight_count}} New Insights",
            "body": "Top insight: {{top_insight}}. View all in your digest.",
        },
        "email": {
            "title": "Your ZenSensei Weekly Digest",
            "body": (
                "Hi {{user_name}},\n\n"
                "Here's your weekly summary from ZenSensei:\n\n"
                "You received **{{insight_count}} new insights** this week.\n\n"
                "Top insight: {{top_insight}}\n\n"
                "View your full digest at {{digest_url}}."
            ),
        },
    },
    # ── REMINDER ─────────────────────────────────────────────────────────────────
    "reminder_task": {
        "notification_type": NotificationType.REMINDER,
        "name": "Task Reminder",
        "description": "Reminds the user about a pending task.",
        "variables": ["user_name", "task_title", "due_date", "task_url"],
        "push": {
            "title": "Task reminder ⏰",
            "body": "{{task_title}} is due {{due_date}}.",
        },
        "in_app": {
            "title": "Reminder: {{task_title}}",
            "body": "This task is due {{due_date}}. Don't forget to complete it!",
        },
        "email": {
            "title": "Reminder: {{task_title}}",
            "body": (
                "Hi {{user_name}},\n\n"
                "This is a friendly reminder that your task **{{task_title}}** is due {{due_date}}.\n\n"
                "View and complete the task at {{task_url}}."
            ),
        },
    },
    "reminder_goal_check_in": {
        "notification_type": NotificationType.REMINDER,
        "name": "Goal Check-In Reminder",
        "description": "Periodic reminder to update goal progress.",
        "variables": ["user_name", "goal_title", "last_updated", "goal_url"],
        "push": {
            "title": "Goal check-in 🎯",
            "body": "How's {{goal_title}} going? Log an update.",
        },
        "in_app": {
            "title": "Time to check in on {{goal_title}}",
            "body": "Last updated {{last_updated}}. Tap to log your progress.",
        },
        "email": {
            "title": "Goal Check-In: {{goal_title}}",
            "body": (
                "Hi {{user_name}},\n\n"
                "It's time to check in on your goal: **{{goal_title}}**.\n\n"
                "You last updated this goal {{last_updated}}. Log your progress at {{goal_url}}."
            ),
        },
    },
    # ── RELATIONSHIP ─────────────────────────────────────────────────────────────
    "relationship_new": {
        "notification_type": NotificationType.RELATIONSHIP,
        "name": "New Relationship Discovered",
        "description": "Sent when a new meaningful connection is detected in the user's graph.",
        "variables": ["user_name", "entity_a", "entity_b", "relationship_type", "graph_url"],
        "push": {
            "title": "New connection found 🔗",
            "body": "{{entity_a}} is linked to {{entity_b}}. Tap to explore.",
        },
        "in_app": {
            "title": "Connection: {{entity_a}} → {{entity_b}}",
            "body": "ZenSensei found a {{relationship_type}} relationship between these two areas of your life.",
        },
        "email": {
            "title": "New Connection Discovered in Your Graph",
            "body": (
                "Hi {{user_name}},\n\n"
                "ZenSensei has discovered a new relationship in your personal knowledge graph:\n\n"
                "**{{entity_a}}** has a **{{relationship_type}}** connection to **{{entity_b}}**.\n\n"
                "Explore this connection at {{graph_url}}."
            ),
        },
    },
    # ── GOAL_MILESTONE ────────────────────────────────────────────────────────────
    "goal_milestone": {
        "notification_type": NotificationType.GOAL_MILESTONE,
        "name": "Goal Milestone Reached",
        "description": "Celebrates when a user hits a significant goal milestone.",
        "variables": ["user_name", "goal_title", "milestone", "progress_pct", "goal_url"],
        "push": {
            "title": "Milestone reached! 🎉",
            "body": "{{goal_title}}: {{milestone}} — {{progress_pct}}% complete.",
        },
        "in_app": {
            "title": "🎉 {{milestone}} on {{goal_title}}",
            "body": "You're {{progress_pct}}% of the way there. Keep it up!",
        },
        "email": {
            "title": "Congratulations — Milestone Reached!",
            "body": (
                "Hi {{user_name}},\n\n"
                "Fantastic work! You've reached a major milestone on your goal **{{goal_title}}**:\n\n"
                "🏆 **{{milestone}}**\n\n"
                "You're now **{{progress_pct}}% complete**. Keep the momentum going!\n\n"
                "View your goal at {{goal_url}}."
            ),
        },
    },
    "goal_completed": {
        "notification_type": NotificationType.GOAL_MILESTONE,
        "name": "Goal Completed",
        "description": "Sent when a user completes a goal.",
        "variables": ["user_name", "goal_title", "completed_at", "next_steps_url"],
        "push": {
            "title": "Goal complete! 🏆",
            "body": "You completed {{goal_title}}! Amazing work.",
        },
        "in_app": {
            "title": "🏆 You completed {{goal_title}}!",
            "body": "Goal achieved on {{completed_at}}. Ready for your next challenge?",
        },
        "email": {
            "title": "You Did It — {{goal_title}} Complete!",
            "body": (
                "Hi {{user_name}},\n\n"
                "You've completed your goal **{{goal_title}}** on {{completed_at}}! 🎊\n\n"
                "This is a huge achievement. Take a moment to celebrate — then check out your "
                "next steps at {{next_steps_url}}."
            ),
        },
    },
    # ── SYSTEM ───────────────────────────────────────────────────────────────────
    "system_welcome": {
        "notification_type": NotificationType.SYSTEM,
        "name": "Welcome to ZenSensei",
        "description": "Sent to new users immediately after signup.",
        "variables": ["user_name", "onboarding_url"],
        "push": {
            "title": "Welcome to ZenSensei! 🌟",
            "body": "Your personal AI coach is ready. Tap to begin.",
        },
        "in_app": {
            "title": "Welcome, {{user_name}}! 🌟",
            "body": "ZenSensei is your AI-powered life coach. Start by completing your profile.",
        },
        "email": {
            "title": "Welcome to ZenSensei, {{user_name}}!",
            "body": (
                "Hi {{user_name}},\n\n"
                "Welcome to ZenSensei — your personal AI coach for life, goals, and growth.\n\n"
                "To get started, complete your onboarding at {{onboarding_url}}.\n\n"
                "We're excited to have you on this journey!"
            ),
        },
    },
    "system_password_reset": {
        "notification_type": NotificationType.SYSTEM,
        "name": "Password Reset",
        "description": "Sent when a user requests a password reset.",
        "variables": ["user_name", "reset_url", "expires_in"],
        "push": {
            "title": "Password reset requested",
            "body": "Tap to reset your password. Link expires in {{expires_in}}.",
        },
        "in_app": {
            "title": "Password Reset Requested",
            "body": "A password reset was requested. If this wasn't you, secure your account immediately.",
        },
        "email": {
            "title": "Reset Your ZenSensei Password",
            "body": (
                "Hi {{user_name}},\n\n"
                "We received a request to reset your ZenSensei password.\n\n"
                "Click the link below to set a new password (expires in {{expires_in}}):\n\n"
                "{{reset_url}}\n\n"
                "If you didn't request this, please ignore this email or contact support."
            ),
        },
    },
    "system_weekly_summary": {
        "notification_type": NotificationType.SYSTEM,
        "name": "Weekly Summary",
        "description": "Weekly activity and progress summary.",
        "variables": [
            "user_name", "week_label", "tasks_completed", "goals_progressed",
            "insights_count", "streak_days", "summary_url",
        ],
        "push": {
            "title": "Your week in review 📊",
            "body": "{{tasks_completed}} tasks done, {{insights_count}} insights. Tap for your full recap.",
        },
        "in_app": {
            "title": "Weekly Summary: {{week_label}}",
            "body": (
                "{{tasks_completed}} tasks completed · {{goals_progressed}} goals updated · "
                "{{insights_count}} new insights · {{streak_days}}-day streak 🔥"
            ),
        },
        "email": {
            "title": "Your ZenSensei Weekly Summary — {{week_label}}",
            "body": (
                "Hi {{user_name}},\n\n"
                "Here's your activity recap for {{week_label}}:\n\n"
                "✅ **{{tasks_completed}}** tasks completed\n"
                "🎯 **{{goals_progressed}}** goals progressed\n"
                "✨ **{{insights_count}}** new insights generated\n"
                "🔥 **{{streak_days}}-day** active streak\n\n"
                "View your full summary at {{summary_url}}."
            ),
        },
    },
    # ── SOCIAL ───────────────────────────────────────────────────────────────────
    "social_follow": {
        "notification_type": NotificationType.SOCIAL,
        "name": "New Follower",
        "description": "Sent when another user follows this user.",
        "variables": ["follower_name", "follower_profile_url"],
        "push": {
            "title": "New follower! 👋",
            "body": "{{follower_name}} started following you.",
        },
        "in_app": {
            "title": "{{follower_name}} is now following you",
            "body": "Check out their profile and connect.",
        },
        "email": {
            "title": "{{follower_name}} started following you on ZenSensei",
            "body": (
                "Hi there,\n\n"
                "**{{follower_name}}** just started following you on ZenSensei.\n\n"
                "View their profile at {{follower_profile_url}}."
            ),
        },
    },
    "social_achievement_shared": {
        "notification_type": NotificationType.SOCIAL,
        "name": "Achievement Shared",
        "description": "Sent when a followed user shares an achievement.",
        "variables": ["sharer_name", "achievement_title", "sharer_profile_url"],
        "push": {
            "title": "{{sharer_name}} hit a milestone! 🎉",
            "body": "{{achievement_title}} — give them a high-five.",
        },
        "in_app": {
            "title": "{{sharer_name}}: {{achievement_title}}",
            "body": "Celebrate their win and stay motivated on your own journey.",
        },
        "email": {
            "title": "{{sharer_name}} just hit a milestone!",
            "body": (
                "Hi there,\n\n"
                "**{{sharer_name}}** achieved **{{achievement_title}}** on ZenSensei! 🎉\n\n"
                "View their profile to celebrate at {{sharer_profile_url}}."
            ),
        },
    },
}

# ─── In-memory custom template store ─────────────────────────────────────────────────

_custom_templates: dict[str, dict[str, Any]] = {}


# ─── Engine ───────────────────────────────────────────────────────────────────────

_VAR_RE = re.compile(r"\{\{(\w+)\}\}")


def _substitute(text: str, variables: dict[str, Any]) -> str:
    """Replace {{variable}} placeholders with values from *variables* dict."""
    def _replace(match: re.Match) -> str:  # type: ignore[type-arg]
        key = match.group(1)
        return str(variables.get(key, match.group(0)))

    return _VAR_RE.sub(_replace, text)


def render_template(
    template_id: str,
    channel: NotificationChannel,
    variables: dict[str, Any],
) -> Optional[tuple[str, str]]:
    """
    Render a template for a given channel.

    Returns:
        Tuple of (title, body) with variables substituted, or None if the
        template or channel mapping doesn't exist.
    """
    template = _custom_templates.get(template_id) or _BUILTIN_TEMPLATES.get(template_id)
    if not template:
        logger.warning("Template '%s' not found", template_id)
        return None

    channel_key = channel.value.lower() if hasattr(channel, "value") else channel.lower()
    channel_content = template.get(channel_key)
    if not channel_content:
        logger.debug("Template '%s' has no content for channel '%s'", template_id, channel_key)
        return None

    title = _substitute(channel_content["title"], variables)
    body = _substitute(channel_content["body"], variables)
    return title, body


def get_template(template_id: str) -> Optional[dict[str, Any]]:
    """Return the raw template dict by ID (custom first, then built-in)."""
    return _custom_templates.get(template_id) or _BUILTIN_TEMPLATES.get(template_id)


def list_templates(
    notification_type: Optional[NotificationType] = None,
    active_only: bool = True,
) -> list[dict[str, Any]]:
    """Return all templates, optionally filtered by type and active status."""
    all_templates = {**_BUILTIN_TEMPLATES, **_custom_templates}
    results = []
    for tid, tmpl in all_templates.items():
        tmpl_copy = {**tmpl, "template_id": tid}
        if notification_type and tmpl.get("notification_type") != notification_type:
            continue
        if active_only and not tmpl_copy.get("is_active", True):
            continue
        results.append(tmpl_copy)
    return results


def create_template(template_id: str, template_data: dict[str, Any]) -> dict[str, Any]:
    """Register a new custom template."""
    if template_id in _BUILTIN_TEMPLATES:
        raise ValueError(f"Cannot overwrite built-in template '{template_id}'")
    template_data["template_id"] = template_id
    template_data.setdefault("is_active", True)
    template_data["created_at"] = datetime.now(tz=timezone.utc)
    template_data["updated_at"] = datetime.now(tz=timezone.utc)
    _custom_templates[template_id] = template_data
    return template_data


def update_template(template_id: str, updates: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Update an existing custom template. Built-in templates cannot be mutated."""
    if template_id in _BUILTIN_TEMPLATES:
        raise ValueError(f"Built-in template '{template_id}' cannot be modified")
    if template_id not in _custom_templates:
        return None
    _custom_templates[template_id].update(updates)
    _custom_templates[template_id]["updated_at"] = datetime.now(tz=timezone.utc)
    return _custom_templates[template_id]


def get_default_template_id(notification_type: NotificationType) -> Optional[str]:
    """Return the first built-in template ID for a given notification type."""
    for tid, tmpl in _BUILTIN_TEMPLATES.items():
        if tmpl.get("notification_type") == notification_type:
            return tid
    return None
