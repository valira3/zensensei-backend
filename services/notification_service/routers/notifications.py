"""
ZenSensei Notification Service - Notifications Router

Endpoints:
  GET  /notifications/{user_id}               - List notifications (paginated, filterable)
  GET  /notifications/{user_id}/unread/count  - Unread count
  PUT  /notifications/{notification_id}/read  - Mark single notification as read
  PUT  /notifications/{user_id}/read-all      - Mark all notifications as read
  DELETE /notifications/{notification_id}      - Delete a notification
  POST /notifications/send                    - Send a notification (internal)
  POST /notifications/broadcast               - Broadcast to multiple users
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import ORJSONResponse

from shared.auth import get_current_active_user
from shared.models.notifications import NotificationChannel, NotificationType

from services.notification_service.schemas import (
    BroadcastRequest,
    BroadcastResponse,
    DeleteNotificationResponse,
    MarkReadResponse,
    NotificationRecord,
    NotificationSendRequest,
)
import services.notification_service.services.notification_service as notif_svc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["notifications"])

# ─── List notifications ───────────────────────────────────────────────────────


@router.get(
    "/{user_id}",
    summary="List notifications for a user",
    response_class=ORJSONResponse,
)
async def list_notifications(
    user_id: str,
    notification_type: Optional[NotificationType] = Query(
        default=None,
        description="Filter by notification type",
    ),
    is_read: Optional[bool] = Query(
        default=None,
        description="Filter by read status (true = read, false = unread)",
    ),
    page: int = Query(default=1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    current_user: dict[str, Any] = Depends(get_current_active_user),
) -> ORJSONResponse:
    """
    Return a paginated list of notifications for *user_id*.

    Supports filtering by notification type and read status.
    Results are sorted newest-first.
    """
    result = await notif_svc.get_notifications(
        user_id=user_id,
        notification_type=notification_type,
        is_read=is_read,
        page=page,
        page_size=page_size,
    )
    return ORJSONResponse(
        {
            "success": True,
            "items": _serialize_list(result["items"]),
            "total": result["total"],
            "page": result["page"],
            "page_size": result["page_size"],
        }
    )


# ─── Unread count ─────────────────────────────────────────────────────────────


@router.get(
    "/{user_id}/unread/count",
    summary="Get unread notification count",
    response_class=ORJSONResponse,
)
async def unread_count(
    user_id: str,
    current_user: dict[str, Any] = Depends(get_current_active_user),
) -> ORJSONResponse:
    """Return the number of unread notifications for *user_id*."""
    count = await notif_svc.get_unread_count(user_id)
    return ORJSONResponse({"user_id": user_id, "unread_count": count})


# ─── Mark as read ─────────────────────────────────────────────────────────────


@router.put(
    "/{notification_id}/read",
    summary="Mark a notification as read",
    response_class=ORJSONResponse,
)
async def mark_notification_read(
    notification_id: str,
    current_user: dict[str, Any] = Depends(get_current_active_user),
) -> ORJSONResponse:
    """Mark the notification identified by *notification_id* as read."""
    record = await notif_svc.mark_read(notification_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Notification '{notification_id}' not found",
        )
    return ORJSONResponse(
        {
            "success": True,
            "data": _serialize_record(record),
        }
    )


# ─── Mark all as read ─────────────────────────────────────────────────────────


@router.put(
    "/{user_id}/read-all",
    summary="Mark all notifications as read for a user",
    response_class=ORJSONResponse,
)
async def mark_all_read(
    user_id: str,
    current_user: dict[str, Any] = Depends(get_current_active_user),
) -> ORJSONResponse:
    """Mark every unread notification for *user_id* as read."""
    updated = await notif_svc.mark_all_read(user_id)
    return ORJSONResponse(
        {
            "success": True,
            "data": MarkReadResponse(updated_count=updated).model_dump(),
        }
    )


# ─── Delete notification ──────────────────────────────────────────────────────


@router.delete(
    "/{notification_id}",
    summary="Delete a notification",
    response_class=ORJSONResponse,
)
async def delete_notification(
    notification_id: str,
    current_user: dict[str, Any] = Depends(get_current_active_user),
) -> ORJSONResponse:
    """Permanently delete the notification identified by *notification_id*."""
    deleted = await notif_svc.delete_notification(notification_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Notification '{notification_id}' not found",
        )
    return ORJSONResponse(
        {
            "success": True,
            "data": DeleteNotificationResponse(notification_id=notification_id).model_dump(),
        }
    )


# ─── Send notification (internal API) ────────────────────────────────────────


@router.post(
    "/send",
    summary="Send a notification to a user (internal API)",
    status_code=status.HTTP_201_CREATED,
    response_class=ORJSONResponse,
)
async def send_notification(
    request: NotificationSendRequest,
    current_user: dict[str, Any] = Depends(get_current_active_user),
) -> ORJSONResponse:
    """
    Dispatch a notification to a single user.

    If *template_id* is provided the title and body are rendered from that
    template using *template_variables*, overriding any supplied title/body.

    Respects user preferences and quiet hours unless the notification type is
    SYSTEM (system notifications bypass quiet hours).
    """
    title = request.title
    body = request.body

    # Render from template if provided
    if request.template_id:
        from services.notification_service.services.template_engine import render_template
        for channel in request.channels:
            rendered = render_template(
                request.template_id, channel, request.template_variables
            )
            if rendered:
                title, body = rendered
                break

    record = await notif_svc.send_notification(
        user_id=request.user_id,
        notification_type=request.notification_type,
        channels=request.channels,
        title=title,
        body=body,
        action_url=request.action_url,
        data=request.data,
        skip_preference_check=(request.notification_type == NotificationType.SYSTEM),
    )

    if record is None:
        return ORJSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "success": True,
                "message": "Notification suppressed by user preferences",
                "data": None,
            },
        )

    return ORJSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "success": True,
            "message": "Notification sent",
            "data": _serialize_record(record),
        },
    )


# ─── Broadcast ────────────────────────────────────────────────────────────────


@router.post(
    "/broadcast",
    summary="Broadcast a notification to multiple users",
    status_code=status.HTTP_202_ACCEPTED,
    response_class=ORJSONResponse,
)
async def broadcast_notification(
    request: BroadcastRequest,
    current_user: dict[str, Any] = Depends(get_current_active_user),
) -> ORJSONResponse:
    """
    Send the same notification to a list of users.

    Returns a summary of queued and failed deliveries.
    """
    title = request.title
    body = request.body

    if request.template_id:
        from services.notification_service.services.template_engine import render_template
        for channel in request.channels:
            rendered = render_template(
                request.template_id, channel, request.template_variables
            )
            if rendered:
                title, body = rendered
                break

    result = await notif_svc.batch_send(
        user_ids=request.user_ids,
        notification_type=request.notification_type,
        channels=request.channels,
        title=title,
        body=body,
        action_url=request.action_url,
        data=request.data,
    )

    return ORJSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "success": True,
            "message": f"Broadcast accepted for {result['total_users']} users",
            "data": BroadcastResponse(**result).model_dump(),
        },
    )


# ─── Serialisation helpers ────────────────────────────────────────────────────


def _serialize_record(record: dict[str, Any]) -> dict[str, Any]:
    """Convert a notification record dict to a JSON-safe dict."""
    from datetime import datetime
    result = dict(record)
    for key in ("created_at", "updated_at", "read_at", "delivered_at", "scheduled_at"):
        val = result.get(key)
        if isinstance(val, datetime):
            result[key] = val.isoformat()
    # Ensure enum values are serialised as strings
    if hasattr(result.get("notification_type"), "value"):
        result["notification_type"] = result["notification_type"].value
    channels = result.get("channels", [])
    result["channels"] = [
        c.value if hasattr(c, "value") else c for c in channels
    ]
    return result


def _serialize_list(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_serialize_record(r) for r in records]
