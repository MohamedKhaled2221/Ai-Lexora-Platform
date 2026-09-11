from __future__ import annotations

from typing import Iterable

from .document_assembler import DocumentAssembler
from .docx_exporter import DocxExporter
from .guided_input import validate_guided_input, validate_field_types
from .manifest import build_generation_manifest
from .pdf_exporter import PdfExporter
from .schemas import (
    ApprovedClause,
    AssembledDraft,
    ClauseDecision,
    GenerationManifest,
    GuidedDocumentRequest,
)
from .template_registry import TemplateRegistry
from .template_selector import TemplateSelector
from .validators import DraftValidator


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
        clauses: Iterable[ApprovedClause],
        decisions: Iterable[ClauseDecision] = (),
    ) -> tuple[AssembledDraft, GenerationManifest]:

        template = self.selector.select(request)

        validate_guided_input(request, template)
        validate_field_types(request, template)

        clauses = list(clauses)
        decisions = list(decisions)

        draft = self.assembler.assemble(
            request,
            template,
            clauses,
            decisions,
        )

        result = self.validator.validate(
            draft,
            template,
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