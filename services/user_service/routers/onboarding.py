"""
ZenSensei User Service - Onboarding Router

Handles new-user onboarding flow:
  POST /onboarding/life-stage       Set or update life stage
  POST /onboarding/interests        Set interest areas
  POST /onboarding/integrations     Connect initial third-party integrations
  GET  /onboarding/status           Check onboarding completion
"""

from __future__ import annotations

import sys
import os

_shared_path = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)
if _shared_path not in sys.path:
    sys.path.insert(0, _shared_path)

from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, Depends, status
from fastapi.responses import ORJSONResponse

from shared.auth import get_current_active_user
from shared.models.base import BaseResponse

from services.user_service.config import get_user_service_config
from services.user_service.schemas import (
    IntegrationsRequest,
    InterestsRequest,
    LifeStageRequest,
    OnboardingStatusResponse,
)
from services.user_service.services.auth_service import (
    _firestore_get_user_by_id,
    _firestore_update_user,
)
from services.user_service.services.user_service import _get_user_or_404

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/onboarding", tags=["Onboarding"])

# ─── Helpers ──────────────────────────────────────────────────────────────────


def _compute_onboarding_status(record: dict[str, Any]) -> OnboardingStatusResponse:
    """Derive onboarding completion state from a user record."""
    cfg = get_user_service_config()
    completed: list[str] = record.get("completed_onboarding_steps", [])

    life_stage_set = "life_stage" in completed
    interests_set = "interests" in completed
    integrations_connected = "integrations" in completed

    pending = [s for s in cfg.onboarding_steps if s not in completed]
    total = len(cfg.onboarding_steps)
    done_count = len([s for s in cfg.onboarding_steps if s in completed])
    pct = round((done_count / total) * 100, 1) if total > 0 else 0.0
    is_complete = len(pending) == 0

    return OnboardingStatusResponse(
        user_id=record["id"],
        is_complete=is_complete,
        completed_steps=completed,
        pending_steps=pending,
        completion_percentage=pct,
        life_stage_set=life_stage_set,
        interests_set=interests_set,
        integrations_connected=integrations_connected,
    )


async def _mark_step_complete(user_id: str, step: str) -> None:
    """Add *step* to the user's completed_onboarding_steps list."""
    record = await _firestore_get_user_by_id(user_id) or {}
    steps: list[str] = list(record.get("completed_onboarding_steps", []))
    if step not in steps:
        steps.append(step)

    cfg = get_user_service_config()
    is_complete = all(s in steps for s in cfg.onboarding_steps)

    await _firestore_update_user(
        user_id,
        {
            "completed_onboarding_steps": steps,
            "onboarding_completed": is_complete,
            "updated_at": datetime.now(tz=timezone.utc),
        },
    )


# ─── Life Stage ───────────────────────────────────────────────────────────────


@router.post(
    "/life-stage",
    response_model=BaseResponse[OnboardingStatusResponse],
    summary="Set or update the user's life stage",
    status_code=status.HTTP_200_OK,
    response_class=ORJSONResponse,
)
async def set_life_stage(
    request: LifeStageRequest,
    current_user: dict[str, Any] = Depends(get_current_active_user),
) -> dict[str, Any]:
    """
    Persist the authenticated user's life stage selection.

    Life stage is used to personalise AI recommendations.
    Can be updated at any time after initial onboarding.
    """
    user_id: str = current_user["sub"]
    record = await _get_user_or_404(user_id)

    await _firestore_update_user(
        user_id,
        {
            "life_stage": str(request.life_stage),
            "updated_at": datetime.now(tz=timezone.utc),
        },
    )
    await _mark_step_complete(user_id, "life_stage")

    # Refresh record after update
    record = await _firestore_get_user_by_id(user_id) or record
    status_response = _compute_onboarding_status(record)

    logger.info("Life stage set", user_id=user_id, life_stage=request.life_stage)
    return {
        "success": True,
        "message": f"Life stage set to '{request.life_stage}'.",
        "data": status_response.model_dump(),
    }


# ─── Interests ────────────────────────────────────────────────────────────────


@router.post(
    "/interests",
    response_model=BaseResponse[OnboardingStatusResponse],
    summary="Set or update the user's interest areas",
    status_code=status.HTTP_200_OK,
    response_class=ORJSONResponse,
)
async def set_interests(
    request: InterestsRequest,
    current_user: dict[str, Any] = Depends(get_current_active_user),
) -> dict[str, Any]:
    """
    Persist the authenticated user's interest areas.

    Interest areas are used to tailor onboarding content, suggested goals,
    and AI-generated insights. At least one interest must be provided.
    """
    user_id: str = current_user["sub"]
    await _get_user_or_404(user_id)

    await _firestore_update_user(
        user_id,
        {
            "interest_areas": request.interest_areas,
            "updated_at": datetime.now(tz=timezone.utc),
        },
    )
    await _mark_step_complete(user_id, "interests")

    record = await _firestore_get_user_by_id(user_id) or {}
    status_response = _compute_onboarding_status(record)

    logger.info("Interests set", user_id=user_id, interests=request.interest_areas)
    return {
        "success": True,
        "message": "Interest areas saved.",
        "data": status_response.model_dump(),
    }


# ─── Integrations ────────────────────────────────────────────────────────────


@router.post(
    "/integrations",
    response_model=BaseResponse[OnboardingStatusResponse],
    summary="Register initial third-party integrations",
    status_code=status.HTTP_200_OK,
    response_class=ORJSONResponse,
)
async def set_integrations(
    request: IntegrationsRequest,
    current_user: dict[str, Any] = Depends(get_current_active_user),
) -> dict[str, Any]:
    """
    Persist the user's selected integrations during onboarding.

    Integrations are stored as a list of provider identifiers (e.g.
    ``["google_calendar", "apple_health"]``). The actual OAuth connection
    is handled by the integrations service; this endpoint merely records
    the user's intent during the onboarding flow.
    """
    user_id: str = current_user["sub"]
    await _get_user_or_404(user_id)

    await _firestore_update_user(
        user_id,
        {
            "connected_integrations": request.integrations,
            "updated_at": datetime.now(tz=timezone.utc),
        },
    )
    await _mark_step_complete(user_id, "integrations")

    record = await _firestore_get_user_by_id(user_id) or {}
    status_response = _compute_onboarding_status(record)

    logger.info(
        "Integrations set", user_id=user_id, integrations=request.integrations
    )
    return {
        "success": True,
        "message": "Integrations registered.",
        "data": status_response.model_dump(),
    }


# ─── Status ───────────────────────────────────────────────────────────────────


@router.get(
    "/status",
    response_model=BaseResponse[OnboardingStatusResponse],
    summary="Check onboarding completion status",
    status_code=status.HTTP_200_OK,
    response_class=ORJSONResponse,
)
async def get_onboarding_status(
    current_user: dict[str, Any] = Depends(get_current_active_user),
) -> dict[str, Any]:
    """Return the current onboarding completion state for the authenticated user."""
    user_id: str = current_user["sub"]
    record = await _get_user_or_404(user_id)
    status_response = _compute_onboarding_status(record)
    return {
        "success": True,
        "message": "OK",
        "data": status_response.model_dump(),
    }
