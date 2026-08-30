"""M1 HTTP interface.

Two consumers, two contracts:

* **M1 -> M2/M3** -- ``POST /ingest`` returns the full ``DocumentChunk`` list
  for a document. This is the retrieval/QA feed.
* **M1 -> M5** -- ``POST /clauses`` returns only clause-level chunks, in a
  flattened shape convenient for contract intelligence.

Both are thin wrappers over :mod:`src.pipeline`; if you are inside the same
Python process, call ``pipeline.ingest()`` / ``pipeline.get_clause_chunks()``
directly and skip the HTTP hop.

Run locally::

    uvicorn src.api:app --host 127.0.0.1 --port 8000

Interactive docs at ``/docs``, OpenAPI JSON at ``/openapi.json``.

DEPLOYMENT NOTE: binds to ``127.0.0.1`` in the examples on purpose. Everything
here runs on firm infrastructure; nothing calls out. There is no authentication
layer because the service is not intended to be network-exposed -- if it is
ever put on the firm LAN, put it behind the firm's existing auth, do not add a
second scheme here.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from .config import PipelineConfig
from .document_chunk_schema import DocumentChunk, DocumentIngestResult
from .pipeline import clause_view, get_clause_chunks, process_document

logger = logging.getLogger(__name__)

app = FastAPI(
    title="M1 Document Processing",
    version="0.1.0",
    description=(
        "Turns legal documents (PDF / DOCX / TXT / image) into standardized "
        "DocumentChunk objects.\n\n"
        "**Runs entirely on firm infrastructure.** No cloud APIs, no data egress.\n\n"
        "- `POST /ingest` -- M1 -> M2/M3: all chunks for a document\n"
        "- `POST /clauses` -- M1 -> M5: clause-level chunks only\n"
    ),
)

# Accepted upload extensions. Type detection re-checks by magic bytes anyway;
# this is only a cheap early reject.
_ALLOWED_SUFFIXES = {
    ".pdf", ".docx", ".txt", ".md",
    ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp",
}
MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # 200 MB


# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------


class IngestOptions(BaseModel):
    """Per-request overrides for the pipeline defaults.

    Only the knobs a caller plausibly wants to vary per document are exposed.
    Everything else lives in :class:`~src.config.PipelineConfig` and is set
    process-wide.
    """

    target_chunk_chars: int | None = Field(default=None, ge=100, le=20000)
    max_chunk_chars: int | None = Field(default=None, ge=200, le=40000)
    overlap_chars: int | None = Field(default=None, ge=0, le=2000)
    respect_structure: bool | None = None
    ocr_enabled: bool | None = None
    keep_raw_text: bool | None = Field(
        default=None,
        description="include pre-normalization text in metadata.raw_text "
                    "(roughly doubles response size)",
    )
    emit_display_form: bool | None = Field(
        default=None,
        description="also emit metadata.display_text (reshaped/bidi presentation "
                    "form). For rendering only -- never embed it.",
    )

    def apply(self, base: PipelineConfig) -> PipelineConfig:
        cfg = base.model_copy(deep=True)
        if self.target_chunk_chars is not None:
            cfg.chunking.target_chunk_chars = self.target_chunk_chars
        if self.max_chunk_chars is not None:
            cfg.chunking.max_chunk_chars = self.max_chunk_chars
        if self.overlap_chars is not None:
            cfg.chunking.overlap_chars = self.overlap_chars
        if self.respect_structure is not None:
            cfg.chunking.respect_structure = self.respect_structure
        if self.ocr_enabled is not None:
            cfg.ocr.enabled = self.ocr_enabled
        if self.keep_raw_text is not None:
            cfg.keep_raw_text_in_metadata = self.keep_raw_text
        if self.emit_display_form is not None:
            cfg.rtl.emit_display_form = self.emit_display_form
        return cfg


class IngestResponse(BaseModel):
    """``POST /ingest`` response. **The M1 -> M2/M3 contract.**"""

    document_id: str
    source_file: str
    file_type: str
    pdf_kind: str | None = None
    document_type: str
    language: str
    n_pages: int
    n_chunks: int
    succeeded: bool
    chunks: list[DocumentChunk]

    engine_log: list[dict[str, Any]] = Field(
        default_factory=list,
        description="which extractor/OCR engine handled each page, and why",
    )
    rtl_flags: list[dict[str, Any]] = Field(
        default_factory=list,
        description="reading-order ambiguities surfaced for manual review; "
                    "these are NOT auto-corrected",
    )
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    timings_ms: dict[str, float] = Field(default_factory=dict)


class ClauseItem(BaseModel):
    """One clause in the M5 view."""

    chunk_id: str
    clause_id: str | None = None
    article: str | None = None
    clause: str | None = None
    section: str | None = None
    heading_path: list[str] = Field(default_factory=list)
    page: int | None = None
    language: str
    is_table: bool = False
    text: str


class ClauseResponse(BaseModel):
    """``POST /clauses`` response. **The M1 -> M5 contract.**"""

    document_id: str
    source_file: str
    document_type: str
    language: str
    n_clauses: int
    n_chunks_total: int = Field(
        description="total chunks in the document; n_clauses is the subset with "
                    "clause identity. A large gap means structure detection "
                    "found little -- worth checking that document."
    )
    clauses: list[ClauseItem]
    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

_BASE_CONFIG = PipelineConfig()


def get_config() -> PipelineConfig:
    """Process-wide pipeline config. Override in tests via
    ``app.dependency_overrides[get_config]``."""
    return _BASE_CONFIG


def _save_upload(upload: UploadFile) -> Path:
    """Persist an upload to a temp file. Caller must delete the parent dir.

    Written to disk rather than held in memory because PyMuPDF, Docling and
    PaddleOCR all want a path, and a 200 MB scanned bundle should not be
    buffered twice.
    """
    name = Path(upload.filename or "upload").name
    suffix = Path(name).suffix.lower()
    if suffix and suffix not in _ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=415,
            detail=f"unsupported file extension '{suffix}'. "
                   f"Accepted: {sorted(_ALLOWED_SUFFIXES)}",
        )

    tmpdir = Path(tempfile.mkdtemp(prefix="m1_ingest_"))
    dest = tmpdir / (name or "upload")
    size = 0
    try:
        with dest.open("wb") as fh:
            while chunk := upload.file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"file exceeds {MAX_UPLOAD_BYTES // (1024*1024)} MB limit",
                    )
                fh.write(chunk)
    except HTTPException:
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise
    except Exception as exc:  # noqa: BLE001
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=f"could not read upload: {exc}") from exc

    if size == 0:
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise HTTPException(status_code=400, detail="uploaded file is empty")
    return dest


def _run(path: Path, cfg: PipelineConfig, document_id: str | None) -> DocumentIngestResult:
    result = process_document(path, cfg, document_id=document_id)
    if not result.succeeded and not result.chunks:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "document could not be processed",
                "document_id": result.document_id,
                "errors": result.errors[:2],
                "warnings": result.warnings,
            },
        )
    return result


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.post("/ingest", response_model=IngestResponse, tags=["M1 -> M2/M3"])
async def ingest_endpoint(
    file: UploadFile = File(..., description="PDF, DOCX, TXT, or image"),
    document_id: str | None = Query(
        default=None,
        description="override the generated document_id (e.g. the firm DMS id)",
    ),
    target_chunk_chars: int | None = Query(default=None, ge=100, le=20000),
    max_chunk_chars: int | None = Query(default=None, ge=200, le=40000),
    overlap_chars: int | None = Query(default=None, ge=0, le=2000),
    respect_structure: bool | None = Query(
        default=None, description="False = baseline paragraph chunking, for A/B tests"
    ),
    keep_raw_text: bool | None = Query(default=None),
    emit_display_form: bool | None = Query(default=None),
    base: PipelineConfig = Depends(get_config),
) -> IngestResponse:
    """**M1 -> M2/M3.** Process one document and return all its chunks.

    Upload a file; get back a list of ``DocumentChunk`` JSON objects, each with
    ``document_id``, ``chunk_id``, ``text``, ``page``, ``section``,
    ``language``, ``document_type`` and an extensible ``metadata`` dict
    (bounding boxes, clause identifiers, OCR confidence, jurisdiction).

    Handles all four input shapes:

    - **text-based PDF** -- PyMuPDF (text + geometry) + Docling (layout + tables)
    - **scanned PDF** -- PaddleOCR (Arabic + English), Tesseract fallback
    - **hybrid PDF** -- per page, whichever of the two applies
    - **DOCX / TXT / image** -- DOCX via Docling, TXT direct, images to OCR

    Response fields beyond ``chunks`` are diagnostics, not payload:

    ``engine_log``
        Which engine handled each page and why. Includes both engines' results
        when an OCR fallback was attempted.
    ``rtl_flags``
        Mixed Arabic/English reading-order ambiguities. **Surfaced, not fixed.**
        Non-empty here means those pages want a human eye before the chunks are
        trusted.
    ``warnings``
        Degradations that did not stop processing (Docling unavailable, DOCX
        pagination synthesized, low-confidence OCR pages kept).

    Errors
    ------
    ``413`` file too large  ``415`` unsupported extension
    ``422`` document could not be processed (see ``detail.errors``)

    Example
    -------
    ``curl -F "file=@contract.pdf" http://127.0.0.1:8000/ingest``
    """
    opts = IngestOptions(
        target_chunk_chars=target_chunk_chars,
        max_chunk_chars=max_chunk_chars,
        overlap_chars=overlap_chars,
        respect_structure=respect_structure,
        keep_raw_text=keep_raw_text,
        emit_display_form=emit_display_form,
    )
    path = _save_upload(file)
    try:
        result = _run(path, opts.apply(base), document_id)
        return IngestResponse(
            document_id=result.document_id,
            source_file=Path(result.source_file).name,
            file_type=result.file_type,
            pdf_kind=result.pdf_kind,
            document_type=str(result.document_type),
            language=str(result.language),
            n_pages=result.n_pages,
            n_chunks=len(result.chunks),
            succeeded=result.succeeded,
            chunks=result.chunks,
            engine_log=result.engine_log,
            rtl_flags=[f.model_dump() for f in result.rtl_flags],
            warnings=result.warnings,
            errors=result.errors[:2],
            timings_ms=result.timings_ms,
        )
    finally:
        shutil.rmtree(path.parent, ignore_errors=True)


@app.post("/clauses", response_model=ClauseResponse, tags=["M1 -> M5"])
async def clauses_endpoint(
    file: UploadFile = File(..., description="PDF, DOCX, TXT, or image"),
    document_id: str | None = Query(default=None),
    include_tables: bool = Query(
        default=True,
        description="keep table chunks that sit inside a clause (payment "
                    "schedules, deliverables)",
    ),
    contracts_only: bool = Query(
        default=False,
        description="restrict to documents classified as contracts",
    ),
    base: PipelineConfig = Depends(get_config),
) -> ClauseResponse:
    """**M1 -> M5.** Clause-level view of a document, for contract intelligence.

    Same pipeline as ``/ingest``, then filtered to chunks that carry a clause
    identity -- those the structural chunker produced by cutting on an article
    or clause boundary the document itself declares. Paragraph-chunked material
    (documents where no structure was detectable) is excluded, because it has
    no clause identity to report.

    Each clause carries:

    ``clause_id``     stable id, e.g. ``art_12.cl_3``
    ``article`` / ``clause``  the labels as they appear (Arabic or English)
    ``heading_path``  full ancestry, outermost heading first
    ``page``          page the clause starts on
    ``is_table``      whether the clause body is a table
    ``text``          normalized clause text

    ``n_clauses`` versus ``n_chunks_total`` is the health signal: a document
    with 200 chunks and 3 clauses did not have its structure detected, and
    should be checked before M5 relies on it.

    Example
    -------
    ``curl -F "file=@contract.pdf" "http://127.0.0.1:8000/clauses?contracts_only=true"``
    """
    path = _save_upload(file)
    try:
        result = _run(path, base, document_id)
        view = clause_view(
            result,
            include_tables=include_tables,
            document_types=["contract"] if contracts_only else None,
        )
        return ClauseResponse(
            document_id=view["document_id"],
            source_file=Path(result.source_file).name,
            document_type=str(view["document_type"]),
            language=str(view["language"]),
            n_clauses=view["n_clauses"],
            n_chunks_total=len(result.chunks),
            clauses=[ClauseItem(**c) for c in view["clauses"]],
            warnings=result.warnings,
        )
    finally:
        shutil.rmtree(path.parent, ignore_errors=True)


@app.get("/health", tags=["ops"])
async def health() -> dict:
    """Liveness plus which optional engines are actually usable in this install.

    Worth checking after deployment: the pipeline degrades quietly when Docling
    or an OCR engine is missing, and this is where that shows up.
    """
    from .extract_pymupdf_docling import docling_available
    from .normalize import pyarabic_available
    from .ocr_pipeline import paddle_available, tesseract_available

    engines = {
        "pymupdf": _importable("fitz"),
        "docling": docling_available(),
        "paddleocr": paddle_available(),
        "tesseract": tesseract_available(),
        "pyarabic": pyarabic_available(),
        "arabic_reshaper": _importable("arabic_reshaper"),
        "python_bidi": _importable("bidi"),
    }
    required = ("pymupdf", "docling", "paddleocr", "tesseract")
    missing = [k for k in required if not engines[k]]
    return {
        "status": "ok" if not missing else "degraded",
        "version": app.version,
        "engines": engines,
        "missing_required": missing,
        "note": "degraded means the pipeline still runs but falls back; see README",
    }


@app.get("/config", tags=["ops"])
async def current_config(base: PipelineConfig = Depends(get_config)) -> dict:
    """The active pipeline configuration.

    Useful for M2/M3 and M5 to record which normalization and chunking settings
    a given batch of chunks was produced under -- results are not comparable
    across different settings.
    """
    return base.model_dump()


def _importable(mod: str) -> bool:
    import importlib.util

    try:
        return importlib.util.find_spec(mod) is not None
    except Exception:  # noqa: BLE001
        return False
