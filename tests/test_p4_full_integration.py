from __future__ import annotations

from types import SimpleNamespace

import pytest

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
from src.orchestration.p4_chat_service import (
    P4ChatService,
    P4RetrievalContractError,
    P4RetrievalPolicyError,
)
from src.orchestration.p4_grounding_validator import (
    P4GroundingValidationOutput,
    P4GroundingValidator,
)
from src.orchestration.p4_orchestrator import (
    P4M4Orchestrator,
)
from src.orchestration.raw_rag_service import (
    M2EmbeddingContractError,
)
from src.orchestration.settings import (
    M4Settings,
)
from src.schemas.access_control import (
    AccessScopeRequired,
)
from src.schemas.m2_contract import (
    EmbeddedQuery,
    IdentifierSet,
    ProcessedQuery,
    QueryFilters,
)
from src.schemas.m4_contract import (
    EvidenceItem,
    M4ModelOutput,
    RetrievedEvidence,
)
from src.schemas.p4_chat_contract import (
    ResponseLanguage,
    SafeContextTurn,
)
from tests.access_helpers import (
    scoped_filters,
)


class FakeM2QueryPipeline:
    def __init__(
        self,
        *,
        language: str = "en",
        broken_mirror: bool = False,
    ) -> None:
        self.language = language
        self.broken_mirror = broken_mirror
        self.calls = 0

    def process(
        self,
        raw_query: str,
    ) -> EmbeddedQuery:

        self.calls += 1

        vector = [0.1] * 1024

        sparse = {
            "10": 0.8,
            "20": 0.4,
        }

        processed = ProcessedQuery(
            query_id="q_p4_001",
            text_original=raw_query,
            normalized_text=(
                raw_query.lower()
            ),
            language=self.language,
            embedding=(
                []
                if self.broken_mirror
                else list(vector)
            ),
            sparse_embedding=sparse,
            query_variants=[
                raw_query.lower(),
                "article 157 force majeure",
            ],
            identifiers=IdentifierSet(
                article_numbers=[
                    "157"
                ],
                party_names=[
                    "Acme Egypt LLC"
                ],
                named_legal_terms=[
                    "force majeure"
                ],
            ),
        )

        return EmbeddedQuery(
            processed_query=processed,
            embedding=vector,
            sparse_embedding=sparse,
            model="BAAI/bge-m3",
            dimension=1024,
        )


class FakeM3RetrievalPipeline:
    def __init__(
        self,
        *,
        evidence: (
            RetrievedEvidence
            | None
        ) = None,
        statuses=("current",),
        include_unversioned: bool = False,
    ) -> None:

        self.hybrid_searcher = (
            SimpleNamespace(
                allowed_validity_statuses=(
                    list(statuses)
                    if statuses is not None
                    else None
                ),
                include_unversioned_points=(
                    include_unversioned
                ),
            )
        )

        self.evidence = evidence
        self.calls = 0
        self.last_query = None

    def run(
        self,
        query: ProcessedQuery,
    ) -> tuple[
        RetrievedEvidence,
        float,
    ]:

        self.calls += 1
        self.last_query = query

        evidence = self.evidence

        if evidence is None:
            evidence = RetrievedEvidence(
                query_id=query.query_id,
                retrieved_evidence=[
                    EvidenceItem(
                        document_id=(
                            "law-001"
                        ),
                        chunk_id=(
                            "chunk-001"
                        ),
                        text=(
                            "Article 157 governs "
                            "the relevant obligation."
                        ),
                        page=15,
                        section="Article 157",
                        language="en",
                        score=0.96,
                    )
                ],
            )

        return evidence, 12.5


class FakeGenerationLLM:
    def __init__(self) -> None:
        self.calls = 0

    def invoke(
        self,
        messages,
    ):
        self.calls += 1

        return M4ModelOutput(
            answer=(
                "Article 157 governs the relevant "
                "obligation. [E1]"
            ),
            citation_ids=["E1"],
            confidence=0.94,
        )

    async def ainvoke(
        self,
        messages,
    ):
        self.calls += 1

        return M4ModelOutput(
            answer=(
                "Article 157 governs the relevant "
                "obligation. [E1]"
            ),
            citation_ids=["E1"],
            confidence=0.94,
        )


class FakeGroundingChecker:
    def __init__(self) -> None:
        self.calls = 0

    @property
    def model_tag(self):
        return "fake-grounding-qwen"

    @property
    def prompt_version(self):
        return (
            "p4-claim-grounding-validation-v1"
        )

    def check(
        self,
        *,
        answer,
        citation_ids,
        evidence_by_id,
    ):
        self.calls += 1

        return P4GroundingValidationOutput(
            grounded=True,
            unsupported_claims=[],
            reason=(
                "All claims are supported."
            ),
        )

    async def acheck(
        self,
        **kwargs,
    ):
        return self.check(
            **kwargs
        )


def make_m6_service(
) -> KnowledgeIntegrationService:

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


def make_service(
    *,
    language: str = "en",
    evidence: (
        RetrievedEvidence
        | None
    ) = None,
    statuses=("current",),
    include_unversioned: bool = False,
    broken_mirror: bool = False,
):

    m2 = FakeM2QueryPipeline(
        language=language,
        broken_mirror=broken_mirror,
    )

    m3 = FakeM3RetrievalPipeline(
        evidence=evidence,
        statuses=statuses,
        include_unversioned=(
            include_unversioned
        ),
    )

    generation = FakeGenerationLLM()

    m4 = P4M4Orchestrator(
        settings=M4Settings(
            model_name="qwen-test",
            validate_model_on_init=False,
        ),
        llm_service=generation,
        grounding_validator=(
            P4GroundingValidator(
                checker=(
                    FakeGroundingChecker()
                )
            )
        ),
    )

    service = P4ChatService(
        query_pipeline=m2,
        retrieval_pipeline=m3,
        knowledge_service=(
            make_m6_service()
        ),
        m4_orchestrator=m4,
        expected_embedding_dimension=1024,
    )

    return (
        service,
        m2,
        m3,
        generation,
    )


def test_full_p4_m6_m2_m3_m6_m4_flow():

    (
        service,
        m2,
        m3,
        generation,
    ) = make_service()

    filters = scoped_filters(
        jurisdiction="Egypt"
    )

    context = [
        SafeContextTurn(
            role="user",
            text="I mean Article 157.",
        )
    ]

    result = service.answer(
        question=(
            "What does Article 157 say "
            "about force majeure for "
            "Acme Egypt LLC?"
        ),
        filters=filters,
        request_id="request-p4-001",
        safe_context=context,
        response_instructions=[
            "Be concise."
        ],
    )

    assert m2.calls == 1
    assert m3.calls == 1
    assert generation.calls == 1

    assert (
        m3.last_query.filters.access
        == filters.access
    )

    assert (
        m3
        .last_query
        .filters
        .jurisdiction
        == "Egypt"
    )

    assert (
        m3
        .last_query
        .identifiers
        .article_numbers
        == ["157"]
    )

    assert (
        m3
        .last_query
        .identifiers
        .party_names
        == ["Acme Egypt LLC"]
    )

    assert (
        m3
        .last_query
        .identifiers
        .named_legal_terms
        == ["force majeure"]
    )

    assert (
        m3
        .last_query
        .query_variants[-1]
        == "article 157 force majeure"
    )

    assert len(
        m3.last_query.embedding
    ) == 1024

    assert (
        m3.last_query.sparse_embedding
        == {
            "10": 0.8,
            "20": 0.4,
        }
    )

    assert (
        result.answer_request.request_id
        == "request-p4-001"
    )

    assert (
        result
        .answer_request
        .response_language
        == ResponseLanguage.ENGLISH
    )

    assert (
        result
        .answer_request
        .evidence_sufficient
        is True
    )

    assert (
        result.answer_request.safe_context
        == context
    )

    assert (
        result
        .answer_request
        .response_instructions
        == ["Be concise."]
    )

    assert (
        result
        .response
        .insufficient_evidence
        is False
    )

    assert (
        result.response.grounding_valid
        is True
    )

    assert len(
        result.response.citations
    ) == 1

    citation = (
        result.response.citations[0]
    )

    assert (
        citation.document_id
        == "law-001"
    )

    assert (
        citation.chunk_id
        == "chunk-001"
    )

    assert (
        result.metrics.retrieval_ms
        == 12.5
    )

    assert (
        result.metrics.evidence_count
        == 1
    )

    assert (
        result
        .metrics
        .generation_invoked
        is True
    )

    assert (
        result.metrics.citation_count
        == 1
    )


@pytest.mark.parametrize(
    (
        "m2_language",
        "expected",
    ),
    [
        (
            "ar",
            ResponseLanguage.ARABIC,
        ),
        (
            "en",
            ResponseLanguage.ENGLISH,
        ),
        (
            "ar-en",
            ResponseLanguage.MIXED,
        ),
        (
            "unknown",
            ResponseLanguage.ENGLISH,
        ),
    ],
)
def test_m2_language_flows_through_m6_policy(
    m2_language,
    expected,
):

    service, _, _, _ = make_service(
        language=m2_language
    )

    result = service.answer(
        question="test question",
        filters=scoped_filters(),
    )

    assert (
        result
        .answer_request
        .response_language
        == expected
    )


def test_empty_m3_evidence_makes_m6_abstain_and_skips_qwen():

    empty = RetrievedEvidence(
        query_id="q_p4_001",
        retrieved_evidence=[],
    )

    (
        service,
        _,
        _,
        generation,
    ) = make_service(
        evidence=empty
    )

    result = service.answer(
        question="What is the rule?",
        filters=scoped_filters(),
    )

    assert (
        result
        .answer_request
        .evidence_sufficient
        is False
    )

    assert (
        result
        .response
        .insufficient_evidence
        is True
    )

    assert (
        result.response.citations
        == []
    )

    assert generation.calls == 0

    assert (
        result
        .metrics
        .generation_invoked
        is False
    )


def test_package4_rejects_non_current_retrieval_policy():

    with pytest.raises(
        P4RetrievalPolicyError,
        match="current",
    ):
        make_service(
            statuses=None
        )

    with pytest.raises(
        P4RetrievalPolicyError,
        match="current",
    ):
        make_service(
            statuses=(
                "current",
                "superseded",
            )
        )


def test_package4_rejects_unversioned_retrieval():

    with pytest.raises(
        P4RetrievalPolicyError,
        match="unversioned",
    ):
        make_service(
            include_unversioned=True
        )


def test_lifecycle_policy_is_rechecked_before_each_query():

    service, m2, m3, _ = (
        make_service()
    )

    m3.hybrid_searcher.allowed_validity_statuses = (
        None
    )

    with pytest.raises(
        P4RetrievalPolicyError,
        match="current",
    ):
        service.answer(
            question="Article 157",
            filters=scoped_filters(),
        )

    assert m2.calls == 0
    assert m3.calls == 0


def test_access_scope_is_required_before_m2_runs():

    (
        service,
        m2,
        m3,
        generation,
    ) = make_service()

    with pytest.raises(
        AccessScopeRequired
    ):
        service.answer(
            question="Article 157",
            filters=QueryFilters(),
        )

    assert m2.calls == 0
    assert m3.calls == 0
    assert generation.calls == 0


def test_broken_m2_embedding_mirror_is_rejected_before_m3():

    (
        service,
        _,
        m3,
        generation,
    ) = make_service(
        broken_mirror=True
    )

    with pytest.raises(
        M2EmbeddingContractError,
        match="must mirror",
    ):
        service.answer(
            question="Article 157",
            filters=scoped_filters(),
        )

    assert m3.calls == 0
    assert generation.calls == 0


def test_m3_query_id_mismatch_is_rejected_before_m6_m4():

    wrong = RetrievedEvidence(
        query_id="q_wrong",
        retrieved_evidence=[
            EvidenceItem(
                document_id="law-001",
                chunk_id="chunk-001",
                text="Trusted evidence.",
                score=0.9,
            )
        ],
    )

    (
        service,
        _,
        _,
        generation,
    ) = make_service(
        evidence=wrong
    )

    with pytest.raises(
        P4RetrievalContractError,
        match="query_id",
    ):
        service.answer(
            question="Article 157",
            filters=scoped_filters(),
        )

    assert generation.calls == 0


@pytest.mark.asyncio
async def test_async_full_p4_flow():

    (
        service,
        _,
        _,
        generation,
    ) = make_service(
        language="ar-en"
    )

    result = await service.aanswer(
        question=(
            "ما معنى force majeure "
            "في Article 157?"
        ),
        filters=scoped_filters(),
    )

    assert (
        result
        .answer_request
        .response_language
        == ResponseLanguage.MIXED
    )

    assert (
        result
        .response
        .citations[0]
        .document_id
        == "law-001"
    )

    assert generation.calls == 1
