"""
Shared access-control fixtures for tests.

Retrieval now refuses to run without an access scope, and stored points are
invisible unless they carry an ACL. Both facts are load-bearing security
behaviour, so tests that are not *about* access control should not each
hand-roll their own scope -- they should take the default one from here, and a
future change to the ACL shape should mean editing this file rather than
hunting through the suite.

Use :func:`scoped_filters` in place of a bare ``QueryFilters()``.
"""

from typing import Any

from src.schemas import QueryFilters
from src.schemas.access_control import (
    NO_MATTER_ID,
    SHARED_CLIENT_ID,
    AccessScope,
)


TEST_CLIENT_ID = "client_test"
OTHER_CLIENT_ID = "client_other"
TEST_MATTER_ID = "matter_test"


def access_scope(**overrides: Any) -> AccessScope:
    """
    A permissive-but-real scope: one tenant, every matter, top of the ladder.

    Permissive on purpose. Tests that are not about access control should not
    fail because the default scope was too tight, while tests that *are* about
    it override what they need.
    """

    values: dict[str, Any] = {
        "client_id": TEST_CLIENT_ID,
        "max_confidentiality": "privileged",
    }
    values.update(overrides)

    return AccessScope(**values)


def scoped_filters(**overrides: Any) -> QueryFilters:
    """
    ``QueryFilters`` carrying a valid access scope.

    The drop-in replacement for a bare ``QueryFilters()``. Pass ``access=...``
    to override the scope, or any other QueryFilters field as usual.
    """

    values: dict[str, Any] = {"access": access_scope()}
    values.update(overrides)

    return QueryFilters(**values)


def acl_payload(
    *,
    client_id: str = TEST_CLIENT_ID,
    matter_id: str = NO_MATTER_ID,
    confidentiality_level: str = "internal",
) -> dict[str, Any]:
    """
    The ACL keys a stored Qdrant point needs to be visible to
    :func:`access_scope`.

    Spread into a fixture payload: ``{"document_id": ..., **acl_payload()}``.
    """

    return {
        "client_id": client_id,
        "matter_id": matter_id,
        "confidentiality_level": confidentiality_level,
    }


def shared_corpus_payload(
    *,
    confidentiality_level: str = "public",
) -> dict[str, Any]:
    """ACL keys for a cross-tenant document (statute, ruling, template)."""

    return acl_payload(
        client_id=SHARED_CLIENT_ID,
        confidentiality_level=confidentiality_level,
    )


# ---------------------------------------------------------------------------
# API-level identity
# ---------------------------------------------------------------------------


def identity_headers(
    *,
    client_id: str = TEST_CLIENT_ID,
    matter_id: str | None = None,
    max_confidentiality: str = "privileged",
) -> dict[str, str]:
    """
    Headers that satisfy the phase-1 identity dependency.

    Every access-controlled route requires them, so tests that are not about
    identity take the default set from here rather than restating it.
    """

    headers = {
        "X-Client-Id": client_id,
        "X-Confidentiality-Ceiling": max_confidentiality,
    }

    if matter_id is not None:
        headers["X-Matter-Id"] = matter_id

    return headers


IDENTITY_HEADERS = identity_headers()
