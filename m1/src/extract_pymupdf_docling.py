"""Text-layer extraction: PyMuPDF + Docling, and DOCX / TXT.

HOW THE TWO LIBRARIES ARE SPLIT
===============================

They are not redundant and neither is a fallback for the other in the normal
path. Each owns what it is actually good at:

**PyMuPDF owns geometry and text.** It is the source of truth for:
  - page count, page width/height
  - the text itself, span by span
  - exact bounding boxes in PDF points
  - font size and weight (used for typographic heading detection)
  - reading order within a page

  PyMuPDF is fast, deterministic, has no model weights, and gives coordinates
  in a stable API. Everything the spec calls "preserve bounding boxes" comes
  from here.

**Docling owns semantics and tables.** It is the source of truth for:
  - what each block *is* (title / section-header / list-item / caption /
    page-header / page-footer / table / formula)
  - heading level and document hierarchy
  - table structure (TableFormer produces real row/column grids, which
    PyMuPDF's ruling-line heuristic cannot match on borderless tables --
    and borderless tables are the norm in Arabic contract payment schedules)

**The merge** (:func:`_merge_docling_labels`): PyMuPDF's block list is the
spine. Docling's items are matched onto it spatially, by intersection-over-
union of bounding boxes on the same page, and only the *label* and *heading
level* are copied across. Text always stays PyMuPDF's. This matters because
Docling normalizes and re-flows text in ways that can disturb Arabic, whereas
PyMuPDF returns exactly what is in the content stream.

  Why IoU rather than trusting Docling's own text: Docling's coordinate origin,
  scaling and text normalization all vary between versions. Matching on
  geometry and taking only the label is the narrowest possible dependency on
  Docling's internals, so a Docling upgrade cannot silently corrupt our text.

**Degradation.** Docling is optional at runtime. If it is not installed, errors,
or exceeds ``ExtractionConfig.docling_timeout_s``, extraction continues with
PyMuPDF alone, tables fall back to ``page.find_tables()``, and the degradation
is written to ``doc.engine_log`` -- never swallowed. A page's
``source_engine`` then reads ``pymupdf`` instead of ``pymupdf+docling``, so the
evaluation report can separate the two.

For DOCX the split inverts: Docling is primary (it understands the OOXML
outline and tables), python-docx is the fallback. PyMuPDF cannot read DOCX.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from .config import ExtractionConfig
from .document_chunk_schema import BlockType, BoundingBox, SourceEngine
from .structure_preservation import (
    ExtractedDocument,
    ExtractedPage,
    ExtractedTable,
    TextBlock,
    clean_control_chars,
)

logger = logging.getLogger(__name__)

# Docling label -> our BlockType. Unmapped labels stay PARAGRAPH.
_DOCLING_LABEL_MAP = {
    "title": BlockType.HEADING,
    "section_header": BlockType.HEADING,
    "page_header": BlockType.HEADER_FOOTER,
    "page_footer": BlockType.HEADER_FOOTER,
    "list_item": BlockType.LIST,
    "table": BlockType.TABLE,
    "caption": BlockType.PARAGRAPH,
    "text": BlockType.PARAGRAPH,
    "paragraph": BlockType.PARAGRAPH,
    "code": BlockType.PARAGRAPH,
    "formula": BlockType.PARAGRAPH,
    "footnote": BlockType.PARAGRAPH,
}


def docling_available() -> bool:
    try:
        import docling  # noqa: F401

        return True
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# PDF: PyMuPDF spine
# ---------------------------------------------------------------------------


def extract_pdf_pymupdf(
    path: str | Path,
    config: ExtractionConfig,
    only_pages: list[int] | None = None,
) -> tuple[list[ExtractedPage], list[str]]:
    """Extract text blocks with bounding boxes and font info via PyMuPDF.

    ``only_pages`` (1-based) limits extraction to the pages type detection
    routed to the text layer, so a hybrid document's scanned pages are left for
    the OCR path.

    Reading order: PyMuPDF's ``sort=True`` gives top-to-bottom, left-to-right.
    For RTL pages that is the wrong horizontal order, so blocks are re-sorted
    right-to-left when the page is predominantly Arabic **and** the page has
    more than one column-ish x-cluster. Single-column Arabic pages are
    unaffected, since block order there is purely vertical.
    """
    import fitz

    from .structure_preservation import detect_language
    from .document_chunk_schema import Language

    warnings: list[str] = []
    pages: list[ExtractedPage] = []
    doc = fitz.open(str(path))
    try:
        if doc.is_encrypted and not doc.authenticate(""):
            raise ValueError("PDF is password-protected")

        wanted = set(only_pages) if only_pages else None
        for pno, page in enumerate(doc, start=1):
            if wanted is not None and pno not in wanted:
                continue

            epage = ExtractedPage(
                page_number=pno,
                width=float(page.rect.width),
                height=float(page.rect.height),
                source_engine=SourceEngine.PYMUPDF,
            )

            try:
                # ``rawdict``, not ``dict``: it carries per-glyph bounding
                # boxes, and those are the only place the *painted* order of an
                # Arabic line survives. MuPDF applies a bidi pass of its own to
                # the text it hands back, which on a pre-shaped Arabic PDF
                # leaves a reading that cannot be repaired from the string. See
                # :func:`_block_readings` and :mod:`src.visual_order`.
                data = page.get_text("rawdict", sort=True)
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"page {pno}: PyMuPDF get_text failed: {exc}")
                pages.append(epage)
                continue

            raw_blocks = []
            for blk in data.get("blocks", []):
                if blk.get("type") != 0:      # 0 = text, 1 = image
                    continue
                sizes: list[float] = []
                bold = False
                for line in blk.get("lines", []):
                    for s in line.get("spans", []):
                        if s.get("size"):
                            sizes.append(float(s["size"]))
                        flags = int(s.get("flags", 0))
                        # bit 4 (16) = bold in PyMuPDF's span flags
                        if flags & 16:
                            bold = True
                stream_text, geometric_text = _block_readings(blk)
                text = clean_control_chars(stream_text).strip()
                if not text:
                    continue
                x0, y0, x1, y1 = blk.get("bbox", (0, 0, 0, 0))
                raw_blocks.append(
                    {
                        "text": text,
                        "geometric_text": clean_control_chars(geometric_text).strip(),
                        "bbox": BoundingBox(x0=x0, y0=y0, x1=x1, y1=y1, page=pno),
                        "font_size": (sum(sizes) / len(sizes)) if sizes else None,
                        "bold": bold,
                    }
                )

            ordered = _order_blocks(raw_blocks, page_width=float(page.rect.width))
            for idx, rb in enumerate(ordered):
                epage.blocks.append(
                    TextBlock(
                        text=rb["text"],
                        page=pno,
                        bbox=rb["bbox"],
                        block_type=BlockType.PARAGRAPH,
                        source_engine=SourceEngine.PYMUPDF,
                        font_size=rb["font_size"],
                        is_bold=rb["bold"],
                        order=idx,
                        geometric_text=rb["geometric_text"] or None,
                    )
                )

            if config.extract_tables and config.table_mode in ("pymupdf", "both"):
                epage.tables.extend(_pymupdf_tables(page, pno, warnings))

            epage.is_blank = epage.char_count == 0
            pages.append(epage)
    finally:
        doc.close()

    return pages, warnings


def _block_readings(blk: dict) -> tuple[str, str]:
    """Two readings of one ``rawdict`` block: MuPDF's, and the painted order's.

    Returns ``(stream_text, geometric_text)``.

    ``stream_text`` is what PyMuPDF would have produced from ``get_text("dict")``
    -- the content stream after MuPDF's own bidi pass. It is the default and
    nothing downstream changes unless the reversal test in
    :mod:`src.visual_order` positively prefers the alternative.

    ``geometric_text`` is each line's glyphs sorted by x and then put through the
    inverse bidi transform. On a PDF whose producer shaped the Arabic before
    writing it -- Arabic DTP output, and every fixture this repo renders with
    ReportLab -- that recovers the original logical text exactly, because the
    glyph positions never lied even though the content stream did.

    **Lines with no Arabic keep the stream reading verbatim.** Forcing an RTL
    paragraph direction onto a pure-English line moves its clause number to the
    far end ("5.1 The scope includes..." -> ".The scope includes... 5.1"), which
    would trade one reading-order bug for another in bilingual documents where
    the two languages sit on alternating lines.

    Deciding *between* the two readings is not done here: a single block rarely
    carries enough evidence, and visual layout is a property of the producing
    software, so the verdict is taken once per document in
    :func:`_resolve_reading_order`.
    """
    from .structure_preservation import is_arabic_char
    from .visual_order import visual_line_from_chars, visual_to_logical

    stream_lines: list[str] = []
    geometric_lines: list[str] = []
    for line in blk.get("lines", []):
        chars = [c for s in line.get("spans", []) for c in s.get("chars", [])]
        if not chars:
            continue
        stream = "".join(c.get("c", "") for c in chars)
        if not stream.strip():
            continue
        stream_lines.append(stream)
        if any(is_arabic_char(c) for c in stream):
            geometric_lines.append(visual_to_logical(visual_line_from_chars(chars)))
        else:
            geometric_lines.append(stream)
    return "\n".join(stream_lines), "\n".join(geometric_lines)


def _resolve_reading_order(doc: ExtractedDocument, cfg) -> None:
    """Decide, once for the whole document, which reading of its text to keep.

    Visual layout comes from the software that produced the file -- Arabic DTP
    that shapes before writing, or a converter that emitted screen order -- so
    it is all-or-nothing per document, not per paragraph. Deciding per block
    would be both weaker (a two-line heading carries almost no evidence) and
    incoherent (half a document reversed and half not is worse than either).

    The verdict, accepted or rejected, is written to ``doc.engine_log`` with its
    numbers, and an accepted repair also raises a document warning and a
    ``visual_order_repaired`` flag on every block it changed. The repair is
    therefore auditable: nothing is silently rewritten, which is the property
    the pipeline had before this was fixable and should not lose by fixing it.
    """
    from .document_chunk_schema import RTLFlag
    from .visual_order import choose_reading

    if not getattr(cfg, "repair_visual_order", True):
        return

    blocks = [b for b in doc.all_blocks() if b.geometric_text and not b.is_empty()]
    if not blocks:
        return

    stream = "\n".join(b.text for b in blocks)
    candidate = "\n".join(b.geometric_text or b.text for b in blocks)
    verdict = choose_reading(stream, candidate)

    doc.log_engine(None, "reading_order", **verdict.as_dict())
    if not verdict.repaired:
        return

    changed = 0
    for b in blocks:
        if b.geometric_text and b.geometric_text != b.text:
            if b.raw_text is None:
                b.raw_text = b.text
            b.text = b.geometric_text
            b.reading_order_repaired = True
            b.rtl_flags.append(
                RTLFlag(
                    kind="visual_order_repaired",
                    page=b.page,
                    severity="warn",
                    detail=(
                        "this block's text layer was stored in VISUAL order and "
                        "was reordered to logical order from glyph geometry. "
                        + verdict.reason
                        + " Digit *order* was not touched -- see digit_order_suspect."
                    ),
                    sample=" ".join(b.text.split())[:120],
                )
            )
            changed += 1

    doc.warnings.append(
        f"document's text layer was stored in VISUAL reading order; {changed} "
        f"block(s) were reordered to logical order from glyph geometry "
        f"(structural markers {verdict.markers_before} -> {verdict.markers_after}, "
        f"order score {verdict.score_before:+.3f} -> {verdict.score_after:+.3f}). "
        f"Reordered blocks carry a visual_order_repaired flag."
    )


def _order_blocks(blocks: list[dict], page_width: float) -> list[dict]:
    """Put blocks into reading order, handling RTL multi-column pages.

    PyMuPDF sorts left-to-right. On a two-column Arabic page the right column
    must come first. We only flip when the page is predominantly Arabic *and*
    the blocks genuinely cluster into more than one horizontal band -- flipping
    a single-column page would be a no-op at best and a reordering bug at worst.
    """
    from .structure_preservation import Language, detect_language

    if len(blocks) < 2:
        return blocks

    joined = " ".join(b["text"] for b in blocks[:40])
    if detect_language(joined) not in (Language.AR, Language.AR_EN):
        return blocks

    mid = page_width / 2
    left = [b for b in blocks if b["bbox"].x1 <= mid * 1.05]
    right = [b for b in blocks if b["bbox"].x0 >= mid * 0.95]
    # Two real columns only if both sides hold a meaningful share of the blocks.
    if len(left) < 2 or len(right) < 2 or (len(left) + len(right)) < 0.8 * len(blocks):
        return blocks

    spanning = [b for b in blocks if b not in left and b not in right]
    key = lambda b: (round(b["bbox"].y0, 1), -b["bbox"].x0)  # noqa: E731
    return sorted(spanning, key=key) + sorted(right, key=key) + sorted(left, key=key)


def _pymupdf_tables(page, pno: int, warnings: list[str]) -> list[ExtractedTable]:
    """PyMuPDF ``find_tables`` -- reliable on ruled tables, weak on borderless."""
    out: list[ExtractedTable] = []
    try:
        finder = page.find_tables()
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"page {pno}: PyMuPDF find_tables failed: {exc}")
        return out
    for order, tbl in enumerate(getattr(finder, "tables", []) or []):
        try:
            rows = [[(c or "").strip() for c in row] for row in tbl.extract()]
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"page {pno}: table extract failed: {exc}")
            continue
        if not rows or all(not any(c for c in r) for r in rows):
            continue
        bx = getattr(tbl, "bbox", None)
        out.append(
            ExtractedTable(
                rows=rows,
                page=pno,
                bbox=BoundingBox(x0=bx[0], y0=bx[1], x1=bx[2], y1=bx[3], page=pno) if bx else None,
                source_engine=SourceEngine.PYMUPDF,
                order=order,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Docling layer
# ---------------------------------------------------------------------------


# One converter, built lazily and reused: constructing it loads the layout and
# TableFormer weights and costs tens of seconds.
_DOCLING_CONVERTER = None


def _get_converter():
    global _DOCLING_CONVERTER
    if _DOCLING_CONVERTER is None:
        from docling.document_converter import DocumentConverter

        try:
            import torch._dynamo

            # Belt and braces alongside TORCHDYNAMO_DISABLE in src/__init__:
            # if Dynamo is somehow active, make its failures non-fatal.
            torch._dynamo.config.suppress_errors = True
        except Exception:  # noqa: BLE001
            pass
        _DOCLING_CONVERTER = DocumentConverter()
    return _DOCLING_CONVERTER


def _docling_convert(path: str | Path, timeout_s: int):
    """Run Docling under a wall-clock deadline; return its ``DoclingDocument``.

    Docling exposes no cancellation, so the conversion runs on a daemon thread
    and we abandon it when ``timeout_s`` elapses. The thread keeps running to
    completion in the background (we cannot kill it safely mid-inference) but
    the pipeline stops waiting and degrades to PyMuPDF-only.

    A hard deadline matters here: Docling's layout model on CPU costs seconds
    per page, and a 90-page statute would otherwise stall a batch for many
    minutes with no bound.

    Raises ``TimeoutError`` on expiry, or whatever the conversion raised.
    """
    import queue
    import threading

    result_q: queue.Queue = queue.Queue(maxsize=1)

    def _work():
        try:
            result_q.put(("ok", _get_converter().convert(str(path)).document))
        except BaseException as exc:  # noqa: BLE001
            result_q.put(("err", exc))

    thread = threading.Thread(target=_work, daemon=True, name="docling-convert")
    thread.start()
    try:
        status, payload = result_q.get(timeout=timeout_s)
    except queue.Empty:
        raise TimeoutError(
            f"Docling exceeded its {timeout_s}s budget "
            f"(ExtractionConfig.docling_timeout_s) and was abandoned"
        ) from None
    if status == "err":
        raise payload
    return payload


def _docling_items(dl_doc) -> list[dict]:
    """Flatten a DoclingDocument into ``{page, bbox, label, level, text}`` dicts.

    Written defensively against Docling's evolving API: several accessor shapes
    are tried and anything unrecognised is skipped rather than raising.
    """
    items: list[dict] = []
    page_heights: dict[int, float] = {}
    try:
        for pno, pg in (getattr(dl_doc, "pages", {}) or {}).items():
            size = getattr(pg, "size", None)
            if size is not None and getattr(size, "height", None):
                page_heights[int(pno)] = float(size.height)
    except Exception:  # noqa: BLE001
        pass

    try:
        iterator = dl_doc.iterate_items()
    except Exception:  # noqa: BLE001
        return items

    for entry in iterator:
        item = entry[0] if isinstance(entry, tuple) else entry
        label = getattr(item, "label", None)
        label = getattr(label, "value", label)
        if label is None:
            continue
        text = getattr(item, "text", "") or ""
        level = getattr(item, "level", None)

        for prov in (getattr(item, "prov", None) or []):
            pno = _prov_page_no(getattr(prov, "page_no", None))
            bbox = getattr(prov, "bbox", None)
            if pno is None or bbox is None:
                continue
            try:
                ph = page_heights.get(pno)
                origin = getattr(getattr(bbox, "coord_origin", None), "value", None)
                l, t, r, b = float(bbox.l), float(bbox.t), float(bbox.r), float(bbox.b)
                if origin == "BOTTOMLEFT" and ph:
                    # Docling's default origin is bottom-left; PyMuPDF is top-left.
                    t, b = ph - t, ph - b
                y0, y1 = (t, b) if t <= b else (b, t)
                items.append(
                    {
                        "page": pno,
                        "bbox": BoundingBox(x0=min(l, r), y0=y0, x1=max(l, r), y1=y1, page=pno),
                        "label": str(label),
                        "level": level,
                        "text": text,
                    }
                )
            except Exception:  # noqa: BLE001
                continue
    return items


def _iou(a: BoundingBox, b: BoundingBox) -> float:
    ix0, iy0 = max(a.x0, b.x0), max(a.y0, b.y0)
    ix1, iy1 = min(a.x1, b.x1), min(a.y1, b.y1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    inter = (ix1 - ix0) * (iy1 - iy0)
    union = a.width * a.height + b.width * b.height - inter
    return inter / union if union > 0 else 0.0


def _merge_docling_labels(
    pages: list[ExtractedPage], dl_items: list[dict], min_iou: float = 0.30
) -> int:
    """Copy Docling's semantic labels onto PyMuPDF blocks by bbox overlap.

    Only ``block_type`` and heading level are transferred. Text is never taken
    from Docling -- see the module docstring for why.

    Returns the number of blocks that received a label, so callers can log how
    much Docling actually contributed (a near-zero match count is a signal that
    coordinate spaces disagreed and the merge should be distrusted).
    """
    by_page: dict[int, list[dict]] = {}
    for it in dl_items:
        by_page.setdefault(it["page"], []).append(it)

    matched = 0
    for page in pages:
        candidates = by_page.get(page.page_number, [])
        if not candidates:
            continue
        for block in page.blocks:
            if block.bbox is None:
                continue
            best, best_iou = None, 0.0
            for it in candidates:
                score = _iou(block.bbox, it["bbox"])
                if score > best_iou:
                    best, best_iou = it, score
            if best is None or best_iou < min_iou:
                continue
            mapped = _DOCLING_LABEL_MAP.get(best["label"].lower())
            if mapped is not None:
                block.block_type = mapped
            if best.get("level") is not None:
                try:
                    block.struct.heading_level = int(best["level"])
                except (TypeError, ValueError):
                    pass
            block.source_engine = SourceEngine.PYMUPDF_DOCLING
            matched += 1
    return matched


def _prov_page_no(raw) -> int | None:
    """Coerce a Docling ``prov.page_no`` to a valid 1-based page, or ``None``.

    Docling numbers pages from 1, so anything below that is a broken value
    rather than a real page -- and a plain truthiness test would silently
    turn ``0`` into "no page", which downstream cannot tell apart from a
    genuinely page-less source.
    """
    if raw is None:
        return None
    try:
        pno = int(raw)
    except (TypeError, ValueError):
        logger.debug("docling page_no %r is not an int", raw)
        return None
    if pno < 1:
        logger.debug("docling page_no %r is below 1; treating as absent", raw)
        return None
    return pno


def _docling_tables(dl_doc) -> list[ExtractedTable]:
    """Pull structured tables out of a DoclingDocument (TableFormer output)."""
    out: list[ExtractedTable] = []
    for order, tbl in enumerate(getattr(dl_doc, "tables", []) or []):
        rows: list[list[str]] = []
        try:
            grid = getattr(getattr(tbl, "data", None), "grid", None)
            if grid:
                rows = [[(getattr(c, "text", "") or "").strip() for c in row] for row in grid]
            else:
                df = tbl.export_to_dataframe()
                rows = [list(map(str, df.columns))] + df.astype(str).values.tolist()
        except Exception as exc:  # noqa: BLE001
            logger.debug("docling table %d unreadable: %s", order, exc)
            continue
        if not rows or all(not any(c.strip() for c in r) for r in rows):
            continue

        page, bbox = None, None
        for prov in (getattr(tbl, "prov", None) or []):
            page = _prov_page_no(getattr(prov, "page_no", None))
            bb = getattr(prov, "bbox", None)
            if bb is not None:
                try:
                    bbox = BoundingBox(
                        x0=min(float(bb.l), float(bb.r)), y0=min(float(bb.t), float(bb.b)),
                        x1=max(float(bb.l), float(bb.r)), y1=max(float(bb.t), float(bb.b)),
                        page=page,
                    )
                except Exception:  # noqa: BLE001
                    bbox = None
            break

        if page is None:
            # Docling gives tables no ``prov`` for formats it reads without a
            # page model (DOCX is the common one). That is a genuinely
            # page-less source, not a lost number -- such documents are
            # extracted as a single page elsewhere in this module, so match
            # that and report page 1 instead of emitting a page-less table.
            logger.debug("docling table %d has no page provenance; using page 1", order)
            page = 1

        out.append(
            ExtractedTable(
                rows=rows,
                page=page,
                bbox=bbox,
                source_engine=SourceEngine.DOCLING,
                order=order,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def _docling_size_guard(path: str | Path, pages: list[ExtractedPage],
                        config: ExtractionConfig) -> str | None:
    """Return a reason to skip Docling on this document, or ``None`` to proceed.

    Docling's preprocessing allocates per page and can raise ``std::bad_alloc``
    in native code, which **aborts the interpreter** -- the thread-based
    timeout in :func:`_docling_convert` cannot save us from that, because there
    is no process left to time anything out. So oversized documents are
    excluded before Docling is ever entered.

    Both limits are also self-justifying on time: a document that trips either
    one would exceed ``docling_timeout_s`` and have its result discarded anyway.
    """
    n_pages = len(pages)
    if config.docling_max_pages and n_pages > config.docling_max_pages:
        return (
            f"{n_pages} pages exceeds docling_max_pages={config.docling_max_pages}; "
            f"at ~5 s/page this would also exceed the "
            f"{config.docling_timeout_s}s budget. Using PyMuPDF-only extraction."
        )

    if config.docling_max_page_pixels:
        # Docling rasterizes internally at ~144 dpi (scale 2.0).
        scale = 2.0
        biggest = max(
            ((p.width or 0) * scale) * ((p.height or 0) * scale) for p in pages
        ) if pages else 0
        if biggest > config.docling_max_page_pixels:
            return (
                f"largest page rasterizes to ~{biggest / 1e6:.0f} MP, over "
                f"docling_max_page_pixels={config.docling_max_page_pixels / 1e6:.0f} MP. "
                "Oversized pages have caused native out-of-memory aborts. "
                "Using PyMuPDF-only extraction."
            )
    return None


def extract_text_pdf(
    path: str | Path,
    doc: ExtractedDocument,
    config: ExtractionConfig,
    only_pages: list[int] | None = None,
) -> ExtractedDocument:
    """Text-layer PDF extraction. Mutates and returns ``doc``.

    Runs PyMuPDF first (always), then Docling (when enabled and importable) to
    enrich labels and tables.
    """
    t0 = time.perf_counter()
    pages, warns = extract_pdf_pymupdf(path, config, only_pages=only_pages)
    doc.warnings.extend(warns)
    doc.timings_ms["pymupdf"] = (time.perf_counter() - t0) * 1000

    for p in pages:
        doc.log_engine(p.page_number, "pymupdf", chars=p.char_count,
                       blocks=len(p.blocks), tables=len(p.tables))

    use_docling = config.use_docling and docling_available()
    if config.use_docling and not use_docling:
        msg = "Docling not importable; degraded to PyMuPDF-only extraction"
        doc.warnings.append(msg)
        doc.log_engine(None, "docling", status="unavailable", detail=msg)

    if use_docling:
        skip_reason = _docling_size_guard(path, pages, config)
        if skip_reason:
            use_docling = False
            doc.warnings.append(f"Docling skipped: {skip_reason}")
            doc.log_engine(None, "docling", status="skipped", detail=skip_reason)

    if use_docling:
        t1 = time.perf_counter()
        try:
            dl_doc = _docling_convert(path, config.docling_timeout_s)
            elapsed = (time.perf_counter() - t1) * 1000
            doc.timings_ms["docling"] = elapsed

            if elapsed > config.docling_timeout_s * 1000:
                doc.warnings.append(
                    f"Docling took {elapsed/1000:.0f}s, over the "
                    f"{config.docling_timeout_s}s budget; result still used"
                )

            items = _docling_items(dl_doc)
            matched = _merge_docling_labels(pages, items)
            doc.log_engine(None, "docling", status="ok", items=len(items),
                           blocks_labelled=matched, ms=round(elapsed, 1))
            if items and matched == 0:
                doc.warnings.append(
                    f"Docling returned {len(items)} items but none matched a PyMuPDF "
                    "block by bbox; layout labels were not applied (coordinate "
                    "spaces may disagree)"
                )

            if config.extract_tables and config.table_mode in ("docling", "both"):
                dtables = _docling_tables(dl_doc)
                if dtables:
                    # Docling tables supersede PyMuPDF's on pages where it found any.
                    covered = {t.page for t in dtables if t.page}
                    for p in pages:
                        if p.page_number in covered:
                            p.tables = [t for t in dtables if t.page == p.page_number]
                    orphans = [t for t in dtables if not t.page]
                    if orphans and pages:
                        pages[0].tables.extend(orphans)
                    doc.log_engine(None, "docling", status="tables",
                                   n_tables=len(dtables), pages=sorted(covered))
        except Exception as exc:  # noqa: BLE001
            doc.timings_ms["docling"] = (time.perf_counter() - t1) * 1000
            msg = f"Docling failed ({type(exc).__name__}: {exc}); using PyMuPDF-only output"
            doc.warnings.append(msg)
            doc.log_engine(None, "docling", status="failed", detail=str(exc)[:400])
            logger.warning(msg)

    _merge_pages(doc, pages)

    # Last, and over the whole document rather than page by page: whether this
    # file's text layer was stored in visual reading order. Runs here because
    # it needs every page's evidence, and before RTL repair and chunking so
    # everything downstream sees one settled reading.
    _resolve_reading_order(doc, config)
    return doc


def extract_docx(path: str | Path, doc: ExtractedDocument, config: ExtractionConfig) -> ExtractedDocument:
    """DOCX extraction: Docling primary, python-docx fallback.

    DOCX has no intrinsic pagination -- page breaks are computed by the renderer,
    not stored. We therefore assign page numbers by counting *explicit* page
    breaks, and leave ``page`` at 1 when there are none. This is recorded as a
    warning so nobody mistakes DOCX page numbers for PDF page numbers.
    """
    t0 = time.perf_counter()
    used = None

    if config.use_docling and docling_available():
        try:
            dl_doc = _docling_convert(path, config.docling_timeout_s)
            pages = _pages_from_docling_only(dl_doc, config)
            if pages and any(p.char_count for p in pages):
                _merge_pages(doc, pages)
                doc.log_engine(None, "docling", status="ok", format="docx",
                               pages=len(pages))
                used = "docling"
        except Exception as exc:  # noqa: BLE001
            doc.warnings.append(f"Docling DOCX conversion failed ({exc}); using python-docx")
            doc.log_engine(None, "docling", status="failed", format="docx", detail=str(exc)[:300])

    if used is None:
        pages = _extract_docx_python_docx(path, doc)
        _merge_pages(doc, pages)
        doc.log_engine(None, "python-docx", status="ok", pages=len(pages))
        used = "python-docx"

    doc.timings_ms["docx"] = (time.perf_counter() - t0) * 1000
    doc.warnings.append(
        "DOCX has no stored pagination; page numbers are derived from explicit "
        "page breaks and are not comparable to PDF page numbers"
    )
    return doc


def _pages_from_docling_only(dl_doc, config: ExtractionConfig) -> list[ExtractedPage]:
    """Build pages purely from Docling, for formats PyMuPDF cannot read (DOCX)."""
    items = _docling_items(dl_doc)
    by_page: dict[int, ExtractedPage] = {}

    if not items:
        # No provenance (typical for DOCX): fall back to the flat item list.
        page = ExtractedPage(page_number=1, source_engine=SourceEngine.DOCLING)
        order = 0
        try:
            for entry in dl_doc.iterate_items():
                item = entry[0] if isinstance(entry, tuple) else entry
                text = (getattr(item, "text", "") or "").strip()
                if not text:
                    continue
                label = getattr(getattr(item, "label", None), "value", None) or ""
                page.blocks.append(
                    TextBlock(
                        text=clean_control_chars(text), page=1, bbox=None,
                        block_type=_DOCLING_LABEL_MAP.get(str(label).lower(), BlockType.PARAGRAPH),
                        source_engine=SourceEngine.DOCLING, order=order,
                    )
                )
                order += 1
        except Exception:  # noqa: BLE001
            pass
        by_page[1] = page
    else:
        for order, it in enumerate(items):
            text = (it["text"] or "").strip()
            if not text:
                continue
            pno = it["page"]
            page = by_page.setdefault(
                pno, ExtractedPage(page_number=pno, source_engine=SourceEngine.DOCLING)
            )
            page.blocks.append(
                TextBlock(
                    text=clean_control_chars(text), page=pno, bbox=it["bbox"],
                    block_type=_DOCLING_LABEL_MAP.get(it["label"].lower(), BlockType.PARAGRAPH),
                    source_engine=SourceEngine.DOCLING, order=order,
                )
            )

    if config.extract_tables:
        for tbl in _docling_tables(dl_doc):
            target = by_page.get(tbl.page or 1)
            if target is None:
                target = by_page.setdefault(
                    tbl.page or 1,
                    ExtractedPage(page_number=tbl.page or 1, source_engine=SourceEngine.DOCLING),
                )
            target.tables.append(tbl)

    return [by_page[k] for k in sorted(by_page)]


def _extract_docx_python_docx(path: str | Path, doc: ExtractedDocument) -> list[ExtractedPage]:
    """python-docx fallback. Reads paragraphs and tables in document order."""
    from docx import Document as DocxDocument
    from docx.table import Table as DocxTable
    from docx.text.paragraph import Paragraph as DocxParagraph

    d = DocxDocument(str(path))
    pages: list[ExtractedPage] = [ExtractedPage(page_number=1, source_engine=SourceEngine.PYTHON_DOCX)]
    order = 0

    body = d.element.body
    for child in body.iterchildren():
        tag = child.tag.split("}")[-1]
        if tag == "p":
            para = DocxParagraph(child, d)
            text = clean_control_chars(para.text).strip()
            # An explicit page break starts a new ExtractedPage.
            if "w:br" in child.xml and 'type="page"' in child.xml:
                pages.append(
                    ExtractedPage(page_number=len(pages) + 1, source_engine=SourceEngine.PYTHON_DOCX)
                )
                order = 0
            if not text:
                continue
            style = (para.style.name or "").lower() if para.style is not None else ""
            btype = BlockType.HEADING if style.startswith(("heading", "title")) else BlockType.PARAGRAPH
            if style.startswith("list"):
                btype = BlockType.LIST
            level = None
            if btype is BlockType.HEADING:
                digits = "".join(c for c in style if c.isdigit())
                level = int(digits) if digits else 1
            bold = any(r.bold for r in para.runs if r.bold is not None)
            size = next(
                (r.font.size.pt for r in para.runs if r.font is not None and r.font.size), None
            )
            block = TextBlock(
                text=text, page=len(pages), bbox=None, block_type=btype,
                source_engine=SourceEngine.PYTHON_DOCX, order=order,
                is_bold=bool(bold), font_size=size,
            )
            if level:
                block.struct.heading_level = level
            pages[-1].blocks.append(block)
            order += 1
        elif tag == "tbl":
            table = DocxTable(child, d)
            rows = [[clean_control_chars(c.text).strip() for c in row.cells] for row in table.rows]
            if rows and any(any(c for c in r) for r in rows):
                pages[-1].tables.append(
                    ExtractedTable(
                        rows=rows, page=len(pages),
                        source_engine=SourceEngine.PYTHON_DOCX, order=order,
                    )
                )
                order += 1

    return pages


def extract_plaintext(path: str | Path, doc: ExtractedDocument) -> ExtractedDocument:
    """TXT extraction. Tries UTF-8, then UTF-16, then CP1256 (legacy Windows
    Arabic -- still produced by older Egyptian office software).

    Paragraphs are split on blank lines. There is no pagination, so ``page``
    stays 1 for every block and downstream consumers see ``page=1``.
    """
    p = Path(path)
    raw = p.read_bytes()
    text, enc = None, None
    for candidate in ("utf-8-sig", "utf-8", "utf-16", "cp1256", "latin-1"):
        try:
            text = raw.decode(candidate)
            enc = candidate
            break
        except (UnicodeDecodeError, LookupError):
            continue
    if text is None:
        raise ValueError(f"could not decode {p} with any known encoding")
    if enc not in ("utf-8", "utf-8-sig"):
        doc.warnings.append(f"decoded as {enc}, not UTF-8; verify Arabic characters")

    text = clean_control_chars(text)
    page = ExtractedPage(page_number=1, source_engine=SourceEngine.PLAINTEXT)
    order = 0
    for para in text.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        page.blocks.append(
            TextBlock(text=para, page=1, bbox=None, block_type=BlockType.PARAGRAPH,
                      source_engine=SourceEngine.PLAINTEXT, order=order)
        )
        order += 1

    doc.log_engine(1, "plaintext", encoding=enc, blocks=len(page.blocks))
    _merge_pages(doc, [page])
    return doc


def _merge_pages(doc: ExtractedDocument, pages: list[ExtractedPage]) -> None:
    """Insert pages into ``doc``, merging with any already present.

    Needed for hybrid PDFs, where the text path and the OCR path each produce a
    disjoint subset of pages and both must land in one page-ordered document.
    """
    existing = {p.page_number: p for p in doc.pages}
    for p in pages:
        if p.page_number in existing:
            prev = existing[p.page_number]
            offset = len(prev.blocks)
            for b in p.blocks:
                b.order += offset
            prev.blocks.extend(p.blocks)
            prev.tables.extend(p.tables)
            prev.notes.extend(p.notes)
        else:
            existing[p.page_number] = p
    doc.pages = [existing[k] for k in sorted(existing)]
