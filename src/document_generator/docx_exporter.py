from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from docx import Document

from .schemas import AssembledDraft, ExportResult


class DocxExporter:
    """
    Export the already assembled final text to DOCX.

    The exporter serializes draft.plain_text rather than the
    provenance section list, because sections are audit/provenance
    records and may not preserve the exact visual paragraph
    composition of the template.
    """

    def export(
        self,
        draft: AssembledDraft,
        output_path: str,
    ) -> ExportResult:

        path = Path(output_path)
        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        try:
            doc = Document()

            for line in draft.plain_text.splitlines():

                if line.strip():
                    doc.add_paragraph(line)

            doc.save(path)

            return ExportResult(
                success=True,
                format="docx",
                path=str(path),
                exported_at=datetime.now(
                    timezone.utc
                ).isoformat(),
            )

        except Exception as exc:

            return ExportResult(
                success=False,
                format="docx",
                error=str(exc),
                exported_at=datetime.now(
                    timezone.utc
                ).isoformat(),
            )