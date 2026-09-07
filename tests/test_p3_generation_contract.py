from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.schemas.p3_generation_contract import (
    AITransformationRecord,
    AssembledDraft,
    ClauseReference,
    DraftSection,
    DraftSourceType,
    DraftValidationResult,
    GenerationManifest,
    LawyerEditReference,
    SourceReference,
    ValidatedDraft,
)


def make_source_reference(
    *,
    source_type: DraftSourceType = (
        DraftSourceType.APPROVED_CLAUSE
    ),
    source_id: str = "clause-001",
    source_version: str | None = "1.0",
) -> SourceReference:
    return SourceReference(
        source_type=source_type,
        source_id=source_id,
        source_version=source_version,
    )


def make_section(
    *,
    section_id: str = "section-001",
    source_references: (
        list[SourceReference] | None
    ) = None,
) -> DraftSection:
    if source_references is None:
        source_references = [
            make_source_reference()
        ]

    return DraftSection(
        section_id=section_id,
        title="Confidentiality",
        text=(
            "The receiving party shall maintain "
            "the information in confidence."
        ),
        source_references=source_references,
    )


def make_draft(
    *,
    draft_id: str = "draft-001",
    template_id: str = "template-nda",
    template_version: str = "1.0",
    sections: list[DraftSection] | None = None,
) -> AssembledDraft:
    if sections is None:
        sections = [
            make_section()
        ]

    return AssembledDraft(
        draft_id=draft_id,
        document_type="nda",
        template_id=template_id,
        template_version=template_version,
        sections=sections,
    )


def make_manifest(
    *,
    draft_id: str = "draft-001",
    template_id: str = "template-nda",
    template_version: str = "1.0",
) -> GenerationManifest:
    return GenerationManifest(
        manifest_id="manifest-001",
        draft_id=draft_id,
        template_id=template_id,
        template_version=template_version,
        clause_references=[
            ClauseReference(
                clause_id="clause-001",
                clause_version="1.0",
            )
        ],
        user_fields={
            "party_a": "Company A",
            "party_b": "Company B",
        },
    )


def make_validation(
    *,
    is_valid: bool = True,
) -> DraftValidationResult:
    return DraftValidationResult(
        is_valid=is_valid,
        structure_valid=is_valid,
        provenance_valid=is_valid,
        grounding_valid=is_valid,
    )


# ---------------------------------------------------------
# SourceReference
# ---------------------------------------------------------


def test_source_reference_accepts_valid_source():
    source = make_source_reference()

    assert (
        source.source_type
        == DraftSourceType.APPROVED_CLAUSE
    )
    assert source.source_id == "clause-001"
    assert source.source_version == "1.0"


@pytest.mark.parametrize(
    "source_type",
    [
        DraftSourceType.TEMPLATE,
        DraftSourceType.APPROVED_CLAUSE,
        DraftSourceType.USER_INPUT,
        DraftSourceType.LAWYER_APPROVED_EDIT,
    ],
)
def test_source_reference_accepts_all_trusted_types(
    source_type,
):
    source = make_source_reference(
        source_type=source_type,
    )

    assert source.source_type == source_type


def test_source_reference_rejects_unknown_type():
    with pytest.raises(ValidationError):
        SourceReference(
            source_type="generated_by_llm",
            source_id="source-001",
        )


def test_source_reference_rejects_empty_source_id():
    with pytest.raises(ValidationError):
        SourceReference(
            source_type=(
                DraftSourceType.APPROVED_CLAUSE
            ),
            source_id="",
        )


def test_source_reference_forbids_extra_fields():
    with pytest.raises(ValidationError):
        SourceReference(
            source_type=(
                DraftSourceType.APPROVED_CLAUSE
            ),
            source_id="clause-001",
            unexpected_field="not allowed",
        )


# ---------------------------------------------------------
# DraftSection
# ---------------------------------------------------------


def test_draft_section_accepts_valid_section():
    section = make_section()

    assert section.section_id == "section-001"
    assert len(section.source_references) == 1


def test_draft_section_rejects_blank_text():
    with pytest.raises(ValidationError):
        DraftSection(
            section_id="section-001",
            title="Invalid",
            text="   ",
        )


def test_draft_section_can_be_unsourced_for_validation():
    section = make_section(
        source_references=[],
    )

    assert section.source_references == []


# ---------------------------------------------------------
# AssembledDraft
# ---------------------------------------------------------


def test_assembled_draft_accepts_valid_draft():
    draft = make_draft()

    assert draft.draft_id == "draft-001"
    assert draft.document_type == "nda"
    assert len(draft.sections) == 1


def test_assembled_draft_requires_at_least_one_section():
    with pytest.raises(ValidationError):
        make_draft(
            sections=[],
        )


def test_assembled_draft_rejects_duplicate_section_ids():
    with pytest.raises(ValidationError):
        make_draft(
            sections=[
                make_section(
                    section_id="section-001",
                ),
                make_section(
                    section_id="section-001",
                ),
            ]
        )


def test_assembled_draft_forbids_extra_fields():
    with pytest.raises(ValidationError):
        AssembledDraft(
            draft_id="draft-001",
            document_type="nda",
            template_id="template-nda",
            template_version="1.0",
            sections=[
                make_section()
            ],
            extra_value="not allowed",
        )


# ---------------------------------------------------------
# GenerationManifest
# ---------------------------------------------------------


def test_generation_manifest_accepts_valid_manifest():
    manifest = make_manifest()

    assert manifest.manifest_id == "manifest-001"
    assert manifest.draft_id == "draft-001"
    assert len(manifest.clause_references) == 1


def test_generation_manifest_rejects_duplicate_clause_versions():
    with pytest.raises(ValidationError):
        GenerationManifest(
            manifest_id="manifest-001",
            draft_id="draft-001",
            template_id="template-nda",
            template_version="1.0",
            clause_references=[
                ClauseReference(
                    clause_id="clause-001",
                    clause_version="1.0",
                ),
                ClauseReference(
                    clause_id="clause-001",
                    clause_version="1.0",
                ),
            ],
        )


def test_generation_manifest_accepts_same_clause_different_versions():
    manifest = GenerationManifest(
        manifest_id="manifest-001",
        draft_id="draft-001",
        template_id="template-nda",
        template_version="1.0",
        clause_references=[
            ClauseReference(
                clause_id="clause-001",
                clause_version="1.0",
            ),
            ClauseReference(
                clause_id="clause-001",
                clause_version="2.0",
            ),
        ],
    )

    assert len(manifest.clause_references) == 2


def test_generation_manifest_rejects_duplicate_lawyer_edits():
    approved_at = datetime.now(
        timezone.utc
    )

    edit = LawyerEditReference(
        edit_id="edit-001",
        section_id="section-001",
        reviewer_id="lawyer-001",
        approved_at=approved_at,
    )

    with pytest.raises(ValidationError):
        GenerationManifest(
            manifest_id="manifest-001",
            draft_id="draft-001",
            template_id="template-nda",
            template_version="1.0",
            lawyer_edit_references=[
                edit,
                edit,
            ],
        )


def test_generation_manifest_rejects_duplicate_ai_transformations():
    transformation = AITransformationRecord(
        transformation_id="transform-001",
        target_section_id="section-001",
        source_ids=[
            "clause-001"
        ],
        model_tag="qwen-test",
        prompt_version="p3-transform-v1",
    )

    with pytest.raises(ValidationError):
        GenerationManifest(
            manifest_id="manifest-001",
            draft_id="draft-001",
            template_id="template-nda",
            template_version="1.0",
            ai_transformations=[
                transformation,
                transformation,
            ],
        )


def test_ai_transformation_requires_source_ids():
    with pytest.raises(ValidationError):
        AITransformationRecord(
            transformation_id="transform-001",
            target_section_id="section-001",
            source_ids=[],
            model_tag="qwen-test",
            prompt_version="p3-transform-v1",
        )


# ---------------------------------------------------------
# DraftValidationResult
# ---------------------------------------------------------


def test_validation_result_accepts_valid_result():
    result = make_validation()

    assert result.is_valid is True
    assert result.structure_valid is True
    assert result.provenance_valid is True
    assert result.grounding_valid is True


def test_validation_result_can_represent_invalid_draft():
    result = DraftValidationResult(
        is_valid=False,
        structure_valid=True,
        provenance_valid=False,
        grounding_valid=False,
        unsourced_section_ids=[
            "section-002"
        ],
        errors=[
            "Section section-002 has no trusted source."
        ],
    )

    assert result.is_valid is False
    assert result.unsourced_section_ids == [
        "section-002"
    ]
    assert len(result.errors) == 1


# ---------------------------------------------------------
# ValidatedDraft
# ---------------------------------------------------------


def test_validated_draft_accepts_matching_contracts():
    result = ValidatedDraft(
        draft=make_draft(),
        manifest=make_manifest(),
        validation=make_validation(),
    )

    assert result.draft.draft_id == "draft-001"
    assert result.manifest.draft_id == "draft-001"
    assert result.validation.is_valid is True


def test_validated_draft_rejects_draft_id_mismatch():
    with pytest.raises(
        ValidationError,
        match="draft.draft_id must match",
    ):
        ValidatedDraft(
            draft=make_draft(
                draft_id="draft-001",
            ),
            manifest=make_manifest(
                draft_id="draft-999",
            ),
            validation=make_validation(),
        )


def test_validated_draft_rejects_template_id_mismatch():
    with pytest.raises(
        ValidationError,
        match="draft.template_id must match",
    ):
        ValidatedDraft(
            draft=make_draft(
                template_id="template-nda",
            ),
            manifest=make_manifest(
                template_id="template-other",
            ),
            validation=make_validation(),
        )


def test_validated_draft_rejects_template_version_mismatch():
    with pytest.raises(
        ValidationError,
        match=(
            "draft.template_version must match"
        ),
    ):
        ValidatedDraft(
            draft=make_draft(
                template_version="1.0",
            ),
            manifest=make_manifest(
                template_version="2.0",
            ),
            validation=make_validation(),
        )


def test_validated_draft_can_require_lawyer_review():
    result = ValidatedDraft(
        draft=make_draft(),
        manifest=make_manifest(),
        validation=make_validation(
            is_valid=False,
        ),
        requires_lawyer_review=True,
    )

    assert result.requires_lawyer_review is True
    assert result.validation.is_valid is False
