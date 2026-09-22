import src.schemas.m6_knowledge as m6_knowledge

from src.knowledge.access_control import (
    AccessControlService,
)
from src.knowledge.governance import (
    KnowledgeGovernanceService,
)
from src.knowledge.integration import (
    KnowledgeIntegrationService,
)
from src.knowledge.relationships import (
    RelationshipService,
)
from src.knowledge.repository import (
    InMemoryKnowledgeRepository,
)
from src.schemas.m4_contract import (
    EvidenceItem,
    RetrievedEvidence,
)
from src.schemas.m6_knowledge import (
    ValidityStatus,
)
from src.schemas.p4_chat_contract import (
    AnswerGenerationRequest,
    ResponseLanguage,
    SafeContextTurn,
)


def make_service():
    return KnowledgeIntegrationService(
        repository=(
            InMemoryKnowledgeRepository()
        ),
        relationship_service=(
            RelationshipService()
        ),
        access_control=(
            AccessControlService()
        ),
        governance=(
            KnowledgeGovernanceService()
        ),
    )


def make_evidence(
    *,
    include_item: bool = True,
) -> RetrievedEvidence:

    items = []

    if include_item:
        items.append(
            EvidenceItem(
                document_id="law-001",
                chunk_id="chunk-001",
                text=(
                    "Article 10 provides "
                    "the relevant rule."
                ),
                page=10,
                section="Article 10",
                language="en",
                score=0.95,
            )
        )

    return RetrievedEvidence(
        query_id="query-001",
        retrieved_evidence=items,
    )


def test_empty_evidence_is_insufficient():
    service = make_service()

    result = service.evaluate_evidence(
        make_evidence(
            include_item=False
        )
    )

    assert result.sufficient is False
    assert (
        result.requires_follow_up
        is True
    )


def test_valid_evidence_is_sufficient():
    service = make_service()

    result = service.evaluate_evidence(
        make_evidence()
    )

    assert result.sufficient is True
    assert result.score > 0


def test_build_answer_request_uses_shared_p4_contract():
    service = make_service()

    evidence = make_evidence()

    request = service.build_answer_request(
        request_id="request-001",
        original_query=(
            "What does Article 10 provide?"
        ),
        response_language="en",
        retrieved_evidence=evidence,
        record_statuses=[
            ValidityStatus.CURRENT
        ],
        safe_context=[
            SafeContextTurn(
                role="user",
                text=(
                    "I was asking about "
                    "Article 10."
                ),
            )
        ],
    )

    assert isinstance(
        request,
        AnswerGenerationRequest,
    )

    assert (
        request.request_id
        == "request-001"
    )

    assert (
        request.query_id
        == "query-001"
    )

    assert (
        request.original_query
        == "What does Article 10 provide?"
    )

    assert (
        request.response_language
        == ResponseLanguage.ENGLISH
    )

    assert (
        request.retrieved_evidence
        is evidence
    )

    assert (
        request.evidence_sufficient
        is True
    )

    assert request.insufficiency_reason is None
    assert len(request.safe_context) == 1


def test_build_answer_request_abstains_for_empty_evidence():
    service = make_service()

    request = service.build_answer_request(
        request_id="request-002",
        original_query="Unknown question",
        response_language="en",
        retrieved_evidence=(
            make_evidence(
                include_item=False
            )
        ),
        record_statuses=[],
    )

    assert (
        request.evidence_sufficient
        is False
    )

    assert (
        request.insufficiency_reason
        == "No evidence was retrieved."
    )


def test_build_answer_request_blocks_superseded_evidence():
    service = make_service()

    request = service.build_answer_request(
        request_id="request-003",
        original_query=(
            "What does the old rule say?"
        ),
        response_language="en",
        retrieved_evidence=make_evidence(),
        record_statuses=[
            ValidityStatus.SUPERSEDED
        ],
    )

    assert (
        request.evidence_sufficient
        is False
    )

    assert request.insufficiency_reason

    assert (
        "superseded"
        in (
            request
            .insufficiency_reason
            .lower()
        )
    )


def test_build_answer_request_blocks_review_required_evidence():
    service = make_service()

    request = service.build_answer_request(
        request_id="request-004",
        original_query="Test",
        response_language="en",
        retrieved_evidence=make_evidence(),
        record_statuses=[
            ValidityStatus.REVIEW_REQUIRED
        ],
    )

    assert (
        request.evidence_sufficient
        is False
    )

    assert request.insufficiency_reason


def test_m6_does_not_define_parallel_p4_contract():
    assert not hasattr(
        m6_knowledge,
        "AnswerGenerationRequest",
    )

    assert not hasattr(
        m6_knowledge,
        "Citation",
    )

def test_explicit_requested_document_must_survive_retrieval():
    service = make_service()

    evidence = RetrievedEvidence(
        query_id="query-title-missing",
        retrieved_evidence=[
            EvidenceItem(
                document_id="qa-public",
                chunk_id="qa-public-001",
                title="Public Test Document",
                text=(
                    "The fictional public registration "
                    "period is 11 days."
                ),
                language="en",
                score=0.70,
            )
        ],
    )

    result = service.evaluate_evidence(
        evidence,
        original_query=(
            "What is the fictional internal registration "
            "period in the Internal Test Document?"
        ),
    )

    assert result.sufficient is False
    assert result.requires_follow_up is True
    assert "requested document" in result.reason.lower()


def test_explicit_requested_document_is_sufficient_when_present():
    service = make_service()

    evidence = RetrievedEvidence(
        query_id="query-title-present",
        retrieved_evidence=[
            EvidenceItem(
                document_id="qa-internal",
                chunk_id="qa-internal-001",
                title="Internal Test Document",
                text=(
                    "The fictional internal registration "
                    "period is 22 days."
                ),
                language="en",
                score=0.70,
            )
        ],
    )

    result = service.evaluate_evidence(
        evidence,
        original_query=(
            "What is the fictional internal registration "
            "period in the Internal Test Document?"
        ),
    )

    assert result.sufficient is True


def test_lowercase_descriptive_document_phrase_is_not_canonical_title_gate():
    service = make_service()

    evidence = RetrievedEvidence(
        query_id="query-cross-lingual",
        retrieved_evidence=[
            EvidenceItem(
                document_id="qa-arabic-contract",
                chunk_id="qa-arabic-contract-001",
                title="عقد اختبار عربي",
                text=(
                    "مدة الإخطار التعاقدي هي خمسة عشر "
                    "يومًا تقويميًا."
                ),
                language="ar",
                score=0.72,
            )
        ],
    )

    result = service.evaluate_evidence(
        evidence,
        original_query=(
            "What is the notice period in the "
            "Arabic test contract?"
        ),
    )

    assert result.sufficient is True


def test_build_answer_request_abstains_when_named_document_is_missing():
    service = make_service()

    evidence = RetrievedEvidence(
        query_id="query-title-build",
        retrieved_evidence=[
            EvidenceItem(
                document_id="qa-public",
                chunk_id="qa-public-001",
                title="Public Test Document",
                text=(
                    "The fictional public registration "
                    "period is 11 days."
                ),
                language="en",
                score=0.70,
            )
        ],
    )

    request = service.build_answer_request(
        request_id="request-title-build",
        original_query=(
            "What is the fictional internal registration "
            "period in the Internal Test Document?"
        ),
        response_language="en",
        retrieved_evidence=evidence,
        record_statuses=[
            ValidityStatus.CURRENT
        ],
    )

    assert request.evidence_sufficient is False
    assert request.insufficiency_reason
    assert (
        "requested document"
        in request.insufficiency_reason.lower()
    )
