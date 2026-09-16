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
from src.api.identity import (
    CallerIdentityDependency,
    apply_access_scope,
    reject_client_supplied_access,
)
from src.api.schemas import (
    RAGAnswerRequest,
    RAGSearchHit,
    RAGSearchRequest,
    RAGSearchResponse,
    RawRAGAnswerRequest,
)
from src.retrieval.reranker import RerankerUnavailable
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
    identity: CallerIdentityDependency,
) -> AIResponse:
    """
    Execute the complete raw-question pipeline:

    M2 processing/embedding
        -> M3 retrieval
        -> M4 grounded generation.

    The access scope is set here from the authenticated caller. A body that
    arrives already carrying one is refused rather than overwritten -- see
    reject_client_supplied_access.
    """

    reject_client_supplied_access(
        request_body.filters,
        request,
        field_path="filters.access",
    )

    scoped_filters = apply_access_scope(
        request_body.filters,
        identity,
    )

    try:
        result = (
            await service
            .aanswer_with_metrics(
                question=request_body.question,
                filters=scoped_filters,
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
@router.post(
    "/search",
    response_model=RAGSearchResponse,
)
async def search_documents(
    request_body: RAGSearchRequest,
    request: Request,
    service: RawRAGServiceDependency,
    identity: CallerIdentityDependency,
) -> RAGSearchResponse:
    """
    Ranked document search: M2 processing/embedding -> M3 retrieval.

    No LLM call. Each document appears once, ranked by its best chunk, which
    is also its snippet. Access is scoped from the authenticated caller exactly
    as on /ask, and a client-supplied scope is refused.
    """

    reject_client_supplied_access(
        request_body.filters,
        request,
        field_path="filters.access",
    )

    scoped_filters = apply_access_scope(
        request_body.filters,
        identity,
    )

    try:
        result = await service.asearch(
            query=request_body.query,
            filters=scoped_filters,
            page=request_body.page,
            page_size=request_body.page_size,
        )

    except M2QueryValidationError as exc:
        _log_raw_rag_failure(request=request, exc=exc,
                             failure_stage="query_processing")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The search query is invalid.",
        ) from exc

    except M2EmbeddingContractError as exc:
        _log_raw_rag_failure(request=request, exc=exc,
                             failure_stage="embedding_validation")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "The local embedding runtime produced an invalid "
                "query embedding."
            ),
        ) from exc

    except (M2QueryRuntimeError, RerankerUnavailable) as exc:
        _log_raw_rag_failure(request=request, exc=exc,
                             failure_stage="retrieval_runtime")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The local search runtime is currently unavailable.",
        ) from exc

    except ValueError as exc:
        _log_raw_rag_failure(request=request, exc=exc,
                             failure_stage="retrieval")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The search query is invalid for retrieval.",
        ) from exc

    logger.info(
        "rag_search_completed",
        extra={
            "request_id": _get_request_id(request),
            "query_id": result.query_id,
            "retrieval_ms": round(result.retrieval_ms, 2),
            "candidate_chunk_count": result.candidate_chunk_count,
            "document_count": result.total,
            "page": result.page,
            "status": "success",
        },
    )

    return RAGSearchResponse(
        query_id=result.query_id,
        hits=[
            RAGSearchHit(
                document_id=hit.document_id,
                score=hit.score,
                snippet=hit.snippet,
                chunk_id=hit.chunk_id,
                page=hit.page,
                section=hit.section,
                matched_chunks=hit.matched_chunks,
            )
            for hit in result.hits
        ],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.post(
    "/answer",
    response_model=AIResponse,
)
async def answer_rag(
    request_body: RAGAnswerRequest,
    request: Request,
    service: RAGServiceDependency,
    identity: CallerIdentityDependency,
) -> AIResponse:
    """
    Execute M3 retrieval followed by grounded
    M4 local-LLM answer generation.

    The access scope is overwritten from the authenticated caller, and a
    client-supplied one is refused, exactly as on /ask.

    FLAG FOR M4 OWNER -- not an access-control issue, and deliberately not
    addressed here: this endpoint accepts a fully client-constructed
    ProcessedQuery, including its embedding vector and normalized text. ACL
    filtering constrains *which documents* the search may return, but it
    cannot constrain a caller who chooses the query vector itself: such a
    caller can probe the vector space of their own tenant freely, and the
    embedding never has to correspond to the text shown to the user. That is
    an argument for making this endpoint internal-only regardless of access
    control. Raised for M4 to decide; M3 has not changed the behaviour.
    """

    reject_client_supplied_access(
        request_body.processed_query.filters,
        request,
        field_path=(
            "processed_query.filters.access"
        ),
    )

    scoped_query = (
        request_body
        .processed_query
        .model_copy(
            update={
                "filters": apply_access_scope(
                    request_body
                    .processed_query
                    .filters,
                    identity,
                )
            }
        )
    )

    try:
        result = (
            await service
            .aanswer_with_metrics(
                scoped_query
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
