import logging
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    status,
)

from src.api.dependencies import (
    get_rag_service,
    get_raw_rag_service,
)
from src.api.schemas import (
    RAGAnswerRequest,
    RawRAGAnswerRequest,
)
from src.orchestration import (
    CitationValidationError,
    M2EmbeddingContractError,
    M2M3M4RAGService,
    M2QueryRuntimeError,
    M2QueryValidationError,
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
    Depends(get_rag_service),
]

RawRAGServiceDependency = Annotated[
    M2M3M4RAGService,
    Depends(get_raw_rag_service),
]

def _get_request_id(
    request: Request,
) -> str:
    return getattr(
        request.state,
        "request_id",
        "unknown",
    )


def _log_rag_failure(
    *,
    request: Request,
    request_body: RAGAnswerRequest,
    exc: Exception,
    failure_stage: str,
) -> None:
    """
    Log operational failure metadata without logging
    question text, evidence, prompts, embeddings,
    generated answers, or exception messages.
    """

    logger.error(
        "rag_request_failed",
        extra={
            "request_id": _get_request_id(
                request
            ),
            "query_id": (
                request_body
                .processed_query
                .query_id
            ),
            "status": "failure",
            "failure_stage": failure_stage,
            "error_type": (
                type(exc).__name__
            ),
        },
    )

def _log_raw_rag_failure(
    *,
    request: Request,
    exc: Exception,
    failure_stage: str,
) -> None:
    """
    Log only safe operational metadata for raw-query
    failures.

    Never log the raw question or embedding.
    """

    logger.error(
        "raw_rag_request_failed",
        extra={
            "request_id": _get_request_id(
                request
            ),
            "status": "failure",
            "failure_stage": failure_stage,
            "error_type": (
                type(exc).__name__
            ),
        },
    )

@router.post(
    "/ask",
    response_model=AIResponse,
)
async def answer_raw_rag(
    request_body: RawRAGAnswerRequest,
    request: Request,
    service: RawRAGServiceDependency,
) -> AIResponse:
    """
    Execute the complete raw-question pipeline:

    M2 processing/embedding
        -> M3 retrieval
        -> M4 grounded generation.
    """

    try:
        result = (
            await service
            .aanswer_with_metrics(
                question=request_body.question,
                filters=request_body.filters,
            )
        )

        metrics = result.metrics

        logger.info(
            "raw_rag_request_completed",
            extra={
                "request_id": (
                    _get_request_id(
                        request
                    )
                ),
                "query_id": (
                    result.response.query_id
                ),
                "retrieval_ms": (
                    metrics.retrieval_ms
                ),
                "generation_ms": (
                    metrics.generation_ms
                ),
                "total_rag_ms": (
                    metrics.total_rag_ms
                ),
                "retrieved_chunk_count": (
                    metrics
                    .retrieved_chunk_count
                ),
                "citation_count": (
                    metrics.citation_count
                ),
                "status": "success",
            },
        )

        return result.response

    except M2QueryValidationError as exc:
        _log_raw_rag_failure(
            request=request,
            exc=exc,
            failure_stage="query_processing",
        )

        raise HTTPException(
            status_code=(
                status.HTTP_400_BAD_REQUEST
            ),
            detail=(
                "The raw question is invalid."
            ),
        ) from exc

    except M2EmbeddingContractError as exc:
        _log_raw_rag_failure(
            request=request,
            exc=exc,
            failure_stage=(
                "embedding_validation"
            ),
        )

        raise HTTPException(
            status_code=(
                status.HTTP_502_BAD_GATEWAY
            ),
            detail=(
                "The local embedding runtime "
                "produced an invalid query "
                "embedding."
            ),
        ) from exc

    except M2QueryRuntimeError as exc:
        _log_raw_rag_failure(
            request=request,
            exc=exc,
            failure_stage="query_embedding",
        )

        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail=(
                "The local embedding runtime is "
                "currently unavailable."
            ),
        ) from exc

    except ValueError as exc:
        _log_raw_rag_failure(
            request=request,
            exc=exc,
            failure_stage="retrieval",
        )

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
        _log_raw_rag_failure(
            request=request,
            exc=exc,
            failure_stage="generation",
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
        _log_raw_rag_failure(
            request=request,
            exc=exc,
            failure_stage="generation",
        )

        raise HTTPException(
            status_code=(
                status.HTTP_502_BAD_GATEWAY
            ),
            detail=(
                "The local AI runtime failed to "
                "produce a valid grounded "
                "response."
            ),
        ) from exc
@router.post(
    "/answer",
    response_model=AIResponse,
)
async def answer_rag(
    request_body: RAGAnswerRequest,
    request: Request,
    service: RAGServiceDependency,
) -> AIResponse:
    """
    Execute M3 retrieval followed by grounded
    M4 local-LLM answer generation.
    """

    try:
        result = (
            await service
            .aanswer_with_metrics(
                request_body.processed_query
            )
        )

        metrics = result.metrics

        logger.info(
            "rag_request_completed",
            extra={
                "request_id": (
                    _get_request_id(
                        request
                    )
                ),
                "query_id": (
                    request_body
                    .processed_query
                    .query_id
                ),
                "retrieval_ms": (
                    metrics.retrieval_ms
                ),
                "generation_ms": (
                    metrics.generation_ms
                ),
                "total_rag_ms": (
                    metrics.total_rag_ms
                ),
                "retrieved_chunk_count": (
                    metrics
                    .retrieved_chunk_count
                ),
                "citation_count": (
                    metrics.citation_count
                ),
                "status": "success",
            },
        )

        return result.response

    except ValueError as exc:
        _log_rag_failure(
            request=request,
            request_body=request_body,
            exc=exc,
            failure_stage="retrieval",
        )

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
        _log_rag_failure(
            request=request,
            request_body=request_body,
            exc=exc,
            failure_stage="generation",
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
        _log_rag_failure(
            request=request,
            request_body=request_body,
            exc=exc,
            failure_stage="generation",
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
