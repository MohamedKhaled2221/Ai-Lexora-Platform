from __future__ import annotations

import tempfile
from pathlib import Path
from uuid import uuid4

from docx import Document

from .schemas import (
    ClauseDecision,
    FieldDefinition,
    GuidedDocumentRequest,
    TemplateDefinition,
)
from .service import M1DocumentService
from .template_registry import TemplateRegistry
from datetime import (
    datetime,
    timedelta,
    timezone,
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

def build_demo_template(path: Path) -> None:
    doc = Document()

    doc.add_heading("NON-LEGAL DEMO AGREEMENT", level=1)

    doc.add_paragraph("Party A: {{party_a_name}}")
    doc.add_paragraph("Party B: {{party_b_name}}")
    doc.add_paragraph("Effective Date: {{effective_date}}")

    doc.add_paragraph(
        "Approved Section: "
        "{{TERMINATION_CLAUSE}}"
    )

    doc.save(path)


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        # ---------------------------------------------------------
        # 1. Create a temporary DOCX template for the technical demo
        # ---------------------------------------------------------
        template_path = tmp / "demo.docx"
        build_demo_template(template_path)

        # ---------------------------------------------------------
        # 2. Define the template
        # ---------------------------------------------------------
        template = TemplateDefinition(
            template_id="TMPL-EMP-EG-DEMO",
            version="1.0.0",
            document_type=DocumentType.EMPLOYMENT_CONTRACT.value,
            jurisdiction=Jurisdiction.EG.value,
            language="en",
            file_path=str(template_path),
            fields=[
                FieldDefinition(
                    name="party_a_name",
                    label="Party A Name",
                    required=True,
                ),
                FieldDefinition(
                    name="party_b_name",
                    label="Party B Name",
                    required=True,
                ),
                FieldDefinition(
                    name="effective_date",
                    label="Effective Date",
                    required=True,
                ),
            ],
        )
        requirement = TemplateClauseRequirement(
            template_id="TMPL-EMP-EG-DEMO",
            document_type=(
                DocumentType.EMPLOYMENT_CONTRACT
            ),
            jurisdiction=Jurisdiction.EG,
            required_clauses=[
                "CLZ-TERM-EG-DEMO"
            ],
            section_placeholders={
                "section_termination":
                    "{{TERMINATION_CLAUSE}}"
            },
            template_structure=(
                "{{TERMINATION_CLAUSE}}"
            ),
        )
        # ---------------------------------------------------------
        # 3. Create a demo approved clause
        # ---------------------------------------------------------
        now = datetime.now(timezone.utc)

        clause = ApprovedClause(
            clause_id="CLZ-TERM-EG-DEMO",
            type=ClauseType.TERMINATION,
            jurisdiction=Jurisdiction.EG,
            document_types=[
                DocumentType.EMPLOYMENT_CONTRACT
            ],
            version="1.0.0",
            approval_status=ApprovalStatus.APPROVED,
            effective_date=(
                now - timedelta(days=1)
            ),
            owner="demo",
            source="DEMO-SOURCE",
            text_ar="نص تجريبي غير قانوني",
            text_en=(
                "NON-LEGAL TEST TEXT — "
                "replace with an approved M5 clause."
            ),
            metadata=ClauseMetadata(
                insertion_key="section_termination"
            ),
        )

        # ---------------------------------------------------------
        # 4. Create the clause decision
        # ---------------------------------------------------------
        decision = ClauseDecision(
            clause_id="demo_clause_1",
            decision="required",
        )

        # ---------------------------------------------------------
        # 5. Create guided user input
        # ---------------------------------------------------------
        request = GuidedDocumentRequest(
            request_id="REQ-DEMO-001",
            document_type=DocumentType.EMPLOYMENT_CONTRACT.value,
            jurisdiction=Jurisdiction.EG.value,
            fields={
                "party_a_name": "Example Company",
                "party_b_name": "Ahmed Ali",
                "effective_date": "2026-09-17",
            },
        )

        # ---------------------------------------------------------
        # 6. Initialize M1 service
        # ---------------------------------------------------------
        service = M1DocumentService(
            TemplateRegistry([template])
        )

        # ---------------------------------------------------------
        # 7. Build the assembled draft + generation manifest
        # ---------------------------------------------------------
        draft, manifest = service.build_draft(
            request,
            requirement,
            [clause],
            [decision],
        )

        # ---------------------------------------------------------
        # 8. Export DOCX + PDF
        # ---------------------------------------------------------
        docx_result, pdf_result = service.export(
            draft,
            docx_path=str(tmp / "demo_output.docx"),
            pdf_dir=str(tmp / "exports"),
        )

        # ---------------------------------------------------------
        # 9. Print results
        # ---------------------------------------------------------
        print("Draft:", draft.draft_id)

        print("\nGeneration Manifest:")
        print(manifest.model_dump_json(indent=2))

        print("\nDOCX:")
        print(docx_result.model_dump())

        print("\nPDF:")
        print(
            pdf_result.model_dump()
            if pdf_result
            else None
        )


if __name__ == "__main__":
    main()