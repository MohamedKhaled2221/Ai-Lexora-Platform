from pathlib import Path

import pytest

from src.clause_engine.service import (
    M5ClauseService,
)
from src.orchestration.grounding_validator import (
    P3GroundingContext,
    TrustedSourceText,
)
from src.orchestration.m5_grounding_adapter import (
    M5ClauseVersionMismatchError,
    M5GroundingAdapter,
)
from src.orchestration.p3_m5_service import (
    P3M5ValidationService,
)
from src.schemas.p3_generation_contract import (
    AssembledDraft,
    ClauseReference,
    DraftSection,
    DraftSourceType,
    GenerationManifest,
    SourceReference,
)


CLAUSE_ID = "CLZ-CONF-EG-001"
CLAUSE_VERSION = "1.0.0"


def m5_service():
    return M5ClauseService(
        library_path=Path(
            "data/clause_library.json"
        ),
        requirements_path=Path(
            "data/template_requirements.json"
        ),
    )


def integrated_service():
    service = m5_service()

    return P3M5ValidationService(
        m5_adapter=(
            M5GroundingAdapter(
                service
            )
        )
    )


def make_manifest(
    *,
    version=CLAUSE_VERSION,
):
    return GenerationManifest(
        manifest_id="manifest-001",
        draft_id="draft-001",
        template_id="template-nda",
        template_version="1.0",
        clause_references=[
            ClauseReference(
                clause_id=CLAUSE_ID,
                clause_version=version,
            )
        ],
    )


def make_draft(
    text: str,
):
    return AssembledDraft(
        draft_id="draft-001",
        document_type="nda",
        template_id="template-nda",
        template_version="1.0",
        sections=[
            DraftSection(
                section_id="confidentiality",
                title="Confidentiality",
                text=text,
                source_references=[
                    SourceReference(
                        source_type=(
                            DraftSourceType
                            .APPROVED_CLAUSE
                        ),
                        source_id=CLAUSE_ID,
                        source_version=(
                            CLAUSE_VERSION
                        ),
                    )
                ],
            )
        ],
    )


def test_real_m5_english_clause_passes_without_manual_context():
    m5 = m5_service()

    clause = (
        m5.clause_library.get_clause(
            CLAUSE_ID
        )
    )

    result = (
        integrated_service()
        .validate(
            draft=make_draft(
                clause.text_en
            ),
            manifest=make_manifest(),
            clause_language="en",
        )
    )

    assert (
        result
        .validated_draft
        .validation
        .is_valid
        is True
    )

    assert (
        result
        .validated_draft
        .requires_lawyer_review
        is False
    )

    assert (
        result.m5_resolved_clause_ids
        == (CLAUSE_ID,)
    )

    assert (
        result.m5_resolved_clause_count
        == 1
    )


def test_real_m5_arabic_clause_passes():
    m5 = m5_service()

    clause = (
        m5.clause_library.get_clause(
            CLAUSE_ID
        )
    )

    result = (
        integrated_service()
        .validate(
            draft=make_draft(
                clause.text_ar
            ),
            manifest=make_manifest(),
            clause_language="ar",
        )
    )

    assert (
        result
        .validated_draft
        .validation
        .is_valid
        is True
    )


def test_wrong_m5_version_is_rejected_before_grounding():
    m5 = m5_service()

    clause = (
        m5.clause_library.get_clause(
            CLAUSE_ID
        )
    )

    with pytest.raises(
        M5ClauseVersionMismatchError
    ):
        integrated_service().validate(
            draft=make_draft(
                clause.text_en
            ),
            manifest=make_manifest(
                version="9.9.9"
            ),
            clause_language="en",
        )


def test_extra_unsourced_legal_text_still_fails_m4_grounding():
    m5 = m5_service()

    clause = (
        m5.clause_library.get_clause(
            CLAUSE_ID
        )
    )

    result = (
        integrated_service()
        .validate(
            draft=make_draft(
                clause.text_en
                + " The receiving party shall "
                "also pay EGP 100,000."
            ),
            manifest=make_manifest(),
            clause_language="en",
        )
    )

    assert (
        result
        .validated_draft
        .validation
        .provenance_valid
        is True
    )

    assert (
        result
        .validated_draft
        .validation
        .grounding_valid
        is False
    )

    assert (
        result
        .validated_draft
        .requires_lawyer_review
        is True
    )


def test_non_m5_template_context_is_preserved():
    m5 = m5_service()

    clause = (
        m5.clause_library.get_clause(
            CLAUSE_ID
        )
    )

    template_source = TrustedSourceText(
        source_type=(
            DraftSourceType.TEMPLATE
        ),
        source_id="another-template",
        source_version="1.0",
        text="Template source.",
    )

    base_context = P3GroundingContext(
        sources=[
            template_source
        ]
    )

    result = (
        integrated_service()
        .validate(
            draft=make_draft(
                clause.text_en
            ),
            manifest=make_manifest(),
            clause_language="en",
            base_grounding_context=(
                base_context
            ),
        )
    )

    assert (
        result
        .validated_draft
        .validation
        .is_valid
        is True
    )
