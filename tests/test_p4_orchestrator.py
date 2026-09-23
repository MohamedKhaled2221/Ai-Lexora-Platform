import pytest

from src.orchestration.p4_grounding_validator import (
    P4GroundingValidationOutput,
    P4GroundingValidator,
)
from src.orchestration.p4_orchestrator import (
    P4GroundingValidationError,
    P4M4Orchestrator,
)
from src.orchestration.settings import (
    M4Settings,
)
from src.schemas.m4_contract import (
    EvidenceItem,
    M4ModelOutput,
    RetrievedEvidence,
)
from src.schemas.p4_chat_contract import (
    AnswerGenerationRequest,
    ResponseLanguage,
)


def make_evidence():
    return RetrievedEvidence(
        query_id="query-001",
        retrieved_evidence=[
            EvidenceItem(
                document_id="law-001",
                chunk_id="chunk-001",
                text=(
                    "Article 10 requires written notice."
                ),
                page=10,
                section="Article 10",
                language="en",
                score=0.95,
            )
        ],
    )


def make_request(
    *,
    evidence_sufficient=True,
):
    return AnswerGenerationRequest(
        request_id="request-001",
        query_id="query-001",
        original_query=(
            "What does Article 10 require?"
        ),
        response_language=(
            ResponseLanguage.ENGLISH
        ),
        retrieved_evidence=(
            make_evidence()
            if evidence_sufficient
            else RetrievedEvidence(
                query_id="query-001",
                retrieved_evidence=[],
            )
        ),
        evidence_sufficient=(
            evidence_sufficient
        ),
        insufficiency_reason=(
            None
            if evidence_sufficient
            else "No relevant approved evidence."
        ),
    )


class FakeGenerationLLM:
    def __init__(
        self,
        output=None,
    ):
        self.output = (
            output
            or M4ModelOutput(
                answer=(
                    "Article 10 requires "
                    "written notice. [E1]"
                ),
                citation_ids=["E1"],
                confidence=0.95,
            )
        )

        self.calls = 0

    def invoke(
        self,
        messages,
    ):
        self.calls += 1
        return self.output

    async def ainvoke(
        self,
        messages,
    ):
        self.calls += 1
        return self.output


class FakeGroundingChecker:
    def __init__(
        self,
        *,
        grounded=True,
    ):
        self.grounded = grounded
        self.calls = 0

    @property
    def model_tag(self):
        return "fake-validation-qwen"

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

        if self.grounded:
            return P4GroundingValidationOutput(
                grounded=True,
                unsupported_claims=[],
                reason=(
                    "All claims are supported."
                ),
            )

        return P4GroundingValidationOutput(
            grounded=False,
            unsupported_claims=[
                "The answer introduced a penalty."
            ],
            reason=(
                "The penalty is not present "
                "in cited evidence."
            ),
        )

    async def acheck(
        self,
        *,
        answer,
        citation_ids,
        evidence_by_id,
    ):
        return self.check(
            answer=answer,
            citation_ids=citation_ids,
            evidence_by_id=evidence_by_id,
        )


def settings():
    return M4Settings(
        model_name="qwen-test",
        validate_model_on_init=False,
    )


def test_grounded_p4_answer_passes():
    generation = FakeGenerationLLM()

    grounding_checker = (
        FakeGroundingChecker(
            grounded=True
        )
    )

    orchestrator = P4M4Orchestrator(
        settings=settings(),
        llm_service=generation,
        grounding_validator=(
            P4GroundingValidator(
                checker=grounding_checker
            )
        ),
    )

    result = orchestrator.answer(
        make_request()
    )

    response = result.response

    assert response.grounding_valid is True
    assert response.citations_valid is True
    assert (
        response.structured_output_valid
        is True
    )

    assert response.insufficient_evidence is False

    assert len(response.citations) == 1

    citation = response.citations[0]

    assert citation.evidence_id == "E1"
    assert citation.document_id == "law-001"
    assert citation.chunk_id == "chunk-001"
    assert citation.page == 10

    assert generation.calls == 1
    assert grounding_checker.calls == 1

    assert (
        result.metrics.generation_invoked
        is True
    )

    assert (
        result.metrics
        .grounding_validation_invoked
        is True
    )



def test_grounding_failure_is_blocked():
    generation = FakeGenerationLLM(
        output=M4ModelOutput(
            answer=(
                "Article 10 requires written notice "
                "and imposes a $50,000 penalty. [E1]"
            ),
            citation_ids=["E1"],
            confidence=0.8,
        )
    )

    checker = FakeGroundingChecker(
        grounded=False
    )

    orchestrator = P4M4Orchestrator(
        settings=settings(),
        llm_service=generation,
        grounding_validator=(
            P4GroundingValidator(
                checker=checker
            )
        ),
    )

    with pytest.raises(
        P4GroundingValidationError
    ):
        orchestrator.answer(
            make_request()
        )

    assert generation.calls == 1
    assert checker.calls == 1

@pytest.mark.asyncio
async def test_async_grounding_failure_is_blocked():
    generation = FakeGenerationLLM(
        output=M4ModelOutput(
            answer=(
                "Article 10 requires written notice "
                "and imposes an unsupported penalty. [E1]"
            ),
            citation_ids=["E1"],
            confidence=0.8,
        )
    )

    checker = FakeGroundingChecker(
        grounded=False
    )

    orchestrator = P4M4Orchestrator(
        settings=settings(),
        llm_service=generation,
        grounding_validator=(
            P4GroundingValidator(
                checker=checker
            )
        ),
    )

    with pytest.raises(
        P4GroundingValidationError
    ):
        await orchestrator.aanswer(
            make_request()
        )

    assert generation.calls == 1
    assert checker.calls == 1
def test_insufficient_evidence_skips_all_llm_calls():
    generation = FakeGenerationLLM()

    checker = FakeGroundingChecker()

    orchestrator = P4M4Orchestrator(
        settings=settings(),
        llm_service=generation,
        grounding_validator=(
            P4GroundingValidator(
                checker=checker
            )
        ),
    )

    result = orchestrator.answer(
        make_request(
            evidence_sufficient=False
        )
    )

    response = result.response

    assert response.insufficient_evidence is True
    assert response.citations == []
    assert response.confidence == 0.0

    assert generation.calls == 0
    assert checker.calls == 0

    assert (
        result.metrics.generation_invoked
        is False
    )

    assert (
        result.metrics
        .grounding_validation_invoked
        is False
    )


@pytest.mark.asyncio
async def test_async_grounded_answer():
    generation = FakeGenerationLLM()

    checker = FakeGroundingChecker(
        grounded=True
    )

    orchestrator = P4M4Orchestrator(
        settings=settings(),
        llm_service=generation,
        grounding_validator=(
            P4GroundingValidator(
                checker=checker
            )
        ),
    )

    result = await orchestrator.aanswer(
        make_request()
    )

    assert (
        result.response.grounding_valid
        is True
    )

    assert generation.calls == 1
    assert checker.calls == 1


def test_prompt_version_is_recorded():
    orchestrator = P4M4Orchestrator(
        settings=settings(),
        llm_service=FakeGenerationLLM(),
        grounding_validator=(
            P4GroundingValidator(
                checker=(
                    FakeGroundingChecker()
                )
            )
        ),
    )

    result = orchestrator.answer(
        make_request()
    )

    assert (
        result.response.prompt_version
        == "p4-grounded-answer-v5"
    )

    assert (
        result.response.model_tag
        == "qwen-test"
    )


def test_model_cannot_invent_citation_alias():
    generation = FakeGenerationLLM(
        output=M4ModelOutput(
            answer=(
                "Article 10 requires notice. [E99]"
            ),
            citation_ids=["E99"],
            confidence=0.9,
        )
    )

    orchestrator = P4M4Orchestrator(
        settings=settings(),
        llm_service=generation,
        grounding_validator=(
            P4GroundingValidator(
                checker=(
                    FakeGroundingChecker()
                )
            )
        ),
    )

    with pytest.raises(
        ValueError
    ):
        orchestrator.answer(
            make_request()
        )


def test_generation_without_citation_is_rejected():
    generation = FakeGenerationLLM(
        output=M4ModelOutput(
            answer=(
                "Article 10 requires written notice."
            ),
            citation_ids=[],
            confidence=0.9,
        )
    )

    orchestrator = P4M4Orchestrator(
        settings=settings(),
        llm_service=generation,
        grounding_validator=(
            P4GroundingValidator(
                checker=(
                    FakeGroundingChecker()
                )
            )
        ),
    )

    with pytest.raises(
        ValueError
    ):
        orchestrator.answer(
            make_request()
        )
