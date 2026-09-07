"""
Package 3 M4 orchestration.

This module combines deterministic provenance validation and
text grounding validation into the final Package 3 M4 handoff:

    AssembledDraft
    + GenerationManifest
    + P3GroundingContext
        ->
    ValidatedDraft

M4 does not assemble the document and does not create new legal
clauses. It validates the document supplied by M1.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.orchestration.grounding_validator import (
    P3GroundingContext,
    P3GroundingValidator,
)
from src.orchestration.provenance_validator import (
    P3ProvenanceValidator,
    ProvenanceValidationReport,
)
from src.schemas.p3_generation_contract import (
    AssembledDraft,
    DraftValidationResult,
    GenerationManifest,
    ValidatedDraft,
)


P3_VALIDATOR_VERSION = "1.0.0"


# ---------------------------------------------------------
# Errors
# ---------------------------------------------------------


class P3OrchestrationError(RuntimeError):
    """
    Base Package 3 M4 orchestration error.
    """


class P3ValidationContractError(
    P3OrchestrationError
):
    """
    Raised when the M1 -> M4 handoff is structurally inconsistent.

    Example:
    - draft ID differs from manifest draft ID
    - template ID differs
    - template version differs

    This is treated as an integration/contract failure rather than
    a normal lawyer-review validation result.
    """

    def __init__(
        self,
        message: str,
        *,
        provenance_report: (
            ProvenanceValidationReport | None
        ) = None,
    ) -> None:
        super().__init__(message)

        self.provenance_report = (
            provenance_report
        )


# ---------------------------------------------------------
# Optional orchestration metrics
# ---------------------------------------------------------


@dataclass(frozen=True)
class P3OrchestrationMetrics:
    """
    Lightweight orchestration metrics.

    Detailed latency/RAM/VRAM collection will be added in the shared
    metrics step later. These counters are useful immediately for
    testing and integration.
    """

    provenance_checked: bool
    grounding_checked: bool
    semantic_grounding_used: bool

    checked_section_count: int
    checked_reference_count: int


@dataclass(frozen=True)
class P3OrchestrationResult:
    """
    Internal service result containing both the public contract and
    orchestration metadata.

    The team-facing output remains `validated_draft`.
    """

    validated_draft: ValidatedDraft
    metrics: P3OrchestrationMetrics


# ---------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------


class P3M4Orchestrator:
    """
    Coordinates M4 Package 3 validation.

    Validation order:

    1. deterministic provenance validation;
    2. structural-contract failure handling;
    3. provenance failure short-circuit;
    4. grounding validation;
    5. combined DraftValidationResult;
    6. ValidatedDraft construction.

    The orchestrator fails closed.
    """

    def __init__(
        self,
        *,
        provenance_validator: (
            P3ProvenanceValidator | None
        ) = None,
        grounding_validator: (
            P3GroundingValidator | None
        ) = None,
        validator_version: str = (
            P3_VALIDATOR_VERSION
        ),
    ) -> None:
        self.provenance_validator = (
            provenance_validator
            or P3ProvenanceValidator()
        )

        self.grounding_validator = (
            grounding_validator
            or P3GroundingValidator()
        )

        self.validator_version = (
            validator_version
        )

    def validate(
        self,
        *,
        draft: AssembledDraft,
        manifest: GenerationManifest,
        grounding_context: P3GroundingContext,
    ) -> P3OrchestrationResult:
        """
        Validate an M1 Package 3 assembled draft.

        Returns a P3OrchestrationResult containing the official
        ValidatedDraft handoff.

        Structural identity mismatches raise
        P3ValidationContractError because ValidatedDraft requires the
        draft and manifest to describe the same generation operation.
        """

        # -------------------------------------------------
        # Stage 1 — deterministic provenance
        # -------------------------------------------------

        provenance = (
            self.provenance_validator.validate(
                draft,
                manifest,
            )
        )

        # -------------------------------------------------
        # Structural M1 -> M4 contract failure
        # -------------------------------------------------

        if not provenance.structure_valid:
            raise P3ValidationContractError(
                (
                    "Package 3 validation cannot continue "
                    "because the AssembledDraft and "
                    "GenerationManifest are structurally "
                    "inconsistent."
                ),
                provenance_report=provenance,
            )

        # -------------------------------------------------
        # Provenance failed: do NOT invoke grounding/LLM
        # -------------------------------------------------

        if not provenance.provenance_valid:
            validation = (
                self._build_provenance_failure_result(
                    provenance
                )
            )

            validated_draft = ValidatedDraft(
                draft=draft,
                manifest=manifest,
                validation=validation,
                validator_version=(
                    self.validator_version
                ),
                model_tag=None,
                prompt_version=None,
                requires_lawyer_review=True,
            )

            metrics = P3OrchestrationMetrics(
                provenance_checked=True,
                grounding_checked=False,
                semantic_grounding_used=False,
                checked_section_count=(
                    provenance
                    .checked_section_count
                ),
                checked_reference_count=(
                    provenance
                    .checked_reference_count
                ),
            )

            return P3OrchestrationResult(
                validated_draft=(
                    validated_draft
                ),
                metrics=metrics,
            )

        # -------------------------------------------------
        # Stage 2 — actual text grounding
        # -------------------------------------------------

        grounding = (
            self.grounding_validator.validate(
                draft=draft,
                manifest=manifest,
                context=grounding_context,
            )
        )

        # -------------------------------------------------
        # Stage 3 — final combined result
        # -------------------------------------------------

        validation = (
            grounding.combine_with_provenance(
                provenance
            )
        )

        requires_lawyer_review = (
            not validation.is_valid
        )

        semantic_grounding_used = (
            grounding
            .semantic_checked_section_count
            > 0
        )

        validated_draft = ValidatedDraft(
            draft=draft,
            manifest=manifest,
            validation=validation,
            validator_version=(
                self.validator_version
            ),
            model_tag=(
                grounding.model_tag
                if semantic_grounding_used
                else None
            ),
            prompt_version=(
                grounding.prompt_version
                if semantic_grounding_used
                else None
            ),
            requires_lawyer_review=(
                requires_lawyer_review
            ),
        )

        metrics = P3OrchestrationMetrics(
            provenance_checked=True,
            grounding_checked=True,
            semantic_grounding_used=(
                semantic_grounding_used
            ),
            checked_section_count=(
                provenance.checked_section_count
            ),
            checked_reference_count=(
                provenance
                .checked_reference_count
            ),
        )

        return P3OrchestrationResult(
            validated_draft=validated_draft,
            metrics=metrics,
        )

    def _build_provenance_failure_result(
        self,
        provenance: ProvenanceValidationReport,
    ) -> DraftValidationResult:
        """
        Build the final validation result when provenance fails.

        Grounding is deliberately false because M4 did not and should
        not attempt to ground text whose trusted provenance could not
        first be established.
        """

        errors = list(
            provenance.errors
        )

        errors.append(
            (
                "Grounding validation was skipped because "
                "provenance validation failed."
            )
        )

        return DraftValidationResult(
            is_valid=False,
            structure_valid=(
                provenance.structure_valid
            ),
            provenance_valid=False,
            grounding_valid=False,
            unsourced_section_ids=list(
                provenance.unsourced_section_ids
            ),
            errors=errors,
            warnings=list(
                provenance.warnings
            ),
        )
