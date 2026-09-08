from pathlib import Path

from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.dependencies import (
    get_p4_m4_orchestrator,
)
from src.clause_engine.service import (
    M5ClauseService,
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


CLAUSE_ID = "CLZ-CONF-EG-001"
CLAUSE_VERSION = "1.0.0"


def get_real_m5_clause():
    service = M5ClauseService(
        library_path=Path(
            "data/clause_library.json"
        ),
        requirements_path=Path(
            "data/template_requirements.json"
        ),
    )

    return service.clause_library.get_clause(
        CLAUSE_ID
    )


def make_p3_body():
    clause = get_real_m5_clause()

    draft = AssembledDraft(
        draft_id="draft-001",
        document_type="nda",
        template_id="template-nda",
        template_version="1.0",
        sections=[
            DraftSection(
                section_id="confidentiality",
                title="Confidentiality",
                text=clause.text_en,
                source_references=[
                    SourceReference(
                        source_type=(
                            DraftSourceType
                            .APPROVED_CLAUSE
                        ),
                        source_id=CLAUSE_ID,
                        source_version=CLAUSE_VERSION,
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
                clause_id=CLAUSE_ID,
                clause_version=CLAUSE_VERSION,
            )
        ],
    )

    return {
        "draft": draft.model_dump(
            mode="json"
        ),
        "manifest": manifest.model_dump(
            mode="json"
        ),
        "clause_language": "en",
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
        body["validation"]["provenance_valid"]
        is True
    )

    assert (
        body["validation"]["grounding_valid"]
        is True
    )

    assert (
        body["requires_lawyer_review"]
        is False
    )


def test_p3_contract_mismatch_returns_400():
    app = create_app()

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


def test_p3_unknown_m5_clause_returns_422():
    app = create_app()

    body = make_p3_body()

    unknown_clause_id = (
        "CLZ-DOES-NOT-EXIST"
    )

    body["manifest"][
        "clause_references"
    ][0]["clause_id"] = (
        unknown_clause_id
    )

    body["draft"][
        "sections"
    ][0]["source_references"][0][
        "source_id"
    ] = unknown_clause_id

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/m4/p3/validate",
            json=body,
        )

    assert response.status_code == 422


def test_p3_wrong_m5_version_returns_422():
    app = create_app()

    body = make_p3_body()

    body["manifest"][
        "clause_references"
    ][0]["clause_version"] = "9.9.9"

    body["draft"][
        "sections"
    ][0]["source_references"][0][
        "source_version"
    ] = "9.9.9"

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/m4/p3/validate",
            json=body,
        )

    assert response.status_code == 422


def test_p3_tampered_clause_text_requires_review():
    app = create_app()

    body = make_p3_body()

    body["draft"]["sections"][0]["text"] += (
        " The receiving party shall also "
        "pay EGP 100,000."
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/m4/p3/validate",
            json=body,
        )

    assert response.status_code == 200

    result = response.json()

    assert (
        result["validation"]["provenance_valid"]
        is True
    )

    assert (
        result["validation"]["grounding_valid"]
        is False
    )

    assert (
        result["validation"]["is_valid"]
        is False
    )

    assert (
        result["requires_lawyer_review"]
        is True
    )


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