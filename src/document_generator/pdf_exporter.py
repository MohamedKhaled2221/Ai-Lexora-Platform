from __future__ import annotations

import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .schemas import ExportResult


class PdfExporter:
    """
    Convert an assembled DOCX document to PDF using a local
    LibreOffice/soffice installation.

    No legal content is generated or modified here.
    """

    def export(
        self,
        docx_path: str,
        output_dir: str,
    ) -> ExportResult:

        out_dir = Path(output_dir)
        out_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        source = Path(docx_path)

        # ---------------------------------------------------------
        # 1. Validate source DOCX
        # ---------------------------------------------------------
        if not source.exists():
            return ExportResult(
                success=False,
                format="pdf",
                error=f"Source DOCX does not exist: {docx_path}",
                exported_at=datetime.now(
                    timezone.utc
                ).isoformat(),
            )

        if not source.is_file():
            return ExportResult(
                success=False,
                format="pdf",
                error=f"Source DOCX is not a file: {docx_path}",
                exported_at=datetime.now(
                    timezone.utc
                ).isoformat(),
            )

        # ---------------------------------------------------------
        # 2. Find local LibreOffice installation
        # ---------------------------------------------------------
        soffice = (
            shutil.which("soffice")
            or shutil.which("libreoffice")
        )

        if not soffice:
            return ExportResult(
                success=False,
                format="pdf",
                error=(
                    "LibreOffice/soffice not found for "
                    "local DOCX->PDF conversion."
                ),
                exported_at=datetime.now(
                    timezone.utc
                ).isoformat(),
            )

        # ---------------------------------------------------------
        # 3. Convert DOCX -> PDF
        # ---------------------------------------------------------
        try:
            result = subprocess.run(
                [
                    soffice,
                    "--headless",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    str(out_dir),
                    str(source),
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode != 0:
                error_message = (
                    result.stderr.strip()
                    or result.stdout.strip()
                    or "LibreOffice PDF conversion failed."
                )

                return ExportResult(
                    success=False,
                    format="pdf",
                    error=error_message,
                    exported_at=datetime.now(
                        timezone.utc
                    ).isoformat(),
                )

            # -----------------------------------------------------
            # 4. Verify generated PDF
            # -----------------------------------------------------
            pdf_path = out_dir / f"{source.stem}.pdf"

            if not pdf_path.exists():
                return ExportResult(
                    success=False,
                    format="pdf",
                    error="PDF conversion completed but no PDF was produced.",
                    exported_at=datetime.now(
                        timezone.utc
                    ).isoformat(),
                )

            return ExportResult(
                success=True,
                format="pdf",
                path=str(pdf_path),
                exported_at=datetime.now(
                    timezone.utc
                ).isoformat(),
            )

        except subprocess.TimeoutExpired:
            return ExportResult(
                success=False,
                format="pdf",
                error="LibreOffice PDF conversion timed out.",
                exported_at=datetime.now(
                    timezone.utc
                ).isoformat(),
            )

        except Exception as exc:
            return ExportResult(
                success=False,
                format="pdf",
                error=str(exc),
                exported_at=datetime.now(
                    timezone.utc
                ).isoformat(),
            )