"""Pipeline orchestrator -- the exact flow from the team spec.

    Legal Document
       -> Detect type (scanned vs text-based; DOCX/TXT/image too)
       -> PyMuPDF / Docling            (text-based path)
       -> OCR if required              (Tesseract primary, PaddleOCR fallback)
       -> Text extraction
       -> RTL fix + Arabic normalization      [inserted here, both paths]
       -> Page / section / clause preservation
       -> Legal chunking
       -> Metadata extraction
       -> DocumentChunk

RTL repair and normalization sit between extraction and chunking because both
extraction paths can produce reading-order and orthography damage, and because
chunking's marker detection has to run against normalized text -- an article
header written "الـمـادة ١٢" only matches after tatweel is stripped and digits
are folded.

Structure annotation runs *after* normalization for the same reason, and
*before* chunking so the chunker has clause ids to group on.

This module is the programmatic entry point for M2/M3 and M5. See
:mod:`src.api` for the HTTP surface over the same functions.
"""

from __future__ import annotations

import logging
import time
import traceback
from pathlib import Path

from .chunking import chunk_document
from .config import PipelineConfig
from .document_chunk_schema import (
    DocumentChunk,
    DocumentIngestResult,
    DocumentType,
    Language,
    make_document_id,
)
from .extract_pymupdf_docling import extract_docx, extract_plaintext, extract_text_pdf
from .normalize import apply_normalization
from .ocr_pipeline import ocr_image_file, ocr_pdf_pages
from .rtl_fix import apply_rtl_fix, collect_flags
from .structure_preservation import (
    ExtractedDocument,
    annotate_structure,
    detect_language,
    infer_document_type,
    infer_jurisdiction,
)
from .type_detection import DetectionResult, ExtractionRoute, FileType, detect

logger = logging.getLogger(__name__)


def process_document(
    path: str | Path,
    config: PipelineConfig | None = None,
    document_id: str | None = None,
) -> DocumentIngestResult:
    """Run one document through the full pipeline.

    This is **the M1 -> M2/M3 handoff function**. Everything the rest of the
    AI Core needs is in the returned object; ``result.chunks`` is the payload.

    Parameters
    ----------
    path
        Any supported input: PDF (text-based, scanned, or hybrid), DOCX, TXT,
        or an image file (PNG/JPG/TIFF/BMP -- routed straight to OCR).
    config
        :class:`~src.config.PipelineConfig`. Defaults are the conservative set;
        every stage is individually switchable. See that module.
    document_id
        Override the generated id. Useful when the firm's DMS already has ids
        and chunks must join back to it.

    Returns
    -------
    DocumentIngestResult
        ``.chunks`` -- the ``DocumentChunk`` list
        ``.engine_log`` -- per-page record of which extractor/OCR engine ran
        ``.rtl_flags`` -- reading-order ambiguities flagged for manual review
        ``.warnings`` / ``.errors`` -- degradations and failures
        ``.succeeded`` -- False when the document produced no chunks or errored

    A failing document does **not** raise unless ``config.fail_fast`` is set;
    it returns with ``succeeded=False`` and the traceback in ``.errors``, so a
    batch run is not taken down by one corrupt file.

    Examples
    --------
    >>> result = process_document("contract.pdf")            # doctest: +SKIP
    >>> [c.model_dump() for c in result.chunks][:1]          # doctest: +SKIP
    """
    cfg = config or PipelineConfig()
    src = Path(path)
    t_start = time.perf_counter()

    doc_id = document_id or make_document_id(str(src.resolve()))
    doc = ExtractedDocument(
        document_id=doc_id, source_path=str(src), file_type="unknown"
    )

    try:
        # --- 1. detect ------------------------------------------------------
        t0 = time.perf_counter()
        det = detect(src, cfg.extraction)
        doc.file_type = det.file_type.value
        doc.pdf_kind = det.pdf_kind
        doc.warnings.extend(det.notes)
        doc.timings_ms["detect"] = (time.perf_counter() - t0) * 1000
        doc.log_engine(None, "type_detection", file_type=det.file_type.value,
                       route=det.route.value, detected_by=det.detected_by,
                       pdf_kind=det.pdf_kind)

        if det.route is ExtractionRoute.UNSUPPORTED:
            raise ValueError(
                f"unsupported input ({det.file_type.value}): "
                + ("; ".join(det.notes) or "no handler for this file type")
            )

        # --- 2/3. extract (text layer and/or OCR) ---------------------------
        # Timed as a whole, not only in its parts. The individual extractors
        # record their own stages (``pymupdf``, ``docling``, ``docx``) but the
        # OCR path recorded nothing at all, so a scanned document's report line
        # read "total 531 s, slowest stage detect (147 ms)" -- an unexplained
        # 99.97% of the runtime. ``extract`` is the honest denominator; the
        # per-engine keys below it are the breakdown where one exists.
        t0 = time.perf_counter()
        _extract(src, doc, det, cfg)
        doc.timings_ms["extract"] = (time.perf_counter() - t0) * 1000

        if not doc.pages:
            if det.pdf_report and det.pdf_report.scanned_pages and not cfg.ocr.enabled:
                raise ValueError(
                    f"every page of this document requires OCR "
                    f"({len(det.pdf_report.scanned_pages)} pages: no usable text "
                    f"layer), but OCR is disabled in the config. Enable "
                    f"`ocr.enabled` to process it."
                )
            raise ValueError("extraction produced no pages")

        # --- 4. RTL repair (both paths) -------------------------------------
        t0 = time.perf_counter()
        apply_rtl_fix(doc, cfg.rtl)
        doc.timings_ms["rtl_fix"] = (time.perf_counter() - t0) * 1000

        # --- 5. Arabic normalization ----------------------------------------
        t0 = time.perf_counter()
        apply_normalization(doc, cfg.normalization)
        doc.timings_ms["normalize"] = (time.perf_counter() - t0) * 1000

        # --- 6. structure annotation ----------------------------------------
        t0 = time.perf_counter()
        annotate_structure(doc)
        doc.timings_ms["structure"] = (time.perf_counter() - t0) * 1000

        # --- 7. document-level metadata -------------------------------------
        full = doc.full_text
        doc.language = detect_language(full)
        doc.document_type, doc.doc_type_confidence = infer_document_type(full)
        doc.jurisdiction = infer_jurisdiction(full, cfg.default_jurisdiction)
        doc.log_engine(None, "metadata", document_type=doc.document_type.value,
                       confidence=doc.doc_type_confidence, language=doc.language.value,
                       jurisdiction=doc.jurisdiction)

        # --- 8. chunking ----------------------------------------------------
        t0 = time.perf_counter()
        chunks = chunk_document(doc, cfg)
        doc.timings_ms["chunking"] = (time.perf_counter() - t0) * 1000

        if not chunks:
            doc.warnings.append("document produced zero chunks (no extractable text)")

        doc.timings_ms["total"] = (time.perf_counter() - t_start) * 1000
        return _to_result(doc, chunks, succeeded=bool(chunks))

    except Exception as exc:  # noqa: BLE001
        if cfg.fail_fast:
            raise
        doc.errors.append(f"{type(exc).__name__}: {exc}")
        doc.errors.append(traceback.format_exc(limit=6))
        doc.timings_ms["total"] = (time.perf_counter() - t_start) * 1000
        logger.error("failed to process %s: %s", src, exc)
        return _to_result(doc, [], succeeded=False)


def _extract(src: Path, doc: ExtractedDocument, det: DetectionResult, cfg: PipelineConfig) -> None:
    """Route to the right extractor(s), including the per-page hybrid split."""
    route = det.route

    if det.file_type is FileType.PDF:
        report = det.pdf_report
        text_pages = report.text_pages if report else []
        scan_pages = report.scanned_pages if report else []

        if text_pages:
            extract_text_pdf(src, doc, cfg.extraction, only_pages=text_pages)
        if scan_pages:
            if not cfg.ocr.enabled:
                doc.warnings.append(
                    f"{len(scan_pages)} page(s) need OCR but OCR is disabled; "
                    f"pages {scan_pages} were skipped"
                )
            else:
                from .extract_pymupdf_docling import _merge_pages

                pages = ocr_pdf_pages(src, doc, cfg.ocr, pages=scan_pages)
                _merge_pages(doc, pages)

        if report and route is ExtractionRoute.HYBRID:
            doc.warnings.append(
                f"hybrid PDF: pages {text_pages} used the text layer, "
                f"pages {scan_pages} were OCR'd"
            )

    elif det.file_type is FileType.DOCX:
        extract_docx(src, doc, cfg.extraction)

    elif det.file_type is FileType.TXT:
        extract_plaintext(src, doc)

    elif det.file_type is FileType.IMAGE:
        if not cfg.ocr.enabled:
            raise ValueError("image input requires OCR, but OCR is disabled in config")
        from .extract_pymupdf_docling import _merge_pages

        _merge_pages(doc, ocr_image_file(src, doc, cfg.ocr))

    else:
        raise ValueError(f"no extractor for file type {det.file_type.value}")


def _to_result(doc: ExtractedDocument, chunks: list[DocumentChunk], succeeded: bool) -> DocumentIngestResult:
    return DocumentIngestResult(
        document_id=doc.document_id,
        source_file=doc.source_path,
        file_type=doc.file_type,
        pdf_kind=doc.pdf_kind,  # type: ignore[arg-type]
        document_type=doc.document_type,
        language=doc.language,
        n_pages=doc.n_pages,
        chunks=chunks,
        engine_log=doc.engine_log,
        rtl_flags=collect_flags(doc),
        warnings=doc.warnings,
        errors=doc.errors,
        timings_ms={k: round(v, 1) for k, v in doc.timings_ms.items()},
        succeeded=succeeded,
    )


# ---------------------------------------------------------------------------
# Convenience wrappers
# ---------------------------------------------------------------------------


def ingest(path: str | Path, config: PipelineConfig | None = None) -> list[DocumentChunk]:
    """**M1 -> M2/M3 handoff.** Chunks for one document, nothing else.

    The thinnest possible interface: give it a path, get the list of
    ``DocumentChunk``. Raises nothing -- a failed document returns ``[]`` and
    the reason is in :func:`process_document`'s result, so use that when you
    need diagnostics.

    >>> chunks = ingest("contract.pdf")                       # doctest: +SKIP
    >>> chunks[0].text                                        # doctest: +SKIP
    """
    return process_document(path, config).chunks


def ingest_batch(
    paths: list[str | Path], config: PipelineConfig | None = None
) -> list[DocumentIngestResult]:
    """Process many documents. One failure does not stop the batch.

    Documents are numbered ``doc_001``, ``doc_002``, ... in the order given, so
    a batch reproduces the spec's literal id format.
    """
    from .document_chunk_schema import make_document_id

    out: list[DocumentIngestResult] = []
    for i, p in enumerate(paths, start=1):
        out.append(process_document(p, config, document_id=make_document_id("", seq=i)))
    return out


def get_clause_chunks(
    chunks: list[DocumentChunk],
    *,
    include_tables: bool = True,
    document_types: list[str] | None = None,
) -> list[DocumentChunk]:
    """**M1 -> M5 handoff.** Filter down to clause-level chunks.

    M5 works on contract intelligence and needs clause-granular data, not every
    paragraph of every document. This returns only chunks anchored to an
    identifiable article or clause -- i.e. those the structural chunker (Tier 1)
    produced, where the boundary is one the document itself declares.

    Parameters
    ----------
    include_tables
        Keep table chunks that sit inside a clause (payment schedules,
        deliverable tables). On by default: they are usually the clause's
        operative content.
    document_types
        Restrict to these ``document_type`` values. Pass ``["contract"]`` for
        contracts only; ``None`` (default) keeps every type, since Egyptian
        practice often needs the statute article a clause references.

    Notes
    -----
    Chunks that fell to paragraph chunking (no detectable structure) are
    **excluded** -- they have no clause identity to offer. If this returns far
    fewer chunks than expected for a document, that document's markers were not
    detected, and it will show up in the evaluation report's chunking tier mix.
    """
    out: list[DocumentChunk] = []
    for c in chunks:
        if document_types and c.document_type not in document_types:
            continue
        if not c.is_clause:
            continue
        if not include_tables and c.metadata.get("is_table"):
            continue
        out.append(c)
    return out


def clause_view(result: DocumentIngestResult, **kwargs) -> dict:
    """M5-shaped view of one ingest result: clauses plus their identity.

    Returns a dict with ``document_id``, ``document_type``, and ``clauses`` --
    each clause carrying its id, label, page, text and table flag. This is the
    shape :func:`src.api.get_clauses` serves over HTTP.
    """
    clauses = get_clause_chunks(result.chunks, **kwargs)
    return {
        "document_id": result.document_id,
        "source_file": result.source_file,
        "document_type": result.document_type,
        "language": result.language,
        "n_clauses": len(clauses),
        "clauses": [
            {
                "chunk_id": c.chunk_id,
                "clause_id": (c.metadata.get("structure") or {}).get("clause_id"),
                "article": (c.metadata.get("structure") or {}).get("article"),
                "clause": (c.metadata.get("structure") or {}).get("clause"),
                "section": c.section,
                "heading_path": (c.metadata.get("structure") or {}).get("heading_path", []),
                "page": c.page,
                "language": c.language,
                "is_table": bool(c.metadata.get("is_table")),
                "text": c.text,
            }
            for c in clauses
        ],
    }
