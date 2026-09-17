from __future__ import annotations

from typing import Iterable

from .document_assembler import DocumentAssembler
from .docx_exporter import DocxExporter
from .guided_input import validate_guided_input, validate_field_types
from .manifest import build_generation_manifest
from .pdf_exporter import PdfExporter
from .schemas import (
    AssembledDraft,
    ClauseDecision,
    GenerationManifest,
    GuidedDocumentRequest,
)
from .template_registry import TemplateRegistry
from .template_selector import TemplateSelector
from .validators import DraftValidator
from src.schemas.m5_contract import (
    ApprovedClause,
    TemplateClauseRequirement,
)

class M1DocumentService:
    def __init__(
        self,
        registry: TemplateRegistry,
        *,
        assembler=None,
        validator=None,
        docx_exporter=None,
        pdf_exporter=None,
    ):
        self.selector = TemplateSelector(registry)
        self.assembler = assembler or DocumentAssembler()
        self.validator = validator or DraftValidator()
        self.docx_exporter = docx_exporter or DocxExporter()
        self.pdf_exporter = pdf_exporter or PdfExporter()

    def build_draft(
        self,
        request: GuidedDocumentRequest,
        requirement: TemplateClauseRequirement,
        clauses: Iterable[ApprovedClause],
        decisions: Iterable[ClauseDecision] = (),
    ) -> tuple[
        AssembledDraft,
        GenerationManifest,
    ]:

        template = self.selector.select(request)
        self._validate_requirement_identity(
            template_id=template.template_id,
            document_type=request.document_type,
            jurisdiction=request.jurisdiction,
            requirement=requirement,
        )
        validate_guided_input(request, template)
        validate_field_types(request, template)

        clauses = list(clauses)
        decisions = list(decisions)

        draft = self.assembler.assemble(
            request,
            template,
            requirement,
            clauses,
            decisions,
        )

        result = self.validator.validate(
            draft,
            template,
            requirement,
            clauses,
            decisions,
        )

        if not result.valid:
            raise ValueError(
                "Draft failed validation: " + " | ".join(result.errors)
            )

        manifest = build_generation_manifest(
            request,
            draft,
            clauses,
        )

        return draft, manifest
    @staticmethod
    def _validate_requirement_identity(
        *,
        template_id: str,
        document_type: str,
        jurisdiction: str,
        requirement: TemplateClauseRequirement,
    ) -> None:

        if requirement.template_id != template_id:
            raise ValueError(
                "M1 template and M5 requirement "
                "template_id mismatch: "
                f"{template_id} != "
                f"{requirement.template_id}"
            )

        if (
            requirement.document_type.value
            != document_type
        ):
            raise ValueError(
                "M1 request and M5 requirement "
                "document_type mismatch: "
                f"{document_type} != "
                f"{requirement.document_type.value}"
            )

        if (
            requirement.jurisdiction.value
            != jurisdiction
        ):
            raise ValueError(
                "M1 request and M5 requirement "
                "jurisdiction mismatch: "
                f"{jurisdiction} != "
                f"{requirement.jurisdiction.value}"
            )
    def export(
        self,
        draft: AssembledDraft,
        *,
        docx_path: str,
        pdf_dir: str,
    ):
        docx_result = self.docx_exporter.export(
            draft,
            docx_path,
        )

        if not docx_result.success:
            return docx_result, None

        pdf_result = self.pdf_exporter.export(
            docx_result.path,
            pdf_dir,
        )

        return docx_result, pdf_result