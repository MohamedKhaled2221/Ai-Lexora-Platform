from fastapi.testclient import (
    TestClient,
)

from src.api.app import create_app
from src.api.health import (
    ReadinessResponse,
)
from src.api.routes import (
    get_readiness_checker,
)


class FakeReadyChecker:
    async def check(
        self,
    ) -> ReadinessResponse:
        return ReadinessResponse(
            status="ready",
            ollama_reachable=True,
            model_available=True,
            model_name="qwen3.5:4b",
            detail=None,
        )


class FakeNotReadyChecker:
    async def check(
        self,
    ) -> ReadinessResponse:
        return ReadinessResponse(
            status="not_ready",
            ollama_reachable=False,
            model_available=False,
            model_name="qwen3.5:4b",
            detail="Ollama unavailable",
        )


class FakeMissingModelChecker:
    async def check(
        self,
    ) -> ReadinessResponse:
        return ReadinessResponse(
            status="not_ready",
            ollama_reachable=True,
            model_available=False,
            model_name="qwen3.5:4b",
            detail=(
                "Configured model is not "
                "installed in Ollama"
            ),
        )


def test_health_endpoint():
    app = create_app()

    with TestClient(
        app
    ) as client:
        response = client.get(
            "/health"
        )

    assert response.status_code == 200

    assert response.json() == {
        "status": "ok"
    }


def test_ready_endpoint_when_runtime_is_ready():
    app = create_app()

    app.dependency_overrides[
        get_readiness_checker
    ] = lambda: FakeReadyChecker()

    with TestClient(
        app
    ) as client:
        response = client.get(
            "/ready"
        )

    assert response.status_code == 200

    assert response.json() == {
        "status": "ready",
        "ollama_reachable": True,
        "model_available": True,
        "model_name": "qwen3.5:4b",
        "detail": None,
    }


def test_ready_returns_503_when_ollama_is_unavailable():
    app = create_app()

    app.dependency_overrides[
        get_readiness_checker
    ] = lambda: FakeNotReadyChecker()

    with TestClient(
        app
    ) as client:
        response = client.get(
            "/ready"
        )

    assert response.status_code == 503

    payload = response.json()

    assert payload["status"] == "not_ready"
    assert payload["ollama_reachable"] is False
    assert payload["model_available"] is False


def test_ready_returns_503_when_model_is_missing():
    app = create_app()

    app.dependency_overrides[
        get_readiness_checker
    ] = lambda: FakeMissingModelChecker()

    with TestClient(
        app
    ) as client:
        response = client.get(
            "/ready"
        )

    assert response.status_code == 503

    payload = response.json()

    assert payload["status"] == "not_ready"
    assert payload["ollama_reachable"] is True
    assert payload["model_available"] is False
    assert payload["model_name"] == "qwen3.5:4b"
