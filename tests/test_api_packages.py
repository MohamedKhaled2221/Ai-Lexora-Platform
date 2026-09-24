from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.dependencies import (
    get_p3_generation_runtime,
)
from src.api.package_runtime import (
    P3APIRuntime,
)
from src.api.security import (
    APISecuritySettings,
)
from src.orchestration import (
    CitationValidationError,
    M2QueryRuntimeError,
    M4LLMConnectionError,
    M4LLMInvocationError,
)
from src.orchestration.p3_generation_service import (
    P3GenerationIntegrationError,
)
from src.orchestration.p4_chat_service import (
    P4RetrievalPolicyError,
)
from src.orchestration.p4_orchestrator import (
    P4GroundingValidationError,
)
from src.retrieval.reranker import (
    RerankerUnavailable,
)
from src.schemas.m4_contract import Citation
from src.schemas.p3_generation_contract import (
    AssembledDraft,
    DraftSection,
    DraftSourceType,
    DraftValidationResult,
    GenerationManifest,
    SourceReference,
    ValidatedDraft,
)
from src.schemas.p4_chat_contract import (
    ValidatedAIResponse,
)
from tests.access_helpers import (
    IDENTITY_HEADERS,
    TEST_CLIENT_ID,
)


# =========================================================
# Shared fakes
# =========================================================


class FakeRAGService:
    pass


class FakeRawRAGService:
    pass


# =========================================================
# Package 3 fakes
# =========================================================


def make_validated_draft() -> ValidatedDraft:
    draft = AssembledDraft(
        draft_id="draft-api-001",
        document_type="employment_contract",
        template_id="TMPL-EMP-EG-001",
        template_version="1.0.0",
        sections=[
            DraftSection(
                section_id="section-1",
                text="Employee: Ahmed.",
                source_references=[
                    SourceReference(
                        source_type=(
                            DraftSourceType.TEMPLATE
                        ),
                        source_id=(
                            "TMPL-EMP-EG-001"
                        ),
                        source_version="1.0.0",
                    )
                ],
            )
        ],
    )

    manifest = GenerationManifest(
        manifest_id="manifest-api-001",
        draft_id=draft.draft_id,
        template_id=draft.template_id,
        template_version=(
            draft.template_version
        ),
        clause_references=[],
        user_fields={
            "employee_name": "Ahmed"
        },
        lawyer_edit_references=[],
        ai_transformations=[],
    )

    validation = DraftValidationResult(
        is_valid=True,
        structure_valid=True,
        provenance_valid=True,
        grounding_valid=True,
        unsourced_section_ids=[],
        errors=[],
        warnings=[],
    )

    return ValidatedDraft(
        draft=draft,
        manifest=manifest,
        validation=validation,
        requires_lawyer_review=False,
    )


class FakeP3GenerationService:
    def __init__(
        self,
        *,
        error: Exception | None = None,
    ) -> None:
        self.error = error
        self.calls = 0
        self.last_kwargs = None

    def generate(
        self,
        **kwargs,
    ):
        self.calls += 1
        self.last_kwargs = kwargs

        if self.error is not None:
            raise self.error

        return SimpleNamespace(
            validated_draft=(
                make_validated_draft()
            ),
            selected_clause_ids=(
                "CLZ-TERM-EG-001",
            ),
            export_allowed=True,
            docx_result=None,
            pdf_result=None,
            m5_resolved_clause_count=1,
        )


def make_p3_app(
    service: FakeP3GenerationService,
    tmp_path: Path,
):
    runtime = SimpleNamespace(
        service=service,
        export_dir=tmp_path,
    )

    return create_app(
        p3_generation_runtime_factory=(
            lambda: runtime
        ),
    )


def p3_request_json():
    return {
        "request": {
            "request_id": "REQ-API-P3-001",
            "document_type": (
                "employment_contract"
            ),
            "jurisdiction": "EG",
            "fields": {
                "employee_name": "Ahmed"
            },
            "requested_clause_ids": [],
            "special_conditions": [],
        },
        "clause_language": "en",
        "export_docx": False,
    }


# =========================================================
# Package 4 fakes
# =========================================================


class FakeP4ChatService:
    def __init__(
        self,
        *,
        insufficient: bool = False,
    ) -> None:
        self.insufficient = insufficient
        self.calls = 0
        self.last_kwargs = None

    async def aanswer(
        self,
        **kwargs,
    ):
        self.calls += 1
        self.last_kwargs = kwargs

        request_id = (
            kwargs.get("request_id")
            or "request-api-p4-001"
        )

        if self.insufficient:
            response = ValidatedAIResponse(
                request_id=request_id,
                query_id="query-api-p4-001",
                answer=(
                    "Insufficient trusted evidence "
                    "is available to answer this "
                    "question."
                ),
                citations=[],
                confidence=0.0,
                insufficient_evidence=True,
                grounding_valid=False,
                citations_valid=True,
                structured_output_valid=True,
                unsupported_claims=[],
                validation_errors=[],
                model_tag="not-invoked",
                prompt_version=(
                    "p4-insufficient-evidence-v1"
                ),
            )

            generation_invoked = False

        else:
            response = ValidatedAIResponse(
                request_id=request_id,
                query_id="query-api-p4-001",
                answer=(
                    "Article 157 governs the "
                    "relevant obligation. [E1]"
                ),
                citations=[
                    Citation(
                        evidence_id="E1",
                        document_id="law-001",
                        chunk_id="chunk-001",
                        page=15,
                        section="Article 157",
                    )
                ],
                confidence=0.93,
                insufficient_evidence=False,
                grounding_valid=True,
                citations_valid=True,
                structured_output_valid=True,
                unsupported_claims=[],
                validation_errors=[],
                model_tag="qwen-test",
                prompt_version="p4-test-v1",
            )

            generation_invoked = True

        return SimpleNamespace(
            response=response,
            metrics=SimpleNamespace(
                retrieval_ms=10.0,
                evidence_count=(
                    0
                    if self.insufficient
                    else 1
                ),
                generation_invoked=(
                    generation_invoked
                ),
                citation_count=(
                    len(response.citations)
                ),
            ),
        )


class FailingP4ChatService:
    def __init__(
        self,
        error: Exception,
    ) -> None:
        self.error = error
        self.calls = 0

    async def aanswer(
        self,
        **kwargs,
    ):
        self.calls += 1
        raise self.error


def make_p4_app(
    service: FakeP4ChatService,
):
    return create_app(
        rag_service_factory=(
            lambda: FakeRAGService()
        ),
        raw_rag_service_factory=(
            lambda _rag: FakeRawRAGService()
        ),
        p4_chat_service_factory=(
            lambda _rag, _raw: service
        ),
    )


# =========================================================
# Package 3 API tests
# =========================================================


def test_p3_returns_503_without_runtime():
    app = create_app()

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/p3/generate",
            headers=IDENTITY_HEADERS,
            json=p3_request_json(),
        )

    assert response.status_code == 503


def test_p3_generation_success(
    tmp_path: Path,
):
    service = FakeP3GenerationService()

    app = make_p3_app(
        service,
        tmp_path,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/p3/generate",
            headers=IDENTITY_HEADERS,
            json=p3_request_json(),
        )

    assert response.status_code == 200

    payload = response.json()

    assert (
        payload["validated_draft"]
        ["validation"]
        ["is_valid"]
        is True
    )

    assert (
        payload["selected_clause_ids"]
        == ["CLZ-TERM-EG-001"]
    )

    assert (
        payload["export_allowed"]
        is True
    )

    assert (
        payload["m5_resolved_clause_count"]
        == 1
    )

    assert (
        payload["docx_generated"]
        is False
    )

    assert service.calls == 1

    assert (
        service
        .last_kwargs["request"]
        .request_id
        == "REQ-API-P3-001"
    )

    assert (
        service
        .last_kwargs["clause_language"]
        == "en"
    )

    assert (
        service
        .last_kwargs["active_conditions"]
        == []
    )

    assert (
        service
        .last_kwargs["optional_clause_ids"]
        == []
    )

    assert (
        service
        .last_kwargs["docx_path"]
        is None
    )


def test_p3_requires_caller_identity(
    tmp_path: Path,
):
    service = FakeP3GenerationService()

    app = make_p3_app(
        service,
        tmp_path,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/p3/generate",
            json=p3_request_json(),
        )

    assert response.status_code == 401
    assert service.calls == 0


def test_p3_invalid_generation_maps_to_400(
    tmp_path: Path,
):
    service = FakeP3GenerationService(
        error=P3GenerationIntegrationError(
            "private generation diagnostic"
        )
    )

    app = make_p3_app(
        service,
        tmp_path,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/p3/generate",
            headers=IDENTITY_HEADERS,
            json=p3_request_json(),
        )

    assert response.status_code == 400

    assert (
        "private generation diagnostic"
        not in str(response.json())
    )


# =========================================================
# Package 4 API tests
# =========================================================


def test_p4_returns_503_without_runtime():
    app = create_app()

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/p4/chat",
            headers=IDENTITY_HEADERS,
            json={
                "question": (
                    "What does Article 157 say?"
                )
            },
        )

    assert response.status_code == 503


def test_p4_applies_server_derived_access_scope():
    service = FakeP4ChatService()

    app = make_p4_app(service)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/p4/chat",
            headers=IDENTITY_HEADERS,
            json={
                "question": (
                    "What does Article 157 say?"
                ),
                "filters": {
                    "jurisdiction": "Egypt"
                },
            },
        )

    assert response.status_code == 200
    assert service.calls == 1

    filters = (
        service
        .last_kwargs["filters"]
    )

    assert filters.access is not None

    assert (
        filters.access.client_id
        == TEST_CLIENT_ID
    )

    assert (
        filters.access
        .max_confidentiality
        == "privileged"
    )

    assert (
        filters.jurisdiction
        == "Egypt"
    )

    payload = response.json()

    assert (
        payload["query_id"]
        == "query-api-p4-001"
    )

    assert (
        payload["grounding_valid"]
        is True
    )

    assert (
        payload["insufficient_evidence"]
        is False
    )

    assert len(
        payload["citations"]
    ) == 1

    assert (
        payload["citations"][0]
        ["document_id"]
        == "law-001"
    )


def test_p4_rejects_client_supplied_access_scope():
    service = FakeP4ChatService()

    app = make_p4_app(service)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/p4/chat",
            headers=IDENTITY_HEADERS,
            json={
                "question": (
                    "What does Article 157 say?"
                ),
                "filters": {
                    "access": {
                        "client_id": "attacker",
                        "max_confidentiality": (
                            "public"
                        ),
                        "include_shared_corpus": (
                            True
                        ),
                    }
                },
            },
        )

    assert response.status_code == 400
    assert service.calls == 0


def test_p4_insufficient_evidence_remains_200():
    service = FakeP4ChatService(
        insufficient=True
    )

    app = make_p4_app(service)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/p4/chat",
            headers=IDENTITY_HEADERS,
            json={
                "question": (
                    "What is the unknown rule?"
                )
            },
        )

    assert response.status_code == 200

    payload = response.json()

    assert (
        payload["insufficient_evidence"]
        is True
    )

    assert payload["citations"] == []

    assert (
        payload["grounding_valid"]
        is False
    )

    assert service.calls == 1


def _assert_p4_chat_validation_failure_is_generic(
    error: Exception,
    private_diagnostic: str,
) -> None:
    service = FailingP4ChatService(
        error
    )

    app = make_p4_app(service)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/p4/chat",
            headers=IDENTITY_HEADERS,
            json={
                "question": (
                    "What does Article 157 say?"
                )
            },
        )

    assert response.status_code == 502

    payload = response.json()

    assert (
        payload["error"]["code"]
        == "HTTP_ERROR"
    )

    assert (
        payload["error"]["message"]
        == (
            "Package 4 could not produce "
            "a valid grounded response."
        )
    )

    assert payload["error"]["request_id"]

    assert (
        private_diagnostic
        not in response.text
    )

    assert service.calls == 1


def test_p4_chat_malformed_model_output_fails_closed():
    private_diagnostic = (
        "private malformed-output diagnostic"
    )

    _assert_p4_chat_validation_failure_is_generic(
        M4LLMInvocationError(
            private_diagnostic
        ),
        private_diagnostic,
    )


def test_p4_chat_citation_failure_fails_closed():
    private_diagnostic = (
        "private citation diagnostic"
    )

    _assert_p4_chat_validation_failure_is_generic(
        CitationValidationError(
            private_diagnostic
        ),
        private_diagnostic,
    )


def test_p4_chat_grounding_failure_fails_closed():
    private_diagnostic = (
        "private grounding diagnostic"
    )

    _assert_p4_chat_validation_failure_is_generic(
        P4GroundingValidationError(
            private_diagnostic
        ),
        private_diagnostic,
    )


@pytest.mark.parametrize(
    "exception_type, private_diagnostic",
    [
        (
            M2QueryRuntimeError,
            "private M2 runtime diagnostic",
        ),
        (
            RerankerUnavailable,
            "private reranker diagnostic",
        ),
        (
            M4LLMConnectionError,
            "private Ollama connection diagnostic",
        ),
        (
            P4RetrievalPolicyError,
            "private retrieval-policy diagnostic",
        ),
    ],
)
def test_p4_chat_runtime_failure_returns_generic_503(
    exception_type,
    private_diagnostic: str,
) -> None:
    service = FailingP4ChatService(
        exception_type(
            private_diagnostic
        )
    )

    app = make_p4_app(service)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/p4/chat",
            headers=IDENTITY_HEADERS,
            json={
                "question": (
                    "What does Article 157 say?"
                )
            },
        )

    assert response.status_code == 503

    payload = response.json()

    assert (
        payload["error"]["code"]
        == "HTTP_ERROR"
    )

    assert (
        payload["error"]["message"]
        == (
            "The local Package 4 runtime "
            "is unavailable."
        )
    )

    assert payload["error"]["request_id"]

    assert (
        private_diagnostic
        not in response.text
    )

    assert service.calls == 1


def test_p3_ollama_unavailable_maps_to_503(
    tmp_path: Path,
):
    private_diagnostic = (
        "private ollama connection diagnostic"
    )

    service = FakeP3GenerationService(
        error=M4LLMConnectionError(
            private_diagnostic
        )
    )

    app = make_p3_app(
        service,
        tmp_path,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/p3/generate",
            headers=IDENTITY_HEADERS,
            json=p3_request_json(),
        )

    assert response.status_code == 503

    payload = response.json()

    assert (
        payload["error"]["code"]
        == "HTTP_ERROR"
    )

    assert (
        payload["error"]["message"]
        ==
        "The local Package 3 AI "
        "validation runtime is unavailable."
    )

    assert isinstance(
        payload["error"]["request_id"],
        str,
    )

    assert (
        payload["error"]["request_id"]
    )

    assert (
        private_diagnostic
        not in response.text
    )

    assert service.calls == 1


# =========================================================
# Package 3 export download tests
# =========================================================


def make_p3_export_app(
    export_dir,
):
    app = create_app(
        api_security_settings=(
            APISecuritySettings(
                environment="development",
                trusted_host_enforcement=False,
            )
        )
    )

    runtime = P3APIRuntime(
        service=object(),
        export_dir=export_dir,
    )

    app.dependency_overrides[
        get_p3_generation_runtime
    ] = lambda: runtime

    return app


def test_p3_export_download_returns_docx(
    tmp_path,
):
    file_name = (
        "0123456789abcdef"
        "0123456789abcdef.docx"
    )

    expected = (
        b"PK\x03\x04synthetic-p3-docx"
    )

    (
        tmp_path / file_name
    ).write_bytes(
        expected
    )

    app = make_p3_export_app(
        tmp_path
    )

    with TestClient(app) as client:
        response = client.get(
            (
                "/api/v1/p3/exports/"
                + file_name
            ),
            headers=IDENTITY_HEADERS,
        )

    assert response.status_code == 200

    assert response.content == expected

    assert (
        response.headers["content-type"]
        ==
        "application/"
        "vnd.openxmlformats-officedocument."
        "wordprocessingml.document"
    )

    disposition = (
        response.headers[
            "content-disposition"
        ]
    )

    assert "attachment" in disposition

    assert file_name in disposition


def test_p3_export_download_missing_file_returns_404(
    tmp_path,
):
    app = make_p3_export_app(
        tmp_path
    )

    with TestClient(app) as client:
        response = client.get(
            (
                "/api/v1/p3/exports/"
                "missing.docx"
            ),
            headers=IDENTITY_HEADERS,
        )

    assert response.status_code == 404


def test_p3_export_download_rejects_unsafe_names(
    tmp_path,
):
    outside = (
        tmp_path.parent
        / "secret.docx"
    )

    outside.write_bytes(
        b"must-not-be-served"
    )

    app = make_p3_export_app(
        tmp_path
    )

    with TestClient(app) as client:
        wrong_extension = client.get(
            (
                "/api/v1/p3/exports/"
                "secret.pdf"
            ),
            headers=IDENTITY_HEADERS,
        )

        traversal = client.get(
            (
                "/api/v1/p3/exports/"
                "..%5Csecret.docx"
            ),
            headers=IDENTITY_HEADERS,
        )

    assert (
        wrong_extension.status_code
        == 404
    )

    assert traversal.status_code == 404

    assert (
        b"must-not-be-served"
        not in traversal.content
    )


def test_p3_export_download_requires_identity(
    tmp_path,
):
    file_name = "protected.docx"

    (
        tmp_path / file_name
    ).write_bytes(
        b"protected"
    )

    app = make_p3_export_app(
        tmp_path
    )

    with TestClient(app) as client:
        response = client.get(
            (
                "/api/v1/p3/exports/"
                + file_name
            )
        )

    assert response.status_code != 200

    assert (
        "X-Client-Id"
        in response.text
    )
