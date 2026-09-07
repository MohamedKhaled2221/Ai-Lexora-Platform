"""
Stable M4 Package 3 and Package 4 API boundaries.

Existing P1/P2 endpoints remain unchanged.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)

from src.api.dependencies import (
    get_p3_m4_orchestrator,
    get_p4_m4_orchestrator,
)
from src.api.schemas import (
    P3ValidationRequest,
)
from src.orchestration.citation_validator import (
    CitationValidationError,
)
from src.orchestration.llm_service import (
    M4LLMConnectionError,
    M4LLMInvocationError,
)
from src.orchestration.model_usage_metrics import (
    ModelUsageTracker,
)
from src.orchestration.p3_orchestrator import (
    P3M4Orchestrator,
    P3ValidationContractError,
)
from src.orchestration.p4_orchestrator import (
    P4GroundingValidationError,
    P4M4Orchestrator,
)
from src.schemas.p3_generation_contract import (
    ValidatedDraft,
)
from src.schemas.p4_chat_contract import (
    AnswerGenerationRequest,
    ValidatedAIResponse,
)


logger = logging.getLogger(
    "src.api.m4_p3_p4_routes"
)


router = APIRouter(
    prefix="/api/v1/m4",
    tags=["M4 P3/P4"],
)


P3Dependency = Annotated[
    P3M4Orchestrator,
    Depends(
        get_p3_m4_orchestrator
    ),
]


P4Dependency = Annotated[
    P4M4Orchestrator,
    Depends(
        get_p4_m4_orchestrator
    ),
]


@router.post(
    "/p3/validate",
    response_model=ValidatedDraft,
)
async def validate_p3(
    request: P3ValidationRequest,
    service: P3Dependency,
) -> ValidatedDraft:
    """
    Validate an M1 Package 3 assembled draft.
    """

    try:
        with ModelUsageTracker() as tracker:
            result = await asyncio.to_thread(
                service.validate,
                draft=request.draft,
                manifest=request.manifest,
                grounding_context=(
                    request.grounding_context
                ),
            )

        usage = tracker.metrics

        logger.info(
            "m4_p3_validation_completed",
            extra={
                "draft_id": (
                    request.draft.draft_id
                ),
                "valid": (
                    result
                    .validated_draft
                    .validation
                    .is_valid
                ),
                "latency_ms": (
                    usage.latency_ms
                ),
                "ram_rss_after_mb": (
                    usage.ram_rss_after_mb
                ),
                "vram_used_after_mb": (
                    usage.vram_used_after_mb
                ),
                "semantic_grounding_used": (
                    result.metrics
                    .semantic_grounding_used
                ),
            },
        )

        return result.validated_draft

    except P3ValidationContractError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_400_BAD_REQUEST
            ),
            detail=(
                "The Package 3 draft and "
                "generation manifest are inconsistent."
            ),
        ) from exc

    except M4LLMConnectionError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail=(
                "The local AI validation runtime "
                "is unavailable."
            ),
        ) from exc

    except M4LLMInvocationError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_502_BAD_GATEWAY
            ),
            detail=(
                "The local AI validation runtime "
                "could not complete validation."
            ),
        ) from exc


@router.post(
    "/p4/answer",
    response_model=ValidatedAIResponse,
)
async def answer_p4(
    request: AnswerGenerationRequest,
    service: P4Dependency,
) -> ValidatedAIResponse:
    """
    Generate the final validated Package 4 answer.
    """

    try:
        with ModelUsageTracker() as tracker:
            result = await service.aanswer(
                request
            )

        usage = tracker.metrics

        logger.info(
            "m4_p4_answer_completed",
            extra={
                "request_id": (
                    request.request_id
                ),
                "query_id": (
                    request.query_id
                ),
                "insufficient_evidence": (
                    result
                    .response
                    .insufficient_evidence
                ),
                "latency_ms": (
                    usage.latency_ms
                ),
                "ram_rss_after_mb": (
                    usage.ram_rss_after_mb
                ),
                "vram_used_after_mb": (
                    usage.vram_used_after_mb
                ),
                "generation_invoked": (
                    result.metrics
                    .generation_invoked
                ),
                "citation_count": (
                    result.metrics
                    .citation_count
                ),
            },
        )

        return result.response

    except M4LLMConnectionError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail=(
                "The local AI runtime is "
                "currently unavailable."
            ),
        ) from exc

    except (
        M4LLMInvocationError,
        CitationValidationError,
        P4GroundingValidationError,
    ) as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_502_BAD_GATEWAY
            ),
            detail=(
                "The local AI runtime failed to "
                "produce a valid grounded response."
            ),
        ) from exc
