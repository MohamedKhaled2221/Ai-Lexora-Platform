"""
Integrated Package 3 M5 -> M4 validation service.

The service resolves authoritative approved-clause text and lifecycle
state from M5 before passing the resulting trusted grounding context
to the existing M4 Package 3 orchestrator.

M5 owns approved clause truth.
M4 owns provenance and grounding validation.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.orchestration.grounding_validator import (
    P3GroundingContext,
)
from src.orchestration.m5_grounding_adapter import (
    ClauseLanguage,
    M5GroundingAdapter,
)
from src.orchestration.p3_orchestrator import (
    P3M4Orchestrator,
    P3OrchestrationMetrics,
)
from src.schemas.p3_generation_contract import (
    AssembledDraft,
    GenerationManifest,
    ValidatedDraft,
)


@dataclass(frozen=True)
class P3M5ValidationResult:
    """
    Final integrated P3 result.

    validated_draft remains the public team-facing contract.
    """

    validated_draft: ValidatedDraft

    metrics: P3OrchestrationMetrics

    m5_resolved_clause_ids: tuple[str, ...]

    m5_resolved_clause_count: int


class P3M5ValidationService:
    """
    M5-backed Package 3 validation entry point.
    """

    def __init__(
        self,
        *,
        m5_adapter: M5GroundingAdapter,
        m4_orchestrator: P3M4Orchestrator | None = None,
    ) -> None:
        self.m5_adapter = m5_adapter

        self.m4_orchestrator = (
            m4_orchestrator
            or P3M4Orchestrator()
        )

    def validate(
        self,
        *,
        draft: AssembledDraft,
        manifest: GenerationManifest,
        clause_language: ClauseLanguage,
        base_grounding_context: (
            P3GroundingContext | None
        ) = None,
    ) -> P3M5ValidationResult:
        """
        Resolve M5 clauses and perform complete M4 validation.

        base_grounding_context is reserved for trusted sources not
        owned by M5, for example:
        - template source text;
        - lawyer-approved edits.

        Approved-clause text supplied in base_grounding_context is
        checked against authoritative M5 text by the adapter.
        """

        m5_result = (
            self.m5_adapter.build_context(
                manifest=manifest,
                language=clause_language,
                base_context=(
                    base_grounding_context
                ),
            )
        )

        m4_result = (
            self.m4_orchestrator.validate(
                draft=draft,
                manifest=manifest,
                grounding_context=(
                    m5_result
                    .grounding_context
                ),
            )
        )

        return P3M5ValidationResult(
            validated_draft=(
                m4_result.validated_draft
            ),
            metrics=m4_result.metrics,
            m5_resolved_clause_ids=(
                m5_result
                .resolved_clause_ids
            ),
            m5_resolved_clause_count=(
                m5_result
                .resolved_clause_count
            ),
        )
