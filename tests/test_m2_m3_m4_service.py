import pytest

from src.orchestration import (
    M2EmbeddingContractError,
    M2M3M4RAGService,
    M2QueryRuntimeError,
    M2QueryValidationError,
    RAGExecutionMetrics,
    RAGExecutionResult,
)
from src.schemas import (
    AIResponse,
    EmbeddedQuery,
    ProcessedQuery,
    QueryFilters,
)


class FakeM2QueryPipeline:
    def __init__(
        self,
        *,
        embedding_dimension: int = 1024,
        declared_dimension: int | None = None,
        error: Exception | None = None,
    ) -> None:
        self.embedding_dimension = (
            embedding_dimension
        )

        self.declared_dimension = (
            declared_dimension
            if declared_dimension is not None
            else embedding_dimension
        )

        self.error = error

        self.calls = 0
        self.last_question = None
        self.last_result = None

    def process(
        self,
        raw_query: str,
    ) -> EmbeddedQuery:
        self.calls += 1
        self.last_question = raw_query

        if self.error is not None:
            raise self.error

        processed_query = ProcessedQuery(
            query_id="q_test001",
            text_original=raw_query,
            normalized_text=(
                raw_query.lower()
            ),
            language="ar-en",
            embedding=[],
            filters=QueryFilters(),
        )

        embedding = [
            0.1
            for _ in range(
                self.embedding_dimension
            )
        ]

        self.last_result = EmbeddedQuery(
            processed_query=processed_query,
            embedding=embedding,
            model="BAAI/bge-m3",
            dimension=(
                self.declared_dimension
            ),
        )

        return self.last_result


class FakeRAGService:
    def __init__(
        self,
    ) -> None:
        self.sync_calls = 0
        self.async_calls = 0
        self.last_query = None

    def answer_with_metrics(
        self,
        processed_query,
    ) -> RAGExecutionResult:
        self.sync_calls += 1
        self.last_query = processed_query

        return self._result(
            processed_query
        )

    async def aanswer_with_metrics(
        self,
        processed_query,
    ) -> RAGExecutionResult:
        self.async_calls += 1
        self.last_query = processed_query

        return self._result(
            processed_query
        )

    @staticmethod
    def _result(
        processed_query,
    ) -> RAGExecutionResult:
        return RAGExecutionResult(
            response=AIResponse(
                query_id=(
                    processed_query.query_id
                ),
                answer="Grounded answer.",
                citations=[],
                confidence=0.8,
            ),
            metrics=RAGExecutionMetrics(
                retrieval_ms=10.0,
                generation_ms=20.0,
                total_rag_ms=31.0,
                retrieved_chunk_count=2,
                citation_count=0,
            ),
        )


def test_sync_composition_copies_embedding_and_filters():
    m2 = FakeM2QueryPipeline()
    rag = FakeRAGService()

    service = M2M3M4RAGService(
        query_pipeline=m2,
        rag_service=rag,
        expected_embedding_dimension=1024,
    )

    filters = QueryFilters(
        document_type="contract",
        jurisdiction="Egypt",
    )

    result = service.answer_with_metrics(
        question="Termination Article 69",
        filters=filters,
    )

    assert (
        result.response.query_id
        == "q_test001"
    )

    assert m2.calls == 1
    assert rag.sync_calls == 1

    assert len(
        rag.last_query.embedding
    ) == 1024

    assert (
        rag.last_query
        .filters
        .document_type
        == "contract"
    )

    assert (
        rag.last_query
        .filters
        .jurisdiction
        == "Egypt"
    )

    assert (
        rag.last_query.language
        == "ar-en"
    )

    assert (
        rag.last_query
        .filters
        .language
        is None
    )

    # Composition must not mutate M2's nested object.
    assert (
        m2.last_result
        .processed_query
        .embedding
        == []
    )
def test_embedding_runtime_ready_after_validated_startup():
    service = M2M3M4RAGService(
        query_pipeline=(
            FakeM2QueryPipeline()
        ),
        rag_service=FakeRAGService(),
        expected_embedding_dimension=1024,
        validated_embedding_dimension=1024,
    )

    assert (
        service.embedding_runtime_ready
        is True
    )


def test_embedding_runtime_not_ready_without_startup_validation():
    service = M2M3M4RAGService(
        query_pipeline=(
            FakeM2QueryPipeline()
        ),
        rag_service=FakeRAGService(),
        expected_embedding_dimension=1024,
    )

    assert (
        service.embedding_runtime_ready
        is False
    )


def test_invalid_validated_startup_dimension_is_rejected():
    with pytest.raises(
        ValueError,
        match=(
            "validated_embedding_dimension"
        ),
    ):
        M2M3M4RAGService(
            query_pipeline=(
                FakeM2QueryPipeline()
            ),
            rag_service=FakeRAGService(),
            expected_embedding_dimension=1024,
            validated_embedding_dimension=768,
        )

@pytest.mark.asyncio
async def test_async_composition_uses_existing_rag_service():
    m2 = FakeM2QueryPipeline()
    rag = FakeRAGService()

    service = M2M3M4RAGService(
        query_pipeline=m2,
        rag_service=rag,
    )

    result = (
        await service
        .aanswer_with_metrics(
            question=(
                "ما هي شروط termination؟"
            ),
            filters=QueryFilters(),
        )
    )

    assert (
        result.response.query_id
        == "q_test001"
    )

    assert m2.calls == 1
    assert rag.async_calls == 1

    assert len(
        rag.last_query.embedding
    ) == 1024


def test_wrong_embedding_dimension_is_rejected_before_rag():
    m2 = FakeM2QueryPipeline(
        embedding_dimension=768
    )

    rag = FakeRAGService()

    service = M2M3M4RAGService(
        query_pipeline=m2,
        rag_service=rag,
        expected_embedding_dimension=1024,
    )

    with pytest.raises(
        M2EmbeddingContractError
    ):
        service.answer_with_metrics(
            question="test",
        )

    assert rag.sync_calls == 0


def test_declared_dimension_must_match_vector_length():
    m2 = FakeM2QueryPipeline(
        embedding_dimension=1024,
        declared_dimension=768,
    )

    rag = FakeRAGService()

    service = M2M3M4RAGService(
        query_pipeline=m2,
        rag_service=rag,
    )

    with pytest.raises(
        M2EmbeddingContractError
    ):
        service.answer_with_metrics(
            question="test",
        )

    assert rag.sync_calls == 0


def test_m2_value_error_is_translated():
    service = M2M3M4RAGService(
        query_pipeline=(
            FakeM2QueryPipeline(
                error=ValueError(
                    "query must not be empty"
                )
            )
        ),
        rag_service=FakeRAGService(),
    )

    with pytest.raises(
        M2QueryValidationError
    ):
        service.answer_with_metrics(
            question="invalid",
        )


def test_unexpected_m2_error_is_sanitized():
    service = M2M3M4RAGService(
        query_pipeline=(
            FakeM2QueryPipeline(
                error=RuntimeError(
                    "secret embedding diagnostic"
                )
            )
        ),
        rag_service=FakeRAGService(),
    )

    with pytest.raises(
        M2QueryRuntimeError,
        match=(
            "local M2 query runtime failed"
        ),
    ):
        service.answer_with_metrics(
            question="test",
        )
