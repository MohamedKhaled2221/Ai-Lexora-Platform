from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.health import (
    ReadinessResponse,
)
from src.api.routes import (
    get_readiness_checker,
)


def make_readiness(
    **overrides,
) -> ReadinessResponse:
    values = {
        "status": "ready",
        "ollama_reachable": True,
        "model_available": True,
        "model_name": "qwen3.5:4b",
        "qdrant_reachable": True,
        "qdrant_collection_available": True,
        "qdrant_collection_name": (
            "legal_documents"
        ),
        "rag_runtime_initialized": True,
        "raw_rag_runtime_initialized": True,
        "embedding_runtime_ready": True,
        "embedding_dimension": 1024,
        "expected_embedding_dimension": 1024,
        "detail": None,
    }

    values.update(
        overrides
    )

    return ReadinessResponse(
        **values
    )


class FakeChecker:
    def __init__(
        self,
        readiness: ReadinessResponse,
    ) -> None:
        self.readiness = readiness

    async def check(
        self,
    ) -> ReadinessResponse:
        return self.readiness


def override_checker(
    app,
    readiness: ReadinessResponse,
) -> None:
    app.dependency_overrides[
        get_readiness_checker
    ] = lambda: FakeChecker(
        readiness
    )


def test_health_endpoint():
    app = create_app()

    with TestClient(app) as client:
        response = client.get(
            "/health"
        )

    assert response.status_code == 200

    assert response.json() == {
        "status": "ok"
    }


def test_ready_when_all_components_are_ready():
    app = create_app()

    override_checker(
        app,
        make_readiness(),
    )

    with TestClient(app) as client:
        response = client.get(
            "/ready"
        )

    assert response.status_code == 200

    payload = response.json()

    assert payload["status"] == "ready"
    assert payload["ollama_reachable"] is True
    assert payload["model_available"] is True
    assert payload["qdrant_reachable"] is True

    assert (
        payload[
            "qdrant_collection_available"
        ]
        is True
    )

    assert (
        payload[
            "rag_runtime_initialized"
        ]
        is True
    )
    assert (
    payload[
        "raw_rag_runtime_initialized"
    ]
    is True
    )

    assert (
        payload[
            "embedding_runtime_ready"
        ]
        is True
    )

    assert (
        payload[
            "embedding_dimension"
        ]
        == 1024
    )

    assert (
        payload[
            "expected_embedding_dimension"
        ]
        == 1024
    )

    assert payload["detail"] is None


def test_ready_returns_503_when_ollama_is_down():
    app = create_app()

    override_checker(
        app,
        make_readiness(
            status="not_ready",
            ollama_reachable=False,
            model_available=False,
            detail="Ollama is unreachable.",
        ),
    )

    with TestClient(app) as client:
        response = client.get(
            "/ready"
        )

    assert response.status_code == 503

    payload = response.json()

    assert (
        payload["ollama_reachable"]
        is False
    )


def test_ready_returns_503_when_model_is_missing():
    app = create_app()

    override_checker(
        app,
        make_readiness(
            status="not_ready",
            model_available=False,
            detail=(
                "Configured Ollama model "
                "is unavailable."
            ),
        ),
    )

    with TestClient(app) as client:
        response = client.get(
            "/ready"
        )

    assert response.status_code == 503

    assert (
        response.json()["model_available"]
        is False
    )


def test_ready_returns_503_when_qdrant_is_down():
    app = create_app()

    override_checker(
        app,
        make_readiness(
            status="not_ready",
            qdrant_reachable=False,
            qdrant_collection_available=False,
            detail="Qdrant is unreachable.",
        ),
    )

    with TestClient(app) as client:
        response = client.get(
            "/ready"
        )

    assert response.status_code == 503

    assert (
        response.json()["qdrant_reachable"]
        is False
    )


def test_ready_returns_503_when_collection_is_missing():
    app = create_app()

    override_checker(
        app,
        make_readiness(
            status="not_ready",
            qdrant_collection_available=False,
            detail=(
                "Configured Qdrant collection "
                "is unavailable."
            ),
        ),
    )

    with TestClient(app) as client:
        response = client.get(
            "/ready"
        )

    assert response.status_code == 503

    assert (
        response.json()[
            "qdrant_collection_available"
        ]
        is False
    )


def test_ready_returns_503_when_rag_runtime_is_missing():
    app = create_app()

    override_checker(
        app,
        make_readiness(
            status="not_ready",
            rag_runtime_initialized=False,
            detail=(
                "RAG runtime is not initialized."
            ),
        ),
    )

    with TestClient(app) as client:
        response = client.get(
            "/ready"
        )

    assert response.status_code == 503

    assert (
        response.json()[
            "rag_runtime_initialized"
        ]
        is False
    )
    
def test_ready_returns_503_when_raw_rag_runtime_is_missing():
    app = create_app()

    override_checker(
        app,
        make_readiness(
            status="not_ready",
            raw_rag_runtime_initialized=False,
            embedding_runtime_ready=False,
            embedding_dimension=None,
            detail=(
                "Raw-query RAG runtime "
                "is not initialized.; "
                "M2 embedding runtime "
                "is not ready."
            ),
        ),
    )

    with TestClient(app) as client:
        response = client.get(
            "/ready"
        )

    assert response.status_code == 503

    payload = response.json()

    assert (
        payload[
            "raw_rag_runtime_initialized"
        ]
        is False
    )

    assert (
        payload[
            "embedding_runtime_ready"
        ]
        is False
    )


def test_ready_returns_503_when_embedding_runtime_is_invalid():
    app = create_app()

    override_checker(
        app,
        make_readiness(
            status="not_ready",
            embedding_runtime_ready=False,
            embedding_dimension=768,
            expected_embedding_dimension=1024,
            detail=(
                "M2 embedding runtime "
                "is not ready."
            ),
        ),
    )

    with TestClient(app) as client:
        response = client.get(
            "/ready"
        )

    assert response.status_code == 503

    payload = response.json()

    assert (
        payload[
            "embedding_runtime_ready"
        ]
        is False
    )

    assert (
        payload[
            "embedding_dimension"
        ]
        == 768
    )

    assert (
        payload[
            "expected_embedding_dimension"
        ]
        == 1024
    )