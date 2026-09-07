from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.dependencies import (
    get_p3_m4_orchestrator,
    get_p4_m4_orchestrator,
)
from src.orchestration.grounding_validator import (
    P3GroundingContext,
    TrustedSourceText,
)
from src.orchestration.p3_orchestrator import (
    P3M4Orchestrator,
)
from src.orchestration.p4_orchestrator import (
    P4GroundingValidationError,
    P4OrchestrationMetrics,
    P4OrchestrationResult,
)
from src.schemas.m4_contract import (
    EvidenceItem,
    RetrievedEvidence,
)
from src.schemas.p3_generation_contract import (
    AssembledDraft,
    ClauseReference,
    DraftSection,
    DraftSourceType,
    GenerationManifest,
    SourceReference,
)
from src.schemas.p4_chat_contract import (
    AnswerGenerationRequest,
    ResponseLanguage,
    ValidatedAIResponse,
)


CLAUSE_TEXT = (
    "The receiving party shall keep "
    "the information confidential."
)


def make_p3_body():
    draft = AssembledDraft(
        draft_id="draft-001",
        document_type="nda",
        template_id="template-nda",
        template_version="1.0",
        sections=[
            DraftSection(
                section_id="confidentiality",
                title="Confidentiality",
                text=CLAUSE_TEXT,
                source_references=[
                    SourceReference(
                        source_type=(
                            DraftSourceType
                            .APPROVED_CLAUSE
                        ),
                        source_id="clause-001",
                        source_version="1.0",
                    )
                ],
            )
        ],
    )

    manifest = GenerationManifest(
        manifest_id="manifest-001",
        draft_id="draft-001",
        template_id="template-nda",
        template_version="1.0",
        clause_references=[
            ClauseReference(
                clause_id="clause-001",
                clause_version="1.0",
            )
        ],
    )

    context = P3GroundingContext(
        sources=[
            TrustedSourceText(
                source_type=(
                    DraftSourceType
                    .APPROVED_CLAUSE
                ),
                source_id="clause-001",
                source_version="1.0",
                text=CLAUSE_TEXT,
            )
        ]
    )

    return {
        "draft": draft.model_dump(
            mode="json"
        ),
        "manifest": manifest.model_dump(
            mode="json"
        ),
        "grounding_context": (
            context.model_dump(
                mode="json"
            )
        ),
    }


def make_p4_request():
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
            RetrievedEvidence(
                query_id="query-001",
                retrieved_evidence=[
                    EvidenceItem(
                        document_id="law-001",
                        chunk_id="chunk-001",
                        text=(
                            "Article 10 requires "
                            "written notice."
                        ),
                        page=10,
                        section="Article 10",
                        language="en",
                        score=0.95,
                    )
                ],
            )
        ),
        evidence_sufficient=True,
    )


class FakeP4Service:
    async def aanswer(
        self,
        request,
    ):
        return P4OrchestrationResult(
            response=ValidatedAIResponse(
                request_id=request.request_id,
                query_id=request.query_id,
                answer=(
                    "Article 10 requires "
                    "written notice. [E1]"
                ),
                citations=[
                    {
                        "evidence_id": "E1",
                        "document_id": "law-001",
                        "chunk_id": "chunk-001",
                        "page": 10,
                        "section": "Article 10",
                    }
                ],
                confidence=0.95,
                insufficient_evidence=False,
                grounding_valid=True,
                citations_valid=True,
                structured_output_valid=True,
                model_tag="fake-qwen",
                prompt_version=(
                    "p4-grounded-answer-v1"
                ),
            ),
            metrics=P4OrchestrationMetrics(
                generation_invoked=True,
                grounding_validation_invoked=True,
                evidence_count=1,
                citation_count=1,
            ),
        )


class FailingP4Service:
    async def aanswer(
        self,
        request,
    ):
        raise P4GroundingValidationError(
            "unsupported claim"
        )


def test_p3_validation_endpoint():
    app = create_app()

    app.dependency_overrides[
        get_p3_m4_orchestrator
    ] = lambda: P3M4Orchestrator()

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/m4/p3/validate",
            json=make_p3_body(),
        )

    assert response.status_code == 200

    body = response.json()

    assert (
        body["validation"]["is_valid"]
        is True
    )

    assert (
        body["requires_lawyer_review"]
        is False
    )


def test_p3_contract_mismatch_returns_400():
    app = create_app()

    app.dependency_overrides[
        get_p3_m4_orchestrator
    ] = lambda: P3M4Orchestrator()

    body = make_p3_body()

    body["manifest"]["draft_id"] = (
        "different-draft"
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/m4/p3/validate",
            json=body,
        )

    assert response.status_code == 400


def test_p4_answer_endpoint():
    app = create_app()

    app.dependency_overrides[
        get_p4_m4_orchestrator
    ] = lambda: FakeP4Service()

    request = make_p4_request()

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/m4/p4/answer",
            json=request.model_dump(
                mode="json"
            ),
        )

    assert response.status_code == 200

    body = response.json()

    assert body["grounding_valid"] is True
    assert body["citations_valid"] is True

    assert (
        body["citations"][0]["document_id"]
        == "law-001"
    )


def test_p4_grounding_failure_returns_502():
    app = create_app()

    app.dependency_overrides[
        get_p4_m4_orchestrator
    ] = lambda: FailingP4Service()

    request = make_p4_request()

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/m4/p4/answer",
            json=request.model_dump(
                mode="json"
            ),
        )

    assert response.status_code == 502
