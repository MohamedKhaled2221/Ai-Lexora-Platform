import pytest
from pydantic import ValidationError

from src.schemas import (
    AIResponse,
    Citation,
    EvidenceItem,
    M4ModelOutput,
    RetrievedEvidence,
)


def test_existing_retrieved_evidence_contract():
    evidence = EvidenceItem(
        document_id="doc_001",
        chunk_id="chunk_017",
        text="Termination may occur upon written notice.",
        page=12,
        section="Termination",
        language="en",
        score=0.91,
    )

    result = RetrievedEvidence(
        query_id="query_001",
        retrieved_evidence=[evidence],
    )

    assert result.query_id == "query_001"
    assert len(result.retrieved_evidence) == 1


def test_valid_m4_model_output():
    output = M4ModelOutput(
        answer="The agreement may be terminated upon written notice.",
        citation_ids=["E1", "E2"],
        confidence=0.91,
    )

    assert output.citation_ids == ["E1", "E2"]
    assert output.confidence == 0.91


@pytest.mark.parametrize(
    "citation_id",
    [
        "E0",
        "E01",
        "e1",
        "doc_001",
        "E1-page12",
        "",
    ],
)
def test_invalid_citation_aliases_are_rejected(citation_id):
    with pytest.raises(ValidationError):
        M4ModelOutput(
            answer="Test answer",
            citation_ids=[citation_id],
            confidence=0.5,
        )


def test_duplicate_model_citations_are_rejected():
    with pytest.raises(ValidationError):
        M4ModelOutput(
            answer="Test answer",
            citation_ids=["E1", "E1"],
            confidence=0.5,
        )


def test_llm_cannot_add_citation_metadata():
    with pytest.raises(ValidationError):
        M4ModelOutput(
            answer="Test answer",
            citation_ids=["E1"],
            confidence=0.8,
            document_id="fake_document",
        )


def test_empty_citations_are_allowed():
    output = M4ModelOutput(
        answer="The retrieved evidence is insufficient to answer the question.",
        citation_ids=[],
        confidence=0.0,
    )

    assert output.citation_ids == []


def test_valid_trusted_citation():
    citation = Citation(
        evidence_id="E1",
        document_id="doc_001",
        chunk_id="chunk_017",
        page=12,
        section="Termination",
    )

    assert citation.evidence_id == "E1"
    assert citation.document_id == "doc_001"


def test_valid_ai_response():
    citation = Citation(
        evidence_id="E1",
        document_id="doc_001",
        chunk_id="chunk_017",
        page=12,
        section="Termination",
    )

    response = AIResponse(
        query_id="query_001",
        answer="The agreement may be terminated upon written notice.",
        citations=[citation],
        confidence=0.91,
    )

    assert response.query_id == "query_001"
    assert len(response.citations) == 1


def test_duplicate_final_citations_are_rejected():
    citation_1 = Citation(
        evidence_id="E1",
        document_id="doc_001",
        chunk_id="chunk_017",
        page=12,
    )

    citation_2 = Citation(
        evidence_id="E1",
        document_id="doc_001",
        chunk_id="chunk_017",
        page=12,
    )

    with pytest.raises(ValidationError):
        AIResponse(
            query_id="query_001",
            answer="Test answer",
            citations=[citation_1, citation_2],
            confidence=0.8,
        )


@pytest.mark.parametrize("confidence", [-0.01, 1.01])
def test_invalid_confidence_is_rejected(confidence):
    with pytest.raises(ValidationError):
        M4ModelOutput(
            answer="Test answer",
            citation_ids=[],
            confidence=confidence,
        )
