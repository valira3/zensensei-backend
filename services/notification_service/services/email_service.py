"""
ZenSensei Notification Service - Email Delivery Service

Sends transactional emails via SendGrid.
Falls back to a mock/log-only mode when the SENDGRID_API_KEY is absent.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ─── SendGrid client (lazy-init) ─────────────────────────────────────────────────


def _is_mock_mode() -> bool:
    """Return True when SendGrid credentials are absent (development mode)."""
    from shared.config import get_config
    cfg = get_config()
    return not cfg.sendgrid_api_key


@lru_cache(maxsize=1)
def _get_sendgrid_client() -> Optional[Any]:
    """
    Lazily create and cache the SendGrid API client.

    Returns None in mock mode.
    """
    if _is_mock_mode():
        logger.info("EmailService: No SendGrid API key — running in mock mode")
        return None

    try:
        from sendgrid import SendGridAPIClient
        from shared.config import get_config
        cfg = get_config()
        client = SendGridAPIClient(cfg.sendgrid_api_key)
        logger.info("EmailService: SendGrid client initialised")
        return client
    except Exception as exc:
        logger.warning("EmailService: Failed to init SendGrid client: %s — falling back to mock", exc)
        return None


def _get_from_email() -> str:
    from shared.config import get_config
    return get_config().sendgrid_from_email


# ─── Core email operations ────────────────────────────────────────────────────────


async def send_email(
    to: str | list[str],
    subject: str,
    html_body: Optional[str] = None,
    text_body: Optional[str] = None,
    from_email: Optional[str] = None,
    reply_to: Optional[str] = None,
    categories: Optional[list[str]] = None,
) -> dict[str, Any]:
    """
    Send a transactional email.

    In mock mode the message is logged and a synthetic success response is returned.

    Args:
        to: Single recipient email or list of emails.
        subject: Email subject line.
        html_body: HTML version of the email body (recommended).
        text_body: Plain-text fallback (auto-generated from html if omitted).
        from_email: Sender override (defaults to config ``sendgrid_from_email``).
        reply_to: Optional reply-to address.
        categories: SendGrid categories for analytics.

    Returns:
        Dict with ``success``, ``status_code``, and ``message_id``.
    """
    recipients = [to] if isinstance(to, str) else to
    sender = from_email or _get_from_email()
    # Auto-generate plain text if needed
    if not text_body and html_body:
        import re
        text_body = re.sub(r"<[^>]+>", "", html_body).strip()

    client = _get_sendgrid_client()

    if client is None:
        # ── Mock mode ──────────────────────────────────────────────────
        mock_id = f"mock-email-{int(datetime.now(tz=timezone.utc).timestamp())}"
        logger.info(
            "EmailService [MOCK]: send_email to=%s subject='%s'",
            recipients,
            subject,
        )
        return {
            "success": True,
            "status_code": 202,
            "message_id": mock_id,
            "mock": True,
        }

    # ── Live SendGrid ──────────────────────────────────────────────────
    try:
        from sendgrid.helpers.mail import Mail, To, Content

        mail = Mail(
            from_email=sender,
            subject=subject,
        )
        for recipient in recipients:
            mail.add_to(To(recipient))

        if html_body:
            mail.add_content(Content("text/html", html_body))
        if text_body:
            mail.add_content(Content("text/plain", text_body))
        if reply_to:
            from sendgrid.helpers.mail import ReplyTo
            mail.reply_to = ReplyTo(reply_to)
        if categories:
            for cat in categories:
                from sendgrid.helpers.mail import Category
                mail.add_category(Category(cat))

        response = client.send(mail)
        message_id = response.headers.get("X-Message-Id", "unknown")
        logger.info(
            "EmailService: sent email to=%s status=%d id=%s",
            recipients,
            response.status_code,
            message_id,
        )
        return {
            "success": response.status_code in (200, 202),
            "status_code": response.status_code,
            "message_id": message_id,
            "mock": False,
        }

    except Exception as exc:  # noqa: BLE001
        logger.error("EmailService: SendGrid send failed: %s", exc)
        return {
            "success": False,
            "error": str(exc),
        }


async def send_template_email(
    to: str | list[str],
    template_id: str,
    variables: dict[str, Any],
    from_email: Optional[str] = None,
    subject_override: Optional[str] = None,
) -> dict[str, Any]:
    """
    Render a notification template for the email channel and send it.

    Looks up the template from the template engine, substitutes variables,
    and delegates to ``send_email``.
    """
    from services.notification_service.services.template_engine import render_template
    from shared.models.notifications import NotificationChannel

    rendered = render_template(template_id, NotificationChannel.EMAIL, variables)
    if not rendered:
        logger.warning("EmailService: template '%s' not found or has no email content", template_id)
        return {
            "success": False,
            "error": f"Template '{template_id}' not found or has no email content",
        }

    title, body = rendered
    subject = subject_override or title

    # Convert markdown-ish body to basic HTML
    html_body = _markdown_to_html(body)

    return await send_email(
        to=to,
        subject=subject,
        html_body=html_body,
        text_body=body,
        from_email=from_email,
    )


# ─── Pre-built email templates ──────────────────────────────────────────────────


async def send_welcome_email(user_email: str, user_name: str) -> dict[str, Any]:
    """Send the welcome email to a newly registered user."""
    return await send_template_email(
        to=user_email,
        template_id="system_welcome",
        variables={
            "user_name": user_name,
            "onboarding_url": "https://app.zensensei.net/onboarding",
        },
    )


async def send_password_reset_email(
    user_email: str,
    user_name: str,
    reset_url: str,
    expires_in: str = "30 minutes",
) -> dict[str, Any]:
    """Send the password reset email."""
    return await send_template_email(
        to=user_email,
        template_id="system_password_reset",
        variables={
            "user_name": user_name,
            "reset_url": reset_url,
            "expires_in": expires_in,
        },
    )


async def send_insight_digest_email(
    user_email: str,
    user_name: str,
    insight_count: int,
    top_insight: str,
) -> dict[str, Any]:
    """Send the weekly insight digest email."""
    return await send_template_email(
        to=user_email,
        template_id="insight_digest",
        variables={
            "user_name": user_name,
            "insight_count": str(insight_count),
            "top_insight": top_insight,
            "digest_url": "https://app.zensensei.net/insights",
        },
    )


async def send_goal_milestone_email(
    user_email: str,
    user_name: str,
    goal_title: str,
    milestone: str,
    progress_pct: int,
    goal_url: str,
) -> dict[str, Any]:
    """Send the goal milestone celebration email."""
    return await send_template_email(
        to=user_email,
        template_id="goal_milestone",
        variables={
            "user_name": user_name,
            "goal_title": goal_title,
            "milestone": milestone,
            "progress_pct": str(progress_pct),
            "goal_url": goal_url,
        },
    )


async def send_weekly_summary_email(
    user_email: str,
    user_name: str,
    week_label: str,
    tasks_completed: int,
    goals_progressed: int,
    insights_count: int,
    streak_days: int,
) -> dict[str, Any]:
    """Send the weekly summary email."""
    return await send_template_email(
        to=user_email,
        template_id="system_weekly_summary",
        variables={
            "user_name": user_name,
            "week_label": week_label,
            "tasks_completed": str(tasks_completed),
            "goals_progressed": str(goals_progressed),
            "insights_count": str(insights_count),
            "streak_days": str(streak_days),
            "summary_url": "https://app.zensensei.net/summary",
        },
    )


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _markdown_to_html(text: str) -> str:
    """
    Convert very basic markdown to HTML for email bodies.
    Handles: **bold**, newlines -> <br>, URLs -> anchor tags.
    """
    import re

    # Bold
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    # Plain URLs not already in anchors
    text = re.sub(
        r"(?<![\"'])(https?://[^\s<>\"']+)",
        r'<a href="\1">\1</a>',
        text,
    )
    # Newlines to <br>
    text = text.replace("\n", "<br>\n")
    return f"<html><body style='font-family:sans-serif;line-height:1.6'>{text}</body></html>"
