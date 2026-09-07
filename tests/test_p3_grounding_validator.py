from src.orchestration.grounding_validator import (
    P3GroundingContext,
    P3GroundingValidator,
    P3SemanticGroundingOutput,
    TrustedSourceText,
)
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
    SourceReference,
)


class FakeSemanticChecker:
    def __init__(
        self,
        *,
        grounded: bool,
    ) -> None:
        self._grounded = grounded
        self.calls = 0

    @property
    def model_tag(self) -> str:
        return "fake-qwen"

    @property
    def prompt_version(self) -> str:
        return "p3-draft-validation-v1"

    def check(
        self,
        *,
        section,
        sources,
        transformation_metadata,
    ):
        self.calls += 1

        if self._grounded:
            return P3SemanticGroundingOutput(
                grounded=True,
                unsupported_fragments=[],
                reason=(
                    "Candidate remains supported "
                    "by approved sources."
                ),
            )

        return P3SemanticGroundingOutput(
            grounded=False,
            unsupported_fragments=[
                "new unsupported obligation"
            ],
            reason=(
                "Candidate introduces unsupported "
                "substantive legal content."
            ),
        )


def clause_reference():
    return SourceReference(
        source_type=(
            DraftSourceType.APPROVED_CLAUSE
        ),
        source_id="clause-001",
        source_version="1.0",
    )


def template_reference():
    return SourceReference(
        source_type=DraftSourceType.TEMPLATE,
        source_id="template-nda",
        source_version="1.0",
    )


def make_manifest(
    *,
    user_fields=None,
    transformations=None,
):
    return GenerationManifest(
        manifest_id="manifest-001",
        draft_id="draft-001",
        template_id="template-nda",
        template_version="1.0",
        clause_references=[
            ClauseReference(
                clause_id="clause-001",
                clause_version="1.0",
            )
        ],
        user_fields=(
            user_fields or {}
        ),
        ai_transformations=(
            transformations or []
        ),
    )


def make_draft(
    section,
):
    return AssembledDraft(
        draft_id="draft-001",
        document_type="nda",
        template_id="template-nda",
        template_version="1.0",
        sections=[section],
    )


def clause_context(
    text="The recipient shall keep the information confidential.",
):
    return P3GroundingContext(
        sources=[
            TrustedSourceText(
                source_type=(
                    DraftSourceType.APPROVED_CLAUSE
                ),
                source_id="clause-001",
                source_version="1.0",
                text=text,
            )
        ]
    )


# ---------------------------------------------------------
# Deterministic grounding
# ---------------------------------------------------------


def test_exact_clause_text_is_grounded():
    text = (
        "The recipient shall keep the "
        "information confidential."
    )

    section = DraftSection(
        section_id="confidentiality",
        title="Confidentiality",
        text=text,
        source_references=[
            clause_reference()
        ],
    )

    report = P3GroundingValidator().validate(
        draft=make_draft(section),
        manifest=make_manifest(),
        context=clause_context(text),
    )

    assert report.grounding_valid is True
    assert report.ungrounded_section_ids == ()
    assert (
        report.deterministic_checked_section_count
        == 1
    )


def test_whitespace_difference_is_allowed():
    section = DraftSection(
        section_id="confidentiality",
        title="Confidentiality",
        text=(
            "The recipient   shall keep\n"
            "the information confidential."
        ),
        source_references=[
            clause_reference()
        ],
    )

    report = P3GroundingValidator().validate(
        draft=make_draft(section),
        manifest=make_manifest(),
        context=clause_context(
            "The recipient shall keep the "
            "information confidential."
        ),
    )

    assert report.grounding_valid is True


def test_added_unsourced_text_fails():
    section = DraftSection(
        section_id="confidentiality",
        title="Confidentiality",
        text=(
            "The recipient shall keep the "
            "information confidential. "
            "The recipient must also pay a penalty."
        ),
        source_references=[
            clause_reference()
        ],
    )

    report = P3GroundingValidator().validate(
        draft=make_draft(section),
        manifest=make_manifest(),
        context=clause_context(),
    )

    assert report.grounding_valid is False

    assert report.ungrounded_section_ids == (
        "confidentiality",
    )


def test_missing_source_snapshot_fails():
    section = DraftSection(
        section_id="confidentiality",
        title="Confidentiality",
        text="Some text",
        source_references=[
            clause_reference()
        ],
    )

    report = P3GroundingValidator().validate(
        draft=make_draft(section),
        manifest=make_manifest(),
        context=P3GroundingContext(),
    )

    assert report.grounding_valid is False

    assert any(
        "cannot resolve trusted source"
        in error
        for error in report.errors
    )


def test_user_input_is_resolved_from_manifest():
    section = DraftSection(
        section_id="party",
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

    report = P3GroundingValidator().validate(
        draft=make_draft(section),
        manifest=make_manifest(
            user_fields={
                "party_a": "Company A"
            }
        ),
        context=P3GroundingContext(),
    )

    assert report.grounding_valid is True


def test_multiple_sources_must_cover_entire_section():
    section = DraftSection(
        section_id="party",
        title="Party",
        text="Party: Company A",
        source_references=[
            template_reference(),
            SourceReference(
                source_type=(
                    DraftSourceType.USER_INPUT
                ),
                source_id="party_a",
            ),
        ],
    )

    context = P3GroundingContext(
        sources=[
            TrustedSourceText(
                source_type=(
                    DraftSourceType.TEMPLATE
                ),
                source_id="template-nda",
                source_version="1.0",
                text="Party:",
            )
        ]
    )

    report = P3GroundingValidator().validate(
        draft=make_draft(section),
        manifest=make_manifest(
            user_fields={
                "party_a": "Company A"
            }
        ),
        context=context,
    )

    assert report.grounding_valid is True


def test_multiple_sources_reject_extra_text():
    section = DraftSection(
        section_id="party",
        title="Party",
        text=(
            "Party: Company A with unlimited liability"
        ),
        source_references=[
            template_reference(),
            SourceReference(
                source_type=(
                    DraftSourceType.USER_INPUT
                ),
                source_id="party_a",
            ),
        ],
    )

    context = P3GroundingContext(
        sources=[
            TrustedSourceText(
                source_type=DraftSourceType.TEMPLATE,
                source_id="template-nda",
                source_version="1.0",
                text="Party:",
            )
        ]
    )

    report = P3GroundingValidator().validate(
        draft=make_draft(section),
        manifest=make_manifest(
            user_fields={
                "party_a": "Company A"
            }
        ),
        context=context,
    )

    assert report.grounding_valid is False


# ---------------------------------------------------------
# AI transformation grounding
# ---------------------------------------------------------


def make_transformation(
    *,
    prompt_version=(
        "p3-approved-transform-v1"
    ),
):
    return AITransformationRecord(
        transformation_id="transform-001",
        target_section_id="confidentiality",
        source_ids=[
            "clause-001"
        ],
        model_tag="qwen-original",
        prompt_version=prompt_version,
    )


def test_ai_transformed_section_uses_semantic_checker():
    checker = FakeSemanticChecker(
        grounded=True
    )

    section = DraftSection(
        section_id="confidentiality",
        title="Confidentiality",
        text=(
            "Confidential information must be "
            "kept private by the recipient."
        ),
        source_references=[
            clause_reference()
        ],
    )

    report = P3GroundingValidator(
        semantic_checker=checker
    ).validate(
        draft=make_draft(section),
        manifest=make_manifest(
            transformations=[
                make_transformation()
            ]
        ),
        context=clause_context(),
    )

    assert report.grounding_valid is True
    assert checker.calls == 1
    assert (
        report.semantic_checked_section_count
        == 1
    )
    assert report.model_tag == "fake-qwen"
    assert (
        report.prompt_version
        == "p3-draft-validation-v1"
    )


def test_ai_transformed_unsupported_text_fails():
    checker = FakeSemanticChecker(
        grounded=False
    )

    section = DraftSection(
        section_id="confidentiality",
        title="Confidentiality",
        text="Modified legal text.",
        source_references=[
            clause_reference()
        ],
    )

    report = P3GroundingValidator(
        semantic_checker=checker
    ).validate(
        draft=make_draft(section),
        manifest=make_manifest(
            transformations=[
                make_transformation()
            ]
        ),
        context=clause_context(),
    )

    assert report.grounding_valid is False

    assert "confidentiality" in (
        report.ungrounded_section_ids
    )

    assert any(
        "failed semantic grounding"
        in error
        for error in report.errors
    )


def test_unregistered_transformation_prompt_fails_before_llm():
    checker = FakeSemanticChecker(
        grounded=True
    )

    section = DraftSection(
        section_id="confidentiality",
        title="Confidentiality",
        text="Modified text.",
        source_references=[
            clause_reference()
        ],
    )

    report = P3GroundingValidator(
        semantic_checker=checker
    ).validate(
        draft=make_draft(section),
        manifest=make_manifest(
            transformations=[
                make_transformation(
                    prompt_version=(
                        "unknown-prompt-v99"
                    )
                )
            ]
        ),
        context=clause_context(),
    )

    assert report.grounding_valid is False
    assert checker.calls == 0

    assert any(
        "unregistered AI transformation "
        "prompt version"
        in error
        for error in report.errors
    )


# ---------------------------------------------------------
# Combined provenance + grounding result
# ---------------------------------------------------------


def test_grounding_combines_with_provenance():
    text = (
        "The recipient shall keep the "
        "information confidential."
    )

    section = DraftSection(
        section_id="confidentiality",
        title="Confidentiality",
        text=text,
        source_references=[
            clause_reference()
        ],
    )

    draft = make_draft(section)
    manifest = make_manifest()

    provenance = (
        P3ProvenanceValidator().validate(
            draft,
            manifest,
        )
    )

    grounding = (
        P3GroundingValidator().validate(
            draft=draft,
            manifest=manifest,
            context=clause_context(text),
        )
    )

    final_result = (
        grounding.combine_with_provenance(
            provenance
        )
    )

    assert final_result.is_valid is True
    assert final_result.structure_valid is True
    assert final_result.provenance_valid is True
    assert final_result.grounding_valid is True


def test_grounding_failure_makes_final_result_invalid():
    section = DraftSection(
        section_id="confidentiality",
        title="Confidentiality",
        text="Completely changed legal text.",
        source_references=[
            clause_reference()
        ],
    )

    draft = make_draft(section)
    manifest = make_manifest()

    provenance = (
        P3ProvenanceValidator().validate(
            draft,
            manifest,
        )
    )

    grounding = (
        P3GroundingValidator().validate(
            draft=draft,
            manifest=manifest,
            context=clause_context(),
        )
    )

    final_result = (
        grounding.combine_with_provenance(
            provenance
        )
    )

    assert provenance.provenance_valid is True
    assert grounding.grounding_valid is False
    assert final_result.is_valid is False
