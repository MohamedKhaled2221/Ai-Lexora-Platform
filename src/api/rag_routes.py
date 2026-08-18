import logging
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)

from src.api.dependencies import (
    get_rag_service,
)
from src.api.schemas import (
    RAGAnswerRequest,
)
from src.orchestration import (
    CitationValidationError,
    M3M4RAGService,
    M4LLMConnectionError,
    M4LLMInvocationError,
)
from src.schemas.m4_contract import (
    AIResponse,
)


logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/api/v1/rag",
    tags=["RAG"],
)


RAGServiceDependency = Annotated[
    M3M4RAGService,
    Depends(
        get_rag_service
    ),
]


@router.post(
    "/answer",
    response_model=AIResponse,
)
async def answer_rag(
    request: RAGAnswerRequest,
    service: RAGServiceDependency,
) -> AIResponse:
    """
    Execute retrieval followed by grounded
    local LLM answer generation.
    """

    try:
        return await service.aanswer(
            request.processed_query
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_400_BAD_REQUEST
            ),
            detail=(
                "The processed query is invalid "
                "for retrieval."
            ),
        ) from exc

    except M4LLMConnectionError as exc:
        logger.exception(
            "RAG generation could not "
            "connect to Ollama."
        )

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
    ) as exc:
        logger.exception(
            "RAG generation produced an "
            "invalid M4 response."
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
