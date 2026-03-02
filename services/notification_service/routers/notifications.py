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
    if user_id != current_user.get("sub", current_user.get("user_id", current_user.get("id"))):
        raise HTTPException(status_code=403, detail="Access denied")
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
    if user_id != current_user.get("sub", current_user.get("user_id", current_user.get("id"))):
        raise HTTPException(status_code=403, detail="Access denied")
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
    if user_id != current_user.get("sub", current_user.get("user_id", current_user.get("id"))):
        raise HTTPException(status_code=403, detail="Access denied")
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
            "data": DeleteNotificationResponse(
                notification_id=notification_id, deleted=True
            ).model_dump(),
        }
    )


# ─── Send notification (internal) ───────────────────────────────────────────


@router.post(
    "/send",
    summary="Send a notification (internal use)",
    response_class=ORJSONResponse,
    status_code=status.HTTP_201_CREATED,
)
async def send_notification(
    payload: NotificationSendRequest,
    current_user: dict[str, Any] = Depends(get_current_active_user),
) -> ORJSONResponse:
    """
    Send a notification to a single user.

    This endpoint is intended for internal service-to-service calls.
    """
    record = await notif_svc.send_notification(
        user_id=payload.user_id,
        notification_type=payload.notification_type,
        title=payload.title,
        message=payload.message,
        data=payload.data,
        channels=payload.channels,
        priority=payload.priority,
    )
    return ORJSONResponse(
        {"success": True, "data": _serialize_record(record)},
        status_code=status.HTTP_201_CREATED,
    )


# ─── Broadcast ────────────────────────────────────────────────────────────────


@router.post(
    "/broadcast",
    summary="Broadcast a notification to multiple users",
    response_class=ORJSONResponse,
    status_code=status.HTTP_201_CREATED,
)
async def broadcast_notification(
    payload: BroadcastRequest,
    current_user: dict[str, Any] = Depends(get_current_active_user),
) -> ORJSONResponse:
    """Send the same notification to all user IDs in *user_ids*."""
    records = await notif_svc.broadcast_notification(
        user_ids=payload.user_ids,
        notification_type=payload.notification_type,
        title=payload.title,
        message=payload.message,
        data=payload.data,
        channels=payload.channels,
        priority=payload.priority,
    )
    return ORJSONResponse(
        {
            "success": True,
            "data": BroadcastResponse(
                sent_count=len(records),
                records=[_serialize_record(r) for r in records],
            ).model_dump(),
        },
        status_code=status.HTTP_201_CREATED,
    )


# ─── Serialization helpers ────────────────────────────────────────────────────


def _serialize_record(record: Any) -> dict[str, Any]:
    """Convert a notification record (dict or Pydantic model) to a plain dict."""
    if hasattr(record, "model_dump"):
        return record.model_dump()
    return dict(record)


def _serialize_list(items: list[Any]) -> list[dict[str, Any]]:
    return [_serialize_record(item) for item in items]
