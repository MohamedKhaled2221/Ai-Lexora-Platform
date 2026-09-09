"""
Stage 2 coverage: caller identity and the access-control domain types.

The theme of every test here is that the absence of information is never
treated as permission.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.api.identity import (
    CLIENT_ID_HEADER,
    CONFIDENTIALITY_CEILING_HEADER,
    MATTER_ID_HEADER,
    CallerIdentity,
    CallerIdentityDependency,
)
from src.api.security import APISecuritySettings
from src.schemas.access_control import (
    NO_MATTER_ID,
    SHARED_CLIENT_ID,
    AccessControlError,
    AccessScope,
    ChunkACL,
    levels_up_to,
)


def _settings(**overrides) -> APISecuritySettings:
    values = {
        "environment": "development",
        "debug": False,
        "docs_enabled": False,
        "max_request_body_bytes": 1024,
        "trusted_host_enforcement": False,
        "trusted_hosts": ["localhost", "testserver"],
        "cors_allowed_origins": [],
        "cors_allowed_headers": ["Content-Type"],
        "cors_allow_credentials": False,
    }
    values.update(overrides)

    return APISecuritySettings(_env_file=None, **values)


def _identity_app(settings: APISecuritySettings) -> FastAPI:
    app = FastAPI()
    app.state.api_security_settings = settings

    @app.get("/whoami")
    def whoami(identity: CallerIdentityDependency) -> dict:
        scope = identity.to_scope()

        return {
            "client_id": identity.client_id,
            "allowed_client_ids": scope.allowed_client_ids,
            "allowed_levels": scope.allowed_confidentiality_levels,
            "allowed_matter_ids": scope.allowed_matter_ids,
        }

    return app


# ---------------------------------------------------------------------------
# Confidentiality ladder
# ---------------------------------------------------------------------------


def test_ladder_expands_to_every_level_at_or_below_the_ceiling():
    assert levels_up_to("public") == ["public"]
    assert levels_up_to("internal") == ["public", "internal"]
    assert levels_up_to("privileged") == [
        "public",
        "internal",
        "privileged",
    ]


def test_unknown_level_is_rejected_rather_than_silently_empty():
    with pytest.raises(AccessControlError):
        levels_up_to("secret")


# ---------------------------------------------------------------------------
# AccessScope
# ---------------------------------------------------------------------------


def test_scope_includes_shared_corpus_by_default():
    scope = AccessScope(
        client_id="client_042",
        max_confidentiality="internal",
    )

    assert scope.allowed_client_ids == ["client_042", SHARED_CLIENT_ID]


def test_scope_can_exclude_shared_corpus():
    scope = AccessScope(
        client_id="client_042",
        max_confidentiality="internal",
        include_shared_corpus=False,
    )

    assert scope.allowed_client_ids == ["client_042"]


def test_narrowing_to_matters_keeps_client_level_documents_visible():
    scope = AccessScope(
        client_id="client_042",
        matter_ids=["matter_1"],
        max_confidentiality="privileged",
    )

    assert scope.allowed_matter_ids == ["matter_1", NO_MATTER_ID]


def test_no_matter_restriction_means_every_matter():
    scope = AccessScope(
        client_id="client_042",
        max_confidentiality="public",
    )

    assert scope.allowed_matter_ids is None


def test_empty_matter_list_is_rejected():
    """An empty list reads as 'no matters', which no caller ever intends."""

    with pytest.raises(ValidationError):
        AccessScope(
            client_id="client_042",
            matter_ids=[],
            max_confidentiality="public",
        )


def test_caller_cannot_authenticate_as_the_shared_corpus():
    with pytest.raises(ValidationError):
        AccessScope(
            client_id=SHARED_CLIENT_ID,
            max_confidentiality="public",
        )


def test_scope_is_frozen_so_it_cannot_be_widened_in_flight():
    scope = AccessScope(
        client_id="client_042",
        max_confidentiality="public",
    )

    with pytest.raises(ValidationError):
        scope.max_confidentiality = "privileged"


# ---------------------------------------------------------------------------
# AccessScope.permits -- the post-retrieval check
# ---------------------------------------------------------------------------


def test_permits_accepts_own_and_shared_content_within_the_ceiling():
    scope = AccessScope(
        client_id="client_042",
        max_confidentiality="internal",
    )

    assert scope.permits(
        client_id="client_042",
        confidentiality_level="internal",
    )
    assert scope.permits(
        client_id=SHARED_CLIENT_ID,
        confidentiality_level="public",
    )


def test_permits_refuses_another_tenant_and_a_higher_rung():
    scope = AccessScope(
        client_id="client_042",
        max_confidentiality="internal",
    )

    assert not scope.permits(
        client_id="client_999",
        confidentiality_level="public",
    )
    assert not scope.permits(
        client_id="client_042",
        confidentiality_level="privileged",
    )


def test_permits_refuses_unstamped_payloads():
    """An unstamped payload is unverifiable, not unrestricted."""

    scope = AccessScope(
        client_id="client_042",
        max_confidentiality="privileged",
    )

    assert not scope.permits(client_id=None, confidentiality_level="public")
    assert not scope.permits(
        client_id="client_042",
        confidentiality_level=None,
    )


def test_permits_enforces_matter_narrowing():
    scope = AccessScope(
        client_id="client_042",
        matter_ids=["matter_1"],
        max_confidentiality="privileged",
    )

    assert scope.permits(
        client_id="client_042",
        confidentiality_level="public",
        matter_id="matter_1",
    )
    assert scope.permits(
        client_id="client_042",
        confidentiality_level="public",
        matter_id=NO_MATTER_ID,
    )
    assert not scope.permits(
        client_id="client_042",
        confidentiality_level="public",
        matter_id="matter_2",
    )


# ---------------------------------------------------------------------------
# CallerIdentity -> ChunkACL
# ---------------------------------------------------------------------------


def test_identity_without_a_matter_stamps_the_client_level_sentinel():
    identity = CallerIdentity(
        client_id="client_042",
        max_confidentiality="internal",
    )

    acl = identity.to_chunk_acl()

    assert acl == ChunkACL(
        client_id="client_042",
        matter_id=NO_MATTER_ID,
        confidentiality_level="internal",
    )


def test_ingest_may_classify_below_the_ceiling_but_never_above_it():
    identity = CallerIdentity(
        client_id="client_042",
        max_confidentiality="internal",
    )

    assert (
        identity.to_chunk_acl(
            confidentiality_level="public"
        ).confidentiality_level
        == "public"
    )

    with pytest.raises(ValueError):
        identity.to_chunk_acl(confidentiality_level="privileged")


# ---------------------------------------------------------------------------
# The dependency
# ---------------------------------------------------------------------------


def test_header_mode_resolves_identity():
    with TestClient(_identity_app(_settings())) as client:
        response = client.get(
            "/whoami",
            headers={
                CLIENT_ID_HEADER: "client_042",
                MATTER_ID_HEADER: "matter_7",
                CONFIDENTIALITY_CEILING_HEADER: "internal",
            },
        )

    assert response.status_code == 200

    body = response.json()

    assert body["client_id"] == "client_042"
    assert body["allowed_client_ids"] == ["client_042", SHARED_CLIENT_ID]
    assert body["allowed_levels"] == ["public", "internal"]
    assert body["allowed_matter_ids"] == ["matter_7", NO_MATTER_ID]


@pytest.mark.parametrize(
    "headers, expected_status",
    [
        ({}, 401),
        ({CONFIDENTIALITY_CEILING_HEADER: "internal"}, 401),
        ({CLIENT_ID_HEADER: "client_042"}, 401),
        ({CLIENT_ID_HEADER: "   ", CONFIDENTIALITY_CEILING_HEADER: "public"}, 401),
        (
            {
                CLIENT_ID_HEADER: "client_042",
                CONFIDENTIALITY_CEILING_HEADER: "secret",
            },
            400,
        ),
        (
            {
                CLIENT_ID_HEADER: SHARED_CLIENT_ID,
                CONFIDENTIALITY_CEILING_HEADER: "public",
            },
            403,
        ),
    ],
)
def test_incomplete_or_invalid_identity_is_refused(headers, expected_status):
    with TestClient(_identity_app(_settings())) as client:
        response = client.get("/whoami", headers=headers)

    assert response.status_code == expected_status


def test_disabled_identity_mode_fails_closed_with_503():
    """
    No identity provider means serve nothing, not serve everything.
    """

    settings = _settings(identity_mode="disabled")

    with TestClient(_identity_app(settings)) as client:
        response = client.get(
            "/whoami",
            headers={
                CLIENT_ID_HEADER: "client_042",
                CONFIDENTIALITY_CEILING_HEADER: "privileged",
            },
        )

    assert response.status_code == 503


def test_missing_settings_object_fails_closed():
    """A route mounted without security settings must not default to open."""

    app = FastAPI()

    @app.get("/whoami")
    def whoami(identity: CallerIdentityDependency) -> dict:
        return {"client_id": identity.client_id}

    with TestClient(app) as client:
        response = client.get(
            "/whoami",
            headers={
                CLIENT_ID_HEADER: "client_042",
                CONFIDENTIALITY_CEILING_HEADER: "public",
            },
        )

    assert response.status_code == 503


# ---------------------------------------------------------------------------
# The production guard
# ---------------------------------------------------------------------------


def test_production_rejects_header_identity_mode():
    with pytest.raises(
        ValidationError,
        match="Header-based caller identity",
    ):
        _settings(
            environment="production",
            docs_enabled=False,
            trusted_host_enforcement=True,
            trusted_hosts=["localhost"],
            identity_mode="header",
        )


def test_production_accepts_disabled_identity_mode():
    settings = _settings(
        environment="production",
        docs_enabled=False,
        trusted_host_enforcement=True,
        trusted_hosts=["localhost"],
        identity_mode="disabled",
    )

    assert settings.identity_mode == "disabled"


def test_development_defaults_to_header_mode():
    assert _settings().identity_mode == "header"
