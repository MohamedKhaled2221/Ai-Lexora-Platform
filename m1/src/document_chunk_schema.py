"""The M1 output contract: ``DocumentChunk``.

This module is the **stable interface** between M1 and the rest of the AI Core
(M2/M3 retrieval + QA, M5 contract intelligence). The top-level fields are
frozen by the team spec:

    document_id, chunk_id, text, page, section, language, document_type, metadata

plus ``clause``, which M2's copy of the contract declares and M1 now populates
from ``metadata.structure.clause`` (see
``reports/schema_contract_verification.md``).

``metadata`` is deliberately an open dict so M1 can keep adding structural
signal (bounding boxes, clause ids, OCR confidence, ...) without breaking
consumers. Consumers should treat unknown metadata keys as additive.

Example
-------
>>> DocumentChunk(
...     document_id="doc_001",
...     chunk_id="chunk_017",
...     text="Termination may occur...",
...     page=12,
...     section="Termination",
...     language="en",
...     document_type="contract",
...     metadata={"jurisdiction": "Egypt"},
... ).model_dump()["chunk_id"]
'chunk_017'
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Controlled vocabularies
# ---------------------------------------------------------------------------


class Language(str, Enum):
    """Dominant language of a chunk.

    ``ar-en`` means Arabic and Latin script are both materially present -- for
    Egyptian legal work this is common (bilingual contracts, English defined
    terms inside Arabic clauses) and downstream consumers may want to route
    those differently.

    This enum is the *only* place the wire values are defined, and every
    producer routes through it, so an unexpected value cannot be emitted. The
    bilingual value was ``"mixed"`` until 2026-08-17; it is now ``"ar-en"``, to
    match M2's ``Literal`` exactly -- see
    ``reports/schema_contract_verification.md``.
    """

    AR = "ar"
    EN = "en"
    AR_EN = "ar-en"
    UNKNOWN = "unknown"


class DocumentType(str, Enum):
    """Coarse document class, inferred heuristically at ingestion time.

    Deliberately coarse. Fine-grained legal taxonomy is M5's problem; M1 only
    needs enough to route and filter.
    """

    CONTRACT = "contract"
    LAW = "law"                 # قانون / لائحة / مرسوم -- statute or regulation
    COURT_RULING = "court_ruling"   # حكم / قرار محكمة
    PLEADING = "pleading"       # مذكرة / صحيفة دعوى
    POWER_OF_ATTORNEY = "power_of_attorney"  # توكيل
    CORRESPONDENCE = "correspondence"
    UNKNOWN = "unknown"


class BlockType(str, Enum):
    """What kind of layout element a chunk's dominant content came from."""

    PARAGRAPH = "paragraph"
    HEADING = "heading"
    TABLE = "table"
    LIST = "list"
    SIGNATURE = "signature"
    STAMP = "stamp"
    HEADER_FOOTER = "header_footer"
    UNKNOWN = "unknown"


class SourceEngine(str, Enum):
    """Which extractor actually produced the text. Tracked per chunk so OCR and
    text-layer quality can be evaluated separately (spec requirement)."""

    PYMUPDF = "pymupdf"
    DOCLING = "docling"
    PYMUPDF_DOCLING = "pymupdf+docling"
    PADDLEOCR = "paddleocr"
    TESSERACT = "tesseract"
    PYTHON_DOCX = "python-docx"
    PLAINTEXT = "plaintext"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Metadata sub-structures
# ---------------------------------------------------------------------------


class BoundingBox(BaseModel):
    """Axis-aligned box in PDF points, origin top-left, as PyMuPDF reports it.

    For OCR pages the box is in the coordinate space of the *rasterized* page
    and ``scale`` records the points-per-pixel factor used, so consumers can map
    back to the original page geometry.
    """

    model_config = ConfigDict(extra="forbid")

    x0: float
    y0: float
    x1: float
    y1: float
    page: int | None = None
    scale: float | None = Field(
        default=None,
        description="points-per-pixel; set when the box came from a rasterized OCR page",
    )

    @model_validator(mode="after")
    def _order_corners(self) -> "BoundingBox":
        if self.x1 < self.x0:
            self.x0, self.x1 = self.x1, self.x0
        if self.y1 < self.y0:
            self.y0, self.y1 = self.y1, self.y0
        return self

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @classmethod
    def union(cls, boxes: Iterable["BoundingBox"]) -> "BoundingBox | None":
        boxes = [b for b in boxes if b is not None]
        if not boxes:
            return None
        return cls(
            x0=min(b.x0 for b in boxes),
            y0=min(b.y0 for b in boxes),
            x1=max(b.x1 for b in boxes),
            y1=max(b.y1 for b in boxes),
            page=boxes[0].page,
            scale=boxes[0].scale,
        )

    @classmethod
    def from_quad(cls, quad, page: int | None = None, scale: float | None = None) -> "BoundingBox":
        """Build from a PaddleOCR polygon ``[[x,y], [x,y], [x,y], [x,y]]``."""
        xs = [float(p[0]) for p in quad]
        ys = [float(p[1]) for p in quad]
        return cls(x0=min(xs), y0=min(ys), x1=max(xs), y1=max(ys), page=page, scale=scale)


class OCRConfidence(BaseModel):
    """Per-chunk OCR quality summary. Absent for text-layer extraction."""

    model_config = ConfigDict(extra="allow")

    engine: SourceEngine
    mean: float | None = Field(default=None, ge=0.0, le=1.0)
    min: float | None = Field(default=None, ge=0.0, le=1.0)
    n_boxes: int | None = None
    low_confidence_boxes: int | None = Field(
        default=None, description="boxes below OCRConfig.drop_below_confidence"
    )
    fallback_used: bool = False
    fallback_reason: str | None = None


class StructuralRef(BaseModel):
    """Where this chunk sits in the document's legal structure.

    Populated as far as the document actually supports. A chunk from an
    Egyptian statute typically fills ``book``/``chapter``/``article``; a chunk
    from a contract typically fills ``section``/``clause``.
    """

    model_config = ConfigDict(extra="allow")

    book: str | None = None        # الباب
    chapter: str | None = None     # الفصل
    section: str | None = None     # القسم / heading
    article: str | None = None     # المادة  -- e.g. "المادة 12" / "Article 12"
    clause: str | None = None      # البند   -- e.g. "12.3" / "(أ)"
    clause_id: str | None = None   # normalized, stable id e.g. "art_12.cl_3"
    title: str | None = Field(
        default=None,
        description="heading text of the deepest open unit, without its "
                    "identifier -- e.g. 'Termination' for 'Article 12. Termination'",
    )
    heading_path: list[str] = Field(default_factory=list)
    """Ordered ancestry of headings, outermost first. Lets M5 reconstruct a
    contract's clause tree without re-parsing."""
    heading_level: int | None = None
    marker_language: Literal["ar", "en", None] = None
    """Which language the structural marker was written in. Useful because
    bilingual contracts often number clauses in only one of the two."""

    marker_fuzzy: bool = False
    """True when this unit's marker was recovered by OCR-tolerant matching
    rather than an exact one -- the marker word or its number was damaged and
    had to be repaired. The chunk is still usable; it is flagged so a rising
    share of fuzzy markers is visible as an OCR-quality signal rather than
    silently absorbed."""
    marker_confidence: float = 1.0
    """1.0 for an exactly-matched marker, lower the further the text was from
    canonical form."""
    marker_evidence: str | None = None
    """What the tolerant matcher had to do, for spot-checking against the
    source. ``None`` for exact matches."""


class RTLFlag(BaseModel):
    """A surfaced (not silently fixed) reading-order concern.

    Per the spec: mixed Arabic/English/numeral content that produces ambiguous
    reading order must be logged for manual review, never quietly rewritten.
    """

    model_config = ConfigDict(extra="allow")

    kind: Literal[
        "mixed_direction",
        "visual_order_suspected",
        "visual_order_repaired",
        "presentation_forms_found",
        "numeral_direction_ambiguous",
        "high_switch_count",
        "neutral_order_mirrored",
        "brackets_unmirrored",
        "digit_order_suspect",
    ]
    page: int | None = None
    detail: str = ""
    severity: Literal["info", "warn"] = "warn"
    sample: str | None = Field(default=None, description="short excerpt for eyeballing")


class ChunkMetadata(BaseModel):
    """Extensible metadata bag carried on every chunk.

    Declared as a model for documentation/validation, but serialized as a plain
    dict on ``DocumentChunk.metadata`` so consumers never have to import M1's
    types. ``extra='allow'`` means adding a field here is always backwards
    compatible.
    """

    model_config = ConfigDict(extra="allow")

    # --- provenance ---------------------------------------------------------
    jurisdiction: str | None = None
    source_file: str | None = None
    source_engine: SourceEngine = SourceEngine.UNKNOWN
    pdf_kind: Literal["text", "scanned", "hybrid", "n/a", None] = None
    ingested_at: datetime | None = None

    # --- structure (spec: page, section, heading, clause, table, bbox) -------
    structure: StructuralRef = Field(default_factory=StructuralRef)
    block_type: BlockType = BlockType.PARAGRAPH
    bboxes: list[BoundingBox] = Field(default_factory=list)
    bbox: BoundingBox | None = Field(
        default=None, description="union of bboxes; convenience for highlighting"
    )
    page_span: list[int] = Field(
        default_factory=list,
        description="all pages this chunk's text came from (usually one)",
    )
    char_span: tuple[int, int] | None = Field(
        default=None, description="offsets into the document's normalized full text"
    )

    # --- tables -------------------------------------------------------------
    is_table: bool = False
    table_markdown: str | None = None
    table_shape: tuple[int, int] | None = None  # (rows, cols)

    # --- quality ------------------------------------------------------------
    ocr_confidence: OCRConfidence | None = None
    rtl_flags: list[RTLFlag] = Field(default_factory=list)
    reading_order_repaired: bool = Field(
        default=False,
        description="True when this chunk's source text was stored in visual "
        "(screen) order and was reordered to logical reading order. The repair "
        "is recorded rather than applied silently: the matching "
        "``visual_order_repaired`` entry in ``rtl_flags`` carries the evidence "
        "and the scores it was accepted on, and ``raw_text`` still holds the "
        "text exactly as extracted.",
    )
    normalization_applied: list[str] = Field(default_factory=list)
    raw_text: str | None = Field(
        default=None, description="pre-normalization, pre-RTL-repair text"
    )
    display_text: str | None = Field(
        default=None,
        description="reshaped + bidi presentation form, for rendering only -- "
        "never embed this",
    )

    # --- chunking provenance ------------------------------------------------
    chunk_index: int | None = None
    chunk_strategy: Literal["structural", "paragraph", "size", "table", None] = None
    split_from_unit: bool = Field(
        default=False,
        description="True when the parent structural unit exceeded max size and "
        "had to be split, i.e. this boundary is artificial",
    )
    n_chars: int | None = None
    n_words: int | None = None


# ---------------------------------------------------------------------------
# The output object
# ---------------------------------------------------------------------------


class DocumentChunk(BaseModel):
    """One retrievable unit of a legal document. **M1's output contract.**

    Field semantics
    ---------------
    document_id
        Stable id for the source document, ``doc_XXX`` by default. Derived from
        a hash of the file contents (see ``make_document_id``) so re-ingesting
        the same file yields the same id.
    chunk_id
        ``chunk_XXX``, unique *within* a document and ordered by reading
        position. Globally unique key is ``(document_id, chunk_id)``.
    text
        The chunk text after RTL repair and Arabic normalization. This is what
        M2/M3 should embed.
    page
        1-based page number where the chunk starts. ``metadata.page_span`` lists
        every page it touches. **Always present.** Formats with no pagination
        (TXT, and DOCX where no explicit page break was found) are treated as a
        single page and report ``1``; the chunker never emits a page-less chunk.
    section
        Human-readable section/heading label, e.g. ``"Termination"`` or
        ``"المادة 12"``. Best-effort; ``None`` when the document has no
        detectable structure. Richer structure lives in
        ``metadata.structure``.
    clause
        The clause/article-level identifier this chunk is anchored to, e.g.
        ``"Clause 1"`` / ``"البند 3"``. Mirrors
        ``metadata.structure.clause`` -- surfaced at the top level because
        consumers filter on it. ``None`` when the chunk is not clause-anchored.
    language
        ``ar`` | ``en`` | ``ar-en`` | ``unknown`` -- see :class:`Language`.
    document_type
        See :class:`DocumentType`.
    metadata
        Open dict. Shape documented by :class:`ChunkMetadata`.

    client_id, matter_id, confidentiality_level
        Access-control provenance, added 2026-09-05 for M3 tenancy filtering.
        **Optional here on purpose.** M1 is not an authority on who may read a
        document -- it only sees the file. These fields exist so a producer
        that *does* know the answer can carry it through unchanged; a producer
        that does not leaves them ``None`` and nothing breaks.

        The authoritative stamp happens at the M3 ingest boundary, from the
        authenticated caller, and overwrites whatever arrives here. Downstream
        indexing refuses any chunk still unstamped at that point, so ``None``
        can never reach the vector store as "unrestricted".

        Reserved sentinel values used downstream: ``client_id="_shared"`` for
        the cross-tenant legal corpus (statutes, rulings, templates) and
        ``matter_id="_none"`` for client-level documents not tied to a matter.
    """

    model_config = ConfigDict(
        extra="forbid",
        use_enum_values=True,
        json_schema_extra={
            "example": {
                "document_id": "doc_001",
                "chunk_id": "chunk_017",
                "text": "Termination may occur...",
                "page": 12,
                "section": "Termination",
                "language": "en",
                "document_type": "contract",
                "metadata": {"jurisdiction": "Egypt"},
            }
        },
    )

    document_id: str = Field(..., min_length=1, examples=["doc_001"])
    chunk_id: str = Field(..., min_length=1, examples=["chunk_017"])
    text: str = Field(..., examples=["Termination may occur..."])
    page: int = Field(..., ge=1, examples=[12])
    section: str | None = Field(default=None, examples=["Termination"])
    clause: str | None = Field(default=None, examples=["Clause 1"])
    language: Language = Field(default=Language.UNKNOWN, examples=["en"])
    document_type: DocumentType = Field(default=DocumentType.UNKNOWN, examples=["contract"])
    metadata: dict[str, Any] = Field(
        default_factory=dict, examples=[{"jurisdiction": "Egypt"}]
    )

    # --- access control (additive; authoritative value is stamped at ingest) --
    client_id: str | None = Field(default=None, examples=["client_042"])
    matter_id: str | None = Field(default=None, examples=["matter_2026_017"])
    confidentiality_level: Literal["public", "internal", "privileged"] | None = Field(
        default=None, examples=["privileged"]
    )

    @field_validator("text")
    @classmethod
    def _text_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("chunk text must not be empty or whitespace-only")
        return v

    @field_validator("document_id", "chunk_id")
    @classmethod
    def _ids_are_tokens(cls, v: str) -> str:
        if any(ch.isspace() for ch in v):
            raise ValueError("ids must not contain whitespace")
        return v

    # -- convenience for consumers -----------------------------------------

    @property
    def structure(self) -> StructuralRef:
        """Typed view of ``metadata['structure']``."""
        return StructuralRef(**(self.metadata.get("structure") or {}))

    @property
    def is_clause(self) -> bool:
        """True when this chunk is anchored to an identifiable clause/article.

        This is the filter M5 uses to pull clause-level contract data.
        """
        s = self.structure
        return bool(s.clause or s.article or s.clause_id)

    def preview(self, n: int = 80) -> str:
        flat = " ".join(self.text.split())
        return flat[:n] + ("..." if len(flat) > n else "")


class DocumentIngestResult(BaseModel):
    """Everything M1 knows about one processed document.

    Returned by ``POST /ingest``. ``chunks`` is the payload M2/M3 consume;
    the rest is diagnostics that make failures debuggable without re-running.
    """

    model_config = ConfigDict(use_enum_values=True)

    document_id: str
    source_file: str
    file_type: str
    pdf_kind: Literal["text", "scanned", "hybrid", "n/a", None] = None
    document_type: DocumentType = DocumentType.UNKNOWN
    language: Language = Language.UNKNOWN
    n_pages: int = 0
    n_chunks: int = 0
    chunks: list[DocumentChunk] = Field(default_factory=list)

    engine_log: list[dict[str, Any]] = Field(
        default_factory=list,
        description="per-page record of which engine handled it and why "
        "(spec requirement: log engine choice for later comparison)",
    )
    rtl_flags: list[RTLFlag] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    timings_ms: dict[str, float] = Field(default_factory=dict)
    succeeded: bool = True

    @model_validator(mode="after")
    def _sync_counts(self) -> "DocumentIngestResult":
        self.n_chunks = len(self.chunks)
        return self


# ---------------------------------------------------------------------------
# Id helpers
# ---------------------------------------------------------------------------


def make_document_id(source: str | bytes, seq: int | None = None) -> str:
    """Deterministic ``doc_XXX`` id.

    ``seq`` gives the spec's literal ``doc_001`` form for ordered batches;
    without it we hash the content so the same file always gets the same id
    across runs and machines (important once documents are re-ingested after a
    pipeline change).
    """
    if seq is not None:
        return f"doc_{seq:03d}"
    import hashlib

    payload = source.encode("utf-8") if isinstance(source, str) else source
    return "doc_" + hashlib.sha1(payload).hexdigest()[:12]


def make_chunk_id(index: int) -> str:
    """``chunk_017`` style id, 1-based, zero-padded to 3."""
    return f"chunk_{index:03d}"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
