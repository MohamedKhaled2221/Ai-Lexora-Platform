"""
Caller identity for the AI-Lexora API.

Before this module existed there was no identity in the request path at all:
``src.api.security`` is transport-only (trusted host, body limit, security
headers, CORS), and the only per-request state was the observability
request id. Access control therefore had nothing to hang off.

Phase 1 (this module) reads identity from request headers, which is only
honest for a local/offline deployment where the process boundary is the trust
boundary. ``APISecuritySettings.validate_security_policy`` refuses header mode
in production for exactly that reason.

Phase 2 replaces the body of :func:`get_caller_identity` with real token or
session verification. Nothing downstream changes: every consumer depends on
:class:`CallerIdentity` and the ``AccessScope`` / ``ChunkACL`` it produces,
not on where those came from.

Fail-closed
-----------
There is no code path here that yields a permissive default. A missing,
malformed, or unconfigured identity raises, and the request fails. Widening a
scope requires a real identity, never the absence of one.
"""

import logging
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.schemas.access_control import (
    AccessScope,
    ChunkACL,
    ConfidentialityLevel,
    CONFIDENTIALITY_LADDER,
    SHARED_CLIENT_ID,
    NO_MATTER_ID,
)


logger = logging.getLogger(__name__)


CLIENT_ID_HEADER = "X-Client-Id"
MATTER_ID_HEADER = "X-Matter-Id"
CONFIDENTIALITY_CEILING_HEADER = "X-Confidentiality-Ceiling"


class CallerIdentity(BaseModel):
    """
    The authenticated principal behind one request.

    Server-derived only. This model is never parsed from a request body.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    client_id: str = Field(
        ...,
        min_length=1,
        description="Tenant this caller belongs to.",
    )

    matter_id: str | None = Field(
        default=None,
        description=(
            "Optional single-matter narrowing. None means the caller works "
            "across every matter belonging to their client."
        ),
    )

    max_confidentiality: ConfidentialityLevel = Field(
        ...,
        description="Highest rung this caller may read or ingest at.",
    )

    def to_scope(self) -> AccessScope:
        """Build the retrieval scope this caller is entitled to."""

        return AccessScope(
            client_id=self.client_id,
            matter_ids=(
                [self.matter_id]
                if self.matter_id is not None
                else None
            ),
            max_confidentiality=self.max_confidentiality,
            include_shared_corpus=True,
        )

    def to_chunk_acl(
        self,
        *,
        confidentiality_level: ConfidentialityLevel | None = None,
        matter_id: str | None = None,
    ) -> ChunkACL:
        """
        Build the ACL stamped onto every chunk of an ingested document.

        ``confidentiality_level`` may lower the classification for a specific
        document but never raise it above the caller's own ceiling: a caller
        cannot create content they would not be allowed to read back.
        """

        effective_matter = (
            matter_id
            if matter_id is not None
            else self.matter_id
        )

        level = (
            confidentiality_level
            if confidentiality_level is not None
            else self.max_confidentiality
        )

        if CONFIDENTIALITY_LADDER.index(level) > CONFIDENTIALITY_LADDER.index(
            self.max_confidentiality
        ):
            raise ValueError(
                "Cannot ingest above the caller's confidentiality ceiling."
            )

        return ChunkACL(
            client_id=self.client_id,
            matter_id=(
                effective_matter
                if effective_matter is not None
                else NO_MATTER_ID
            ),
            confidentiality_level=level,
        )


def _reject(
    request: Request,
    *,
    status_code: int,
    detail: str,
    reason: str,
) -> HTTPException:
    """
    Build the failure and log why, without logging header values.

    A caller's client id is tenant-identifying, so only the failure reason is
    recorded -- enough to debug a misconfigured client, not enough to leak who
    was probing what.
    """

    logger.warning(
        "caller_identity_rejected",
        extra={
            "request_id": getattr(
                request.state,
                "request_id",
                "unknown",
            ),
            "reason": reason,
        },
    )

    return HTTPException(
        status_code=status_code,
        detail=detail,
    )


def get_caller_identity(
    request: Request,
) -> CallerIdentity:
    """
    FastAPI dependency resolving the authenticated caller.

    Behaviour is governed by ``APISecuritySettings.identity_mode``:

    ``"header"``
        Phase 1. Trust ``X-Client-Id`` / ``X-Matter-Id`` /
        ``X-Confidentiality-Ceiling``. Rejected in production by the settings
        validator, so this branch cannot serve real traffic.
    ``"disabled"``
        No identity provider is wired up. Every identity-requiring route
        fails with 503. This is the deliberate fail-closed posture: with no
        way to establish who is asking, the correct answer is to serve
        nothing, not to serve everything.
    """

    settings = getattr(
        request.app.state,
        "api_security_settings",
        None,
    )

    identity_mode = getattr(
        settings,
        "identity_mode",
        "disabled",
    )

    if identity_mode != "header":
        raise _reject(
            request,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "No caller-identity provider is configured, so access "
                "control cannot be enforced."
            ),
            reason="identity_mode_disabled",
        )

    client_id = request.headers.get(CLIENT_ID_HEADER)
    matter_id = request.headers.get(MATTER_ID_HEADER)
    ceiling = request.headers.get(CONFIDENTIALITY_CEILING_HEADER)

    if not client_id or not client_id.strip():
        raise _reject(
            request,
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"{CLIENT_ID_HEADER} is required.",
            reason="missing_client_id",
        )

    if client_id.strip() == SHARED_CLIENT_ID:
        raise _reject(
            request,
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"{SHARED_CLIENT_ID!r} identifies the shared corpus, not a "
                "tenant, and cannot be used as a caller identity."
            ),
            reason="shared_corpus_impersonation",
        )

    if not ceiling or not ceiling.strip():
        raise _reject(
            request,
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"{CONFIDENTIALITY_CEILING_HEADER} is required.",
            reason="missing_confidentiality_ceiling",
        )

    try:
        return CallerIdentity(
            client_id=client_id.strip(),
            matter_id=(
                matter_id.strip()
                if matter_id and matter_id.strip()
                else None
            ),
            max_confidentiality=ceiling.strip(),
        )

    except ValidationError as exc:
        raise _reject(
            request,
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Caller identity headers are invalid. "
                f"{CONFIDENTIALITY_CEILING_HEADER} must be one of: "
                + ", ".join(CONFIDENTIALITY_LADDER)
                + "."
            ),
            reason="invalid_identity_headers",
        ) from exc


CallerIdentityDependency = Annotated[
    CallerIdentity,
    Depends(get_caller_identity),
]


def reject_client_supplied_access(
    filters: object,
    request: Request,
    *,
    field_path: str,
) -> None:
    """
    Refuse a request that arrived carrying its own access scope.

    Silently overwriting would be safe -- the server value wins either way --
    but it would also be silent. A client populating this field is either
    confused about where authorization comes from or checking whether the
    server will honour it, and the second case is exactly the one worth
    seeing in the logs. So: 400, and a log line.
    """

    if getattr(filters, "access", None) is None:
        return

    logger.warning(
        "client_supplied_access_scope_rejected",
        extra={
            "request_id": getattr(
                request.state,
                "request_id",
                "unknown",
            ),
            "field_path": field_path,
        },
    )

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=(
            f"{field_path} is set by the server from the authenticated "
            "caller and must not be supplied by the client."
        ),
    )


def apply_access_scope(
    filters,
    identity: CallerIdentity,
):
    """
    Return a copy of ``filters`` carrying the caller's server-derived scope.

    Always call :func:`reject_client_supplied_access` first; this function
    assumes the incoming scope is absent, not that it is safe to replace.
    """

    return filters.model_copy(
        update={"access": identity.to_scope()},
    )


__all__ = [
    "AccessScope",
    "CallerIdentity",
    "CallerIdentityDependency",
    "ChunkACL",
    "CLIENT_ID_HEADER",
    "CONFIDENTIALITY_CEILING_HEADER",
    "MATTER_ID_HEADER",
    "apply_access_scope",
    "get_caller_identity",
    "reject_client_supplied_access",
]
