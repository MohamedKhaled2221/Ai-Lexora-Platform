import asyncio
from dataclasses import dataclass
from typing import Protocol

from src.retrieval.document_search import (
    DocumentSearchHit,
    group_by_document,
)

from src.orchestration.rag_service import (
    M3M4RAGService,
    RAGExecutionResult,
)
from src.schemas.access_control import AccessScopeRequired
from src.schemas.m2_contract import (
    EmbeddedQuery,
    ProcessedQuery,
    QueryFilters,
)
from src.schemas.m4_contract import (
    AIResponse,
)


class M2QueryPipelineProtocol(Protocol):
    """
    Minimal M2 interface required by the M4
    composition layer.
    """

    def process(
        self,
        raw_query: str,
    ) -> EmbeddedQuery:
        ...


class M2QueryValidationError(ValueError):
    """
    Raised when M2 rejects the raw user query.
    """


class M2EmbeddingContractError(ValueError):
    """
    Raised when M2 returns an embedding that violates
    the M2 -> M3 shared contract.
    """


class M2QueryRuntimeError(RuntimeError):
    """
    Raised when the local M2 query runtime fails
    unexpectedly.
    """


MAX_SEARCH_CANDIDATES = 100
"""Upper bound on chunks ranked for one search page request."""


@dataclass(frozen=True)
class DocumentSearchResult:
    query_id: str
    hits: list[DocumentSearchHit]
    total: int
    page: int
    page_size: int
    retrieval_ms: float
    candidate_chunk_count: int


class M2M3M4RAGService:
    """
    Compose the raw-query M2 pipeline with the existing
    M3 -> M4 RAG service.

    Flow:
        raw question + filters
            -> M2QueryPipeline
            -> EmbeddedQuery
            -> validate/copy embedding
            -> ProcessedQuery
            -> M3M4RAGService
            -> AIResponse

    M2 remains responsible for:
        - normalization
        - language detection
        - identifier extraction
        - BGE-M3 embedding

    M3 remains responsible for retrieval.

    M4 remains responsible for grounded answer
    generation and citation validation.
    """

    def __init__(
        self,
        *,
        query_pipeline: M2QueryPipelineProtocol,
        rag_service: M3M4RAGService,
        expected_embedding_dimension: int = 1024,
        validated_embedding_dimension: int | None = None,
    ) -> None:
        if expected_embedding_dimension < 1:
            raise ValueError(
                "expected_embedding_dimension "
                "must be positive"
            )

        if (
            validated_embedding_dimension
            is not None
            and validated_embedding_dimension
            != expected_embedding_dimension
        ):
            raise ValueError(
                "validated_embedding_dimension "
                "must match "
                "expected_embedding_dimension"
            )

        self.query_pipeline = (
            query_pipeline
        )

        self.rag_service = (
            rag_service
        )

        self.expected_embedding_dimension = (
            expected_embedding_dimension
        )

        self.validated_embedding_dimension = (
            validated_embedding_dimension
        )
        if expected_embedding_dimension < 1:
            raise ValueError(
                "expected_embedding_dimension "
                "must be positive"
            )

        self.query_pipeline = (
            query_pipeline
        )

        self.rag_service = (
            rag_service
        )

        self.expected_embedding_dimension = (
            expected_embedding_dimension
        )
    @property
    def embedding_runtime_ready(
        self,
    ) -> bool:
        return (
            self.validated_embedding_dimension
            == self.expected_embedding_dimension
        )

    def answer(
        self,
        *,
        question: str,
        filters: QueryFilters | None = None,
    ) -> AIResponse:
        result = self.answer_with_metrics(
            question=question,
            filters=filters,
        )

        return result.response

    def answer_with_metrics(
        self,
        *,
        question: str,
        filters: QueryFilters | None = None,
    ) -> RAGExecutionResult:
        processed_query = (
            self._prepare_processed_query(
                question=question,
                filters=filters,
            )
        )

        return (
            self.rag_service
            .answer_with_metrics(
                processed_query
            )
        )

    async def aanswer(
        self,
        *,
        question: str,
        filters: QueryFilters | None = None,
    ) -> AIResponse:
        result = (
            await self.aanswer_with_metrics(
                question=question,
                filters=filters,
            )
        )

        return result.response

    async def aanswer_with_metrics(
        self,
        *,
        question: str,
        filters: QueryFilters | None = None,
    ) -> RAGExecutionResult:
        processed_query = await asyncio.to_thread(
            self._prepare_processed_query,
            question=question,
            filters=filters,
        )

        return await (
            self.rag_service
            .aanswer_with_metrics(
                processed_query
            )
        )

    def search(
        self,
        *,
        query: str,
        filters: QueryFilters | None = None,
        page: int = 1,
        page_size: int = 10,
    ) -> DocumentSearchResult:
        """
        Ranked documents for a search page: M2 -> M3 retrieval only, no LLM.

        The candidate window grows with the requested page so later pages
        have documents to show, capped at MAX_SEARCH_CANDIDATES chunks. The
        total therefore counts documents found within that window, not every
        document that mentions the query.
        """
        if page < 1 or page_size < 1:
            raise ValueError("page and page_size must be positive")

        processed_query = self._prepare_processed_query(
            question=query,
            filters=filters,
        )

        retrieval = self.rag_service.retrieval_pipeline
        window = min(
            MAX_SEARCH_CANDIDATES,
            max(
                retrieval.candidate_top_k,
                page * page_size * 3,
            ),
        )

        chunks, retrieval_ms = retrieval.search_candidates(
            processed_query,
            candidate_top_k=window,
        )

        documents = group_by_document(chunks)
        start = (page - 1) * page_size

        return DocumentSearchResult(
            query_id=processed_query.query_id,
            hits=documents[start:start + page_size],
            total=len(documents),
            page=page,
            page_size=page_size,
            retrieval_ms=retrieval_ms,
            candidate_chunk_count=len(chunks),
        )

    async def asearch(
        self,
        **kwargs,
    ) -> DocumentSearchResult:
        # Embedding and retrieval are both blocking model/database calls.
        return await asyncio.to_thread(
            self.search,
            **kwargs,
        )

    def _prepare_processed_query(
        self,
        *,
        question: str,
        filters: QueryFilters | None,
    ) -> ProcessedQuery:
        # Checked first, before any embedding work: an unscoped request can
        # never succeed, so paying for an embedding to discover that wastes
        # the local model's time and reports the failure several layers away
        # from the caller who can fix it.
        if filters is None or filters.access is None:
            raise AccessScopeRequired(
                "answer()/aanswer() require QueryFilters carrying an access "
                "scope. The API layer sets it from the authenticated caller; "
                "a direct caller must supply one explicitly."
            )

        try:
            embedded_query = (
                self.query_pipeline.process(
                    question
                )
            )

        except ValueError as exc:
            raise M2QueryValidationError(
                "M2 rejected the raw query."
            ) from exc

        except Exception as exc:
            raise M2QueryRuntimeError(
                "The local M2 query runtime failed."
            ) from exc

        self._validate_embedding(
            embedded_query
        )

        effective_filters = filters

        return (
            embedded_query
            .processed_query
            .model_copy(
                update={
                    "embedding": list(
                        embedded_query.embedding
                    ),
                    "filters": (
                        effective_filters
                        .model_copy(
                            deep=True
                        )
                    ),
                },
                deep=True,
            )
        )

    def _validate_embedding(
        self,
        embedded_query: EmbeddedQuery,
    ) -> None:
        vector_length = len(
            embedded_query.embedding
        )

        if vector_length == 0:
            raise M2EmbeddingContractError(
                "M2 returned an empty embedding."
            )

        if (
            embedded_query.dimension
            != vector_length
        ):
            raise M2EmbeddingContractError(
                "M2 embedding dimension metadata "
                "does not match the vector length."
            )

        if (
            vector_length
            != self.expected_embedding_dimension
        ):
            raise M2EmbeddingContractError(
                "M2 returned an embedding with "
                "an unexpected dimension."
            )
