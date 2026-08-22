from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.dependencies import (
    get_m4_orchestration_service,
)
from src.orchestration import (
    M4LLMConnectionError,
    M4LLMInvocationError,
)
from src.schemas import (
    AIResponse,
    Citation,
)


def make_request_body() -> dict:
    return {
        "processed_query": {
            "query_id": "query_001",
            "text_original": (
                "What notice is required?"
            ),
            "normalized_text": (
                "what notice is required"
            ),
            "language": "en",
            "embedding": [
                0.1,
                0.2,
                0.3,
            ],
            "sparse_embedding": None,
            "filters": {
                "document_type": "contract",
                "jurisdiction": "Egypt",
                "language": "en",
                "extra_filters": {},
            },
        },
        "retrieved_evidence": {
            "query_id": "query_001",
            "retrieved_evidence": [
                {
                    "document_id": "doc_001",
                    "chunk_id": "chunk_001",
                    "text": (
                        "Thirty days' written "
                        "notice is required."
                    ),
                    "page": 12,
                    "section": "Termination",
                    "language": "en",
                    "score": 0.97,
                }
            ],
        },
    }


class FakeM4Service:
    async def aanswer_search(
        self,
        *,
        processed_query,
        retrieved_evidence,
    ):
        return AIResponse(
            query_id=processed_query.query_id,
            answer=(
                "Thirty days' written notice "
                "is required."
            ),
            citations=[
                Citation(
                    evidence_id="E1",
                    document_id="doc_001",
                    chunk_id="chunk_001",
                    page=12,
                    section="Termination",
                )
            ],
            confidence=0.95,
        )


def test_answer_endpoint_returns_ai_response():
    app = create_app()

    app.dependency_overrides[
        get_m4_orchestration_service
    ] = lambda: FakeM4Service()

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/ai/answer",
            json=make_request_body(),
        )

    assert response.status_code == 200

    payload = response.json()

    assert payload["query_id"] == "query_001"
    assert payload["confidence"] == 0.95

    assert len(
        payload["citations"]
    ) == 1

    assert (
        payload["citations"][0]["document_id"]
        == "doc_001"
    )

    assert (
        payload["citations"][0]["page"]
        == 12
    )


class QueryMismatchM4Service:
    async def aanswer_search(
        self,
        *,
        processed_query,
        retrieved_evidence,
    ):
        raise ValueError(
            "query IDs differ"
        )


def test_answer_endpoint_returns_400_for_mismatched_query():
    app = create_app()

    app.dependency_overrides[
        get_m4_orchestration_service
    ] = lambda: QueryMismatchM4Service()

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/ai/answer",
            json=make_request_body(),
        )

    assert response.status_code == 400


class UnavailableM4Service:
    async def aanswer_search(
        self,
        *,
        processed_query,
        retrieved_evidence,
    ):
        raise M4LLMConnectionError(
            "Ollama unavailable"
        )


def test_answer_endpoint_returns_503_when_ollama_unavailable():
    app = create_app()

    app.dependency_overrides[
        get_m4_orchestration_service
    ] = lambda: UnavailableM4Service()

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/ai/answer",
            json=make_request_body(),
        )

    assert response.status_code == 503

    payload = response.json()

    assert payload["error"]["code"] == (
        "HTTP_ERROR"
    )

    assert payload["error"]["message"] == (
        "The local AI runtime is "
        "currently unavailable."
    )

    assert payload["error"]["request_id"]

    assert (
        response.headers["X-Request-ID"]
        == payload["error"]["request_id"]
    )


class InvalidGenerationM4Service:
    async def aanswer_search(
        self,
        *,
        processed_query,
        retrieved_evidence,
    ):
        raise M4LLMInvocationError(
            "invalid structured output"
        )


def test_answer_endpoint_returns_502_for_generation_failure():
    app = create_app()

    app.dependency_overrides[
        get_m4_orchestration_service
    ] = lambda: InvalidGenerationM4Service()

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/ai/answer",
            json=make_request_body(),
        )

    assert response.status_code == 502


def test_answer_endpoint_rejects_invalid_request():
    app = create_app()

    app.dependency_overrides[
        get_m4_orchestration_service
    ] = lambda: FakeM4Service()

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/ai/answer",
            json={
                "processed_query": {
                    "query_id": "broken"
                }
            },
        )

    assert response.status_code == 422
