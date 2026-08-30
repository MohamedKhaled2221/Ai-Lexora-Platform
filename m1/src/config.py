"""Pipeline configuration.

Every behavioural knob the pipeline has lives here so it can be A/B tested
against real firm documents once they arrive, without touching pipeline code.

Config can be supplied three ways (later wins):
  1. defaults below
  2. a JSON/YAML-ish dict passed to ``PipelineConfig(**d)``
  3. environment variables prefixed ``M1_`` (see ``PipelineConfig.from_env``)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

# --------------------------------------------------------------------------
# Repo layout
# --------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEST_CORPUS_DIR = PROJECT_ROOT / "test_corpus"
PUBLIC_CORPUS_DIR = TEST_CORPUS_DIR / "public"
SYNTHETIC_CORPUS_DIR = TEST_CORPUS_DIR / "synthetic"
REPORTS_DIR = PROJECT_ROOT / "reports"
LOGS_DIR = PROJECT_ROOT / "logs"
OUTPUT_DIR = PROJECT_ROOT / "output"


class NormalizationConfig(BaseModel):
    """Arabic normalization toggles.

    Each step is individually switchable so their effect can be measured
    separately once real firm documents are available. Defaults are the
    conservative set: things that are almost always safe for legal Arabic.

    NOTE: normalization is *lossy*. ``text`` on the emitted chunk carries the
    normalized form (what M2/M3 should embed); ``metadata.raw_text`` carries the
    pre-normalization form so nothing is destroyed. See
    :mod:`src.normalize` for the per-step semantics.
    """

    enabled: bool = True

    # --- safe / near-lossless ------------------------------------------------
    strip_tatweel: bool = True
    """Remove kashida/tatweel (U+0640) used for justification, not meaning."""

    strip_diacritics: bool = True
    """Remove harakat (fatha, damma, ...). Legal Arabic is rarely vocalized;
    when it is, the diacritics are decorative."""

    normalize_ligatures: bool = True
    """Decompose lam-alef presentation ligatures (U+FEFB..) into ل + ا."""

    strip_presentation_forms: bool = True
    """Map Arabic Presentation Forms A/B (U+FB50-U+FEFF) back to their base
    letters. Critical after OCR, which frequently emits presentation forms."""

    collapse_whitespace: bool = True
    normalize_punctuation: bool = True
    """Map Arabic punctuation variants (، ؛ ؟) to canonical codepoints and
    collapse repeated dot leaders used in form fields."""

    # --- orthographic folding: helps recall, loses distinctions ---------------
    normalize_alef: bool = True
    """أ إ آ ٱ -> ا. Standard for Arabic IR. Slightly lossy."""

    normalize_hamza: bool = False
    """ؤ ئ ء folding. OFF by default: changes legal terms' spelling more
    aggressively than alef folding and is worth A/B testing."""

    normalize_teh_marbuta: bool = False
    """ة -> ه. OFF by default: distinguishes real words in legal Arabic."""

    normalize_alef_maksura: bool = True
    """ى -> ي at word end. Common OCR/typing inconsistency in Egyptian docs."""

    normalize_digits: Literal["none", "to_arabic", "to_western"] = "to_western"
    """Arabic-Indic (٠١٢) vs Western (012) digits. Egyptian legal documents mix
    both freely; folding to one form makes article/clause numbers matchable.
    ``none`` preserves the source."""


class RTLConfig(BaseModel):
    """RTL reading-order / shaping configuration.

    IMPORTANT DESIGN DECISION (flagged for review):

    ``arabic_reshaper`` + ``python-bidi`` convert *logical-order* Arabic into
    *visual-order presentation forms*. That is the correct transform for
    rendering into a canvas that has no bidi engine (PDF drawing, terminal).
    It is the WRONG transform to feed an embedding model or a tokenizer --
    presentation forms are different codepoints and will wreck retrieval.

    So the pipeline uses these libraries for two distinct, deliberate jobs:

      * ``repair_visual_order`` (default ON) -- detect text that arrived already
        in *visual* order (a genuine OCR/legacy-PDF artifact) and put it back
        into logical order. This is the fix that actually matters for M2/M3.
      * ``emit_display_form`` (default OFF) -- additionally produce the
        reshaped/bidi'd presentation string, stored in
        ``metadata.display_text``, never in ``text``.

    Set ``force_display_in_text=True`` only if a downstream consumer explicitly
    wants presentation forms in the primary text field.
    """

    enabled: bool = True
    repair_visual_order: bool = True
    emit_display_form: bool = False
    force_display_in_text: bool = False

    flag_mixed_direction: bool = True
    """Log (do not silently fix) blocks where Arabic + Latin + numerals produce
    ambiguous reading order. These are surfaced in
    ``metadata.rtl_flags`` and in the evaluation report for manual review."""

    mixed_direction_min_latin_chars: int = 2
    """A Latin run shorter than this inside an Arabic block is treated as noise
    rather than a genuine direction switch."""

    max_direction_switches_before_flag: int = 4
    """Blocks with more bidi direction switches than this are flagged as
    high-risk reading order."""


class PreprocessConfig(BaseModel):
    """Image preprocessing applied to a page raster before OCR.

    Every field here was swept against the Arabic ground-truth benchmark by
    ``scripts/arabic_preprocess_sweep.py``; the results are in
    ``reports/arabic_preprocess_sweep.md``. The defaults are whatever that sweep
    justified, and ``enabled=False`` is a result rather than a placeholder: the
    unprocessed raster is what Tesseract was measured to read best, because it
    runs its own Otsu internally and gets to see the full grayscale while doing
    it.

    Re-run the sweep before changing any of these -- it is one command and it
    reports the alternative you would be choosing.
    """

    enabled: bool = False
    """Master switch. When False the raster reaches OCR exactly as rendered."""

    binarization: Literal["none", "otsu", "global", "adaptive"] = "none"
    """Thresholding method. ``none`` leaves grayscale for the engine's own
    internal binarization, which on this corpus beat every explicit method."""

    global_threshold: int = 180
    """Cut point for ``binarization="global"``. Ignored otherwise."""

    adaptive_block_size: int = 31
    """Neighbourhood size for ``binarization="adaptive"``, in pixels. Forced odd.
    Must scale with render DPI: a block smaller than a glyph turns the inside of
    a stroke into background."""

    adaptive_c: int = 10
    """Constant subtracted from the local mean for ``binarization="adaptive"``.
    Higher = more aggressive removal of light pixels."""

    deskew: bool = False
    """Auto-straighten the page by projection-profile variance."""

    deskew_limit_deg: float = 6.0
    """Search range for skew estimation. Wider is not better: a page with strong
    vertical structure (a ruled table, a two-column gutter) can score a spurious
    variance peak at a large angle."""

    contrast: Literal["none", "unsharp", "clahe", "clahe+unsharp"] = "none"
    """Contrast/sharpening stage."""

    unsharp_amount: float = 0.8
    unsharp_radius: float = 1.2
    """Kept light on purpose: a strong mask thickens Arabic strokes until the
    dots that distinguish ب ت ث merge, which is the failure mode the whole
    preprocessing question exists to avoid."""


class OCRConfig(BaseModel):
    """OCR engine selection and the PaddleOCR -> Tesseract fallback policy."""

    enabled: bool = True

    primary_engine: Literal["paddleocr", "tesseract"] = "tesseract"
    fallback_engine: Literal["tesseract", "paddleocr", "none"] = "paddleocr"
    """Engine order. **This inverts the team spec's assumed ordering**, on
    measured evidence -- see ``reports/ocr_engine_comparison.md``, where both
    engines were run on identical rasters across Arabic and English fixtures at
    two quality levels each.

    Three reasons, in order of weight:

    1. **Arabic accuracy.** Tesseract reads Arabic better on every fixture in
       the corpus, and Arabic is the majority of the firm's material.
    2. **Reliability.** PaddleOCR on this stack (paddleocr 3.7 / paddlepaddle
       3.2 / Windows / CPU) fails non-deterministically: the same image at the
       same resolution succeeded on one run and raised
       ``RuntimeError: Unknown exception`` on the next, and one resolution
       killed the worker process outright. Tesseract had no failures.
    3. **Speed.** Roughly an order of magnitude faster per page.

    PaddleOCR stays wired as the fallback rather than being removed: it is a
    genuinely different architecture, so the pages it fails on are unlikely to
    be the pages Tesseract fails on, and running it out-of-process already makes
    it safe to attempt.

    Reverting is these two lines. Worth re-testing on the firm's own scans --
    rendered pages and scanner output are not the same input, and the engines
    may not degrade at the same rate."""

    paddle_langs: list[str] = Field(default_factory=lambda: ["arabic"])
    """PaddleOCR loads one recognition model per language, so a bilingual page
    means running each and merging by bounding box (see
    :func:`src.ocr_pipeline.run_paddleocr`).

    Defaults to Arabic alone because PaddleOCR's Arabic model
    (``arabic_PP-OCRv5_mobile_rec``) is *multilingual*: it reads Latin script
    in the same pass, and on the interim corpus it recognized English headings
    correctly without the English model present. Adding ``"en"`` is supported
    and roughly doubles page time; measure before enabling it.

    NOTE: on this install the separate English model (PP-OCRv6) crashes with an
    opaque oneDNN error. That failure is caught per-language and does not stop
    the page, but it is why ``"en"`` is not in the default. Re-check on the
    firm's own hardware."""

    paddle_isolate_subprocess: bool = True
    """Run PaddleOCR in a separate process (see :mod:`src.paddle_worker`).

    ON by default because PaddleOCR does not always fail catchably: on this
    stack it terminated the interpreter with a native access violation on some
    scanned pages. In-process, that kills the whole batch and no ``except``
    clause can prevent it -- which would make the Tesseract fallback useless
    precisely when it is most needed.

    A persistent worker is reused across pages, so the ~20-40s model load is
    paid once, not per page. Set False only when debugging PaddleOCR itself,
    where an in-process traceback is more useful than survival."""

    paddle_light_models: bool = False
    """Use PaddleOCR's *mobile* text detector instead of the server one.

    OFF by default on measured evidence, not preference. On the interim corpus
    (synthetic_stamped_page.png, 200 dpi A4, CPU) the mobile detector was a bad
    trade:

        server detector : 25 boxes, 645 chars, mean conf 0.891, 27.2s warm
        mobile detector : 12 boxes, 117 chars, mean conf 0.662, 19.8s warm

    It lost 82% of the text to save 27% of the time. Re-measure on real firm
    scans before enabling -- the balance may differ on cleaner input."""

    tesseract_lang: str = "ara+eng"
    tesseract_cmd: str | None = None
    """Absolute path to tesseract.exe if it is not on PATH."""

    render_dpi: int = 300
    """DPI used to rasterize PDF pages before OCR.

    **300 is a deliberate choice to be robust rather than optimal, and the
    evidence for both halves of that sentence is worth reading before changing
    it.** Two measurements bear on this value and they point in opposite
    directions.

    ``reports/arabic_preprocess_sweep.md`` walked this axis from 75 to 600 dpi
    over the eight Arabic fixtures with verified ground truth, and found **150
    dpi materially better than 300**: CER 0.130 -> 0.095 (27% fewer errors),
    English 0.021 -> 0.013, and 2.8 s/page instead of 3.9. That result is real
    and reproducible.

    ``reports/dpi_probe_300.md`` then asked whether it generalizes, using fresh
    authored fixtures on a true 300 dpi A4 raster at four print sizes. It does
    not. **The optimum moves with print size, and it moves a long way**:

        print size   best rung   CER at 150 dpi   CER at 300 dpi
        7 pt         300 dpi     0.042            0.013     <- 3.2x worse
        9 pt         250 dpi     0.034            0.023
        11 pt        200 dpi     0.014            0.030
        14 pt        175 dpi     0.037            0.035

    At 7 pt -- footnote, schedule and gazette-notice size, which legal documents
    are full of -- 150 dpi costs 0.029 CER, as much as it gains on body text,
    and 100 dpi collapses outright (0.570; the page stops being legible). The
    benchmark corpus is ~11 pt throughout, so it could not have seen this.

    So the default stays where the *downside* is bounded. Small print is the
    case that fails loudly and the case we cannot rule out of the firm's
    archive; body text at 300 dpi merely underperforms slightly. Given a corpus
    we cannot see, that asymmetry decides it.

    **Lower this only for material you have measured.** On a known-uniform body
    text archive, 150 dpi is a 27% accuracy win *and* 30% faster, and it is one
    line. The sweep and the probe both re-run unchanged against
    ``test_corpus/real``.

    The real fix is neither number: choose the render resolution per page from
    the type size actually on it, rather than fixing one DPI for an archive that
    contains both. That is a follow-up, and it should not be guessed at -- see
    ``reports/arabic_preprocess_summary.md``."""

    max_render_side: int = 4000
    """Cap on the longest side of a rasterized page, in pixels.

    Not all legal PDFs are A4 -- oversized court-bundle scans exist, and one
    interim corpus file renders to 6487px at 300 dpi. PaddleOCR rejects
    anything above 4000px and its internal downscale crashed the process
    (native access violation) on this build, so the effective DPI is reduced
    at render time instead. Set 0 to disable the cap."""

    paddle_max_side: int = 1600
    """Longest side, in pixels, of the image handed to **PaddleOCR only**.

    Measured limitation, not a guess. In the engine benchmark PaddleOCR failed
    on 4 of 4 pages probed at the pipeline's 300 dpi render (~3500 px), with
    either ``RuntimeError: Unknown exception`` from native code or a dead worker
    process, and succeeded on the same pages at 1600 px -- on every document
    tested. The failure is resolution-dependent, not content-dependent.

    So rather than paying a ~60 s failure per page and then re-reading it with
    Tesseract, PaddleOCR is simply handed an image inside the range it can
    survive. Tesseract still receives the full-resolution raster, because it has
    no such ceiling and Arabic diacritics are worth the pixels.

    This is a downscale for one engine, not a reduction of ``render_dpi``. Set 0
    to disable it and give PaddleOCR the full-size page -- worth re-testing on
    the firm's hardware, since the ceiling may be specific to this
    Windows/CPU/oneDNN build.

    NOTE: at the shipped ``render_dpi = 300`` an A4 page renders to ~3500 px, so
    this cap engages on essentially every page -- PaddleOCR receives a markedly
    smaller raster than Tesseract does. That is the intended behaviour and the
    reason the cap exists, but it is worth stating plainly rather than assuming
    the two engines see the same image. It stays at 1600 rather than being
    removed because the failure it guards against is resolution-dependent and
    non-deterministic.

    (An earlier revision of this note described a 150 dpi default and a ~1750 px
    render under which the cap "barely engages". That default was shipped and
    then reverted -- see ``render_dpi`` above and ``reports/dpi_probe_300.md``
    -- so the note no longer described the running config.)"""

    preprocess: PreprocessConfig = Field(default_factory=PreprocessConfig)
    """Pre-OCR image preprocessing (see :class:`PreprocessConfig`). Off by
    default on measured evidence -- ``reports/arabic_preprocess_sweep.md``."""

    # --- fallback thresholds ------------------------------------------------
    min_mean_confidence: float = 0.75
    """Page-level mean confidence below which PaddleOCR's result is considered
    unreliable and the fallback engine is tried."""

    min_chars_per_page: int = 40
    """A page yielding fewer characters than this from a *non-blank* image is
    treated as an OCR failure (blank pages are detected separately)."""

    min_recognized_ratio: float = 0.60
    """Fraction of detected text boxes that must survive recognition with
    confidence >= ``drop_below_confidence``. Below this, fall back."""

    drop_below_confidence: float = 0.30
    """Individual boxes below this confidence are dropped from the output but
    still counted in the diagnostics."""

    blank_page_ink_ratio: float = 0.002
    """Fraction of non-white pixels below which a rasterized page is called
    blank, so an empty OCR result is not miscounted as a failure."""

    prefer_higher_confidence_on_fallback: bool = True
    """When both engines produce output, keep whichever has the higher mean
    confidence rather than blindly preferring the fallback."""

    # --- tables on the OCR path ---------------------------------------------
    detect_tables: bool = True
    """Reconstruct tables from OCR geometry (see
    :func:`src.ocr_pipeline.tables_from_atoms`).

    Docling and PyMuPDF own table extraction on the *text* path, but neither
    ever sees an OCR'd page: Docling is only run over the source file on the
    text-layer route, and PyMuPDF's ``find_tables`` reads ruling lines from the
    content stream, which a scan does not have. Without this, every table in
    every scanned document is silently emitted as loose paragraph text -- which
    is exactly what ``synthetic_table_page.png`` did (1 table present, 0 found).

    Docling *can* be pointed at an image, and was measured doing so: it found
    the grid, but took 56 s for one page and returned empty cells for the Arabic
    column, because the OCR engine it bundles has no Arabic model. Reconstructing
    from our own OCR output keeps the Arabic text we already read correctly and
    costs microseconds."""

    table_min_rows: int = 3
    """Consecutive multi-cell lines required before a run is called a table.

    Three, not two, because a two-line run of `label ....... value` pairs is
    common in letterheads and signature blocks and is not a table."""

    table_min_cols: int = 2

    table_cell_gap_factor: float = 1.5
    """A horizontal gap wider than this many median glyph-heights separates two
    cells rather than two words. Scale-free by construction, so it holds at any
    render DPI."""

    table_column_occupancy: float = 0.5
    """Fraction of a run's rows a column must appear in for the run to be
    accepted. Filters ragged prose that happens to have wide inter-word gaps
    (justified Arabic text is full of them) from real grids."""

    table_min_cell_retention: float = 0.8
    """Fraction of a run's cells that must sit in one of its accepted columns.

    The occupancy test alone is not enough. Every line of prose starts at the
    left margin, so that x-position always has 100% occupancy, and a single
    accidental alignment further down the page supplies a second "column" --
    two columns, both passing, from text that is not a table. The tell is that
    most of the words sit in neither."""


class ChunkingConfig(BaseModel):
    """Legal-aware chunking parameters."""

    target_chunk_chars: int = 1200
    """Soft target. Structural units below this are emitted whole."""

    max_chunk_chars: int = 2000
    """Hard cap. A structural unit longer than this is split at paragraph, then
    sentence, then whitespace boundaries."""

    min_chunk_chars: int = 120
    """Fragments shorter than this are merged forward into the next chunk.

    Applies only to text with **no structural identity of its own** -- bare
    headings ("الباب الأول") and stray fragments. A unit that carries a
    clause_id is always emitted, however short: a one-line article is a
    complete article, and merging it away would destroy the clause identity
    that M5 depends on."""

    overlap_chars: int = 150
    """Overlap applied only when a single structural unit had to be split, so
    that no artificial boundary loses context. Chunks that correspond to whole
    clauses get no overlap -- the boundary is real."""

    respect_structure: bool = True
    """When False, degrades to plain paragraph/size chunking (useful as an
    evaluation baseline)."""

    split_by: Literal["clause", "section", "article", "auto"] = "auto"
    """Preferred structural granularity. ``auto`` uses the deepest structural
    level actually detected in the document."""

    keep_tables_whole: bool = True
    """Never split a table across chunks; oversized tables are emitted as their
    own chunk regardless of ``max_chunk_chars``."""

    attach_heading_to_body: bool = True
    """Prepend the governing heading text to each chunk so a retrieved chunk is
    self-describing."""


class ExtractionConfig(BaseModel):
    """Text-layer extraction (PyMuPDF + Docling) configuration."""

    use_docling: bool = True
    """If Docling is unavailable or fails, the pipeline degrades to PyMuPDF-only
    and records the degradation in the engine log rather than erroring."""

    use_pymupdf: bool = True

    docling_timeout_s: int = 180
    """Docling's layout models are slow on long documents; past this we keep the
    PyMuPDF result and log a Docling timeout."""

    docling_max_pages: int = 40
    """Skip Docling entirely on documents longer than this.

    Two reasons, and the first alone would justify it:

    1. **Docling's preprocessing can abort the process.** On a 94-page Egyptian
       statute with oversized pages it raised ``std::bad_alloc`` in native code
       and killed the interpreter. That is not catchable from Python and the
       ``docling_timeout_s`` thread guard cannot help -- the process is gone.
    2. It would not finish anyway. At roughly 5 s/page on CPU, 40 pages is
       already 200 s, past the 180 s budget, so Docling's result would be
       discarded even if it survived.

    Long documents therefore use PyMuPDF-only extraction, which is logged.
    Raise this only if Docling is running on a machine with plenty of RAM and
    ``docling_timeout_s`` is raised to match."""

    docling_max_page_pixels: int = 40_000_000
    """Skip Docling when a page rasterizes above this many pixels.

    Page *area* drives Docling's memory use more than page count. A3 and
    oversized court-bundle scans blow past what A4-tuned defaults assume."""

    text_layer_min_chars_per_page: int = 100
    """Used by type detection: pages with less extractable text than this are
    candidates for the scanned path."""

    min_text_layer_quality: float = 0.50
    """Minimum share of non-space characters that must be letters or digits for
    a text layer to be trusted.

    Guards against PDFs whose embedded fonts have broken or custom encodings:
    the text extracts fine but decodes to mojibake, and the text path then
    produces confident garbage. Below this threshold the page is sent to OCR
    instead. See :func:`src.type_detection.text_layer_quality`.

    Real prose scores 0.75-0.85; mojibake scores well under 0.5. Lower this if
    legitimate documents are being pushed to OCR unnecessarily."""

    repair_visual_order: bool = True
    """Reconstruct a PDF text layer's reading order from glyph geometry when it
    was stored in visual order.

    ON by default on measured evidence -- ``reports/visual_order_arabic_fix.md``.
    The decision is per document and requires two independent criteria to agree
    (see :mod:`src.visual_order`), and the extractor logs the verdict either way,
    so turning this off does not make the pipeline quieter, only less correct.

    Set False to reproduce pre-repair behaviour when comparing outputs. The
    equivalent switch for sources with no glyph geometry -- OCR, DOCX, TXT -- is
    ``RTLConfig.repair_visual_order``."""

    extract_tables: bool = True
    table_mode: Literal["docling", "pymupdf", "both"] = "both"
    """``both`` = take Docling tables when present, fall back to PyMuPDF's
    ``find_tables`` per page otherwise."""


class PipelineConfig(BaseModel):
    """Top-level configuration object threaded through the whole pipeline."""

    extraction: ExtractionConfig = Field(default_factory=ExtractionConfig)
    ocr: OCRConfig = Field(default_factory=OCRConfig)
    rtl: RTLConfig = Field(default_factory=RTLConfig)
    normalization: NormalizationConfig = Field(default_factory=NormalizationConfig)
    chunking: ChunkingConfig = Field(default_factory=ChunkingConfig)

    default_jurisdiction: str | None = "Egypt"
    """Fallback jurisdiction when none can be inferred from the text.
    Set to None to leave it unset rather than guess.

    NOTE: this default reflects the firm's Cairo/Tanta practice, NOT anything
    observed in a real firm document. Revisit once real samples arrive."""

    keep_raw_text_in_metadata: bool = True
    """Store the pre-normalization text on each chunk. Roughly doubles output
    size; invaluable while tuning normalization."""

    log_level: str = "INFO"
    fail_fast: bool = False
    """When False (default), a document that errors is recorded as a failure and
    the batch continues."""

    max_batch_documents: int = 50
    """How many documents to hand :func:`src.pipeline.ingest_batch` in one call.

    **What this actually controls, because the name invites a wrong guess.**
    Nothing in this pipeline processes two documents, two pages, or two models
    at once. ``ingest_batch`` is a sequential loop; ``ocr_pipeline.ocr_pdf_pages``
    renders, reads and discards one page raster before the next; Tesseract is
    CPU-only and PaddleOCR-VL is not wired into the pipeline at all. So this is
    **not** a GPU batch, not a concurrency level, and not an OCR parameter --
    changing it cannot make OCR faster or exhaust VRAM.

    It controls exactly one thing: **how many** ``DocumentIngestResult`` **objects
    accumulate in memory before the call returns**, and therefore how much work
    is lost if the run dies partway. ``ingest_batch`` returns only at the end.

    **Measured, not guessed** -- ``reports/batch_size_probe.md``, harness
    ``scripts/batch_size_probe.py``. Sizes 1, 5, 10, 25 over a mixed OCR+text
    corpus and 1, 10, 25, 50 over a text-layer corpus, each in a fresh process
    with RSS sampled externally over the whole process tree:

        batch   live results held   peak RSS   failures
        1       0.01 MB             1.0-2.0 GB   0
        10      6.6 MB              1.4 GB       0
        25      13.3 MB             1.6-2.1 GB   0
        50      33.0 MB             1.7 GB       0

    Two results decide the value:

    1. **Accumulation is cheap and linear: 54 KB per page**, dead flat across
       10, 25 and 50 (0.054 / 0.053 / 0.054 MB/page). Fifty documents hold ~33 MB.
    2. **Peak RSS does not track batch size.** It is set by the *largest single
       document's* working set -- Docling's layout models and the page raster --
       which is paid identically at batch 1 and batch 50. The mixed-corpus peak
       was in fact *higher* at batch 5 (3.04 GB) than at batch 25 (2.14 GB).

    So RAM does not bind here, and the honest reason for a bound is the second
    one: work at risk. Fifty documents is ~11 min of text-layer material, or
    ~75 min at the corpus's worst-case OCR mix (93 s/doc) -- a tolerable amount
    to redo. Retention would only approach even a conservative 10%-of-free-RAM
    line (~230 MB against the 2.3 GB free measured on this shared box while the
    LLM work packages run) at roughly **190 documents**, so 50 sits ~4x inside
    that with 97% headroom, and every size tested had **zero failures** and
    linear-to-improving wall clock (22.5 s/doc at 1 -> 12.8 s/doc at 50, as the
    one-time model load amortizes).

    **This is advisory: no code enforces it.** ``ingest_batch`` accepts any list
    length, and capping it inside would change that function's return contract,
    which is deliberately out of scope here. Callers chunking a large corpus
    should read this value; ``GET /config`` already exposes it.

    Raise it if the corpus is text-layer-only and a longer redo is acceptable --
    50 is nowhere near a measured ceiling. Lower it if documents are being
    ingested from a slow or flaky source where losing a batch is expensive.
    Re-run the probe on the firm's hardware before assuming either: it is one
    command and it prints the table above."""

    @classmethod
    def from_env(cls, prefix: str = "M1_") -> "PipelineConfig":
        """Build a config from ``M1_``-prefixed env vars.

        Nested fields use a double underscore, e.g.::

            M1_OCR__MIN_MEAN_CONFIDENCE=0.6
            M1_NORMALIZATION__NORMALIZE_TEH_MARBUTA=true
            M1_CHUNKING__TARGET_CHUNK_CHARS=800
        """
        data: dict = {}
        for key, raw in os.environ.items():
            if not key.startswith(prefix):
                continue
            path = key[len(prefix):].lower().split("__")
            cursor = data
            for part in path[:-1]:
                cursor = cursor.setdefault(part, {})
            cursor[path[-1]] = _coerce(raw)
        return cls(**data)

    @classmethod
    def from_json(cls, path: str | Path) -> "PipelineConfig":
        return cls(**json.loads(Path(path).read_text(encoding="utf-8")))


def _coerce(raw: str):
    low = raw.strip().lower()
    if low in {"true", "yes", "1", "on"}:
        return True
    if low in {"false", "no", "0", "off"}:
        return False
    for caster in (int, float):
        try:
            return caster(raw)
        except ValueError:
            pass
    if raw.startswith(("[", "{")):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
    return raw


DEFAULT_CONFIG = PipelineConfig()
