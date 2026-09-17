from __future__ import annotations

from datetime import (
    datetime,
    timedelta,
    timezone,
)
from pathlib import Path

import pytest
from docx import Document

from src.clause_engine.clause_library import (
    ClauseLibrary,
)
from src.clause_engine.required_clause_rules import (
    RequiredClauseEngine,
)
from src.clause_engine.service import (
    M5ClauseService,
)
from src.document_generator.schemas import (
    FieldDefinition,
    GuidedDocumentRequest,
    TemplateDefinition,
)
from src.document_generator.service import (
    M1DocumentService,
)
from src.document_generator.template_registry import (
    TemplateRegistry,
)
from src.orchestration.m5_grounding_adapter import (
    M5GroundingAdapter,
)
from src.orchestration.p3_generation_service import (
    P3GenerationIntegrationError,
    P3GenerationService,
)
from src.orchestration.p3_m5_service import (
    P3M5ValidationService,
)
from src.schemas.m5_contract import (
    ApprovalStatus,
    ApprovedClause,
    ClauseMetadata,
    ClauseType,
    DocumentType,
    Jurisdiction,
    TemplateClauseRequirement,
)


def build_service(
    tmp_path: Path,
) -> P3GenerationService:

    template_path = (
        tmp_path / "employment.docx"
    )

    doc = Document()

    doc.add_paragraph(
        "Employee: {{employee_name}}."
    )

    doc.add_paragraph(
        "Termination: "
        "{{TERMINATION_CLAUSE}}"
    )

    doc.add_paragraph(
        "{{CONFIDENTIALITY_CLAUSE}}"
    )

    doc.save(template_path)

    template = TemplateDefinition(
        template_id="TMPL-EMP-EG-001",
        version="1.0.0",
        document_type=(
            DocumentType
            .EMPLOYMENT_CONTRACT
            .value
        ),
        jurisdiction=(
            Jurisdiction.EG.value
        ),
        file_path=str(template_path),
        fields=[
            FieldDefinition(
                name="employee_name",
                label="Employee",
            )
        ],
    )

    m1_service = M1DocumentService(
        TemplateRegistry(
            [template]
        )
    )

    now = datetime.now(
        timezone.utc
    )

    termination = ApprovedClause(
        clause_id="CLZ-TERM-EG-001",
        type=ClauseType.TERMINATION,
        jurisdiction=Jurisdiction.EG,
        document_types=[
            DocumentType
            .EMPLOYMENT_CONTRACT
        ],
        version="1.0.0",
        approval_status=(
            ApprovalStatus.APPROVED
        ),
        effective_date=(
            now - timedelta(days=1)
        ),
        owner="legal",
        source="approved source",
        text_ar="نص الإنهاء المعتمد",
        text_en=(
            "Approved termination text."
        ),
        metadata=ClauseMetadata(
            insertion_key=(
                "section_termination"
            )
        ),
    )

    confidentiality = ApprovedClause(
        clause_id="CLZ-CONF-EMP-EG-001",
        type=ClauseType.CONFIDENTIALITY,
        jurisdiction=Jurisdiction.EG,
        document_types=[
            DocumentType
            .EMPLOYMENT_CONTRACT
        ],
        version="1.0.0",
        approval_status=(
            ApprovalStatus.APPROVED
        ),
        effective_date=(
            now - timedelta(days=1)
        ),
        owner="legal",
        source="approved source",
        text_ar="نص السرية المعتمد",
        text_en=(
            "Approved confidentiality text."
        ),
        metadata=ClauseMetadata(
            insertion_key=(
                "section_confidentiality"
            )
        ),
    )

    library = ClauseLibrary()

    library.add_clause(termination)
    library.add_clause(confidentiality)

    requirement = (
        TemplateClauseRequirement(
            template_id=(
                "TMPL-EMP-EG-001"
            ),
            document_type=(
                DocumentType
                .EMPLOYMENT_CONTRACT
            ),
            jurisdiction=(
                Jurisdiction.EG
            ),
            required_clauses=[
                "CLZ-TERM-EG-001"
            ],
            optional_clauses=[
                "CLZ-CONF-EMP-EG-001"
            ],
            section_placeholders={
                "section_termination":
                    "{{TERMINATION_CLAUSE}}",
                "section_confidentiality":
                    "{{CONFIDENTIALITY_CLAUSE}}",
            },
            template_structure=(
                "Employee: "
                "{{employee_name}}.\n"
                "Termination: "
                "{{TERMINATION_CLAUSE}}\n"
                "{{CONFIDENTIALITY_CLAUSE}}"
            ),
        )
    )

    engine = RequiredClauseEngine(
        library
    )

    engine.add_template(
        requirement
    )

    m5_service = M5ClauseService(
        clause_library=library,
        required_clause_engine=engine,
    )

    m4_service = P3M5ValidationService(
        m5_adapter=(
            M5GroundingAdapter(
                m5_service
            )
        )
    )

    return P3GenerationService(
        m5_service=m5_service,
        m1_service=m1_service,
        m4_validation_service=(
            m4_service
        ),
    )


def request():
    return GuidedDocumentRequest(
        request_id="REQ-P3-001",
        document_type=(
            DocumentType
            .EMPLOYMENT_CONTRACT
            .value
        ),
        jurisdiction=(
            Jurisdiction.EG.value
        ),
        fields={
            "employee_name": "Ahmed"
        },
    )


def test_full_p3_m5_m1_m4_export_flow(
    tmp_path: Path,
):
    service = build_service(
        tmp_path
    )

    output = tmp_path / "result.docx"

    result = service.generate(
        request=request(),
        clause_language="en",
        docx_path=str(output),
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

    assert result.export_allowed is True

    assert result.docx_result
    assert result.docx_result.success

    assert output.exists()

    assert result.selected_clause_ids == (
        "CLZ-TERM-EG-001",
    )

    assert (
        result.m5_resolved_clause_count
        == 1
    )

    sections = (
        result
        .validated_draft
        .draft
        .sections
    )

    assert any(
        reference.source_type.value
        == "user_input"
        for section in sections
        for reference
        in section.source_references
    )

    assert any(
        reference.source_type.value
        == "approved_clause"
        for section in sections
        for reference
        in section.source_references
    )


def test_optional_clause_is_used_only_when_requested(
    tmp_path: Path,
):
    service = build_service(
        tmp_path
    )

    result = service.generate(
        request=request(),
        optional_clause_ids=[
            "CLZ-CONF-EMP-EG-001"
        ],
    )

    assert set(
        result.selected_clause_ids
    ) == {
        "CLZ-TERM-EG-001",
        "CLZ-CONF-EMP-EG-001",
    }

    text = "\n".join(
        section.text
        for section
        in result
        .validated_draft
        .draft
        .sections
    )

    assert (
        "Approved confidentiality text."
        in text
    )


def test_unknown_optional_clause_is_rejected(
    tmp_path: Path,
):
    service = build_service(
        tmp_path
    )

    with pytest.raises(
        P3GenerationIntegrationError,
        match="not optional clauses",
    ):
        service.generate(
            request=request(),
            optional_clause_ids=[
                "CLZ-NOT-OPTIONAL"
            ],
        )
