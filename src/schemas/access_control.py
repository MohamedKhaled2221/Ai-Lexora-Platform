"""
Access-control domain types shared by ingestion, retrieval, and the API.

Deliberately dependency-free (pydantic only). ``src/schemas`` is imported by
the vector store, the retrieval pipeline, and the API layer alike, so these
types must not reach back into ``src.api`` -- that would invert the layering
and create an import cycle through ``src.api.security``.

Trust model
-----------
Nothing in this module is ever populated from a request body. ``AccessScope``
is derived server-side from an authenticated caller; ``ChunkACL`` is stamped
server-side at ingestion. A client that supplies either one is probing, and
the API layer rejects the request rather than silently overwriting it.

Sentinels
---------
``client_id`` and ``matter_id`` are never ``None`` once stored. "Unowned" is
expressed with explicit reserved values so every Qdrant condition stays a flat
keyword match and "unset" can never be mistaken for "unrestricted":

``SHARED_CLIENT_ID = "_shared"``
    The cross-tenant legal corpus -- statutes, court rulings, clause
    templates. Readable by every tenant when a scope opts in.
``NO_MATTER_ID = "_none"``
    A client-level document not tied to any single matter.

``_shared`` rather than ``_public`` on purpose: ``confidentiality_level``
already has a ``"public"`` value meaning something entirely different (an
access rung, not an owner), and two unrelated concepts must not both read as
"public" in one payload.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


SHARED_CLIENT_ID = "_shared"
NO_MATTER_ID = "_none"

ConfidentialityLevel = Literal[
    "public",
    "internal",
    "privileged",
]

CONFIDENTIALITY_LADDER: tuple[ConfidentialityLevel, ...] = (
    "public",
    "internal",
    "privileged",
)
"""Ordered least- to most-restricted.

Stored as a keyword and queried by expanding this ladder to an explicit set,
never by range: Qdrant keyword indices do not order, and an explicit set is
auditable at the point of the query.
"""


class AccessControlError(Exception):
    """Base class for access-control failures."""


class AccessScopeRequired(AccessControlError):
    """
    Raised when a retrieval path was reached without an access scope.

    This is a programming error, not a user error: every read path is
    required to carry a scope, so the absence of one means a caller bypassed
    the intended construction. It fails the request rather than degrading to
    an unfiltered search.
    """


class AccessScopeViolation(AccessControlError):
    """
    Raised when retrieved content falls outside the requesting scope.

    Reaching this means the Qdrant filter did not do its job. The offending
    result is never dropped and retried -- a silent drop would turn a
    filtering bug into an invisible one.
    """


def levels_up_to(
    max_confidentiality: ConfidentialityLevel,
) -> list[ConfidentialityLevel]:
    """
    Expand a ceiling into the explicit set of readable levels.

    >>> levels_up_to("internal")
    ['public', 'internal']
    """

    if max_confidentiality not in CONFIDENTIALITY_LADDER:
        raise AccessControlError(
            f"Unknown confidentiality level: {max_confidentiality!r}"
        )

    ceiling = CONFIDENTIALITY_LADDER.index(max_confidentiality)

    return list(CONFIDENTIALITY_LADDER[: ceiling + 1])


def _clean_token(value: str, field_name: str) -> str:
    cleaned = value.strip()

    if not cleaned:
        raise ValueError(f"{field_name} must not be empty")

    if any(character.isspace() for character in cleaned):
        raise ValueError(f"{field_name} must not contain whitespace")

    return cleaned


class ChunkACL(BaseModel):
    """
    The access-control stamp applied to every indexed chunk.

    Built server-side from the authenticated caller at the ingest boundary and
    written onto every chunk of the document, overwriting whatever M1 or the
    uploader supplied. A document's ACL is never derived from its contents.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    client_id: str = Field(..., min_length=1)
    matter_id: str = Field(default=NO_MATTER_ID, min_length=1)
    confidentiality_level: ConfidentialityLevel

    @field_validator("client_id", "matter_id")
    @classmethod
    def _validate_ids(cls, value: str, info) -> str:
        return _clean_token(value, info.field_name)


class AccessScope(BaseModel):
    """
    What one authenticated caller is allowed to retrieve.

    Compiled into Qdrant ``must`` conditions by
    ``QdrantVectorStore.build_qdrant_filter``. Frozen so a scope cannot be
    widened in flight after the identity layer produced it.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    client_id: str = Field(
        ...,
        min_length=1,
        description="The caller's own tenant.",
    )

    matter_ids: list[str] | None = Field(
        default=None,
        description=(
            "Restrict to these matters. None means every matter belonging "
            "to the client. Client-level documents (matter_id '_none') stay "
            "visible either way."
        ),
    )

    max_confidentiality: ConfidentialityLevel = Field(
        ...,
        description="Highest rung this caller may read.",
    )

    include_shared_corpus: bool = Field(
        default=True,
        description=(
            "Whether the cross-tenant '_shared' corpus is in scope alongside "
            "the caller's own documents."
        ),
    )

    @field_validator("client_id")
    @classmethod
    def _validate_client_id(cls, value: str) -> str:
        cleaned = _clean_token(value, "client_id")

        if cleaned == SHARED_CLIENT_ID:
            raise ValueError(
                "A caller cannot authenticate as the shared corpus "
                f"({SHARED_CLIENT_ID!r}); it is a document owner, not a "
                "tenant. Use include_shared_corpus to read it."
            )

        return cleaned

    @field_validator("matter_ids")
    @classmethod
    def _validate_matter_ids(
        cls,
        values: list[str] | None,
    ) -> list[str] | None:
        if values is None:
            return None

        if not values:
            raise ValueError(
                "matter_ids must not be an empty list; use None to mean "
                "'every matter for this client'. An empty list would read "
                "as 'no matters', which is never what a caller intends."
            )

        normalized: list[str] = []
        seen: set[str] = set()

        for value in values:
            cleaned = _clean_token(value, "matter_ids")

            if cleaned not in seen:
                normalized.append(cleaned)
                seen.add(cleaned)

        return normalized

    @property
    def allowed_client_ids(self) -> list[str]:
        """Client ids readable under this scope, for a flat keyword match."""

        if self.include_shared_corpus:
            return [self.client_id, SHARED_CLIENT_ID]

        return [self.client_id]

    @property
    def allowed_matter_ids(self) -> list[str] | None:
        """
        Matter ids readable under this scope, or None for "no restriction".

        ``NO_MATTER_ID`` is always appended so client-level documents remain
        readable when a caller narrows to specific matters.
        """

        if self.matter_ids is None:
            return None

        return [*self.matter_ids, NO_MATTER_ID]

    @property
    def allowed_confidentiality_levels(self) -> list[ConfidentialityLevel]:
        return levels_up_to(self.max_confidentiality)

    def permits(
        self,
        *,
        client_id: str | None,
        confidentiality_level: str | None,
        matter_id: str | None = None,
    ) -> bool:
        """
        Whether one stored payload is readable under this scope.

        Used for the post-retrieval assertion. Missing values are refused: an
        unstamped payload is not "unrestricted", it is unverifiable.
        """

        if not client_id or client_id not in self.allowed_client_ids:
            return False

        if (
            not confidentiality_level
            or confidentiality_level
            not in self.allowed_confidentiality_levels
        ):
            return False

        allowed_matters = self.allowed_matter_ids

        if allowed_matters is not None:
            if not matter_id or matter_id not in allowed_matters:
                return False

        return True
