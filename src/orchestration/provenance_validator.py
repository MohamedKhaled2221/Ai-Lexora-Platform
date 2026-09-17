"""
Deterministic Package 3 provenance validation.

This module validates the M1 -> M4 handoff:

    AssembledDraft + GenerationManifest

It verifies structural identity and source traceability before any
semantic/LLM grounding validation is performed.

No LLM is called from this module.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.schemas.p3_generation_contract import (
    AssembledDraft,
    DraftSection,
    DraftSourceType,
    DraftValidationResult,
    GenerationManifest,
    SourceReference,
)


@dataclass(frozen=True)
class ProvenanceValidationReport:
    """
    Internal deterministic validation result.

    This intentionally remains separate from DraftValidationResult
    because semantic grounding is performed in a later validation stage.
    """

    structure_valid: bool
    provenance_valid: bool

    unsourced_section_ids: tuple[str, ...]

    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    checked_section_count: int
    checked_reference_count: int
    checked_transformation_count: int

    @property
    def valid(self) -> bool:
        """
        True only when structural and provenance validation both pass.
        """

        return (
            self.structure_valid
            and self.provenance_valid
        )

    def to_draft_validation_result(
        self,
        *,
        grounding_valid: bool,
    ) -> DraftValidationResult:
        """
        Combine deterministic provenance validation with a later
        grounding result.

        Step 4 will supply grounding_valid.
        """

        overall_valid = (
            self.structure_valid
            and self.provenance_valid
            and grounding_valid
        )

        return DraftValidationResult(
            is_valid=overall_valid,
            structure_valid=self.structure_valid,
            provenance_valid=self.provenance_valid,
            grounding_valid=grounding_valid,
            unsourced_section_ids=list(
                self.unsourced_section_ids
            ),
            errors=list(self.errors),
            warnings=list(self.warnings),
        )


class P3ProvenanceValidator:
    """
    Validates Package 3 generation provenance.

    The validator verifies:

    - draft/manifest identity;
    - template identity/version;
    - section provenance presence;
    - approved-clause references;
    - user-input references;
    - lawyer-approved edit references;
    - AI transformation target/source relationships.

    It does NOT determine whether the actual natural-language text
    semantically matches the approved source text. That belongs to the
    grounding validator.
    """

    def validate(
        self,
        draft: AssembledDraft,
        manifest: GenerationManifest,
    ) -> ProvenanceValidationReport:
        structure_errors: list[str] = []
        provenance_errors: list[str] = []
        warnings: list[str] = []

        unsourced_section_ids: set[str] = set()

        checked_reference_count = 0

        # -------------------------------------------------
        # Structural identity checks
        # -------------------------------------------------

        if draft.draft_id != manifest.draft_id:
            structure_errors.append(
                "Draft ID mismatch: "
                f"draft={draft.draft_id!r}, "
                f"manifest={manifest.draft_id!r}."
            )

        if draft.template_id != manifest.template_id:
            structure_errors.append(
                "Template ID mismatch: "
                f"draft={draft.template_id!r}, "
                f"manifest={manifest.template_id!r}."
            )

        if (
            draft.template_version
            != manifest.template_version
        ):
            structure_errors.append(
                "Template version mismatch: "
                f"draft={draft.template_version!r}, "
                f"manifest={manifest.template_version!r}."
            )

        section_by_id = {
            section.section_id: section
            for section in draft.sections
        }

        # -------------------------------------------------
        # Manifest indexes
        # -------------------------------------------------

        clause_versions = {
            (
                reference.clause_id,
                reference.clause_version,
            )
            for reference in manifest.clause_references
        }

        lawyer_edits = {
            reference.edit_id: reference
            for reference
            in manifest.lawyer_edit_references
        }

        known_source_ids = {
            manifest.template_id,
            *(
                reference.clause_id
                for reference
                in manifest.clause_references
            ),
            *manifest.user_fields.keys(),
            *lawyer_edits.keys(),
        }

        # -------------------------------------------------
        # Section provenance
        # -------------------------------------------------

        for section in draft.sections:
            if not section.source_references:
                provenance_errors.append(
                    f"Section {section.section_id!r} "
                    "has no trusted source references."
                )

                unsourced_section_ids.add(
                    section.section_id
                )

                continue

            for reference in section.source_references:
                checked_reference_count += 1

                errors = (
                    self._validate_source_reference(
                        section=section,
                        reference=reference,
                        manifest=manifest,
                        clause_versions=clause_versions,
                        lawyer_edits=lawyer_edits,
                    )
                )

                if errors:
                    provenance_errors.extend(
                        errors
                    )

                    unsourced_section_ids.add(
                        section.section_id
                    )

        # -------------------------------------------------
        # Lawyer edit integrity
        # -------------------------------------------------

        for edit in manifest.lawyer_edit_references:
            if edit.section_id not in section_by_id:
                provenance_errors.append(
                    f"Lawyer edit {edit.edit_id!r} "
                    f"references unknown section "
                    f"{edit.section_id!r}."
                )

        # -------------------------------------------------
        # AI transformation provenance
        # -------------------------------------------------

        for transformation in manifest.ai_transformations:
            target_section = section_by_id.get(
                transformation.target_section_id
            )

            if target_section is None:
                provenance_errors.append(
                    f"AI transformation "
                    f"{transformation.transformation_id!r} "
                    "references unknown target section "
                    f"{transformation.target_section_id!r}."
                )

                continue

            if len(
                transformation.source_ids
            ) != len(
                set(transformation.source_ids)
            ):
                provenance_errors.append(
                    f"AI transformation "
                    f"{transformation.transformation_id!r} "
                    "contains duplicate source IDs."
                )

            target_source_ids = {
                reference.source_id
                for reference
                in target_section.source_references
            }

            for source_id in transformation.source_ids:
                if (
                    source_id not in known_source_ids
                    and not self._is_template_source_id(
                        source_id,
                        manifest.template_id,
                    )
                ):
                    provenance_errors.append(
                        f"AI transformation "
                        f"{transformation.transformation_id!r} "
                        f"references unknown trusted source "
                        f"{source_id!r}."
                    )

                    unsourced_section_ids.add(
                        target_section.section_id
                    )

                    continue

                if source_id not in target_source_ids:
                    provenance_errors.append(
                        f"AI transformation "
                        f"{transformation.transformation_id!r} "
                        f"uses source {source_id!r}, but "
                        f"section "
                        f"{target_section.section_id!r} "
                        "does not declare that source."
                    )

                    unsourced_section_ids.add(
                        target_section.section_id
                    )

        # -------------------------------------------------
        # Non-blocking manifest consistency warnings
        # -------------------------------------------------

        used_clause_versions = {
            (
                reference.source_id,
                reference.source_version,
            )
            for section in draft.sections
            for reference in section.source_references
            if (
                reference.source_type
                == DraftSourceType.APPROVED_CLAUSE
            )
        }

        for clause_reference in manifest.clause_references:
            key = (
                clause_reference.clause_id,
                clause_reference.clause_version,
            )

            if key not in used_clause_versions:
                warnings.append(
                    f"Manifest clause "
                    f"{clause_reference.clause_id!r} "
                    f"version "
                    f"{clause_reference.clause_version!r} "
                    "is not referenced by any draft section."
                )

        used_lawyer_edit_ids = {
            reference.source_id
            for section in draft.sections
            for reference in section.source_references
            if (
                reference.source_type
                == DraftSourceType.LAWYER_APPROVED_EDIT
            )
        }

        for edit in manifest.lawyer_edit_references:
            if edit.edit_id not in used_lawyer_edit_ids:
                warnings.append(
                    f"Lawyer edit {edit.edit_id!r} "
                    "is present in the manifest but is not "
                    "referenced by any draft section."
                )

        # -------------------------------------------------
        # Final report
        # -------------------------------------------------

        structure_valid = not structure_errors
        provenance_valid = not provenance_errors

        return ProvenanceValidationReport(
            structure_valid=structure_valid,
            provenance_valid=provenance_valid,
            unsourced_section_ids=tuple(
                sorted(unsourced_section_ids)
            ),
            errors=tuple(
                structure_errors
                + provenance_errors
            ),
            warnings=tuple(warnings),
            checked_section_count=len(
                draft.sections
            ),
            checked_reference_count=(
                checked_reference_count
            ),
            checked_transformation_count=len(
                manifest.ai_transformations
            ),
        )

    def _validate_source_reference(
        self,
        *,
        section: DraftSection,
        reference: SourceReference,
        manifest: GenerationManifest,
        clause_versions: set[
            tuple[str, str]
        ],
        lawyer_edits: dict[str, object],
    ) -> list[str]:
        """
        Validate one section-level provenance reference.
        """

        errors: list[str] = []

        # ---------------------------------------------
        # Template
        # ---------------------------------------------

        if (
            reference.source_type
            == DraftSourceType.TEMPLATE
        ):
            if not self._is_template_source_id(
                reference.source_id,
                manifest.template_id,
            ):
                errors.append(
                    f"Section {section.section_id!r} "
                    "references template "
                    f"{reference.source_id!r}, but the "
                    "manifest template is "
                    f"{manifest.template_id!r}."
                )

            if reference.source_version is None:
                errors.append(
                    f"Section {section.section_id!r} "
                    "template provenance is missing "
                    "source_version."
                )

            elif (
                reference.source_version
                != manifest.template_version
            ):
                errors.append(
                    f"Section {section.section_id!r} "
                    "references template version "
                    f"{reference.source_version!r}, but "
                    "the manifest uses "
                    f"{manifest.template_version!r}."
                )

            return errors

        # ---------------------------------------------
        # Approved clause
        # ---------------------------------------------

        if (
            reference.source_type
            == DraftSourceType.APPROVED_CLAUSE
        ):
            if reference.source_version is None:
                errors.append(
                    f"Section {section.section_id!r} "
                    f"approved clause "
                    f"{reference.source_id!r} "
                    "is missing source_version."
                )

                return errors

            key = (
                reference.source_id,
                reference.source_version,
            )

            if key not in clause_versions:
                errors.append(
                    f"Section {section.section_id!r} "
                    "references approved clause "
                    f"{reference.source_id!r} version "
                    f"{reference.source_version!r}, "
                    "but that exact clause/version is "
                    "not present in the "
                    "GenerationManifest."
                )

            return errors

        # ---------------------------------------------
        # User input
        # ---------------------------------------------

        if (
            reference.source_type
            == DraftSourceType.USER_INPUT
        ):
            if (
                reference.source_id
                not in manifest.user_fields
            ):
                errors.append(
                    f"Section {section.section_id!r} "
                    "references user field "
                    f"{reference.source_id!r}, but that "
                    "field is not present in the "
                    "GenerationManifest."
                )

            return errors

        # ---------------------------------------------
        # Lawyer-approved edit
        # ---------------------------------------------

        if (
            reference.source_type
            == DraftSourceType.LAWYER_APPROVED_EDIT
        ):
            edit = lawyer_edits.get(
                reference.source_id
            )

            if edit is None:
                errors.append(
                    f"Section {section.section_id!r} "
                    "references lawyer edit "
                    f"{reference.source_id!r}, but that "
                    "edit is not present in the "
                    "GenerationManifest."
                )

                return errors

            edit_section_id = getattr(
                edit,
                "section_id",
                None,
            )

            if edit_section_id != section.section_id:
                errors.append(
                    f"Section {section.section_id!r} "
                    "references lawyer edit "
                    f"{reference.source_id!r}, but the "
                    "edit belongs to section "
                    f"{edit_section_id!r}."
                )

            return errors

        # The enum currently prevents unknown source types.
        # Keep this fallback for defensive future compatibility.

        errors.append(
            f"Section {section.section_id!r} "
            "contains unsupported source type "
            f"{reference.source_type!r}."
        )

        return errors
    
    @staticmethod
    def _is_template_source_id(
        source_id: str,
        template_id: str,
    ) -> bool:
        return (
            source_id == template_id
            or source_id.startswith(
                template_id + "::"
            )
        )
