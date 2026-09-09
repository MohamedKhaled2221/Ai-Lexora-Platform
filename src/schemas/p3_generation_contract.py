"""
Package 3 shared contracts for controlled legal document generation.

These models define the M1 -> M4 handoff and the validated
M4 output for Package 3.

M1 -> M4:
    AssembledDraft
    GenerationManifest

M4 -> downstream:
    ValidatedDraft

M4 validates provenance, grounding, and structure. It does not
freely generate new legal clauses.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


# ---------------------------------------------------------
# Provenance enums
# ---------------------------------------------------------


class DraftSourceType(str, Enum):
    """
    Trusted origins from which draft text may come.
    """

    TEMPLATE = "template"
    APPROVED_CLAUSE = "approved_clause"
    USER_INPUT = "user_input"
    LAWYER_APPROVED_EDIT = "lawyer_approved_edit"


# ---------------------------------------------------------
# Draft provenance
# ---------------------------------------------------------


class SourceReference(BaseModel):
    """
    Identifies a trusted source used to construct a draft section.

    Examples:
    - template + template ID/version
    - approved_clause + clause ID/version
    - user_input + field name
    - lawyer_approved_edit + review/edit ID
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    source_type: DraftSourceType = Field(
        ...,
        description="Trusted source category",
    )

    source_id: str = Field(
        ...,
        min_length=1,
        description=(
            "Stable source identifier such as a template ID, "
            "clause ID, user-field name, or lawyer-edit ID"
        ),
    )

    source_version: str | None = Field(
        default=None,
        description=(
            "Version of the source when versioning applies"
        ),
    )

    @field_validator("source_id")
    @classmethod
    def validate_source_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError(
                "source_id must not be empty"
            )

        return value


class DraftSection(BaseModel):
    """
    One section of the deterministic document assembled by M1.

    source_references may temporarily be empty because M4 must be
    able to receive an invalid draft and report missing provenance
    instead of Pydantic rejecting the whole request.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    section_id: str = Field(
        ...,
        min_length=1,
        description="Stable section identifier",
    )

    title: str = Field(
        default="",
        description="Human-readable section/clause title",
    )

    text: str = Field(
        ...,
        min_length=1,
        description="Final assembled text for this section",
    )

    source_references: list[SourceReference] = Field(
        default_factory=list,
        description=(
            "Trusted sources contributing to this section"
        ),
    )

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError(
                "section text must not be whitespace-only"
            )

        return value


# ---------------------------------------------------------
# M1 -> M4: assembled draft
# ---------------------------------------------------------


class AssembledDraft(BaseModel):
    """
    Deterministically assembled legal document supplied by M1 to M4.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    draft_id: str = Field(
        ...,
        min_length=1,
        description="Stable identifier for this draft",
    )

    document_type: str = Field(
        ...,
        min_length=1,
        description=(
            "Document type such as nda, employment_contract, "
            "or partnership_agreement"
        ),
    )

    template_id: str = Field(
        ...,
        min_length=1,
        description="Template used by M1",
    )

    template_version: str = Field(
        ...,
        min_length=1,
        description="Version of the template used",
    )

    sections: list[DraftSection] = Field(
        ...,
        min_length=1,
        description="Ordered assembled document sections",
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Time the draft was assembled",
    )

    @field_validator("sections")
    @classmethod
    def validate_unique_section_ids(
        cls,
        sections: list[DraftSection],
    ) -> list[DraftSection]:
        section_ids = [
            section.section_id
            for section in sections
        ]

        if len(section_ids) != len(set(section_ids)):
            raise ValueError(
                "AssembledDraft cannot contain duplicate section IDs"
            )

        return sections


# ---------------------------------------------------------
# Generation manifest
# ---------------------------------------------------------


class ClauseReference(BaseModel):
    """
    Approved M5 clause used by M1 during assembly.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    clause_id: str = Field(
        ...,
        min_length=1,
        description="Approved clause identifier",
    )

    clause_version: str = Field(
        ...,
        min_length=1,
        description="Exact approved clause version used",
    )


class LawyerEditReference(BaseModel):
    """
    Reference to a lawyer-reviewed/approved edit.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    edit_id: str = Field(
        ...,
        min_length=1,
        description="Stable lawyer-edit/review identifier",
    )

    section_id: str = Field(
        ...,
        min_length=1,
        description="Draft section affected by the edit",
    )

    reviewer_id: str = Field(
        ...,
        min_length=1,
        description="Identifier of the approving reviewer",
    )

    approved_at: datetime = Field(
        ...,
        description="Time the lawyer edit was approved",
    )


class AITransformationRecord(BaseModel):
    """
    Audit record for any AI-assisted transformation.

    AI transformation is not itself a trusted legal source. The
    transformation must remain grounded in approved source material.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    transformation_id: str = Field(
        ...,
        min_length=1,
        description="Stable transformation identifier",
    )

    target_section_id: str = Field(
        ...,
        min_length=1,
        description="Section whose text was transformed",
    )

    source_ids: list[str] = Field(
        ...,
        min_length=1,
        description=(
            "Trusted source IDs from which the transformation was made"
        ),
    )

    model_tag: str = Field(
        ...,
        min_length=1,
        description="Exact local model tag used",
    )

    prompt_version: str = Field(
        ...,
        min_length=1,
        description="Version of the prompt used",
    )

    transformed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Time the transformation occurred",
    )


class GenerationManifest(BaseModel):
    """
    Complete provenance manifest created by M1.

    It records the exact template, approved clauses, user-provided
    fields, lawyer-approved edits, and any AI-assisted transformations
    involved in creating the draft.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    manifest_id: str = Field(
        ...,
        min_length=1,
        description="Stable generation-manifest identifier",
    )

    draft_id: str = Field(
        ...,
        min_length=1,
        description="Draft associated with this manifest",
    )

    template_id: str = Field(
        ...,
        min_length=1,
        description="Template used for generation",
    )

    template_version: str = Field(
        ...,
        min_length=1,
        description="Exact template version used",
    )

    clause_references: list[ClauseReference] = Field(
        default_factory=list,
        description="Approved clauses used in the draft",
    )

    user_fields: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "User-provided fields inserted during deterministic assembly"
        ),
    )

    lawyer_edit_references: list[LawyerEditReference] = Field(
        default_factory=list,
        description="Lawyer-approved edits included in the draft",
    )

    ai_transformations: list[AITransformationRecord] = Field(
        default_factory=list,
        description="AI-assisted transformations, if any",
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Time this manifest was created",
    )

    @field_validator("clause_references")
    @classmethod
    def validate_unique_clause_versions(
        cls,
        references: list[ClauseReference],
    ) -> list[ClauseReference]:
        keys = [
            (reference.clause_id, reference.clause_version)
            for reference in references
        ]

        if len(keys) != len(set(keys)):
            raise ValueError(
                "GenerationManifest cannot contain duplicate "
                "clause/version references"
            )

        return references

    @field_validator("lawyer_edit_references")
    @classmethod
    def validate_unique_lawyer_edits(
        cls,
        references: list[LawyerEditReference],
    ) -> list[LawyerEditReference]:
        edit_ids = [
            reference.edit_id
            for reference in references
        ]

        if len(edit_ids) != len(set(edit_ids)):
            raise ValueError(
                "GenerationManifest cannot contain duplicate "
                "lawyer edit IDs"
            )

        return references

    @field_validator("ai_transformations")
    @classmethod
    def validate_unique_transformations(
        cls,
        transformations: list[AITransformationRecord],
    ) -> list[AITransformationRecord]:
        transformation_ids = [
            item.transformation_id
            for item in transformations
        ]

        if len(transformation_ids) != len(
            set(transformation_ids)
        ):
            raise ValueError(
                "GenerationManifest cannot contain duplicate "
                "AI transformation IDs"
            )

        return transformations


# ---------------------------------------------------------
# M4 validation result
# ---------------------------------------------------------


class DraftValidationResult(BaseModel):
    """
    Detailed M4 validation result for a Package 3 draft.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    is_valid: bool = Field(
        ...,
        description="Overall validation result",
    )

    structure_valid: bool = Field(
        ...,
        description="Whether the draft structure is valid",
    )

    provenance_valid: bool = Field(
        ...,
        description="Whether all required provenance is valid",
    )

    grounding_valid: bool = Field(
        ...,
        description=(
            "Whether legal text is grounded in trusted sources"
        ),
    )

    unsourced_section_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Sections containing missing or invalid provenance"
        ),
    )

    errors: list[str] = Field(
        default_factory=list,
        description="Blocking validation errors",
    )

    warnings: list[str] = Field(
        default_factory=list,
        description="Non-blocking validation warnings",
    )

    validated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Time M4 performed validation",
    )


# ---------------------------------------------------------
# M4 -> downstream: validated draft
# ---------------------------------------------------------


class ValidatedDraft(BaseModel):
    """
    Final validated Package 3 output produced by M4.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    draft: AssembledDraft = Field(
        ...,
        description="Original assembled draft",
    )

    manifest: GenerationManifest = Field(
        ...,
        description="Generation provenance manifest",
    )

    validation: DraftValidationResult = Field(
        ...,
        description="M4 validation result",
    )

    validator_version: str = Field(
        default="1.0.0",
        min_length=1,
        description="Version of the M4 validation logic",
    )

    model_tag: str | None = Field(
        default=None,
        description=(
            "Local model tag if an LLM participated in validation"
        ),
    )

    prompt_version: str | None = Field(
        default=None,
        description=(
            "Prompt version if an LLM participated in validation"
        ),
    )

    requires_lawyer_review: bool = Field(
        default=False,
        description=(
            "Whether this draft must be routed to lawyer review"
        ),
    )

    validated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Time the final validated result was produced",
    )

    @model_validator(mode="after")
    def validate_draft_manifest_identity(
        self,
    ) -> "ValidatedDraft":
        if self.draft.draft_id != self.manifest.draft_id:
            raise ValueError(
                "draft.draft_id must match manifest.draft_id"
            )

        if self.draft.template_id != self.manifest.template_id:
            raise ValueError(
                "draft.template_id must match manifest.template_id"
            )

        if (
            self.draft.template_version
            != self.manifest.template_version
        ):
            raise ValueError(
                "draft.template_version must match "
                "manifest.template_version"
            )

        return self
