import pytest

from src.orchestration.citation_validator import (
    CitationValidationError,
    CitationValidator,
)
from src.schemas import EvidenceItem, M4ModelOutput


def make_evidence(
    *,
    document_id: str,
    chunk_id: str,
    page: int | None = None,
    section: str | None = None,
) -> EvidenceItem:
    return EvidenceItem(
        document_id=document_id,
        chunk_id=chunk_id,
        text="Example legal evidence.",
        page=page,
        section=section,
        language="en",
        score=0.95,
    )


def make_evidence_map() -> dict[str, EvidenceItem]:
    return {
        "E1": make_evidence(
            document_id="doc_001",
            chunk_id="chunk_001",
            page=10,
            section="Termination",
        ),
        "E2": make_evidence(
            document_id="doc_002",
            chunk_id="chunk_002",
            page=20,
            section="Payment",
        ),
        "E3": make_evidence(
            document_id="doc_003",
            chunk_id="chunk_003",
            page=None,
            section=None,
        ),
    }


def test_valid_citations_are_resolved_to_trusted_metadata():
    validator = CitationValidator()

    evidence_by_id = make_evidence_map()

    output = M4ModelOutput(
        answer=(
            "Termination requires written notice [E1]. "
            "Payment obligations are described separately [E2]."
        ),
        citation_ids=["E1", "E2"],
        confidence=0.9,
    )

    citations = validator.validate(
        model_output=output,
        evidence_by_id=evidence_by_id,
    )

    assert len(citations) == 2

    assert citations[0].evidence_id == "E1"
    assert citations[0].document_id == "doc_001"
    assert citations[0].chunk_id == "chunk_001"
    assert citations[0].page == 10
    assert citations[0].section == "Termination"

    assert citations[1].evidence_id == "E2"
    assert citations[1].document_id == "doc_002"


def test_repeated_inline_citation_is_allowed():
    validator = CitationValidator()

    output = M4ModelOutput(
        answer=(
            "Written notice is required [E1]. "
            "The same clause specifies the notice period [E1]."
        ),
        citation_ids=["E1"],
        confidence=0.8,
    )

    citations = validator.validate(
        model_output=output,
        evidence_by_id=make_evidence_map(),
    )

    assert len(citations) == 1
    assert citations[0].evidence_id == "E1"


def test_multiple_structured_citations_are_resolved_in_declared_order():
    validator = CitationValidator()

    output = M4ModelOutput(
        answer=(
            "Payment and termination provisions both apply."
        ),
        citation_ids=["E2", "E1"],
        confidence=0.8,
    )

    citations = validator.validate(
        model_output=output,
        evidence_by_id=make_evidence_map(),
    )

    assert [
        citation.evidence_id
        for citation in citations
    ] == ["E2", "E1"]

def test_unknown_declared_citation_is_rejected():
    validator = CitationValidator()

    output = M4ModelOutput(
        answer="The contract contains another rule [E9].",
        citation_ids=["E9"],
        confidence=0.5,
    )

    with pytest.raises(
        CitationValidationError,
        match="not supplied",
    ):
        validator.validate(
            model_output=output,
            evidence_by_id=make_evidence_map(),
        )


def test_unknown_inline_citation_is_rejected():
    validator = CitationValidator()

    output = M4ModelOutput(
        answer=(
            "Termination requires notice [E1]. "
            "Another rule applies [E9]."
        ),
        citation_ids=["E1"],
        confidence=0.5,
    )

    with pytest.raises(
        CitationValidationError,
        match="not supplied",
    ):
        validator.validate(
            model_output=output,
            evidence_by_id=make_evidence_map(),
        )


def test_inline_citation_missing_from_citation_ids_is_rejected():
    validator = CitationValidator()

    output = M4ModelOutput(
        answer="Termination requires notice [E1].",
        citation_ids=[],
        confidence=0.5,
    )

    with pytest.raises(
        CitationValidationError,
        match="missing from citation_ids",
    ):
        validator.validate(
            model_output=output,
            evidence_by_id=make_evidence_map(),
        )


def test_structured_citation_without_inline_marker_is_allowed():
    validator = CitationValidator()

    output = M4ModelOutput(
        answer="Termination requires written notice.",
        citation_ids=["E1"],
        confidence=0.9,
    )

    citations = validator.validate(
        model_output=output,
        evidence_by_id=make_evidence_map(),
    )

    assert len(citations) == 1
    assert citations[0].evidence_id == "E1"
    assert citations[0].document_id == "doc_001"

@pytest.mark.parametrize(
    "malformed_marker",
    [
        "[E0]",
        "[E01]",
        "[e1]",
        "[E1-page12]",
    ],
)
def test_malformed_inline_citations_are_rejected(
    malformed_marker,
):
    validator = CitationValidator()

    output = M4ModelOutput(
        answer=f"Example answer {malformed_marker}.",
        citation_ids=[],
        confidence=0.4,
    )

    with pytest.raises(
        CitationValidationError,
        match="Malformed citation marker",
    ):
        validator.validate(
            model_output=output,
            evidence_by_id=make_evidence_map(),
        )


def test_no_citations_are_valid_for_insufficient_evidence():
    validator = CitationValidator()

    output = M4ModelOutput(
        answer=(
            "The retrieved evidence is insufficient "
            "to answer the question."
        ),
        citation_ids=[],
        confidence=0.0,
    )

    citations = validator.validate(
        model_output=output,
        evidence_by_id={},
    )

    assert citations == []


def test_empty_evidence_cannot_be_cited():
    validator = CitationValidator()

    output = M4ModelOutput(
        answer="The contract requires notice [E1].",
        citation_ids=["E1"],
        confidence=0.7,
    )

    with pytest.raises(
        CitationValidationError,
        match="not supplied",
    ):
        validator.validate(
            model_output=output,
            evidence_by_id={},
        )


def test_optional_source_metadata_is_preserved():
    validator = CitationValidator()

    evidence_by_id = {
        "E1": make_evidence(
            document_id="doc_001",
            chunk_id="chunk_001",
            page=None,
            section=None,
        )
    }

    output = M4ModelOutput(
        answer="The source supports the statement [E1].",
        citation_ids=["E1"],
        confidence=0.8,
    )

    citations = validator.validate(
        model_output=output,
        evidence_by_id=evidence_by_id,
    )

    assert citations[0].page is None
    assert citations[0].section is None


def test_invalid_trusted_alias_is_rejected():
    validator = CitationValidator()

    evidence_by_id = {
        "source_one": make_evidence(
            document_id="doc_001",
            chunk_id="chunk_001",
        )
    }

    output = M4ModelOutput(
        answer="Insufficient evidence.",
        citation_ids=[],
        confidence=0.0,
    )

    with pytest.raises(
        CitationValidationError,
        match="Invalid trusted evidence alias",
    ):
        validator.validate(
            model_output=output,
            evidence_by_id=evidence_by_id,
        )
