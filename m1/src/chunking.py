"""Legal-aware chunking.

Turns the annotated IR into ``DocumentChunk`` objects, splitting on real legal
boundaries rather than character counts.

BOUNDARY LOGIC (flagged for review)
===================================

Three tiers, tried in order. Every chunk records which tier produced it in
``metadata.chunk_strategy``, so the evaluation report can show how often the
good path was actually taken.

**Tier 1 -- structural (``chunk_strategy="structural"``).**
:func:`~src.structure_preservation.annotate_structure` has already tagged every
block with the article/clause that governs it. Blocks are grouped by their
``clause_id``, and each group becomes one chunk. This is the path that matters:
the boundary is a boundary the *document* declares, so a retrieved chunk is
exactly one clause and M5 can reason about it as a clause.

  The granularity is chosen per document, not globally. ``split_by="auto"``
  uses the deepest structural level that actually occurs: a statute chunked at
  ARTICLE, a contract with numbered sub-clauses at CLAUSE. Choosing globally
  would over-split statutes (whose articles are the atomic legal unit) or
  under-split contracts (whose sub-clauses each carry an obligation).

**Tier 2 -- paragraph (``chunk_strategy="paragraph"``).** No usable markers were
found. Blocks are accumulated in reading order and cut at paragraph boundaries
once ``target_chunk_chars`` is reached. Applies to unstructured scans, letters,
and any document whose markers OCR destroyed.

**Tier 3 -- size (``chunk_strategy="size"``).** A single structural unit that
exceeds ``max_chunk_chars`` -- a long article, or an OCR page that came back as
one undifferentiated block. Split at paragraph, then sentence, then whitespace,
never mid-word. **Only these chunks get overlap**, and each is marked
``metadata.split_from_unit=True``.

  Overlap only on artificial boundaries is the deliberate part. Overlapping
  whole clauses would duplicate obligation text across chunks, and duplicate
  clause text is exactly what makes a contract-QA system answer twice or cite
  the wrong clause number. When the boundary is real, the boundary is enough.

**Tables (``chunk_strategy="table"``)** are never split (``keep_tables_whole``).
An oversized table exceeds ``max_chunk_chars`` rather than being cut, because
half a payment schedule is worse than a long chunk.

KNOWN LIMITS on interim data
----------------------------
* Marker detection is regex-based and tuned on public Egyptian legal documents
  plus synthetic fixtures. It has not seen firm documents.
* A heavily OCR-damaged marker ("اﻟﻤﺎدة" with broken joins, "1 2" for "12")
  will miss and silently demote the document to Tier 2. The evaluation report
  therefore reports the tier mix per document -- a document that fell to
  paragraph chunking when it visibly has articles is the signal to look at.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from .config import ChunkingConfig, PipelineConfig
from .document_chunk_schema import (
    BlockType,
    BoundingBox,
    ChunkMetadata,
    DocumentChunk,
    Language,
    OCRConfidence,
    SourceEngine,
    StructuralRef,
    make_chunk_id,
    now_utc,
)
from .structure_preservation import (
    ExtractedDocument,
    ExtractedPage,
    ExtractedTable,
    StructLevel,
    TextBlock,
    detect_language,
)

logger = logging.getLogger(__name__)

# Sentence terminators for Arabic and English. Arabic full stop is the same
# U+002E as Latin; the question mark and semicolon differ.
_SENTENCE_END = re.compile(r"(?<=[.!?؟؛])\s+")
_PARA_BREAK = re.compile(r"\n\s*\n")


@dataclass
class _Unit:
    """One candidate chunk before size handling: a structural unit or a table."""

    blocks: list[TextBlock] = field(default_factory=list)
    table: ExtractedTable | None = None
    struct: StructuralRef = field(default_factory=StructuralRef)
    strategy: str = "structural"

    @property
    def text(self) -> str:
        if self.table is not None:
            head = f"{self.table.caption}\n" if self.table.caption else ""
            return head + self.table.to_markdown()
        return "\n\n".join(b.text for b in self.blocks if b.text.strip())

    @property
    def pages(self) -> list[int]:
        if self.table is not None:
            return [self.table.page] if self.table.page is not None else []
        seen = []
        for b in self.blocks:
            if b.page is not None and b.page not in seen:
                seen.append(b.page)
        return seen


# ---------------------------------------------------------------------------
# Granularity choice
# ---------------------------------------------------------------------------


def choose_granularity(doc: ExtractedDocument, cfg: ChunkingConfig) -> StructLevel | None:
    """Pick the structural level to cut at for this document.

    Returns ``None`` when the document has no usable structure, which sends
    chunking to Tier 2.

    ``auto`` takes the deepest level that occurs *enough times to be a real
    scheme* -- at least three distinct units. A document with one stray
    "(a)" has not got a sub-clause scheme; it has a typo.
    """
    counts: dict[StructLevel, set[str]] = {}
    for block in doc.all_blocks():
        m = block.marker
        if m is None:
            continue
        counts.setdefault(m.level, set()).add(m.label)

    real = {lvl: labels for lvl, labels in counts.items() if len(labels) >= 3}
    if not real:
        # A document may legitimately have only 1-2 sections (a short letter).
        # Accept a shallower level with >=2 units, else give up.
        real = {lvl: labels for lvl, labels in counts.items() if len(labels) >= 2}
        if not real:
            return None

    if cfg.split_by == "auto":
        return max(real)
    wanted = {
        "clause": StructLevel.CLAUSE,
        "section": StructLevel.SECTION,
        "article": StructLevel.ARTICLE,
    }[cfg.split_by]
    if wanted in real:
        return wanted
    # Requested level absent: fall back to the deepest available at or above it.
    at_or_above = [lvl for lvl in real if lvl <= wanted]
    return max(at_or_above) if at_or_above else max(real)


def _unit_key(block: TextBlock, level: StructLevel) -> str:
    """Key identifying which structural unit a block belongs to, at ``level``.

    Uses the heading path truncated to ``level`` so that two different articles
    that happen to share a clause number do not collapse into one unit.
    """
    s = block.struct
    parts: list[str] = []
    if s.book:
        parts.append(s.book)
    if s.chapter:
        parts.append(s.chapter)
    if level >= StructLevel.SECTION and s.section:
        parts.append(s.section)
    if level >= StructLevel.ARTICLE and s.article:
        parts.append(s.article)
    if level >= StructLevel.CLAUSE and s.clause:
        parts.append(s.clause)
    return "|".join(parts) if parts else "__unstructured__"


# ---------------------------------------------------------------------------
# Unit building
# ---------------------------------------------------------------------------


def build_units(doc: ExtractedDocument, cfg: ChunkingConfig) -> list[_Unit]:
    """Group the document into pre-size-handling units, in reading order."""
    level = choose_granularity(doc, cfg) if cfg.respect_structure else None
    units: list[_Unit] = []

    if level is None:
        if cfg.respect_structure:
            _report_structural_demotion(doc)
        units = _paragraph_units(doc, cfg)
    else:
        current: _Unit | None = None
        current_key: str | None = None
        for page in doc.pages:
            for block in sorted(page.blocks, key=lambda b: b.order):
                if block.is_empty():
                    continue
                if block.block_type is BlockType.HEADER_FOOTER:
                    # Running headers/footers repeat on every page and add no
                    # retrievable content; dropping them stops page numbers and
                    # firm letterhead from polluting every chunk.
                    continue
                key = _unit_key(block, level)
                if current is None or key != current_key:
                    current = _Unit(struct=block.struct, strategy="structural")
                    units.append(current)
                    current_key = key
                current.blocks.append(block)

    # Tables become their own units, inserted after the page's text units so
    # reading order stays roughly right.
    if cfg.keep_tables_whole:
        for page in doc.pages:
            for table in page.tables:
                struct = _nearest_struct(doc, page, table)
                units.append(_Unit(table=table, struct=struct, strategy="table"))

    return [u for u in units if u.text.strip()]


def _report_structural_demotion(doc: ExtractedDocument) -> None:
    """Say out loud that this document just lost clause-level chunking.

    This is the exact moment the silent failure used to happen. Structural
    chunking was asked for, no usable marker scheme was found, and the document
    drops to Tier 2 -- every chunk loses its clause identity, the M1->M5 clause
    view returns nothing for it, and **the output is indistinguishable from a
    document that genuinely has no clauses.** A single OCR-mangled marker word
    can cause it, and before this the only trace was a `chunk_strategy` value
    somebody had to think to go and look at.

    Some documents legitimately have no structure -- letters, memos, single-page
    notes -- so this is a warning rather than an error, and it says which case
    it thinks it is by reporting what markers *were* seen. A document showing
    "2 marker(s) found" is one damaged marker away from working; a document
    showing zero on forty pages of statute is an extraction problem upstream.
    """
    seen: dict[str, set[str]] = {}
    for block in doc.all_blocks():
        if block.marker is not None:
            seen.setdefault(block.marker.kind, set()).add(block.marker.label)
    total = sum(len(v) for v in seen.values())

    doc.log_engine(None, "chunking", status="structure_detection_failed",
                   strategy="paragraph", distinct_markers=total,
                   marker_kinds=sorted(seen))
    detail = (
        ", ".join(f"{k}: {len(v)}" for k, v in sorted(seen.items()))
        if seen else "none at any level"
    )
    doc.warnings.append(
        f"structure_detection_failed: no usable clause/article scheme was found "
        f"(markers seen -- {detail}), so this document was chunked by PARAGRAPH "
        f"rather than by clause. Its chunks carry no clause_id and it will not "
        f"appear in the M1->M5 clause view. If the source visibly has numbered "
        f"articles or clauses, their markers did not survive extraction -- check "
        f"reading order and OCR quality for this file."
    )


def _paragraph_units(doc: ExtractedDocument, cfg: ChunkingConfig) -> list[_Unit]:
    """Tier 2: accumulate blocks, cutting at paragraph boundaries near target size."""
    units: list[_Unit] = []
    current = _Unit(strategy="paragraph")
    size = 0
    for page in doc.pages:
        for block in sorted(page.blocks, key=lambda b: b.order):
            if block.is_empty() or block.block_type is BlockType.HEADER_FOOTER:
                continue
            blen = len(block.text)
            if size and size + blen > cfg.target_chunk_chars:
                units.append(current)
                current = _Unit(strategy="paragraph", struct=block.struct)
                size = 0
            if not current.blocks:
                current.struct = block.struct
            current.blocks.append(block)
            size += blen
    if current.blocks:
        units.append(current)
    return units


def _nearest_struct(doc: ExtractedDocument, page: ExtractedPage, table: ExtractedTable) -> StructuralRef:
    """Attribute a table to the structural unit whose text sits closest above it.

    Docling and PyMuPDF both report tables separately from the text flow, so a
    table has no marker of its own. Anchoring it to the nearest preceding block
    on the same page means a payment schedule inherits the clause that
    introduces it -- which is how a lawyer would cite it.
    """
    if table.bbox is None:
        return page.blocks[0].struct if page.blocks else StructuralRef()
    above = [
        b for b in page.blocks
        if b.bbox is not None and b.bbox.y1 <= table.bbox.y0 + 5
    ]
    if not above:
        return page.blocks[0].struct if page.blocks else StructuralRef()
    return max(above, key=lambda b: b.bbox.y1).struct


# ---------------------------------------------------------------------------
# Size handling (Tier 3)
# ---------------------------------------------------------------------------


def split_oversized(text: str, cfg: ChunkingConfig, budget: int | None = None) -> list[str]:
    """Split text that exceeds ``max_chunk_chars``, with overlap.

    Descends through boundary quality: paragraph breaks, then sentence ends,
    then whitespace. Never splits mid-word -- a truncated Arabic word is
    unrecoverable for both a reader and an embedding model.

    ``budget`` is the true ceiling for the *finished* chunk, defaulting to
    ``cfg.max_chunk_chars``. The caller passes a reduced budget when it will
    prepend a heading. Overlap is subtracted from the working limit here for the
    same reason: both the heading and the overlap tail are added *after* the
    split, so a naive implementation silently overshoots the configured maximum
    on every split chunk -- which then breaks whatever token limit downstream
    sized itself against ``max_chunk_chars``.
    """
    ceiling = cfg.max_chunk_chars if budget is None else budget
    if len(text) <= ceiling:
        return [text]

    # Leave room for the overlap tail that gets prepended below.
    limit = max(ceiling - max(cfg.overlap_chars, 0), 100)

    pieces = _split_on(text, _PARA_BREAK, limit)
    if any(len(p) > limit for p in pieces):
        out: list[str] = []
        for p in pieces:
            out.extend(_split_on(p, _SENTENCE_END, limit) if len(p) > limit else [p])
        pieces = out
    if any(len(p) > limit for p in pieces):
        out = []
        for p in pieces:
            out.extend(_hard_wrap(p, limit) if len(p) > limit else [p])
        pieces = out

    return _apply_overlap(pieces, cfg.overlap_chars) if cfg.overlap_chars > 0 else pieces


def _split_on(text: str, pattern: re.Pattern, limit: int) -> list[str]:
    """Greedily pack the pattern-delimited parts of ``text`` into <= ``limit`` chunks."""
    parts = [p for p in pattern.split(text) if p and p.strip()]
    if len(parts) <= 1:
        return [text]
    out, buf = [], ""
    for part in parts:
        candidate = f"{buf}\n\n{part}" if buf else part
        if buf and len(candidate) > limit:
            out.append(buf)
            buf = part
        else:
            buf = candidate
    if buf:
        out.append(buf)
    return out


def _hard_wrap(text: str, limit: int) -> list[str]:
    """Last resort: pack whitespace-delimited tokens up to ``limit``."""
    out, buf = [], ""
    for token in text.split(" "):
        candidate = f"{buf} {token}" if buf else token
        if buf and len(candidate) > limit:
            out.append(buf)
            buf = token
        else:
            buf = candidate
    if buf:
        out.append(buf)
    return out


def _apply_overlap(pieces: list[str], overlap: int) -> list[str]:
    """Prepend a tail of the previous piece, cut at a word boundary."""
    if len(pieces) < 2:
        return pieces
    out = [pieces[0]]
    for prev, cur in zip(pieces, pieces[1:]):
        tail = prev[-overlap:]
        cut = tail.find(" ")
        tail = tail[cut + 1:] if cut != -1 else tail
        out.append(f"{tail.strip()} {cur}".strip() if tail.strip() else cur)
    return out


# ---------------------------------------------------------------------------
# Chunk emission
# ---------------------------------------------------------------------------


def chunk_document(doc: ExtractedDocument, config: PipelineConfig) -> list[DocumentChunk]:
    """Produce the document's ``DocumentChunk`` list. **Main entry point.**

    Every returned chunk has all seven spec fields populated plus the metadata
    bag described by :class:`~src.document_chunk_schema.ChunkMetadata`.
    """
    cfg = config.chunking
    units = build_units(doc, cfg)
    units = _merge_tiny_units(units, cfg)

    chunks: list[DocumentChunk] = []
    index = 0
    char_cursor = 0

    for unit in units:
        text = unit.text.strip()
        if not text:
            continue

        heading = _heading_prefix(unit, cfg)
        head_cost = len(heading) + 1 if heading else 0

        if unit.table is not None and cfg.keep_tables_whole:
            pieces, split = [text], False
        else:
            pieces = split_oversized(text, cfg, budget=cfg.max_chunk_chars - head_cost)
            split = len(pieces) > 1

        for piece in pieces:
            body = piece.strip()
            if not body:
                continue
            final = f"{heading}\n{body}" if heading and not body.startswith(heading) else body
            index += 1
            chunks.append(
                _emit(
                    doc=doc, config=config, unit=unit, text=final, index=index,
                    split_from_unit=split, char_start=char_cursor,
                )
            )
            char_cursor += len(final) + 2

    return chunks


def _merge_tiny_units(units: list[_Unit], cfg: ChunkingConfig) -> list[_Unit]:
    """Fold sub-minimum *identity-less* units forward into the next one.

    The case this exists for: a structural heading that sits in its own layout
    block ("الباب الأول", "الفصل الأول") with the substantive text in the next
    unit. Emitting that alone gives a chunk that retrieves well and answers
    nothing.

    **A unit that has its own ``clause_id`` is never merged, however short.**
    Short articles are entirely normal in Egyptian statutes -- "المادة (1)
    يعمل بأحكام القانون المرفق" is a complete article in about eighty
    characters. Merging it into the next article would erase the clause
    identity that is the whole point of structural chunking, and would make M5
    cite article 1's text under article 2's number.

    So ``min_chunk_chars`` governs *fragments*, not *clauses*. Tables are never
    merged either way.
    """
    out: list[_Unit] = []
    pending: _Unit | None = None

    def flush_into(unit: _Unit) -> None:
        nonlocal pending
        if pending is None:
            return
        unit.blocks = pending.blocks + unit.blocks
        # The merged chunk now starts at the pending unit; inherit its identity
        # only when the receiving unit has none of its own.
        if not unit.struct.clause_id and pending.struct.clause_id:
            unit.struct = pending.struct
        pending = None

    for unit in units:
        if unit.table is not None:
            if pending is not None:
                out.append(pending)
                pending = None
            out.append(unit)
            continue

        flush_into(unit)

        too_short = len(unit.text.strip()) < cfg.min_chunk_chars
        has_identity = bool(unit.struct.clause_id)
        if too_short and not has_identity:
            pending = unit
            continue
        out.append(unit)

    if pending is not None:
        if out and out[-1].table is None:
            out[-1].blocks.extend(pending.blocks)
        else:
            out.append(pending)
    return out


def _heading_prefix(unit: _Unit, cfg: ChunkingConfig) -> str | None:
    """The governing heading, prepended so a retrieved chunk is self-describing.

    Suppressed when the unit's text already opens with it, which is the normal
    case for a structural unit whose first block *is* the heading line.
    """
    if not cfg.attach_heading_to_body:
        return None
    s = unit.struct
    label = s.clause or s.article or s.section
    if not label:
        return None

    # Suppress when the body already opens with this heading. The comparison
    # squashes whitespace and punctuation because the body writes
    # "المادة (1) : التعريفات" while the label is "المادة 1" -- a literal
    # containment test misses that and duplicates the heading on every chunk.
    head = _squash(unit.text.strip()[:300])
    return None if _squash(label) in head else label


def _squash(s: str) -> str:
    """Strip everything but letters and digits, for heading comparison."""
    return "".join(c for c in s if c.isalnum())


def _emit(
    *, doc: ExtractedDocument, config: PipelineConfig, unit: _Unit, text: str,
    index: int, split_from_unit: bool, char_start: int,
) -> DocumentChunk:
    """Build one fully-populated ``DocumentChunk``."""
    pages = unit.pages
    # ``page`` is required by the contract (M1 and M2 both declare ``ge=1``).
    # Every extractor stamps a page number -- paginated formats from their
    # provenance, unpaginated ones (TXT, single-"page" DOCX) from a synthetic
    # page 1. A unit with no page at all means an extractor lost the number,
    # so fall back to page 1 rather than emit an invalid chunk, and say so.
    if pages:
        page = pages[0]
    else:
        page = 1
        logger.warning(
            "chunk %d of %s carries no page provenance; defaulting page=1",
            index, doc.source_path,
        )

    bboxes: list[BoundingBox] = []
    rtl_flags = []
    norm_applied: list[str] = []
    confs: list[float] = []
    n_boxes = 0
    low_conf = 0
    engines: set[SourceEngine] = set()
    raw_parts: list[str] = []
    reading_order_repaired = False
    block_type = BlockType.TABLE if unit.table is not None else BlockType.PARAGRAPH

    if unit.table is not None:
        if unit.table.bbox:
            bboxes.append(unit.table.bbox)
        engines.add(unit.table.source_engine)
    else:
        for b in unit.blocks:
            if b.bbox:
                bboxes.append(b.bbox)
            rtl_flags.extend(b.rtl_flags)
            reading_order_repaired = reading_order_repaired or b.reading_order_repaired
            norm_applied.extend(b.normalization_applied)
            engines.add(b.source_engine)
            if b.confidence is not None:
                confs.append(b.confidence)
                n_boxes += b.n_boxes or 0
            if b.raw_text:
                raw_parts.append(b.raw_text)
        types = [b.block_type for b in unit.blocks]
        if types and all(t is BlockType.HEADING for t in types):
            block_type = BlockType.HEADING
        elif types and types.count(BlockType.LIST) > len(types) / 2:
            block_type = BlockType.LIST

    ocr_conf = None
    if confs:
        page_ocr = next(
            (p.ocr for p in doc.pages if p.page_number == page and p.ocr), None
        )
        ocr_conf = OCRConfidence(
            engine=next(iter(engines), SourceEngine.UNKNOWN),
            mean=round(sum(confs) / len(confs), 4),
            min=round(min(confs), 4),
            n_boxes=n_boxes or None,
            low_confidence_boxes=page_ocr.low_confidence_boxes if page_ocr else None,
            fallback_used=page_ocr.fallback_used if page_ocr else False,
            fallback_reason=page_ocr.fallback_reason if page_ocr else None,
        )

    engine = (
        next(iter(engines)) if len(engines) == 1
        else (SourceEngine.PYMUPDF_DOCLING if engines else SourceEngine.UNKNOWN)
    )

    meta = ChunkMetadata(
        jurisdiction=doc.jurisdiction or config.default_jurisdiction,
        source_file=doc.source_path,
        source_engine=engine,
        pdf_kind=doc.pdf_kind,  # type: ignore[arg-type]
        ingested_at=now_utc(),
        structure=unit.struct,
        block_type=block_type,
        bboxes=bboxes,
        bbox=BoundingBox.union(bboxes),
        page_span=pages,
        char_span=(char_start, char_start + len(text)),
        is_table=unit.table is not None,
        table_markdown=unit.table.to_markdown() if unit.table else None,
        table_shape=unit.table.shape if unit.table else None,
        ocr_confidence=ocr_conf,
        rtl_flags=rtl_flags,
        reading_order_repaired=reading_order_repaired,
        normalization_applied=sorted(set(norm_applied)),
        raw_text=("\n\n".join(raw_parts) if (config.keep_raw_text_in_metadata and raw_parts) else None),
        display_text=next((b.display_text for b in unit.blocks if b.display_text), None)
        if unit.table is None else None,
        chunk_index=index,
        chunk_strategy=("table" if unit.table is not None
                        else "size" if split_from_unit
                        else unit.strategy),  # type: ignore[arg-type]
        split_from_unit=split_from_unit,
        n_chars=len(text),
        n_words=len(text.split()),
    )

    # ``section`` is the human-readable label the spec's example shows
    # ("Termination"), so prefer the deepest unit's *title*. Fall back to the
    # deepest identifier when the heading carried no text of its own. The full
    # hierarchy is always available in ``metadata.structure``.
    s = unit.struct
    section = s.title or s.clause or s.article or s.section
    if section and len(section) > 120:
        section = section[:117].rstrip() + "..."

    return DocumentChunk(
        document_id=doc.document_id,
        chunk_id=make_chunk_id(index),
        text=text,
        page=page,
        section=section,
        # Surfaced from ``metadata.structure.clause``, which stays populated --
        # this is an additional location for the same value, not a move.
        clause=s.clause,
        language=detect_language(text),
        document_type=doc.document_type,
        metadata=meta.model_dump(mode="json", exclude_none=False),
    )
