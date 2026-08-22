import logging
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)

from src.api.dependencies import (
    get_m4_orchestration_service,
)
from src.api.schemas import M4AnswerRequest
from src.orchestration import (
    CitationValidationError,
    M4LLMConnectionError,
    M4LLMInvocationError,
    M4OrchestrationService,
)
from src.schemas.m4_contract import AIResponse


logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/api/v1/ai",
    tags=["AI"],
)


M4ServiceDependency = Annotated[
    M4OrchestrationService,
    Depends(
        get_m4_orchestration_service
    ),
]


@router.post(
    "/answer",
    response_model=AIResponse,
)
async def answer(
    request: M4AnswerRequest,
    service: M4ServiceDependency,
) -> AIResponse:
    """
    Generate a grounded legal answer from an upstream
    ProcessedQuery and RetrievedEvidence bundle.
    """

    try:
        return await service.aanswer_search(
            processed_query=(
                request.processed_query
            ),
            retrieved_evidence=(
                request.retrieved_evidence
            ),
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_400_BAD_REQUEST
            ),
            detail=(
                "ProcessedQuery and RetrievedEvidence "
                "are inconsistent."
            ),
        ) from exc

    except M4LLMConnectionError as exc:
        logger.error(
            "m4_ollama_connection_failed",
            extra={
                "error_type": (
                    type(exc).__name__
                ),
            },
        )

        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail=(
                "The local AI runtime is currently "
                "unavailable."
            ),
        ) from exc

    except (
        M4LLMInvocationError,
        CitationValidationError,
    ) as exc:
        logger.error(
            "m4_generation_failed",
            extra={
                "error_type": (
                    type(exc).__name__
                ),
            },
        )

        raise HTTPException(
            status_code=(
                status.HTTP_502_BAD_GATEWAY
            ),
            detail=(
                "The local AI runtime failed to "
                "produce a valid grounded response."
            ),
        ) from exc
