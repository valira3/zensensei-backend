"""
ZenSensei Notification Service - Templates Router

Endpoints:
  GET  /notifications/templates                      - List notification templates
  POST /notifications/templates                      - Create a custom template
  PUT  /notifications/templates/{template_id}        - Update a custom template
  GET  /notifications/templates/{template_id}        - Get a single template
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import ORJSONResponse

from shared.auth import get_current_active_user
from shared.models.notifications import NotificationType

from services.notification_service.schemas import (
    TemplateCreateRequest,
    TemplateResponse,
    TemplateUpdateRequest,
)
from services.notification_service.services import template_engine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications/templates", tags=["templates"])


# ─── List templates ───────────────────────────────────────────────────────────


@router.get(
    "",
    summary="List notification templates",
    response_class=ORJSONResponse,
)
async def list_templates(
    notification_type: Optional[NotificationType] = Query(
        default=None,
        description="Filter by notification type",
    ),
    active_only: bool = Query(
        default=True,
        description="When true, only active templates are returned",
    ),
    current_user: dict[str, Any] = Depends(get_current_active_user),
) -> ORJSONResponse:
    """
    Return all available notification templates.

    Both built-in system templates and custom templates are included.
    Built-in templates cannot be deleted or modified; use the PUT endpoint
    to manage custom templates only.
    """
    templates = template_engine.list_templates(
        notification_type=notification_type,
        active_only=active_only,
    )
    return ORJSONResponse(
        {
            "success": True,
            "items": [_serialize_template(t) for t in templates],
            "total": len(templates),
        }
    )


# ─── Get single template ──────────────────────────────────────────────────────


@router.get(
    "/{template_id}",
    summary="Get a notification template by ID",
    response_class=ORJSONResponse,
)
async def get_template(
    template_id: str,
    current_user: dict[str, Any] = Depends(get_current_active_user),
) -> ORJSONResponse:
    """Fetch a single notification template by its slug ID."""
    tmpl = template_engine.get_template(template_id)
    if not tmpl:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template '{template_id}' not found",
        )
    return ORJSONResponse(
        {
            "success": True,
            "data": _serialize_template({**tmpl, "template_id": template_id}),
        }
    )


# ─── Create template ──────────────────────────────────────────────────────────


@router.post(
    "",
    summary="Create a custom notification template",
    status_code=status.HTTP_201_CREATED,
    response_class=ORJSONResponse,
)
async def create_template(
    request: TemplateCreateRequest,
    current_user: dict[str, Any] = Depends(get_current_active_user),
) -> ORJSONResponse:
    """
    Register a new custom notification template.

    Templates use ``{{variable}}`` syntax for variable substitution.
    Channel content (``push``, ``email``, ``in_app``) is optional —
    omit a channel to skip rendering for that channel.

    Built-in template IDs are protected and will return 409 Conflict.
    """
    template_data = request.model_dump(exclude_none=True)
    template_data.pop("template_id", None)  # handled by engine

    try:
        created = template_engine.create_template(request.template_id, template_data)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return ORJSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "success": True,
            "message": f"Template '{request.template_id}' created",
            "data": _serialize_template(created),
        },
    )


# ─── Update template ──────────────────────────────────────────────────────────


@router.put(
    "/{template_id}",
    summary="Update a custom notification template",
    response_class=ORJSONResponse,
)
async def update_template(
    template_id: str,
    request: TemplateUpdateRequest,
    current_user: dict[str, Any] = Depends(get_current_active_user),
) -> ORJSONResponse:
    """
    Partially update a custom notification template.

    Only non-null fields in the request body are applied.
    Built-in templates cannot be modified and will return 409 Conflict.
    """
    updates = request.model_dump(exclude_none=True)

    try:
        updated = template_engine.update_template(template_id, updates)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Custom template '{template_id}' not found",
        )

    return ORJSONResponse(
        {
            "success": True,
            "message": f"Template '{template_id}' updated",
            "data": _serialize_template(updated),
        }
    )


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _serialize_template(tmpl: dict[str, Any]) -> dict[str, Any]:
    """Convert a raw template dict to a JSON-safe structure."""
    from datetime import datetime
    result = dict(tmpl)
    for key in ("created_at", "updated_at"):
        val = result.get(key)
        if isinstance(val, datetime):
            result[key] = val.isoformat()
    # Normalise notification_type enum
    nt = result.get("notification_type")
    if hasattr(nt, "value"):
        result["notification_type"] = nt.value
    return result
