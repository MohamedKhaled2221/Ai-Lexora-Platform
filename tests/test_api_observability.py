import logging

from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.dependencies import (
    get_rag_service,
)

from src.orchestration import (
    M4LLMConnectionError,
    RAGExecutionMetrics,
    RAGExecutionResult,
)
from src.schemas import (
    AIResponse,
    Citation,
)


def make_observability_rag_request() -> dict:
    return {
        "processed_query": {
            "query_id": "obs_query_001",
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


class MetricsRAGService:
    async def aanswer_with_metrics(
        self,
        processed_query,
    ):
        response = AIResponse(
            query_id=processed_query.query_id,
            answer=(
                "Termination is allowed under "
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

        return RAGExecutionResult(
            response=response,
            metrics=RAGExecutionMetrics(
                retrieval_ms=50.0,
                generation_ms=120.0,
                total_rag_ms=171.0,
                retrieved_chunk_count=3,
                citation_count=1,
            ),
        )


class UnavailableMetricsRAGService:
    async def aanswer_with_metrics(
        self,
        processed_query,
    ):
        raise M4LLMConnectionError(
            "sensitive internal Ollama detail"
        )


def test_response_contains_request_id():
    app = create_app()

    with TestClient(app) as client:
        response = client.get(
            "/health"
        )

    assert response.status_code == 200

    request_id = response.headers.get(
        "X-Request-ID"
    )

    assert request_id
    assert len(request_id) == 32


def test_unknown_route_uses_common_error_format():
    app = create_app()

    with TestClient(app) as client:
        response = client.get(
            "/does-not-exist"
        )

    assert response.status_code == 404

    payload = response.json()

    assert payload["error"]["code"] == (
        "NOT_FOUND"
    )

    assert (
        payload["error"]["message"]
        == "Not Found"
    )

    assert payload["error"]["request_id"]

    assert (
        response.headers["X-Request-ID"]
        == payload["error"]["request_id"]
    )


def test_validation_error_uses_common_format():
    app = create_app()

    # This test is about request validation, not
    # RAG runtime availability. Bypass that dependency
    # so malformed input reaches Pydantic validation.
    app.dependency_overrides[
        get_rag_service
    ] = lambda: object()

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

    payload = response.json()

    assert (
        payload["error"]["code"]
        == "VALIDATION_ERROR"
    )

    assert payload["error"]["message"] == (
        "The request payload is invalid."
    )

    assert payload["error"]["request_id"]

    assert (
        response.headers["X-Request-ID"]
        == payload["error"]["request_id"]
    )

def test_unexpected_error_is_sanitized(
    caplog,
):
    app = create_app()

    @app.get(
        "/test-internal-error"
    )
    async def test_internal_error():
        raise RuntimeError(
            "secret internal diagnostic"
        )

    caplog.set_level(
        logging.ERROR,
        logger="ai_lexora.errors",
    )

    with TestClient(
        app,
        raise_server_exceptions=False,
    ) as client:
        response = client.get(
            "/test-internal-error"
        )

    assert response.status_code == 500

    payload = response.json()

    assert (
        payload["error"]["code"]
        == "INTERNAL_ERROR"
    )

    assert (
        "secret internal diagnostic"
        not in str(payload)
    )

    records = [
        record
        for record in caplog.records
        if (
            record.name
            == "ai_lexora.errors"
            and record.getMessage()
            == "unexpected_api_error"
        )
    ]

    assert len(records) == 1

    record = records[0]

    assert (
        record.error_type
        == "RuntimeError"
    )

    assert (
        record.request_id
        == response.headers[
            "X-Request-ID"
        ]
    )

    assert record.exc_info is None

    assert (
        "secret internal diagnostic"
        not in caplog.text
    )

def test_http_log_contains_safe_metadata(
    caplog,
):
    app = create_app()

    caplog.set_level(
        logging.INFO,
        logger="ai_lexora.http",
    )

    with TestClient(app) as client:
        response = client.get(
            "/health"
        )

    assert response.status_code == 200

    records = [
        record
        for record in caplog.records
        if (
            record.name
            == "ai_lexora.http"
            and record.getMessage()
            == "http_request_completed"
        )
    ]

    assert len(records) == 1

    record = records[0]

    assert record.http_method == "GET"
    assert record.http_path == "/health"
    assert record.status_code == 200

    assert record.duration_ms >= 0

    assert (
        record.request_id
        == response.headers[
            "X-Request-ID"
        ]
    )
    
def test_rag_success_log_contains_safe_metrics(
    caplog,
):
    app = create_app(
        rag_service_factory=(
            lambda: MetricsRAGService()
        )
    )

    caplog.set_level(
        logging.INFO,
        logger="src.api.rag_routes",
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/rag/answer",
            json=(
                make_observability_rag_request()
            ),
        )

    assert response.status_code == 200

    records = [
        record
        for record in caplog.records
        if (
            record.name
            == "src.api.rag_routes"
            and record.getMessage()
            == "rag_request_completed"
        )
    ]

    assert len(records) == 1

    record = records[0]

    assert (
        record.query_id
        == "obs_query_001"
    )

    assert record.retrieval_ms == 50.0
    assert record.generation_ms == 120.0
    assert record.total_rag_ms == 171.0

    assert (
        record.retrieved_chunk_count
        == 3
    )

    assert record.citation_count == 1

    assert record.status == "success"

    assert (
        record.request_id
        == response.headers[
            "X-Request-ID"
        ]
    )

    assert not hasattr(
        record,
        "question",
    )

    assert not hasattr(
        record,
        "normalized_text",
    )

    assert not hasattr(
        record,
        "evidence",
    )

    assert not hasattr(
        record,
        "embedding",
    )

    assert not hasattr(
        record,
        "answer",
    )
    
def test_rag_failure_log_is_sanitized(
    caplog,
):
    app = create_app(
        rag_service_factory=(
            lambda: (
                UnavailableMetricsRAGService()
            )
        )
    )

    caplog.set_level(
        logging.ERROR,
        logger="src.api.rag_routes",
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/rag/answer",
            json=(
                make_observability_rag_request()
            ),
        )

    assert response.status_code == 503

    records = [
        record
        for record in caplog.records
        if (
            record.name
            == "src.api.rag_routes"
            and record.getMessage()
            == "rag_request_failed"
        )
    ]

    assert len(records) == 1

    record = records[0]

    assert (
        record.query_id
        == "obs_query_001"
    )

    assert record.status == "failure"

    assert (
        record.failure_stage
        == "generation"
    )

    assert (
        record.error_type
        == "M4LLMConnectionError"
    )

    assert (
        record.request_id
        == response.headers[
            "X-Request-ID"
        ]
    )

    assert not hasattr(
        record,
        "error_message",
    )

    assert not hasattr(
        record,
        "question",
    )

    assert not hasattr(
        record,
        "evidence",
    )

    assert not hasattr(
        record,
        "embedding",
    )

    assert not hasattr(
        record,
        "answer",
    )

    assert (
        "sensitive internal Ollama detail"
        not in record.getMessage()
    )
