import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.api.app import create_app
from src.api.security import (
    APISecuritySettings,
)


def security_values(
    **overrides,
) -> dict:
    values = {
        "environment": "development",
        "debug": False,
        "docs_enabled": False,
        "max_request_body_bytes": 1024,
        "trusted_host_enforcement": False,
        "trusted_hosts": [
            "127.0.0.1",
            "localhost",
            "::1",
        ],
        "cors_allowed_origins": [],
        "cors_allowed_headers": [
            "Content-Type",
        ],
        "cors_allow_credentials": False,
    }

    values.update(
        overrides
    )

    return values


def make_security_settings(
    **overrides,
) -> APISecuritySettings:
    return APISecuritySettings(
        _env_file=None,
        **security_values(
            **overrides
        ),
    )


def test_security_headers_are_added():
    app = create_app(
        api_security_settings=(
            make_security_settings()
        )
    )

    with TestClient(app) as client:
        response = client.get(
            "/health"
        )

    assert response.status_code == 200

    assert (
        response.headers[
            "X-Content-Type-Options"
        ]
        == "nosniff"
    )

    assert (
        response.headers[
            "X-Frame-Options"
        ]
        == "DENY"
    )

    assert (
        response.headers[
            "Referrer-Policy"
        ]
        == "no-referrer"
    )

    assert (
        response.headers[
            "Permissions-Policy"
        ]
        == (
            "camera=(), microphone=(), "
            "geolocation=()"
        )
    )

    assert (
        response.headers[
            "Cache-Control"
        ]
        == "no-store"
    )

    assert (
        "X-Request-ID"
        in response.headers
    )


def test_request_body_limit_returns_413():
    app = create_app(
        api_security_settings=(
            make_security_settings(
                max_request_body_bytes=1024
            )
        )
    )

    @app.post(
        "/test-body-limit"
    )
    async def test_body_limit(
        payload: dict,
    ):
        return payload

    with TestClient(app) as client:
        response = client.post(
            "/test-body-limit",
            content=b"x" * 1025,
            headers={
                "Content-Type": (
                    "application/json"
                )
            },
        )

    assert response.status_code == 413

    payload = response.json()

    assert (
        payload["error"]["code"]
        == "REQUEST_TOO_LARGE"
    )

    assert (
        payload["error"]["message"]
        == (
            "The request body exceeds "
            "the configured size limit."
        )
    )

    assert (
        payload["error"]["request_id"]
        == response.headers[
            "X-Request-ID"
        ]
    )


def test_request_below_limit_is_replayed():
    app = create_app(
        api_security_settings=(
            make_security_settings(
                max_request_body_bytes=1024
            )
        )
    )

    @app.post(
        "/test-small-body"
    )
    async def test_small_body(
        payload: dict,
    ):
        return payload

    with TestClient(app) as client:
        response = client.post(
            "/test-small-body",
            json={
                "value": "safe"
            },
        )

    assert response.status_code == 200

    assert response.json() == {
        "value": "safe"
    }


def test_trusted_host_rejects_unknown_host():
    app = create_app(
        api_security_settings=(
            make_security_settings(
                trusted_host_enforcement=True,
                trusted_hosts=[
                    "localhost",
                ],
            )
        )
    )

    with TestClient(app) as client:
        response = client.get(
            "/health",
            headers={
                "Host": "evil.example",
            },
        )

    assert response.status_code == 400

    payload = response.json()

    assert (
        payload["error"]["code"]
        == "INVALID_HOST"
    )

    assert (
        payload["error"]["request_id"]
        == response.headers[
            "X-Request-ID"
        ]
    )


def test_trusted_host_allows_configured_host():
    app = create_app(
        api_security_settings=(
            make_security_settings(
                trusted_host_enforcement=True,
                trusted_hosts=[
                    "localhost",
                ],
            )
        )
    )

    with TestClient(app) as client:
        response = client.get(
            "/health",
            headers={
                "Host": "localhost",
            },
        )

    assert response.status_code == 200


def test_cors_allows_only_configured_origin():
    allowed_origin = (
        "http://127.0.0.1:5500"
    )

    app = create_app(
        api_security_settings=(
            make_security_settings(
                cors_allowed_origins=[
                    allowed_origin,
                ]
            )
        )
    )

    with TestClient(app) as client:
        allowed_response = client.get(
            "/health",
            headers={
                "Origin": allowed_origin,
            },
        )

        denied_response = client.get(
            "/health",
            headers={
                "Origin": (
                    "http://evil.example"
                ),
            },
        )

    assert (
        allowed_response.headers[
            "Access-Control-Allow-Origin"
        ]
        == allowed_origin
    )

    assert (
        "Access-Control-Allow-Origin"
        not in denied_response.headers
    )


def test_cors_preflight_for_allowed_origin():
    allowed_origin = (
        "http://127.0.0.1:5500"
    )

    app = create_app(
        api_security_settings=(
            make_security_settings(
                cors_allowed_origins=[
                    allowed_origin,
                ]
            )
        )
    )

    with TestClient(app) as client:
        response = client.options(
            "/health",
            headers={
                "Origin": allowed_origin,
                (
                    "Access-Control-"
                    "Request-Method"
                ): "GET",
            },
        )

    assert response.status_code == 200

    assert (
        response.headers[
            "Access-Control-Allow-Origin"
        ]
        == allowed_origin
    )


def test_production_disables_docs_by_default():
    settings = (
        make_security_settings(
            environment="production",
            docs_enabled=None,
            trusted_host_enforcement=None,
            trusted_hosts=[
                "localhost",
            ],
        )
    )

    app = create_app(
        api_security_settings=settings
    )

    with TestClient(app) as client:
        docs_response = client.get(
            "/docs",
            headers={
                "Host": "localhost",
            },
        )

        redoc_response = client.get(
            "/redoc",
            headers={
                "Host": "localhost",
            },
        )

        openapi_response = client.get(
            "/openapi.json",
            headers={
                "Host": "localhost",
            },
        )

    assert (
        docs_response.status_code
        == 404
    )

    assert (
        redoc_response.status_code
        == 404
    )

    assert (
        openapi_response.status_code
        == 404
    )


def test_production_rejects_debug_mode():
    with pytest.raises(
        ValidationError,
        match=(
            "API debug mode must be "
            "disabled in production"
        ),
    ):
        APISecuritySettings(
            _env_file=None,
            **security_values(
                environment="production",
                debug=True,
                docs_enabled=False,
                trusted_host_enforcement=True,
                trusted_hosts=[
                    "localhost",
                ],
            ),
        )


def test_production_rejects_enabled_docs():
    with pytest.raises(
        ValidationError,
        match=(
            "API documentation must be "
            "disabled in production"
        ),
    ):
        APISecuritySettings(
            _env_file=None,
            **security_values(
                environment="production",
                docs_enabled=True,
                trusted_host_enforcement=True,
                trusted_hosts=[
                    "localhost",
                ],
            ),
        )


def test_production_rejects_disabled_host_protection():
    with pytest.raises(
        ValidationError,
        match=(
            "Trusted-host enforcement "
            "cannot be disabled"
        ),
    ):
        APISecuritySettings(
            _env_file=None,
            **security_values(
                environment="production",
                docs_enabled=False,
                trusted_host_enforcement=False,
                trusted_hosts=[
                    "localhost",
                ],
            ),
        )


def test_production_rejects_wildcard_cors():
    with pytest.raises(
        ValidationError,
        match="Wildcard CORS origins",
    ):
        APISecuritySettings(
            _env_file=None,
            **security_values(
                environment="production",
                docs_enabled=False,
                trusted_host_enforcement=True,
                trusted_hosts=[
                    "localhost",
                ],
                cors_allowed_origins=[
                    "*",
                ],
            ),
        )


def test_wildcard_trusted_host_is_rejected():
    with pytest.raises(
        ValidationError,
        match="Wildcard trusted hosts",
    ):
        APISecuritySettings(
            _env_file=None,
            **security_values(
                trusted_host_enforcement=True,
                trusted_hosts=[
                    "*",
                ],
            ),
        )
