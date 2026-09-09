"""
M5 -> M4 Package 3 grounding adapter.

This module bridges M5's Approved Clause Library with M4's
P3GroundingContext.

M5 remains the source of truth for:
- clause identity;
- exact version;
- approval status;
- effective/expiry state;
- supersession;
- lawyer-edit/reapproval state;
- approved Arabic and English text.

M4 does not reconstruct missing clause text and does not ask the LLM
to determine whether an unavailable clause should be trusted.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from src.clause_engine.clause_library import (
    ClauseNotFoundError,
)
from src.clause_engine.service import (
    M5ClauseService,
)
from src.orchestration.grounding_validator import (
    P3GroundingContext,
    TrustedSourceText,
)
from src.schemas.m5_contract import (
    ApprovalStatus,
    ApprovedClause,
)
from src.schemas.p3_generation_contract import (
    DraftSourceType,
    GenerationManifest,
)


ClauseLanguage = Literal["ar", "en"]


# ---------------------------------------------------------
# Integration errors
# ---------------------------------------------------------


class M5GroundingAdapterError(RuntimeError):
    """
    Base M5 -> M4 grounding integration error.
    """


class M5ClauseNotFoundError(
    M5GroundingAdapterError
):
    """
    Raised when a GenerationManifest references a clause that
    does not exist in the authoritative M5 Clause Library.
    """


class M5ClauseVersionMismatchError(
    M5GroundingAdapterError
):
    """
    Raised when the manifest's exact clause version differs from
    the version currently resolved from M5.
    """


class M5ClauseNotUsableError(
    M5GroundingAdapterError
):
    """
    Raised when the referenced M5 clause exists but cannot be used.

    Examples:
    - not approved;
    - not yet effective;
    - expired;
    - superseded;
    - lawyer-edited and awaiting separate approval.
    """


class M5GroundingContextConflictError(
    M5GroundingAdapterError
):
    """
    Raised when upstream context already contains the same
    clause/version but with text different from authoritative M5 text.
    """


# ---------------------------------------------------------
# Result
# ---------------------------------------------------------


@dataclass(frozen=True)
class M5GroundingAdapterResult:
    """
    Result of resolving GenerationManifest clauses through M5.
    """

    grounding_context: P3GroundingContext

    resolved_clause_ids: tuple[str, ...]

    resolved_clause_count: int

    language: ClauseLanguage


# ---------------------------------------------------------
# Adapter
# ---------------------------------------------------------


class M5GroundingAdapter:
    """
    Resolves approved clause references from M5 into trusted M4
    grounding sources.

    The adapter intentionally consumes the concrete M5
    ApprovedClause state instead of treating free-form rule
    dictionaries as executable validation logic.
    """

    def __init__(
        self,
        m5_service: M5ClauseService,
    ) -> None:
        self.m5_service = m5_service

    def build_context(
        self,
        *,
        manifest: GenerationManifest,
        language: ClauseLanguage,
        base_context: P3GroundingContext | None = None,
    ) -> M5GroundingAdapterResult:
        """
        Resolve all clause references in a GenerationManifest.

        base_context may already contain trusted template or
        lawyer-approved-edit source text. M5 clause sources are merged
        into that context without replacing existing authoritative text.
        """

        if language not in ("ar", "en"):
            raise ValueError(
                "language must be either 'ar' or 'en'"
            )

        sources = list(
            base_context.sources
            if base_context is not None
            else []
        )

        existing_sources = {
            self._source_key(source): source
            for source in sources
        }

        resolved_ids: list[str] = []

        for reference in manifest.clause_references:
            clause = self._resolve_clause(
                clause_id=reference.clause_id
            )

            self._validate_clause(
                clause=clause,
                expected_version=(
                    reference.clause_version
                ),
            )

            source = self._to_grounding_source(
                clause=clause,
                language=language,
            )

            key = self._source_key(
                source
            )

            existing = existing_sources.get(
                key
            )

            if existing is not None:
                if existing.text != source.text:
                    raise (
                        M5GroundingContextConflictError(
                            "Trusted grounding context "
                            f"already contains clause "
                            f"{clause.clause_id!r} "
                            f"version {clause.version!r} "
                            "with text that differs from "
                            "the authoritative M5 text."
                        )
                    )

                # Same authoritative source already exists.
                # Do not duplicate it.
                resolved_ids.append(
                    clause.clause_id
                )
                continue

            sources.append(
                source
            )

            existing_sources[
                key
            ] = source

            resolved_ids.append(
                clause.clause_id
            )

        context = P3GroundingContext(
            sources=sources
        )

        return M5GroundingAdapterResult(
            grounding_context=context,
            resolved_clause_ids=tuple(
                resolved_ids
            ),
            resolved_clause_count=len(
                resolved_ids
            ),
            language=language,
        )

    # -----------------------------------------------------
    # Resolution
    # -----------------------------------------------------

    def _resolve_clause(
        self,
        *,
        clause_id: str,
    ) -> ApprovedClause:
        try:
            return (
                self.m5_service
                .clause_library
                .get_clause(
                    clause_id
                )
            )

        except ClauseNotFoundError as exc:
            raise M5ClauseNotFoundError(
                "GenerationManifest references "
                f"unknown M5 clause {clause_id!r}."
            ) from exc

    # -----------------------------------------------------
    # Status/version validation
    # -----------------------------------------------------

    def _validate_clause(
        self,
        *,
        clause: ApprovedClause,
        expected_version: str,
    ) -> None:
        if clause.version != expected_version:
            raise M5ClauseVersionMismatchError(
                f"M5 clause {clause.clause_id!r} "
                "version mismatch: manifest requires "
                f"{expected_version!r}, but M5 currently "
                f"resolves {clause.version!r}."
            )

        if (
            clause.approval_status
            != ApprovalStatus.APPROVED
        ):
            raise M5ClauseNotUsableError(
                f"M5 clause {clause.clause_id!r} "
                "cannot be used because its approval "
                f"status is "
                f"{clause.approval_status.value!r}."
            )

        if clause.superseded_by is not None:
            raise M5ClauseNotUsableError(
                f"M5 clause {clause.clause_id!r} "
                "cannot be used because it has been "
                f"superseded by "
                f"{clause.superseded_by!r}."
            )

        now = datetime.now(
            timezone.utc
        )

        if clause.effective_date > now:
            raise M5ClauseNotUsableError(
                f"M5 clause {clause.clause_id!r} "
                "cannot be used because it is not "
                "effective yet."
            )

        if (
            clause.expiry_date is not None
            and clause.expiry_date < now
        ):
            raise M5ClauseNotUsableError(
                f"M5 clause {clause.clause_id!r} "
                "cannot be used because it has expired."
            )

        if (
            clause.is_lawyer_edited
            and clause.requires_separate_approval
        ):
            raise M5ClauseNotUsableError(
                f"M5 clause {clause.clause_id!r} "
                "cannot be reused because the "
                "lawyer-edited version requires "
                "separate approval."
            )

        # Defensive final check against M5's own
        # authoritative usability policy.
        if not clause.is_usable():
            raise M5ClauseNotUsableError(
                f"M5 clause {clause.clause_id!r} "
                "is not usable according to M5 "
                "clause policy."
            )

    # -----------------------------------------------------
    # Trusted source construction
    # -----------------------------------------------------

    def _to_grounding_source(
        self,
        *,
        clause: ApprovedClause,
        language: ClauseLanguage,
    ) -> TrustedSourceText:
        if language == "ar":
            text = clause.text_ar
        else:
            text = clause.text_en

        if not text.strip():
            raise M5ClauseNotUsableError(
                f"M5 clause {clause.clause_id!r} "
                f"has no approved {language!r} text."
            )

        return TrustedSourceText(
            source_type=(
                DraftSourceType.APPROVED_CLAUSE
            ),
            source_id=clause.clause_id,
            source_version=clause.version,
            text=text,
        )

    def _source_key(
        self,
        source: TrustedSourceText,
    ) -> tuple[
        DraftSourceType,
        str,
        str | None,
    ]:
        return (
            source.source_type,
            source.source_id,
            source.source_version,
        )
