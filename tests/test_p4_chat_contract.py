import pytest
from pydantic import ValidationError

from src.schemas.m4_contract import (
    Citation,
    EvidenceItem,
    RetrievedEvidence,
)
from src.schemas.p4_chat_contract import (
    AnswerGenerationRequest,
    ResponseLanguage,
    SafeContextTurn,
    ValidatedAIResponse,
    P4GroundedModelOutput,
)

def test_p4_grounded_model_output_requires_citation():
    with pytest.raises(ValidationError):
        P4GroundedModelOutput(
            answer="تسعين يومًا",
            citation_ids=[],
            confidence=1.0,
        )


def test_p4_grounded_model_output_accepts_trusted_alias():
    output = P4GroundedModelOutput(
        answer="تسعين يومًا",
        citation_ids=["E1"],
        confidence=1.0,
    )

    assert output.citation_ids == ["E1"]
def make_evidence() -> RetrievedEvidence:
    return RetrievedEvidence(
        query_id="query-001",
        retrieved_evidence=[
            EvidenceItem(
                document_id="law-001",
                chunk_id="chunk-001",
                text=(
                    "Article 10 provides the relevant "
                    "legal requirement."
                ),
                page=10,
                section="Article 10",
                language="en",
                score=0.95,
            )
        ],
    )


def make_empty_evidence() -> RetrievedEvidence:
    return RetrievedEvidence(
        query_id="query-001",
        retrieved_evidence=[],
    )


def make_request() -> AnswerGenerationRequest:
    return AnswerGenerationRequest(
        request_id="request-001",
        query_id="query-001",
        original_query=(
            "What does Article 10 require?"
        ),
        response_language=ResponseLanguage.ENGLISH,
        retrieved_evidence=make_evidence(),
        evidence_sufficient=True,
    )


def make_citation() -> Citation:
    return Citation(
        evidence_id="E1",
        document_id="law-001",
        chunk_id="chunk-001",
        page=10,
        section="Article 10",
    )


# ---------------------------------------------------------
# Safe context
# ---------------------------------------------------------


def test_safe_context_accepts_user_turn():
    context = SafeContextTurn(
        role="user",
        text="What about Article 10?",
    )

    assert context.role == "user"


def test_safe_context_accepts_assistant_turn():
    context = SafeContextTurn(
        role="assistant",
        text="Previous conversational answer.",
    )

    assert context.role == "assistant"


def test_safe_context_rejects_invalid_role():
    with pytest.raises(ValidationError):
        SafeContextTurn(
            role="system",
            text="Invalid role",
        )


def test_safe_context_rejects_blank_text():
    with pytest.raises(ValidationError):
        SafeContextTurn(
            role="user",
            text="   ",
        )


# ---------------------------------------------------------
# AnswerGenerationRequest
# ---------------------------------------------------------


def test_valid_answer_generation_request():
    request = make_request()

    assert request.request_id == "request-001"
    assert request.query_id == "query-001"
    assert request.evidence_sufficient is True
    assert (
        request.response_language
        == ResponseLanguage.ENGLISH
    )


@pytest.mark.parametrize(
    "language",
    [
        ResponseLanguage.ARABIC,
        ResponseLanguage.ENGLISH,
        ResponseLanguage.MIXED,
    ],
)
def test_supported_response_languages(language):
    request = AnswerGenerationRequest(
        request_id="request-001",
        query_id="query-001",
        original_query="Test question",
        response_language=language,
        retrieved_evidence=make_evidence(),
        evidence_sufficient=True,
    )

    assert request.response_language == language


def test_request_rejects_query_id_mismatch():
    evidence = make_evidence()

    with pytest.raises(
        ValidationError,
        match="query_id must match",
    ):
        AnswerGenerationRequest(
            request_id="request-001",
            query_id="query-other",
            original_query="Test",
            response_language=(
                ResponseLanguage.ENGLISH
            ),
            retrieved_evidence=evidence,
            evidence_sufficient=True,
        )


def test_sufficient_request_requires_evidence():
    with pytest.raises(
        ValidationError,
        match="RetrievedEvidence is empty",
    ):
        AnswerGenerationRequest(
            request_id="request-001",
            query_id="query-001",
            original_query="Test question",
            response_language=(
                ResponseLanguage.ENGLISH
            ),
            retrieved_evidence=(
                make_empty_evidence()
            ),
            evidence_sufficient=True,
        )


def test_insufficient_request_requires_reason():
    with pytest.raises(
        ValidationError,
        match="insufficiency_reason is required",
    ):
        AnswerGenerationRequest(
            request_id="request-001",
            query_id="query-001",
            original_query="Test question",
            response_language=(
                ResponseLanguage.ENGLISH
            ),
            retrieved_evidence=(
                make_empty_evidence()
            ),
            evidence_sufficient=False,
        )


def test_insufficient_request_accepts_reason():
    request = AnswerGenerationRequest(
        request_id="request-001",
        query_id="query-001",
        original_query="Test question",
        response_language=ResponseLanguage.ENGLISH,
        retrieved_evidence=make_empty_evidence(),
        evidence_sufficient=False,
        insufficiency_reason=(
            "No approved evidence met the "
            "minimum relevance threshold."
        ),
    )

    assert request.evidence_sufficient is False
    assert request.insufficiency_reason is not None


def test_sufficient_request_rejects_insufficiency_reason():
    with pytest.raises(
        ValidationError,
        match="insufficiency_reason must be empty",
    ):
        AnswerGenerationRequest(
            request_id="request-001",
            query_id="query-001",
            original_query="Test question",
            response_language=(
                ResponseLanguage.ENGLISH
            ),
            retrieved_evidence=make_evidence(),
            evidence_sufficient=True,
            insufficiency_reason="Not needed",
        )


def test_request_accepts_safe_context():
    request = AnswerGenerationRequest(
        request_id="request-001",
        query_id="query-001",
        original_query="What about Article 10?",
        response_language=ResponseLanguage.ENGLISH,
        retrieved_evidence=make_evidence(),
        evidence_sufficient=True,
        safe_context=[
            SafeContextTurn(
                role="user",
                text="Tell me about termination.",
            ),
            SafeContextTurn(
                role="assistant",
                text="Previous conversational response.",
            ),
        ],
    )

    assert len(request.safe_context) == 2


def test_request_forbids_extra_fields():
    with pytest.raises(ValidationError):
        AnswerGenerationRequest(
            request_id="request-001",
            query_id="query-001",
            original_query="Test",
            response_language=(
                ResponseLanguage.ENGLISH
            ),
            retrieved_evidence=make_evidence(),
            evidence_sufficient=True,
            unauthorized_field="not allowed",
        )


# ---------------------------------------------------------
# ValidatedAIResponse
# ---------------------------------------------------------


def test_valid_ai_response():
    response = ValidatedAIResponse(
        request_id="request-001",
        query_id="query-001",
        answer=(
            "Article 10 provides the stated "
            "requirement. [E1]"
        ),
        citations=[
            make_citation()
        ],
        confidence=0.95,
        insufficient_evidence=False,
        grounding_valid=True,
        citations_valid=True,
        structured_output_valid=True,
        model_tag="qwen-test",
        prompt_version="p4-answer-v1",
    )

    assert response.query_id == "query-001"
    assert response.grounding_valid is True
    assert len(response.citations) == 1


def test_grounded_response_requires_citation():
    with pytest.raises(
        ValidationError,
        match="requires at least one citation",
    ):
        ValidatedAIResponse(
            request_id="request-001",
            query_id="query-001",
            answer="Unsupported answer.",
            citations=[],
            confidence=0.5,
            insufficient_evidence=False,
            grounding_valid=False,
            citations_valid=False,
            structured_output_valid=True,
            model_tag="qwen-test",
            prompt_version="p4-answer-v1",
        )


def test_insufficient_response_can_have_no_citations():
    response = ValidatedAIResponse(
        request_id="request-001",
        query_id="query-001",
        answer=(
            "The available approved evidence is "
            "insufficient to answer this question."
        ),
        citations=[],
        confidence=0.0,
        insufficient_evidence=True,
        grounding_valid=True,
        citations_valid=True,
        structured_output_valid=True,
        model_tag="qwen-test",
        prompt_version="p4-answer-v1",
    )

    assert response.insufficient_evidence is True
    assert response.citations == []


def test_duplicate_citations_are_rejected():
    citation = make_citation()

    with pytest.raises(
        ValidationError,
        match="duplicate evidence citations",
    ):
        ValidatedAIResponse(
            request_id="request-001",
            query_id="query-001",
            answer="Grounded answer. [E1]",
            citations=[
                citation,
                citation,
            ],
            confidence=0.9,
            insufficient_evidence=False,
            grounding_valid=True,
            citations_valid=True,
            structured_output_valid=True,
            model_tag="qwen-test",
            prompt_version="p4-answer-v1",
        )


@pytest.mark.parametrize(
    "confidence",
    [-0.01, 1.01],
)
def test_response_rejects_invalid_confidence(
    confidence,
):
    with pytest.raises(ValidationError):
        ValidatedAIResponse(
            request_id="request-001",
            query_id="query-001",
            answer="Grounded answer. [E1]",
            citations=[
                make_citation()
            ],
            confidence=confidence,
            insufficient_evidence=False,
            grounding_valid=True,
            citations_valid=True,
            structured_output_valid=True,
            model_tag="qwen-test",
            prompt_version="p4-answer-v1",
        )


def test_response_can_record_unsupported_claims():
    response = ValidatedAIResponse(
        request_id="request-001",
        query_id="query-001",
        answer="Potentially invalid answer. [E1]",
        citations=[
            make_citation()
        ],
        confidence=0.5,
        insufficient_evidence=False,
        grounding_valid=False,
        citations_valid=True,
        structured_output_valid=True,
        unsupported_claims=[
            "Claim was not supported by E1."
        ],
        validation_errors=[
            "Grounding validation failed."
        ],
        model_tag="qwen-test",
        prompt_version="p4-answer-v1",
    )

    assert response.grounding_valid is False
    assert len(response.unsupported_claims) == 1
