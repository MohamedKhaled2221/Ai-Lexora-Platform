import asyncio
from typing import Protocol

from src.orchestration.rag_service import (
    M3M4RAGService,
    RAGExecutionResult,
)
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

    def _prepare_processed_query(
        self,
        *,
        question: str,
        filters: QueryFilters | None,
    ) -> ProcessedQuery:
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

        effective_filters = (
            filters
            if filters is not None
            else QueryFilters()
        )

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
