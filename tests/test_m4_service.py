import pytest

from src.orchestration import (
    M4OrchestrationService,
    M4Settings,
)
from src.schemas import (
    EvidenceItem,
    M4ModelOutput,
    RetrievedEvidence,
)
from src.schemas.m2_contract import (
    ProcessedQuery,
    QueryFilters,
)

def make_query(
    *,
    query_id: str = "query_001",
    language: str = "en",
) -> ProcessedQuery:
    return ProcessedQuery(
        query_id=query_id,
        text_original="What notice is required?",
        normalized_text="what notice is required",
        language=language,
        embedding=[0.1, 0.2, 0.3],
        sparse_embedding=None,
        filters=QueryFilters(),
    )


def make_retrieved(
    *,
    query_id: str = "query_001",
) -> RetrievedEvidence:
    return RetrievedEvidence(
        query_id=query_id,
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
    )
    
class FakeLLMService:
    def __init__(self):
        self.invoke_calls = 0
        self.ainvoke_calls = 0

    def invoke(self, messages):
        self.invoke_calls += 1

        return M4ModelOutput(
            answer=(
                "Thirty days' written notice "
                "is required."
            ),
            citation_ids=["E1"],
            confidence=0.95,
        )

    async def ainvoke(self, messages):
        self.ainvoke_calls += 1

        return M4ModelOutput(
            answer=(
                "Thirty days' written notice "
                "is required."
            ),
            citation_ids=["E1"],
            confidence=0.95,
        )
        
def test_answer_search_returns_ai_response():
    fake_llm = FakeLLMService()

    service = M4OrchestrationService(
        settings=M4Settings(
            _env_file=None
        ),
        llm_service=fake_llm,
    )

    result = service.answer_search(
        processed_query=make_query(),
        retrieved_evidence=make_retrieved(),
    )

    assert result.query_id == "query_001"

    assert (
        result.answer
        == "Thirty days' written notice is required."
    )

    assert result.confidence == 0.95

    assert len(result.citations) == 1

    citation = result.citations[0]

    assert citation.evidence_id == "E1"
    assert citation.document_id == "doc_001"
    assert citation.chunk_id == "chunk_001"
    assert citation.page == 12
    assert citation.section == "Termination"

    assert fake_llm.invoke_calls == 1
    
@pytest.mark.asyncio
async def test_async_answer_search_returns_ai_response():
    fake_llm = FakeLLMService()

    service = M4OrchestrationService(
        settings=M4Settings(
            _env_file=None
        ),
        llm_service=fake_llm,
    )

    result = await service.aanswer_search(
        processed_query=make_query(),
        retrieved_evidence=make_retrieved(),
    )

    assert result.query_id == "query_001"
    assert len(result.citations) == 1
    assert result.citations[0].evidence_id == "E1"

    assert fake_llm.ainvoke_calls == 1
    
def test_empty_evidence_skips_llm():
    fake_llm = FakeLLMService()

    service = M4OrchestrationService(
        settings=M4Settings(
            _env_file=None
        ),
        llm_service=fake_llm,
    )

    query = make_query()

    retrieved = RetrievedEvidence(
        query_id=query.query_id,
        retrieved_evidence=[],
    )

    result = service.answer_search(
        processed_query=query,
        retrieved_evidence=retrieved,
    )

    assert result.confidence == 0.0
    assert result.citations == []

    assert (
        result.answer
        == "The retrieved evidence is insufficient "
        "to answer the question."
    )

    assert fake_llm.invoke_calls == 0
    
def test_empty_arabic_evidence_returns_arabic_response():
    fake_llm = FakeLLMService()

    service = M4OrchestrationService(
        settings=M4Settings(
            _env_file=None
        ),
        llm_service=fake_llm,
    )

    query = make_query(
        language="ar"
    )

    retrieved = RetrievedEvidence(
        query_id=query.query_id,
        retrieved_evidence=[],
    )

    result = service.answer_search(
        processed_query=query,
        retrieved_evidence=retrieved,
    )

    assert (
        result.answer
        == "الأدلة المسترجعة غير كافية للإجابة عن هذا السؤال."
    )

    assert result.citations == []
    assert result.confidence == 0.0
    assert fake_llm.invoke_calls == 0
    
def test_query_id_mismatch_is_rejected_before_llm():
    fake_llm = FakeLLMService()

    service = M4OrchestrationService(
        settings=M4Settings(
            _env_file=None
        ),
        llm_service=fake_llm,
    )

    with pytest.raises(
        ValueError,
        match="same query_id",
    ):
        service.answer_search(
            processed_query=make_query(
                query_id="query_A"
            ),
            retrieved_evidence=make_retrieved(
                query_id="query_B"
            ),
        )

    assert fake_llm.invoke_calls == 0
    
def test_empty_mixed_evidence_returns_bilingual_response():
    fake_llm = FakeLLMService()

    service = M4OrchestrationService(
        settings=M4Settings(
            _env_file=None
        ),
        llm_service=fake_llm,
    )

    query = make_query(
        language="mixed"
    )

    retrieved = RetrievedEvidence(
        query_id=query.query_id,
        retrieved_evidence=[],
    )

    result = service.answer_search(
        processed_query=query,
        retrieved_evidence=retrieved,
    )

    assert "الأدلة المسترجعة غير كافية" in result.answer
    assert (
        "The retrieved evidence is insufficient"
        in result.answer
    )

    assert fake_llm.invoke_calls == 0