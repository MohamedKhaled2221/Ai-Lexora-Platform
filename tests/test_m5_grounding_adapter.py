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
    M5GroundingContextConflictError,
)
from src.schemas.m5_contract import (
    ApprovalStatus,
    ApprovedClause,
    ClauseType,
    DocumentType,
    Jurisdiction,
)
from src.schemas.p3_generation_contract import (
    ClauseReference,
    DraftSourceType,
    GenerationManifest,
)


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------


def make_manifest(
    *,
    clause_id: str = "CLZ-CONF-EG-001",
    clause_version: str = "1.0.0",
) -> GenerationManifest:
    return GenerationManifest(
        manifest_id="manifest-001",
        draft_id="draft-001",
        template_id="template-nda",
        template_version="1.0",
        clause_references=[
            ClauseReference(
                clause_id=clause_id,
                clause_version=clause_version,
            )
        ],
    )


def make_clause(
    *,
    clause_id: str = "CLZ-TEST-EG-001",
    version: str = "1.0.0",
    status: ApprovalStatus = (
        ApprovalStatus.APPROVED
    ),
    effective_date: datetime | None = None,
    expiry_date: datetime | None = None,
    superseded_by: str | None = None,
    is_lawyer_edited: bool = False,
    requires_separate_approval: bool = False,
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
        version=version,
        approval_status=status,
        effective_date=(
            effective_date
            if effective_date is not None
            else now - timedelta(days=30)
        ),
        expiry_date=expiry_date,
        owner="M5 Test Owner",
        source="M5 test source",
        text_ar="نص قانوني معتمد للاختبار.",
        text_en=(
            "Approved legal text for testing."
        ),
        superseded_by=superseded_by,
        is_lawyer_edited=is_lawyer_edited,
        requires_separate_approval=(
            requires_separate_approval
        ),
    )


def make_service_with_clause(
    clause: ApprovedClause,
) -> M5ClauseService:
    library = ClauseLibrary()

    library.add_clause(
        clause
    )

    return M5ClauseService(
        clause_library=library
    )


def real_m5_service() -> M5ClauseService:
    return M5ClauseService(
        library_path=Path(
            "data/clause_library.json"
        ),
        requirements_path=Path(
            "data/template_requirements.json"
        ),
    )


# ---------------------------------------------------------
# Real M5 seed-data integration
# ---------------------------------------------------------


def test_adapter_resolves_real_m5_clause_in_english():
    service = real_m5_service()

    clause = (
        service
        .clause_library
        .get_clause(
            "CLZ-CONF-EG-001"
        )
    )

    result = M5GroundingAdapter(
        service
    ).build_context(
        manifest=make_manifest(),
        language="en",
    )

    assert result.resolved_clause_count == 1

    assert result.resolved_clause_ids == (
        "CLZ-CONF-EG-001",
    )

    assert len(
        result.grounding_context.sources
    ) == 1

    source = (
        result.grounding_context.sources[0]
    )

    assert (
        source.source_type
        == DraftSourceType.APPROVED_CLAUSE
    )

    assert (
        source.source_id
        == "CLZ-CONF-EG-001"
    )

    assert source.source_version == "1.0.0"

    assert source.text == clause.text_en


def test_adapter_resolves_real_m5_clause_in_arabic():
    service = real_m5_service()

    clause = (
        service
        .clause_library
        .get_clause(
            "CLZ-CONF-EG-001"
        )
    )

    result = M5GroundingAdapter(
        service
    ).build_context(
        manifest=make_manifest(),
        language="ar",
    )

    source = (
        result.grounding_context.sources[0]
    )

    assert source.text == clause.text_ar


# ---------------------------------------------------------
# Existing context merge
# ---------------------------------------------------------


def test_adapter_preserves_existing_template_source():
    service = real_m5_service()

    template_source = TrustedSourceText(
        source_type=DraftSourceType.TEMPLATE,
        source_id="template-nda",
        source_version="1.0",
        text="Approved NDA template text.",
    )

    base_context = P3GroundingContext(
        sources=[
            template_source
        ]
    )

    result = M5GroundingAdapter(
        service
    ).build_context(
        manifest=make_manifest(),
        language="en",
        base_context=base_context,
    )

    assert len(
        result.grounding_context.sources
    ) == 2

    assert (
        result.grounding_context.sources[0]
        == template_source
    )


def test_identical_existing_clause_source_is_not_duplicated():
    service = real_m5_service()

    clause = (
        service
        .clause_library
        .get_clause(
            "CLZ-CONF-EG-001"
        )
    )

    base_context = P3GroundingContext(
        sources=[
            TrustedSourceText(
                source_type=(
                    DraftSourceType
                    .APPROVED_CLAUSE
                ),
                source_id=clause.clause_id,
                source_version=clause.version,
                text=clause.text_en,
            )
        ]
    )

    result = M5GroundingAdapter(
        service
    ).build_context(
        manifest=make_manifest(),
        language="en",
        base_context=base_context,
    )

    assert len(
        result.grounding_context.sources
    ) == 1


def test_conflicting_existing_clause_text_fails():
    service = real_m5_service()

    base_context = P3GroundingContext(
        sources=[
            TrustedSourceText(
                source_type=(
                    DraftSourceType
                    .APPROVED_CLAUSE
                ),
                source_id="CLZ-CONF-EG-001",
                source_version="1.0.0",
                text=(
                    "Tampered non-authoritative text."
                ),
            )
        ]
    )

    with pytest.raises(
        M5GroundingContextConflictError
    ):
        M5GroundingAdapter(
            service
        ).build_context(
            manifest=make_manifest(),
            language="en",
            base_context=base_context,
        )


# ---------------------------------------------------------
# Identity/version failures
# ---------------------------------------------------------


def test_unknown_m5_clause_fails_closed():
    service = real_m5_service()

    with pytest.raises(
        M5ClauseNotFoundError,
        match="unknown M5 clause",
    ):
        M5GroundingAdapter(
            service
        ).build_context(
            manifest=make_manifest(
                clause_id="CLZ-UNKNOWN-EG-999"
            ),
            language="en",
        )


def test_wrong_clause_version_fails_closed():
    service = real_m5_service()

    with pytest.raises(
        M5ClauseVersionMismatchError,
        match="version mismatch",
    ):
        M5GroundingAdapter(
            service
        ).build_context(
            manifest=make_manifest(
                clause_version="9.9.9"
            ),
            language="en",
        )


# ---------------------------------------------------------
# M5 status/lifecycle failures
# ---------------------------------------------------------


def test_unapproved_clause_fails_closed():
    clause = make_clause(
        status=ApprovalStatus.DRAFT
    )

    service = make_service_with_clause(
        clause
    )

    with pytest.raises(
        M5ClauseNotUsableError,
        match="approval status",
    ):
        M5GroundingAdapter(
            service
        ).build_context(
            manifest=make_manifest(
                clause_id=clause.clause_id
            ),
            language="en",
        )


def test_future_effective_clause_fails_closed():
    clause = make_clause(
        effective_date=(
            datetime.now(timezone.utc)
            + timedelta(days=30)
        )
    )

    service = make_service_with_clause(
        clause
    )

    with pytest.raises(
        M5ClauseNotUsableError,
        match="not effective yet",
    ):
        M5GroundingAdapter(
            service
        ).build_context(
            manifest=make_manifest(
                clause_id=clause.clause_id
            ),
            language="en",
        )


def test_expired_clause_fails_closed():
    now = datetime.now(
        timezone.utc
    )

    clause = make_clause(
        effective_date=(
            now - timedelta(days=60)
        ),
        expiry_date=(
            now - timedelta(days=1)
        ),
    )

    service = make_service_with_clause(
        clause
    )

    with pytest.raises(
        M5ClauseNotUsableError,
        match="expired",
    ):
        M5GroundingAdapter(
            service
        ).build_context(
            manifest=make_manifest(
                clause_id=clause.clause_id
            ),
            language="en",
        )


def test_superseded_clause_fails_closed():
    clause = make_clause(
        status=ApprovalStatus.SUPERSEDED,
        superseded_by="CLZ-NEW-EG-001",
    )

    service = make_service_with_clause(
        clause
    )

    with pytest.raises(
        M5ClauseNotUsableError
    ):
        M5GroundingAdapter(
            service
        ).build_context(
            manifest=make_manifest(
                clause_id=clause.clause_id
            ),
            language="en",
        )


def test_lawyer_edited_clause_requiring_reapproval_fails():
    clause = make_clause(
        is_lawyer_edited=True,
        requires_separate_approval=True,
    )

    service = make_service_with_clause(
        clause
    )

    with pytest.raises(
        M5ClauseNotUsableError,
        match="separate approval",
    ):
        M5GroundingAdapter(
            service
        ).build_context(
            manifest=make_manifest(
                clause_id=clause.clause_id
            ),
            language="en",
        )


# ---------------------------------------------------------
# Edge cases
# ---------------------------------------------------------


def test_manifest_without_clauses_returns_base_context():
    service = real_m5_service()

    base = P3GroundingContext(
        sources=[
            TrustedSourceText(
                source_type=DraftSourceType.TEMPLATE,
                source_id="template-nda",
                source_version="1.0",
                text="Template text.",
            )
        ]
    )

    manifest = GenerationManifest(
        manifest_id="manifest-001",
        draft_id="draft-001",
        template_id="template-nda",
        template_version="1.0",
        clause_references=[],
    )

    result = M5GroundingAdapter(
        service
    ).build_context(
        manifest=manifest,
        language="en",
        base_context=base,
    )

    assert result.resolved_clause_count == 0

    assert (
        result.grounding_context
        == base
    )


def test_invalid_language_is_rejected():
    service = real_m5_service()

    with pytest.raises(
        ValueError,
        match="language",
    ):
        M5GroundingAdapter(
            service
        ).build_context(
            manifest=make_manifest(),
            language="fr",  # type: ignore[arg-type]
        )
