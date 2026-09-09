from datetime import (
    datetime,
    timedelta,
    timezone,
)
from pathlib import Path

import pytest

from src.clause_engine.clause_library import (
    ClauseLibrary,
)
from src.clause_engine.service import (
    M5ClauseService,
)
from src.orchestration.grounding_validator import (
    P3GroundingContext,
    TrustedSourceText,
)
from src.orchestration.m5_grounding_adapter import (
    M5ClauseNotFoundError,
    M5ClauseNotUsableError,
    M5ClauseVersionMismatchError,
    M5GroundingAdapter,
)
from src.orchestration.p3_m5_service import (
    P3M5ValidationService,
)
from src.schemas.m5_contract import (
    ApprovalStatus,
    ApprovedClause,
    ClauseType,
    DocumentType,
    Jurisdiction,
)
from src.schemas.p3_generation_contract import (
    AssembledDraft,
    ClauseReference,
    DraftSection,
    DraftSourceType,
    GenerationManifest,
    SourceReference,
)


CONFIDENTIALITY_ID = "CLZ-CONF-EG-001"
GOVERNING_LAW_ID = "CLZ-GLAW-EG-001"

VERSION = "1.0.0"


# =========================================================
# Helpers
# =========================================================


def real_m5_service() -> M5ClauseService:
    return M5ClauseService(
        library_path=Path(
            "data/clause_library.json"
        ),
        requirements_path=Path(
            "data/template_requirements.json"
        ),
    )


def integrated_service(
    m5_service: M5ClauseService | None = None,
) -> P3M5ValidationService:
    service = (
        m5_service
        if m5_service is not None
        else real_m5_service()
    )

    return P3M5ValidationService(
        m5_adapter=(
            M5GroundingAdapter(
                service
            )
        )
    )


def make_single_clause_manifest(
    *,
    clause_id: str = CONFIDENTIALITY_ID,
    version: str = VERSION,
) -> GenerationManifest:
    return GenerationManifest(
        manifest_id="manifest-001",
        draft_id="draft-001",
        template_id="template-nda",
        template_version="1.0",
        clause_references=[
            ClauseReference(
                clause_id=clause_id,
                clause_version=version,
            )
        ],
    )


def make_single_clause_draft(
    *,
    text: str,
    clause_id: str = CONFIDENTIALITY_ID,
    version: str = VERSION,
) -> AssembledDraft:
    return AssembledDraft(
        draft_id="draft-001",
        document_type="nda",
        template_id="template-nda",
        template_version="1.0",
        sections=[
            DraftSection(
                section_id="section-001",
                title="Legal Clause",
                text=text,
                source_references=[
                    SourceReference(
                        source_type=(
                            DraftSourceType
                            .APPROVED_CLAUSE
                        ),
                        source_id=clause_id,
                        source_version=version,
                    )
                ],
            )
        ],
    )


def make_custom_clause(
    *,
    clause_id: str = "CLZ-CUSTOM-EG-001",
    approval_status: ApprovalStatus = (
        ApprovalStatus.APPROVED
    ),
    effective_date: datetime | None = None,
    expiry_date: datetime | None = None,
    superseded_by: str | None = None,
) -> ApprovedClause:
    now = datetime.now(
        timezone.utc
    )

    return ApprovedClause(
        clause_id=clause_id,
        type=ClauseType.CONFIDENTIALITY,
        jurisdiction=Jurisdiction.EG,
        document_types=[
            DocumentType.NDA
        ],
        version="1.0.0",
        approval_status=approval_status,
        effective_date=(
            effective_date
            if effective_date is not None
            else now - timedelta(days=30)
        ),
        expiry_date=expiry_date,
        owner="Integration Test",
        source="Integration fixture",
        text_ar="نص قانوني معتمد للاختبار.",
        text_en=(
            "Approved legal text for integration testing."
        ),
        superseded_by=superseded_by,
    )


def service_with_clause(
    clause: ApprovedClause,
) -> M5ClauseService:
    library = ClauseLibrary()

    library.add_clause(
        clause
    )

    return M5ClauseService(
        clause_library=library
    )


# =========================================================
# Real M5 happy paths
# =========================================================


def test_real_m5_english_clause_end_to_end():
    m5 = real_m5_service()

    clause = (
        m5.clause_library.get_clause(
            CONFIDENTIALITY_ID
        )
    )

    result = integrated_service(
        m5
    ).validate(
        draft=make_single_clause_draft(
            text=clause.text_en
        ),
        manifest=(
            make_single_clause_manifest()
        ),
        clause_language="en",
    )

    validated = result.validated_draft

    assert validated.validation.is_valid is True
    assert validated.validation.structure_valid is True
    assert validated.validation.provenance_valid is True
    assert validated.validation.grounding_valid is True

    assert (
        validated.requires_lawyer_review
        is False
    )

    assert (
        result.m5_resolved_clause_ids
        == (CONFIDENTIALITY_ID,)
    )

    assert (
        result.m5_resolved_clause_count
        == 1
    )


def test_real_m5_arabic_clause_end_to_end():
    m5 = real_m5_service()

    clause = (
        m5.clause_library.get_clause(
            CONFIDENTIALITY_ID
        )
    )

    result = integrated_service(
        m5
    ).validate(
        draft=make_single_clause_draft(
            text=clause.text_ar
        ),
        manifest=(
            make_single_clause_manifest()
        ),
        clause_language="ar",
    )

    validated = result.validated_draft

    assert validated.validation.is_valid is True

    assert (
        validated.validation.grounding_valid
        is True
    )

    assert (
        validated.requires_lawyer_review
        is False
    )


# =========================================================
# Multiple approved clauses
# =========================================================


def test_multiple_real_m5_clauses_are_resolved_and_grounded():
    m5 = real_m5_service()

    confidentiality = (
        m5.clause_library.get_clause(
            CONFIDENTIALITY_ID
        )
    )

    governing_law = (
        m5.clause_library.get_clause(
            GOVERNING_LAW_ID
        )
    )

    draft = AssembledDraft(
        draft_id="draft-multi",
        document_type="nda",
        template_id="template-nda",
        template_version="1.0",
        sections=[
            DraftSection(
                section_id="confidentiality",
                title="Confidentiality",
                text=confidentiality.text_en,
                source_references=[
                    SourceReference(
                        source_type=(
                            DraftSourceType
                            .APPROVED_CLAUSE
                        ),
                        source_id=(
                            CONFIDENTIALITY_ID
                        ),
                        source_version=VERSION,
                    )
                ],
            ),
            DraftSection(
                section_id="governing-law",
                title="Governing Law",
                text=governing_law.text_en,
                source_references=[
                    SourceReference(
                        source_type=(
                            DraftSourceType
                            .APPROVED_CLAUSE
                        ),
                        source_id=(
                            GOVERNING_LAW_ID
                        ),
                        source_version=VERSION,
                    )
                ],
            ),
        ],
    )

    manifest = GenerationManifest(
        manifest_id="manifest-multi",
        draft_id="draft-multi",
        template_id="template-nda",
        template_version="1.0",
        clause_references=[
            ClauseReference(
                clause_id=(
                    CONFIDENTIALITY_ID
                ),
                clause_version=VERSION,
            ),
            ClauseReference(
                clause_id=(
                    GOVERNING_LAW_ID
                ),
                clause_version=VERSION,
            ),
        ],
    )

    result = integrated_service(
        m5
    ).validate(
        draft=draft,
        manifest=manifest,
        clause_language="en",
    )

    assert (
        result.validated_draft
        .validation
        .is_valid
        is True
    )

    assert (
        result.m5_resolved_clause_count
        == 2
    )

    assert set(
        result.m5_resolved_clause_ids
    ) == {
        CONFIDENTIALITY_ID,
        GOVERNING_LAW_ID,
    }


# =========================================================
# Tampering / wrong-language attacks
# =========================================================


def test_tampered_real_clause_is_blocked_by_m4_grounding():
    m5 = real_m5_service()

    clause = (
        m5.clause_library.get_clause(
            CONFIDENTIALITY_ID
        )
    )

    tampered_text = (
        clause.text_en
        + " The receiving party shall pay "
        + "EGP 250,000 as an automatic penalty."
    )

    result = integrated_service(
        m5
    ).validate(
        draft=make_single_clause_draft(
            text=tampered_text
        ),
        manifest=(
            make_single_clause_manifest()
        ),
        clause_language="en",
    )

    validated = result.validated_draft

    assert (
        validated.validation.provenance_valid
        is True
    )

    assert (
        validated.validation.grounding_valid
        is False
    )

    assert validated.validation.is_valid is False

    assert (
        validated.requires_lawyer_review
        is True
    )


def test_wrong_language_selection_does_not_silently_translate():
    m5 = real_m5_service()

    clause = (
        m5.clause_library.get_clause(
            CONFIDENTIALITY_ID
        )
    )

    # Draft contains English text, but adapter is explicitly
    # instructed to resolve Arabic authoritative text.
    result = integrated_service(
        m5
    ).validate(
        draft=make_single_clause_draft(
            text=clause.text_en
        ),
        manifest=(
            make_single_clause_manifest()
        ),
        clause_language="ar",
    )

    validated = result.validated_draft

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


# =========================================================
# Identity / version failures
# =========================================================


def test_unknown_clause_fails_before_m4_grounding():
    manifest = (
        make_single_clause_manifest(
            clause_id="CLZ-UNKNOWN-999"
        )
    )

    draft = make_single_clause_draft(
        text="Unknown clause text.",
        clause_id="CLZ-UNKNOWN-999",
    )

    with pytest.raises(
        M5ClauseNotFoundError
    ):
        integrated_service().validate(
            draft=draft,
            manifest=manifest,
            clause_language="en",
        )


def test_wrong_version_fails_before_m4_grounding():
    m5 = real_m5_service()

    clause = (
        m5.clause_library.get_clause(
            CONFIDENTIALITY_ID
        )
    )

    with pytest.raises(
        M5ClauseVersionMismatchError
    ):
        integrated_service(
            m5
        ).validate(
            draft=(
                make_single_clause_draft(
                    text=clause.text_en,
                    version="9.9.9",
                )
            ),
            manifest=(
                make_single_clause_manifest(
                    version="9.9.9"
                )
            ),
            clause_language="en",
        )


# =========================================================
# Lifecycle/status failures
# =========================================================


def test_expired_clause_is_rejected_end_to_end():
    now = datetime.now(
        timezone.utc
    )

    clause = make_custom_clause(
        effective_date=(
            now - timedelta(days=60)
        ),
        expiry_date=(
            now - timedelta(days=1)
        ),
    )

    m5 = service_with_clause(
        clause
    )

    draft = make_single_clause_draft(
        text=clause.text_en,
        clause_id=clause.clause_id,
    )

    manifest = make_single_clause_manifest(
        clause_id=clause.clause_id
    )

    with pytest.raises(
        M5ClauseNotUsableError
    ):
        integrated_service(
            m5
        ).validate(
            draft=draft,
            manifest=manifest,
            clause_language="en",
        )


def test_unapproved_clause_is_rejected_end_to_end():
    clause = make_custom_clause(
        approval_status=(
            ApprovalStatus.DRAFT
        )
    )

    m5 = service_with_clause(
        clause
    )

    with pytest.raises(
        M5ClauseNotUsableError
    ):
        integrated_service(
            m5
        ).validate(
            draft=(
                make_single_clause_draft(
                    text=clause.text_en,
                    clause_id=(
                        clause.clause_id
                    ),
                )
            ),
            manifest=(
                make_single_clause_manifest(
                    clause_id=(
                        clause.clause_id
                    )
                )
            ),
            clause_language="en",
        )


def test_superseded_clause_is_rejected_end_to_end():
    clause = make_custom_clause(
        approval_status=(
            ApprovalStatus.SUPERSEDED
        ),
        superseded_by=(
            "CLZ-CUSTOM-EG-002"
        ),
    )

    m5 = service_with_clause(
        clause
    )

    with pytest.raises(
        M5ClauseNotUsableError
    ):
        integrated_service(
            m5
        ).validate(
            draft=(
                make_single_clause_draft(
                    text=clause.text_en,
                    clause_id=(
                        clause.clause_id
                    ),
                )
            ),
            manifest=(
                make_single_clause_manifest(
                    clause_id=(
                        clause.clause_id
                    )
                )
            ),
            clause_language="en",
        )


# =========================================================
# Non-M5 sources
# =========================================================


def test_template_only_draft_still_works_without_m5_clauses():
    template_text = (
        "NON-DISCLOSURE AGREEMENT"
    )

    draft = AssembledDraft(
        draft_id="draft-template",
        document_type="nda",
        template_id="template-nda",
        template_version="1.0",
        sections=[
            DraftSection(
                section_id="heading",
                title="Heading",
                text=template_text,
                source_references=[
                    SourceReference(
                        source_type=(
                            DraftSourceType.TEMPLATE
                        ),
                        source_id="template-nda",
                        source_version="1.0",
                    )
                ],
            )
        ],
    )

    manifest = GenerationManifest(
        manifest_id="manifest-template",
        draft_id="draft-template",
        template_id="template-nda",
        template_version="1.0",
        clause_references=[],
    )

    context = P3GroundingContext(
        sources=[
            TrustedSourceText(
                source_type=(
                    DraftSourceType.TEMPLATE
                ),
                source_id="template-nda",
                source_version="1.0",
                text=template_text,
            )
        ]
    )

    result = integrated_service().validate(
        draft=draft,
        manifest=manifest,
        clause_language="en",
        base_grounding_context=context,
    )

    assert (
        result.m5_resolved_clause_count
        == 0
    )

    assert (
        result.validated_draft
        .validation
        .is_valid
        is True
    )


def test_m5_clause_and_template_source_can_coexist():
    m5 = real_m5_service()

    clause = (
        m5.clause_library.get_clause(
            CONFIDENTIALITY_ID
        )
    )

    template_text = "CONFIDENTIALITY"

    draft = AssembledDraft(
        draft_id="draft-combined",
        document_type="nda",
        template_id="template-nda",
        template_version="1.0",
        sections=[
            DraftSection(
                section_id="heading",
                title="Heading",
                text=template_text,
                source_references=[
                    SourceReference(
                        source_type=(
                            DraftSourceType.TEMPLATE
                        ),
                        source_id="template-nda",
                        source_version="1.0",
                    )
                ],
            ),
            DraftSection(
                section_id="clause",
                title="Confidentiality",
                text=clause.text_en,
                source_references=[
                    SourceReference(
                        source_type=(
                            DraftSourceType
                            .APPROVED_CLAUSE
                        ),
                        source_id=(
                            CONFIDENTIALITY_ID
                        ),
                        source_version=VERSION,
                    )
                ],
            ),
        ],
    )

    manifest = GenerationManifest(
        manifest_id="manifest-combined",
        draft_id="draft-combined",
        template_id="template-nda",
        template_version="1.0",
        clause_references=[
            ClauseReference(
                clause_id=(
                    CONFIDENTIALITY_ID
                ),
                clause_version=VERSION,
            )
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
                text=template_text,
            )
        ]
    )

    result = integrated_service(
        m5
    ).validate(
        draft=draft,
        manifest=manifest,
        clause_language="en",
        base_grounding_context=context,
    )

    assert (
        result.validated_draft
        .validation
        .is_valid
        is True
    )

    assert (
        result.m5_resolved_clause_count
        == 1
    )
