from datetime import datetime, timezone

from src.orchestration.provenance_validator import (
    P3ProvenanceValidator,
)
from src.schemas.p3_generation_contract import (
    AITransformationRecord,
    AssembledDraft,
    ClauseReference,
    DraftSection,
    DraftSourceType,
    GenerationManifest,
    LawyerEditReference,
    SourceReference,
)


def template_source() -> SourceReference:
    return SourceReference(
        source_type=DraftSourceType.TEMPLATE,
        source_id="template-nda",
        source_version="1.0",
    )


def clause_source(
    *,
    clause_id: str = "CLZ-CONF-EG-001",
    version: str = "1.0.0",
) -> SourceReference:
    return SourceReference(
        source_type=(
            DraftSourceType.APPROVED_CLAUSE
        ),
        source_id=clause_id,
        source_version=version,
    )

def test_section_scoped_template_source_id_is_valid():
    section = DraftSection(
        section_id="party",
        text="Party:",
        source_references=[
            SourceReference(
                source_type=(
                    DraftSourceType.TEMPLATE
                ),
                source_id=(
                    "template-nda"
                    "::section-1"
                    "::part-1"
                ),
                source_version="1.0",
            )
        ],
    )

    report = P3ProvenanceValidator().validate(
        make_draft(
            sections=[section],
        ),
        make_manifest(),
    )

    assert report.structure_valid is True
    assert report.provenance_valid is True
def make_draft(
    *,
    draft_id: str = "draft-001",
    template_id: str = "template-nda",
    template_version: str = "1.0",
    sections: list[DraftSection] | None = None,
) -> AssembledDraft:
    if sections is None:
        sections = [
            DraftSection(
                section_id="intro",
                title="Introduction",
                text="This Agreement is entered into...",
                source_references=[
                    template_source()
                ],
            ),
            DraftSection(
                section_id="confidentiality",
                title="Confidentiality",
                text=(
                    "The receiving party shall keep "
                    "information confidential."
                ),
                source_references=[
                    clause_source()
                ],
            ),
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
    clause_references: (
        list[ClauseReference] | None
    ) = None,
    user_fields: dict[str, str] | None = None,
    lawyer_edits: (
        list[LawyerEditReference] | None
    ) = None,
    transformations: (
        list[AITransformationRecord] | None
    ) = None,
) -> GenerationManifest:
    if clause_references is None:
        clause_references = [
            ClauseReference(
                clause_id="CLZ-CONF-EG-001",
                clause_version="1.0.0",
            )
        ]

    return GenerationManifest(
        manifest_id="manifest-001",
        draft_id=draft_id,
        template_id=template_id,
        template_version=template_version,
        clause_references=clause_references,
        user_fields=(
            user_fields
            if user_fields is not None
            else {}
        ),
        lawyer_edit_references=(
            lawyer_edits
            if lawyer_edits is not None
            else []
        ),
        ai_transformations=(
            transformations
            if transformations is not None
            else []
        ),
    )


def validator() -> P3ProvenanceValidator:
    return P3ProvenanceValidator()


def test_valid_draft_and_manifest_pass():
    report = validator().validate(
        make_draft(),
        make_manifest(),
    )

    assert report.structure_valid is True
    assert report.provenance_valid is True
    assert report.valid is True
    assert report.errors == ()
    assert report.unsourced_section_ids == ()
    assert report.checked_section_count == 2
    assert report.checked_reference_count == 2


def test_report_converts_to_final_validation_result():
    report = validator().validate(
        make_draft(),
        make_manifest(),
    )

    result = report.to_draft_validation_result(
        grounding_valid=True,
    )

    assert result.structure_valid is True
    assert result.provenance_valid is True
    assert result.grounding_valid is True
    assert result.is_valid is True


def test_grounding_failure_prevents_overall_validation():
    report = validator().validate(
        make_draft(),
        make_manifest(),
    )

    result = report.to_draft_validation_result(
        grounding_valid=False,
    )

    assert result.provenance_valid is True
    assert result.grounding_valid is False
    assert result.is_valid is False


def test_draft_id_mismatch_fails_structure():
    report = validator().validate(
        make_draft(
            draft_id="draft-001",
        ),
        make_manifest(
            draft_id="draft-999",
        ),
    )

    assert report.structure_valid is False
    assert report.valid is False

    assert any(
        "Draft ID mismatch"
        in error
        for error in report.errors
    )


def test_template_id_mismatch_fails_structure():
    report = validator().validate(
        make_draft(
            template_id="template-nda",
        ),
        make_manifest(
            template_id="template-other",
        ),
    )

    assert report.structure_valid is False

    assert any(
        "Template ID mismatch"
        in error
        for error in report.errors
    )


def test_template_version_mismatch_fails_structure():
    report = validator().validate(
        make_draft(
            template_version="1.0",
        ),
        make_manifest(
            template_version="2.0",
        ),
    )

    assert report.structure_valid is False

    assert any(
        "Template version mismatch"
        in error
        for error in report.errors
    )


def test_unsourced_section_fails_provenance():
    draft = make_draft(
        sections=[
            DraftSection(
                section_id="bad-section",
                title="Unsourced",
                text="Unsourced legal text.",
                source_references=[],
            )
        ]
    )

    manifest = make_manifest(
        clause_references=[],
    )

    report = validator().validate(
        draft,
        manifest,
    )

    assert report.provenance_valid is False

    assert report.unsourced_section_ids == (
        "bad-section",
    )

    assert any(
        "has no trusted source references"
        in error
        for error in report.errors
    )


def test_wrong_clause_version_fails_provenance():
    draft = make_draft(
        sections=[
            DraftSection(
                section_id="confidentiality",
                title="Confidentiality",
                text="Approved text.",
                source_references=[
                    clause_source(
                        version="2.0.0",
                    )
                ],
            )
        ]
    )

    report = validator().validate(
        draft,
        make_manifest(),
    )

    assert report.provenance_valid is False

    assert "confidentiality" in (
        report.unsourced_section_ids
    )


def test_unknown_clause_fails_provenance():
    draft = make_draft(
        sections=[
            DraftSection(
                section_id="confidentiality",
                title="Confidentiality",
                text="Legal text.",
                source_references=[
                    clause_source(
                        clause_id="CLZ-UNKNOWN-001",
                    )
                ],
            )
        ]
    )

    report = validator().validate(
        draft,
        make_manifest(),
    )

    assert report.provenance_valid is False


def test_valid_user_input_reference():
    draft = make_draft(
        sections=[
            DraftSection(
                section_id="party-name",
                title="Party",
                text="Company A",
                source_references=[
                    SourceReference(
                        source_type=(
                            DraftSourceType.USER_INPUT
                        ),
                        source_id="party_a",
                    )
                ],
            )
        ]
    )

    manifest = make_manifest(
        clause_references=[],
        user_fields={
            "party_a": "Company A"
        },
    )

    report = validator().validate(
        draft,
        manifest,
    )

    assert report.provenance_valid is True


def test_unknown_user_field_fails_provenance():
    draft = make_draft(
        sections=[
            DraftSection(
                section_id="party-name",
                title="Party",
                text="Company A",
                source_references=[
                    SourceReference(
                        source_type=(
                            DraftSourceType.USER_INPUT
                        ),
                        source_id="party_a",
                    )
                ],
            )
        ]
    )

    report = validator().validate(
        draft,
        make_manifest(
            clause_references=[],
        ),
    )

    assert report.provenance_valid is False

    assert "party-name" in (
        report.unsourced_section_ids
    )


def test_valid_lawyer_edit_reference():
    edit = LawyerEditReference(
        edit_id="edit-001",
        section_id="special-term",
        reviewer_id="lawyer-001",
        approved_at=datetime.now(
            timezone.utc
        ),
    )

    draft = make_draft(
        sections=[
            DraftSection(
                section_id="special-term",
                title="Special Term",
                text="Lawyer approved text.",
                source_references=[
                    SourceReference(
                        source_type=(
                            DraftSourceType
                            .LAWYER_APPROVED_EDIT
                        ),
                        source_id="edit-001",
                    )
                ],
            )
        ]
    )

    manifest = make_manifest(
        clause_references=[],
        lawyer_edits=[
            edit
        ],
    )

    report = validator().validate(
        draft,
        manifest,
    )

    assert report.provenance_valid is True


def test_lawyer_edit_for_wrong_section_fails():
    edit = LawyerEditReference(
        edit_id="edit-001",
        section_id="different-section",
        reviewer_id="lawyer-001",
        approved_at=datetime.now(
            timezone.utc
        ),
    )

    draft = make_draft(
        sections=[
            DraftSection(
                section_id="special-term",
                title="Special Term",
                text="Lawyer text.",
                source_references=[
                    SourceReference(
                        source_type=(
                            DraftSourceType
                            .LAWYER_APPROVED_EDIT
                        ),
                        source_id="edit-001",
                    )
                ],
            )
        ]
    )

    report = validator().validate(
        draft,
        make_manifest(
            clause_references=[],
            lawyer_edits=[edit],
        ),
    )

    assert report.provenance_valid is False


def test_manifest_lawyer_edit_unknown_section_fails():
    edit = LawyerEditReference(
        edit_id="edit-001",
        section_id="missing-section",
        reviewer_id="lawyer-001",
        approved_at=datetime.now(
            timezone.utc
        ),
    )

    report = validator().validate(
        make_draft(),
        make_manifest(
            lawyer_edits=[edit],
        ),
    )

    assert report.provenance_valid is False

    assert any(
        "references unknown section"
        in error
        for error in report.errors
    )


def test_valid_ai_transformation_provenance():
    transformation = AITransformationRecord(
        transformation_id="transform-001",
        target_section_id="confidentiality",
        source_ids=[
            "CLZ-CONF-EG-001"
        ],
        model_tag="qwen-test",
        prompt_version=(
            "p3-approved-transform-v1"
        ),
    )

    manifest = make_manifest(
        transformations=[
            transformation
        ],
    )

    report = validator().validate(
        make_draft(),
        manifest,
    )

    assert report.provenance_valid is True
    assert report.checked_transformation_count == 1


def test_ai_transformation_unknown_target_fails():
    transformation = AITransformationRecord(
        transformation_id="transform-001",
        target_section_id="missing-section",
        source_ids=[
            "CLZ-CONF-EG-001"
        ],
        model_tag="qwen-test",
        prompt_version=(
            "p3-approved-transform-v1"
        ),
    )

    report = validator().validate(
        make_draft(),
        make_manifest(
            transformations=[
                transformation
            ],
        ),
    )

    assert report.provenance_valid is False


def test_ai_transformation_unknown_source_fails():
    transformation = AITransformationRecord(
        transformation_id="transform-001",
        target_section_id="confidentiality",
        source_ids=[
            "UNKNOWN-SOURCE"
        ],
        model_tag="qwen-test",
        prompt_version=(
            "p3-approved-transform-v1"
        ),
    )

    report = validator().validate(
        make_draft(),
        make_manifest(
            transformations=[
                transformation
            ],
        ),
    )

    assert report.provenance_valid is False

    assert "confidentiality" in (
        report.unsourced_section_ids
    )


def test_ai_transformation_source_must_be_declared_by_section():
    transformation = AITransformationRecord(
        transformation_id="transform-001",
        target_section_id="intro",
        source_ids=[
            "CLZ-CONF-EG-001"
        ],
        model_tag="qwen-test",
        prompt_version=(
            "p3-approved-transform-v1"
        ),
    )

    report = validator().validate(
        make_draft(),
        make_manifest(
            transformations=[
                transformation
            ],
        ),
    )

    assert report.provenance_valid is False
    assert "intro" in report.unsourced_section_ids


def test_ai_transformation_duplicate_sources_fail():
    transformation = AITransformationRecord(
        transformation_id="transform-001",
        target_section_id="confidentiality",
        source_ids=[
            "CLZ-CONF-EG-001",
            "CLZ-CONF-EG-001",
        ],
        model_tag="qwen-test",
        prompt_version=(
            "p3-approved-transform-v1"
        ),
    )

    report = validator().validate(
        make_draft(),
        make_manifest(
            transformations=[
                transformation
            ],
        ),
    )

    assert report.provenance_valid is False

    assert any(
        "duplicate source IDs"
        in error
        for error in report.errors
    )


def test_unused_manifest_clause_produces_warning():
    manifest = make_manifest(
        clause_references=[
            ClauseReference(
                clause_id="CLZ-CONF-EG-001",
                clause_version="1.0.0",
            ),
            ClauseReference(
                clause_id="CLZ-UNUSED-EG-001",
                clause_version="1.0.0",
            ),
        ]
    )

    report = validator().validate(
        make_draft(),
        manifest,
    )

    assert report.provenance_valid is True

    assert any(
        "CLZ-UNUSED-EG-001"
        in warning
        for warning in report.warnings
    )
