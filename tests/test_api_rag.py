from fastapi.testclient import TestClient

from src.api.app import create_app
from src.schemas import (
    AIResponse,
    Citation,
)


def make_request_body() -> dict:
    return {
        "processed_query": {
            "query_id": "query_001",
            "text_original": (
                "What are the termination conditions?"
            ),
            "normalized_text": (
                "what are the termination conditions"
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
        }
    }


class FakeRAGService:
    async def aanswer(
        self,
        processed_query,
    ):
        return AIResponse(
            query_id=processed_query.query_id,
            answer=(
                "Termination is allowed after "
                "the stated contractual conditions."
            ),
            citations=[
                Citation(
                    evidence_id="E1",
                    document_id="doc_001",
                    chunk_id="chunk_017",
                    page=12,
                    section="Termination",
                )
            ],
            confidence=0.95,
        )


def test_rag_answer_endpoint():
    app = create_app(
        rag_service_factory=(
            lambda: FakeRAGService()
        )
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/rag/answer",
            json=make_request_body(),
        )

    assert response.status_code == 200

    payload = response.json()

    assert payload["query_id"] == "query_001"
    assert payload["confidence"] == 0.95

    assert (
        payload["citations"][0]["chunk_id"]
        == "chunk_017"
    )


def test_rag_endpoint_returns_503_without_runtime():
    app = create_app()

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/rag/answer",
            json=make_request_body(),
        )

    assert response.status_code == 503

    assert response.json() == {
        "detail": (
            "The RAG runtime is not initialized."
        )
    }


def test_rag_endpoint_rejects_invalid_request():
    app = create_app(
        rag_service_factory=(
            lambda: FakeRAGService()
        )
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/rag/answer",
            json={
                "processed_query": {
                    "query_id": "broken"
                }
            },
        )

    assert response.status_code == 422
