import pytest

from src.orchestration import (
    M3M4RAGService,
    RAGExecutionResult,
)
from src.schemas import (
    AIResponse,
    Citation,
    EvidenceItem,
    RetrievedEvidence,
)
from src.schemas.m2_contract import (
    ProcessedQuery,
    QueryFilters,
)


def make_query() -> ProcessedQuery:
    return ProcessedQuery(
        query_id="query_001",
        text_original="What notice is required?",
        normalized_text="what notice is required",
        language="en",
        embedding=[0.1, 0.2, 0.3],
        sparse_embedding=None,
        filters=QueryFilters(),
    )


class FakeRetrievalPipeline:
    def __init__(self):
        self.run_calls = 0

    def run(self, query):
        self.run_calls += 1

        return (
            RetrievedEvidence(
                query_id=query.query_id,
                retrieved_evidence=[
                    EvidenceItem(
                        document_id="doc_001",
                        chunk_id="chunk_001",
                        text=(
                            "Thirty days' written notice "
                            "is required."
                        ),
                        page=12,
                        section="Termination",
                        language="en",
                        score=0.97,
                    )
                ],
            ),
            12.5,
        )


class FakeOrchestrationService:
    def __init__(self):
        self.sync_calls = 0
        self.async_calls = 0
        self.last_query = None
        self.last_evidence = None

    def answer_search(
        self,
        *,
        processed_query,
        retrieved_evidence,
    ):
        self.sync_calls += 1
        self.last_query = processed_query
        self.last_evidence = retrieved_evidence

        return AIResponse(
            query_id=processed_query.query_id,
            answer="Thirty days' written notice is required.",
            citations=[
                Citation(
                    evidence_id="E1",
                    document_id="doc_001",
                    chunk_id="chunk_001",
                    page=12,
                    section="Termination",
                )
            ],
            confidence=0.95,
        )

    async def aanswer_search(
        self,
        *,
        processed_query,
        retrieved_evidence,
    ):
        self.async_calls += 1
        self.last_query = processed_query
        self.last_evidence = retrieved_evidence

        return AIResponse(
            query_id=processed_query.query_id,
            answer="Thirty days' written notice is required.",
            citations=[
                Citation(
                    evidence_id="E1",
                    document_id="doc_001",
                    chunk_id="chunk_001",
                    page=12,
                    section="Termination",
                )
            ],
            confidence=0.95,
        )
        
def test_m3_output_is_passed_to_m4():
    retrieval = FakeRetrievalPipeline()
    orchestration = FakeOrchestrationService()

    service = M3M4RAGService(
        retrieval_pipeline=retrieval,
        orchestration_service=orchestration,
    )

    query = make_query()

    result = service.answer(query)

    assert isinstance(result, AIResponse)
    assert result.query_id == query.query_id

    assert retrieval.run_calls == 1
    assert orchestration.sync_calls == 1

    assert orchestration.last_query is query

    assert (
        orchestration
        .last_evidence
        .retrieved_evidence[0]
        .document_id
        == "doc_001"
    )
    
def test_sync_rag_execution_metrics():
    retrieval = FakeRetrievalPipeline()
    orchestration = FakeOrchestrationService()

    service = M3M4RAGService(
        retrieval_pipeline=retrieval,
        orchestration_service=orchestration,
    )

    query = make_query()

    result = service.answer_with_metrics(
        query
    )

    assert isinstance(
        result,
        RAGExecutionResult,
    )

    assert result.response.query_id == (
        query.query_id
    )

    assert (
        result.metrics.retrieval_ms
        == 12.5
    )

    assert (
        result.metrics.generation_ms
        >= 0
    )

    assert (
        result.metrics.total_rag_ms
        >= result.metrics.generation_ms
    )

    assert (
        result.metrics
        .retrieved_chunk_count
        == 1
    )

    assert (
        result.metrics.citation_count
        == 1
    )

    assert retrieval.run_calls == 1
    assert orchestration.sync_calls == 1


@pytest.mark.asyncio
async def test_async_rag_execution_metrics():
    retrieval = FakeRetrievalPipeline()
    orchestration = FakeOrchestrationService()

    service = M3M4RAGService(
        retrieval_pipeline=retrieval,
        orchestration_service=orchestration,
    )

    query = make_query()

    result = (
        await service
        .aanswer_with_metrics(
            query
        )
    )

    assert isinstance(
        result,
        RAGExecutionResult,
    )

    assert result.response.query_id == (
        query.query_id
    )

    assert (
        result.metrics.retrieval_ms
        == 12.5
    )

    assert (
        result.metrics.generation_ms
        >= 0
    )

    assert (
        result.metrics.total_rag_ms
        >= result.metrics.generation_ms
    )

    assert (
        result.metrics
        .retrieved_chunk_count
        == 1
    )

    assert (
        result.metrics.citation_count
        == 1
    )

    assert retrieval.run_calls == 1
    assert orchestration.async_calls == 1
    
@pytest.mark.asyncio
async def test_async_m3_output_is_passed_to_m4():
    retrieval = FakeRetrievalPipeline()
    orchestration = FakeOrchestrationService()

    service = M3M4RAGService(
        retrieval_pipeline=retrieval,
        orchestration_service=orchestration,
    )

    query = make_query()

    result = await service.aanswer(query)

    assert isinstance(result, AIResponse)

    assert retrieval.run_calls == 1
    assert orchestration.async_calls == 1
