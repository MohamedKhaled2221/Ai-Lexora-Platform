import pytest

from src.orchestration.grounding_validator import (
    P3GroundingContext,
    P3GroundingValidator,
    P3SemanticGroundingOutput,
    TrustedSourceText,
)
from src.orchestration.p3_orchestrator import (
    P3M4Orchestrator,
    P3ValidationContractError,
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


SOURCE_TEXT = (
    "The receiving party shall keep "
    "the information confidential."
)


def make_clause_source():
    return SourceReference(
        source_type=(
            DraftSourceType.APPROVED_CLAUSE
        ),
        source_id="clause-001",
        source_version="1.0",
    )


def make_draft(
    *,
    draft_id="draft-001",
    template_id="template-nda",
    template_version="1.0",
    text=SOURCE_TEXT,
    source_references=None,
):
    if source_references is None:
        source_references = [
            make_clause_source()
        ]

    return AssembledDraft(
        draft_id=draft_id,
        document_type="nda",
        template_id=template_id,
        template_version=template_version,
        sections=[
            DraftSection(
                section_id="confidentiality",
                title="Confidentiality",
                text=text,
                source_references=(
                    source_references
                ),
            )
        ],
    )


def make_manifest(
    *,
    draft_id="draft-001",
    template_id="template-nda",
    template_version="1.0",
    clause_references=None,
    transformations=None,
):
    if clause_references is None:
        clause_references = [
            ClauseReference(
                clause_id="clause-001",
                clause_version="1.0",
            )
        ]

    return GenerationManifest(
        manifest_id="manifest-001",
        draft_id=draft_id,
        template_id=template_id,
        template_version=template_version,
        clause_references=(
            clause_references
        ),
        ai_transformations=(
            transformations or []
        ),
    )


def make_context():
    return P3GroundingContext(
        sources=[
            TrustedSourceText(
                source_type=(
                    DraftSourceType
                    .APPROVED_CLAUSE
                ),
                source_id="clause-001",
                source_version="1.0",
                text=SOURCE_TEXT,
            )
        ]
    )


# ---------------------------------------------------------
# Deterministic valid draft
# ---------------------------------------------------------


def test_valid_deterministic_draft_passes():
    result = P3M4Orchestrator().validate(
        draft=make_draft(),
        manifest=make_manifest(),
        grounding_context=make_context(),
    )

    validated = (
        result.validated_draft
    )

    assert validated.validation.is_valid is True

    assert (
        validated.validation.structure_valid
        is True
    )

    assert (
        validated.validation.provenance_valid
        is True
    )

    assert (
        validated.validation.grounding_valid
        is True
    )

    assert (
        validated.requires_lawyer_review
        is False
    )

    assert validated.model_tag is None
    assert validated.prompt_version is None

    assert (
        result.metrics.provenance_checked
        is True
    )

    assert (
        result.metrics.grounding_checked
        is True
    )

    assert (
        result.metrics.semantic_grounding_used
        is False
    )


# ---------------------------------------------------------
# Provenance failure short circuit
# ---------------------------------------------------------


class GroundingValidatorMustNotRun:
    def validate(
        self,
        **kwargs,
    ):
        raise AssertionError(
            "Grounding validator must not run "
            "after provenance failure."
        )


def test_provenance_failure_skips_grounding():
    draft = make_draft(
        source_references=[],
    )

    orchestrator = P3M4Orchestrator(
        grounding_validator=(
            GroundingValidatorMustNotRun()
        )
    )

    result = orchestrator.validate(
        draft=draft,
        manifest=make_manifest(
            clause_references=[]
        ),
        grounding_context=(
            P3GroundingContext()
        ),
    )

    validated = (
        result.validated_draft
    )

    assert validated.validation.is_valid is False

    assert (
        validated.validation.provenance_valid
        is False
    )

    assert (
        validated.validation.grounding_valid
        is False
    )

    assert (
        validated.requires_lawyer_review
        is True
    )

    assert (
        result.metrics.grounding_checked
        is False
    )

    assert any(
        "Grounding validation was skipped"
        in error
        for error
        in validated.validation.errors
    )


# ---------------------------------------------------------
# Structural contract failures
# ---------------------------------------------------------


def test_draft_id_mismatch_raises_contract_error():
    with pytest.raises(
        P3ValidationContractError,
    ) as exc_info:
        P3M4Orchestrator().validate(
            draft=make_draft(
                draft_id="draft-001"
            ),
            manifest=make_manifest(
                draft_id="draft-999"
            ),
            grounding_context=make_context(),
        )

    report = (
        exc_info.value
        .provenance_report
    )

    assert report is not None
    assert report.structure_valid is False


def test_template_id_mismatch_raises_contract_error():
    with pytest.raises(
        P3ValidationContractError
    ):
        P3M4Orchestrator().validate(
            draft=make_draft(
                template_id="template-nda"
            ),
            manifest=make_manifest(
                template_id="template-other"
            ),
            grounding_context=make_context(),
        )


def test_template_version_mismatch_raises_contract_error():
    with pytest.raises(
        P3ValidationContractError
    ):
        P3M4Orchestrator().validate(
            draft=make_draft(
                template_version="1.0"
            ),
            manifest=make_manifest(
                template_version="2.0"
            ),
            grounding_context=make_context(),
        )


# ---------------------------------------------------------
# Grounding failure
# ---------------------------------------------------------


def test_changed_legal_text_requires_lawyer_review():
    result = P3M4Orchestrator().validate(
        draft=make_draft(
            text=(
                SOURCE_TEXT
                + " The receiving party must "
                "pay a penalty."
            )
        ),
        manifest=make_manifest(),
        grounding_context=make_context(),
    )

    validated = result.validated_draft

    assert validated.validation.is_valid is False

    assert (
        validated.validation.provenance_valid
        is True
    )

    assert (
        validated.validation.grounding_valid
        is False
    )

    assert (
        validated.requires_lawyer_review
        is True
    )


# ---------------------------------------------------------
# Semantic grounding
# ---------------------------------------------------------


class FakeSemanticChecker:
    def __init__(
        self,
        *,
        grounded: bool,
    ):
        self.grounded = grounded
        self.calls = 0

    @property
    def model_tag(self):
        return "fake-qwen"

    @property
    def prompt_version(self):
        return "p3-draft-validation-v1"

    def check(
        self,
        *,
        section,
        sources,
        transformation_metadata,
    ):
        self.calls += 1

        if self.grounded:
            return P3SemanticGroundingOutput(
                grounded=True,
                unsupported_fragments=[],
                reason=(
                    "Transformation remains "
                    "supported."
                ),
            )

        return P3SemanticGroundingOutput(
            grounded=False,
            unsupported_fragments=[
                "unsupported obligation"
            ],
            reason=(
                "Transformation introduced "
                "unsupported legal content."
            ),
        )


def make_transformation():
    return AITransformationRecord(
        transformation_id="transform-001",
        target_section_id=(
            "confidentiality"
        ),
        source_ids=[
            "clause-001"
        ],
        model_tag="qwen-source",
        prompt_version=(
            "p3-approved-transform-v1"
        ),
    )


def test_semantically_grounded_transformation_passes():
    checker = FakeSemanticChecker(
        grounded=True
    )

    grounding_validator = (
        P3GroundingValidator(
            semantic_checker=checker
        )
    )

    orchestrator = P3M4Orchestrator(
        grounding_validator=(
            grounding_validator
        )
    )

    result = orchestrator.validate(
        draft=make_draft(
            text=(
                "The receiving party must "
                "keep the information private."
            )
        ),
        manifest=make_manifest(
            transformations=[
                make_transformation()
            ]
        ),
        grounding_context=make_context(),
    )

    validated = result.validated_draft

    assert validated.validation.is_valid is True

    assert (
        validated.requires_lawyer_review
        is False
    )

    assert validated.model_tag == "fake-qwen"

    assert (
        validated.prompt_version
        == "p3-draft-validation-v1"
    )

    assert (
        result.metrics.semantic_grounding_used
        is True
    )

    assert checker.calls == 1


def test_semantic_grounding_failure_requires_review():
    checker = FakeSemanticChecker(
        grounded=False
    )

    orchestrator = P3M4Orchestrator(
        grounding_validator=(
            P3GroundingValidator(
                semantic_checker=checker
            )
        )
    )

    result = orchestrator.validate(
        draft=make_draft(
            text="Modified legal text."
        ),
        manifest=make_manifest(
            transformations=[
                make_transformation()
            ]
        ),
        grounding_context=make_context(),
    )

    validated = result.validated_draft

    assert validated.validation.is_valid is False

    assert (
        validated.validation.grounding_valid
        is False
    )

    assert (
        validated.requires_lawyer_review
        is True
    )

    assert checker.calls == 1


# ---------------------------------------------------------
# Output preservation
# ---------------------------------------------------------


def test_output_preserves_original_draft_and_manifest():
    draft = make_draft()
    manifest = make_manifest()

    result = P3M4Orchestrator().validate(
        draft=draft,
        manifest=manifest,
        grounding_context=make_context(),
    )

    assert (
        result.validated_draft.draft
        == draft
    )

    assert (
        result.validated_draft.manifest
        == manifest
    )


def test_validator_version_is_recorded():
    result = P3M4Orchestrator(
        validator_version="test-validator-v99"
    ).validate(
        draft=make_draft(),
        manifest=make_manifest(),
        grounding_context=make_context(),
    )

    assert (
        result.validated_draft
        .validator_version
        == "test-validator-v99"
    )
