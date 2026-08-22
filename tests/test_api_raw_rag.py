import logging

from fastapi.testclient import (
    TestClient,
)

from src.api.app import create_app
from src.orchestration import (
    M2EmbeddingContractError,
    M2QueryRuntimeError,
    RAGExecutionMetrics,
    RAGExecutionResult,
)
from src.schemas import AIResponse


class FakeRAGService:
    pass


class FakeRawRAGService:
    def __init__(
        self,
        error: Exception | None = None,
    ) -> None:
        self.error = error
        self.calls = 0
        self.last_question = None
        self.last_filters = None

    async def aanswer_with_metrics(
        self,
        *,
        question,
        filters,
    ) -> RAGExecutionResult:
        self.calls += 1
        self.last_question = question
        self.last_filters = filters

        if self.error is not None:
            raise self.error

        return RAGExecutionResult(
            response=AIResponse(
                query_id="q_api001",
                answer="Grounded answer.",
                citations=[],
                confidence=0.9,
            ),
            metrics=RAGExecutionMetrics(
                retrieval_ms=12.0,
                generation_ms=25.0,
                total_rag_ms=38.0,
                retrieved_chunk_count=3,
                citation_count=0,
            ),
        )


def make_app(
    raw_service: FakeRawRAGService,
):
    return create_app(
        rag_service_factory=(
            lambda: FakeRAGService()
        ),
        raw_rag_service_factory=(
            lambda rag_service: raw_service
        ),
    )


def test_raw_rag_answer_endpoint():
    raw_service = (
        FakeRawRAGService()
    )

    app = make_app(
        raw_service
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/rag/ask",
            json={
                "question": (
                    "ما هي شروط الفسخ؟"
                ),
                "filters": {
                    "document_type": (
                        "contract"
                    ),
                    "jurisdiction": (
                        "Egypt"
                    ),
                },
            },
        )

    assert response.status_code == 200

    assert (
        response.json()["query_id"]
        == "q_api001"
    )

    assert raw_service.calls == 1

    assert (
        raw_service.last_question
        == "ما هي شروط الفسخ؟"
    )

    assert (
        raw_service
        .last_filters
        .document_type
        == "contract"
    )

    assert (
        raw_service
        .last_filters
        .jurisdiction
        == "Egypt"
    )

    assert (
        raw_service
        .last_filters
        .language
        is None
    )


def test_raw_rag_rejects_whitespace_question():
    raw_service = (
        FakeRawRAGService()
    )

    app = make_app(
        raw_service
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/rag/ask",
            json={
                "question": "   "
            },
        )

    assert response.status_code == 422
    assert raw_service.calls == 0


def test_raw_rag_returns_503_without_runtime():
    app = create_app()

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/rag/ask",
            json={
                "question": (
                    "What is Article 69?"
                )
            },
        )

    assert response.status_code == 503

    assert (
        response
        .json()["error"]["message"]
        == (
            "The raw-query RAG runtime "
            "is not initialized."
        )
    )


def test_raw_rag_maps_embedding_contract_failure_to_502():
    app = make_app(
        FakeRawRAGService(
            error=M2EmbeddingContractError(
                "private dimension diagnostic"
            )
        )
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/rag/ask",
            json={
                "question": (
                    "What is Article 69?"
                )
            },
        )

    assert response.status_code == 502

    assert (
        "private dimension diagnostic"
        not in str(
            response.json()
        )
    )


def test_raw_rag_maps_m2_runtime_failure_to_503():
    app = make_app(
        FakeRawRAGService(
            error=M2QueryRuntimeError(
                "secret model runtime diagnostic"
            )
        )
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/rag/ask",
            json={
                "question": (
                    "What is Article 69?"
                )
            },
        )

    assert response.status_code == 503

    assert (
        "secret model runtime diagnostic"
        not in str(
            response.json()
        )
    )


def test_raw_rag_logging_does_not_include_question(
    caplog,
):
    question = (
        "CONFIDENTIAL LEGAL QUESTION 8675309"
    )

    raw_service = (
        FakeRawRAGService()
    )

    app = make_app(
        raw_service
    )

    caplog.set_level(
        logging.INFO,
        logger="src.api.rag_routes",
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/rag/ask",
            json={
                "question": question
            },
        )

    assert response.status_code == 200
    assert question not in caplog.text


def test_raw_rag_factory_is_initialized_once():
    raw_service = (
        FakeRawRAGService()
    )

    factory_calls = 0

    def raw_factory(
        rag_service,
    ):
        nonlocal factory_calls

        factory_calls += 1

        return raw_service

    app = create_app(
        rag_service_factory=(
            lambda: FakeRAGService()
        ),
        raw_rag_service_factory=(
            raw_factory
        ),
    )

    with TestClient(app) as client:
        first = client.post(
            "/api/v1/rag/ask",
            json={
                "question": (
                    "First question"
                )
            },
        )

        second = client.post(
            "/api/v1/rag/ask",
            json={
                "question": (
                    "Second question"
                )
            },
        )

    assert first.status_code == 200
    assert second.status_code == 200

    assert factory_calls == 1
    assert raw_service.calls == 2
