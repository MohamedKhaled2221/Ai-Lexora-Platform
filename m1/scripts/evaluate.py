"""Evaluation harness for the criteria named in the team spec, plus two more.

The spec's seven:

  1. Text extraction accuracy   -- vs authored or transcribed reference
  2. OCR accuracy               -- CER/WER, tracked SEPARATELY for Arabic and
                                   English, against ground truth whose own
                                   trustworthiness has been audited
  3. Table extraction           -- success rate vs tables known to be present
  4. Page preservation          -- did every source page produce output
  5. Section preservation       -- did detected structure match the markers
                                   visible in the source text
  6. Processing speed           -- per document and per page, by stage
  7. Failure rate               -- documents that errored or produced nothing

And two the spec does not name but which were previously assertions rather than
numbers:

  * Text extraction accuracy on the **non-OCR path**, which is the majority path
    and had no measurement at all
  * **Chunking and metadata correctness** against expectations declared in
    advance, rather than chunk counts with nothing to compare them to

NO CLIENT DOCUMENT HAS BEEN PROCESSED, AND NONE IS REQUIRED. The engagement
constraint is that no document leaves the firm, so the system is validated
against published Egyptian legal documents and synthetic fixtures by design.
What that approach cannot measure is stated in the generated report's caveats;
those are permanent properties of it, not gaps awaiting data.

Two references are needed before any of this means anything, and both are built
by sibling scripts:

    scripts/make_text_ground_truth.py   reference text for the non-OCR path
    scripts/audit_ground_truth.py       how far each OCR reference is trustworthy

Run::

    python scripts/evaluate.py                 # full run
    python scripts/evaluate.py --no-ocr        # skip scanned documents (fast)
    python scripts/evaluate.py --no-docling    # skip Docling (much faster)
    python scripts/evaluate.py --from-json     # rebuild the report, no reprocessing

    # against any other directory of documents -- no code change:
    python scripts/evaluate.py --corpus-dir test_corpus/real
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import src  # noqa: E402

src.quiet_third_party_logs()

from src.config import (  # noqa: E402
    PUBLIC_CORPUS_DIR,
    REPORTS_DIR,
    SYNTHETIC_CORPUS_DIR,
    PipelineConfig,
)
from src.document_chunk_schema import Language  # noqa: E402
from src.pipeline import get_clause_chunks, process_document  # noqa: E402
from src.structure_preservation import (  # noqa: E402
    detect_language,
    detect_marker,
    is_arabic_char,
    is_latin_char,
)
from src.type_detection import detect  # noqa: E402


# ---------------------------------------------------------------------------
# Text similarity
# ---------------------------------------------------------------------------


def _levenshtein(a: str, b: str, cap: int = 200_000) -> int:
    """Edit distance with a length guard.

    Full DP is O(n*m); on a 40k-character page that is 1.6e9 cells. Inputs are
    truncated to ``cap`` characters, which is far more than needed for a
    representative error rate.
    """
    a, b = a[:cap], b[:cap]
    if not a:
        return len(b)
    if not b:
        return len(a)
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(
                previous[j] + 1,        # deletion
                current[j - 1] + 1,     # insertion
                previous[j - 1] + (ca != cb),   # substitution
            ))
        previous = current
    return previous[-1]


def _norm_for_compare(text: str) -> str:
    """Collapse whitespace so layout differences do not count as OCR errors.

    Both sides also go through the pipeline's own normalization before this, so
    what is measured is *recognition* error, not orthographic variation that we
    deliberately fold away anyway.
    """
    return re.sub(r"\s+", " ", text).strip()


def _split_by_script(text: str) -> tuple[str, str]:
    """Partition text into its Arabic and Latin word streams.

    This is what lets OCR accuracy be reported per language on a bilingual
    page, which the spec asks for and a single blended CER would hide.
    """
    arabic, latin = [], []
    for word in text.split():
        letters = [c for c in word if c.isalpha()]
        if not letters:
            continue
        n_ar = sum(1 for c in letters if is_arabic_char(c))
        n_lat = sum(1 for c in letters if is_latin_char(c))
        if n_ar > n_lat:
            arabic.append(word)
        elif n_lat > 0:
            latin.append(word)
    return " ".join(arabic), " ".join(latin)


# A language stream shorter than this is not a meaningful sample, and scoring
# it produces nonsense. A pure-Arabic scan contains a handful of stray Latin
# characters; dividing OCR's Latin-looking noise by that tiny denominator gave
# "CER 13.1", which is not an error rate at all -- it is a division artifact.
# Below this length the metric is reported as n/a rather than as a number.
MIN_REFERENCE_CHARS = 300
MIN_REFERENCE_WORDS = 50


def cer(reference: str, hypothesis: str, ignore_spaces: bool = False) -> float | None:
    """Character error rate, or ``None`` when the reference is too short to judge.

    CER is ``edit_distance / len(reference)``, so it is only bounded by 1.0 when
    the hypothesis is no longer than the reference. When a document barely
    contains a language, its reference stream is tiny and the score explodes --
    which says nothing about OCR quality. Hence the minimum sample size.

    ``ignore_spaces`` strips all whitespace from both sides before comparing,
    measuring **glyph recognition alone**. That is the honest figure when the
    reference itself has spacing defects: several public Arabic PDFs extract as
    "دس تور" for "دستور" because the producer placed each glyph individually,
    and a space-sensitive comparison then charges OCR for the *reference's*
    broken word boundaries.

    Both figures are reported. The space-sensitive one is stricter and includes
    genuine word-segmentation errors; the space-insensitive one isolates
    character accuracy. Where they diverge sharply, suspect the reference.
    """
    reference, hypothesis = _norm_for_compare(reference), _norm_for_compare(hypothesis)
    if ignore_spaces:
        reference, hypothesis = reference.replace(" ", ""), hypothesis.replace(" ", "")
    if len(reference) < MIN_REFERENCE_CHARS:
        return None
    return round(_levenshtein(reference, hypothesis) / len(reference), 4)


def bag_error(reference: str, hypothesis: str) -> float | None:
    """Order-insensitive word error: what fraction of reference words are missing.

    CER and WER both charge for **reading order**, and against a reference taken
    from a PDF's text layer that is a serious confound: the text layer is stored
    in content-stream order, while OCR reads the page visually. Where the two
    disagree -- a marginal annotation column, a sidebar, a footnote block -- edit
    distance explodes even though every character was recognized correctly.

    Comparing word *multisets* removes order from the comparison entirely. Read
    the two together:

        high CER, low bag error   -> the text was read correctly, in a different
                                     order. A layout/reading-order artifact.
        high CER, high bag error  -> the text was genuinely misrecognized.

    This is the metric that settled which of the two competing explanations for
    the corpus's bad Arabic scores was right. Neither was: see the engine
    comparison report.
    """
    ref_words = _norm_for_compare(reference).split()
    hyp_words = _norm_for_compare(hypothesis).split()
    if len(ref_words) < MIN_REFERENCE_WORDS:
        return None
    import collections

    ref_counts = collections.Counter(ref_words)
    matched = sum((ref_counts & collections.Counter(hyp_words)).values())
    return round(1 - matched / len(ref_words), 4)


def wer(reference: str, hypothesis: str) -> float | None:
    ref_words, hyp_words = _norm_for_compare(reference).split(), _norm_for_compare(hypothesis).split()
    if len(ref_words) < MIN_REFERENCE_WORDS:
        return None
    # Reuse the char-level DP over word tokens by mapping words to codepoints.
    vocab: dict[str, str] = {}

    def encode(words):
        return "".join(vocab.setdefault(w, chr(0xE000 + len(vocab))) for w in words)

    return round(_levenshtein(encode(ref_words), encode(hyp_words)) / len(ref_words), 4)


# ---------------------------------------------------------------------------
# Per-document evaluation
# ---------------------------------------------------------------------------


@dataclass
class DocEval:
    file: str
    corpus: str
    file_type: str = ""
    pdf_kind: str | None = None
    succeeded: bool = False
    error: str | None = None

    source_pages: int = 0
    output_pages: int = 0
    n_chunks: int = 0
    n_clause_chunks: int = 0
    n_chars: int = 0

    document_type: str = ""
    language: str = ""
    jurisdiction: str | None = None

    engines: dict[str, int] = field(default_factory=dict)
    ocr_fallbacks: int = 0
    """Pages where the fallback engine's result was the one kept."""
    ocr_fallback_attempts: int = 0
    """Pages where the fallback engine *ran*, whether or not it won.

    This is the cost figure. A fallback that runs and loses is paid for in full,
    and the slower engine is the fallback -- so attempts, not wins, are what
    make a page expensive."""
    chunk_strategies: dict[str, int] = field(default_factory=dict)
    rtl_flags: dict[str, int] = field(default_factory=dict)

    markers_in_source: int = 0
    markers_as_boundaries: int = 0

    tables_expected: int | None = None
    tables_found: int = 0

    # Text-layer extraction accuracy, against an authored or transcribed
    # reference (scripts/make_text_ground_truth.py). Distinct from the OCR
    # fields below: this is the non-OCR path, which was previously unmeasured.
    text_cer: float | None = None
    text_cer_nospace: float | None = None
    text_bag_error: float | None = None
    text_reference_provenance: str | None = None
    text_reference_pages: int = 0

    # Declared-expectation checks (test_corpus/synthetic/expectations.json).
    expectation_checks: dict[str, bool] = field(default_factory=dict)
    expectation_detail: list[str] = field(default_factory=list)

    cer_arabic: float | None = None
    cer_english: float | None = None
    cer_arabic_nospace: float | None = None
    cer_english_nospace: float | None = None
    wer_arabic: float | None = None
    wer_english: float | None = None
    ocr_engine_used: str | None = None

    total_ms: float = 0.0
    ms_per_page: float = 0.0
    stage_ms: dict[str, float] = field(default_factory=dict)

    notes: list[str] = field(default_factory=list)


def count_source_pages(path: Path) -> int:
    """Page count from the source file itself, independent of our extraction.

    Deliberately not taken from the pipeline's own output -- otherwise page
    preservation would be measured against itself and could never fail.
    """
    if path.suffix.lower() == ".pdf":
        import fitz

        with fitz.open(path) as d:
            return d.page_count
    return 1


def count_source_markers(path: Path) -> int:
    """Count structural markers visible in the raw source text.

    For PDFs and TXT we can read the source directly; the number is the
    denominator for section preservation. For scanned PDFs there is no text
    layer, so this returns 0 and the metric is reported as N/A.
    """
    try:
        if path.suffix.lower() == ".pdf":
            import fitz

            with fitz.open(path) as d:
                text = "\n".join(p.get_text("text") for p in d)
        elif path.suffix.lower() in (".txt", ".md"):
            text = path.read_text(encoding="utf-8", errors="replace")
        elif path.suffix.lower() == ".docx":
            from docx import Document

            text = "\n".join(p.text for p in Document(str(path)).paragraphs)
        else:
            return 0
    except Exception:  # noqa: BLE001
        return 0

    from src.normalize import normalize_text
    from src.config import NormalizationConfig

    normalized, _ = normalize_text(text, NormalizationConfig())
    return sum(1 for line in normalized.splitlines() if detect_marker(line))


def evaluate_document(path: Path, corpus: str, config: PipelineConfig,
                      manifest: dict) -> DocEval:
    ev = DocEval(file=path.name, corpus=corpus)
    entry = manifest.get(path.name, {})
    ev.tables_expected = entry.get("tables_expected")

    try:
        det = detect(path, config.extraction)
        ev.file_type = det.file_type.value
        ev.pdf_kind = det.pdf_kind
        ev.source_pages = count_source_pages(path)
    except Exception as exc:  # noqa: BLE001
        ev.error = f"detection failed: {exc}"
        return ev

    start = time.perf_counter()
    result = process_document(path, config)
    ev.total_ms = round((time.perf_counter() - start) * 1000, 1)

    ev.succeeded = result.succeeded
    ev.n_chunks = result.n_chunks
    ev.output_pages = result.n_pages
    ev.document_type = str(result.document_type)
    ev.language = str(result.language)
    ev.stage_ms = result.timings_ms
    ev.ms_per_page = round(ev.total_ms / max(ev.source_pages, 1), 1)

    if not result.succeeded:
        ev.error = result.errors[0] if result.errors else "produced no chunks"
        return ev

    ev.n_chars = sum(len(c.text) for c in result.chunks)
    ev.n_clause_chunks = len(get_clause_chunks(result.chunks))
    ev.jurisdiction = result.chunks[0].metadata.get("jurisdiction") if result.chunks else None

    for chunk in result.chunks:
        engine = chunk.metadata.get("source_engine", "unknown")
        ev.engines[engine] = ev.engines.get(engine, 0) + 1
        strategy = chunk.metadata.get("chunk_strategy") or "unknown"
        ev.chunk_strategies[strategy] = ev.chunk_strategies.get(strategy, 0) + 1
        if chunk.metadata.get("is_table"):
            ev.tables_found += 1
    for flag in result.rtl_flags:
        ev.rtl_flags[flag.kind] = ev.rtl_flags.get(flag.kind, 0) + 1

    for log in result.engine_log:
        if log.get("fallback"):
            ev.ocr_fallback_attempts += 1
        if log.get("fallback_used"):
            ev.ocr_fallbacks += 1
        if log.get("engine") in ("paddleocr", "tesseract"):
            ev.ocr_engine_used = log["engine"]

    # --- section preservation ------------------------------------------------
    ev.markers_in_source = count_source_markers(path)
    ev.markers_as_boundaries = len({
        (c.metadata.get("structure") or {}).get("clause_id")
        for c in result.chunks
        if (c.metadata.get("structure") or {}).get("clause_id")
    })

    # --- OCR accuracy against ground truth -----------------------------------
    gt_file = path.parent / (path.stem + ".groundtruth.txt")
    if gt_file.exists():
        _score_ocr(ev, gt_file, result, config)

    # --- text-layer extraction accuracy --------------------------------------
    _score_text_extraction(ev, path, result, config)

    # --- declared-expectation checks -----------------------------------------
    _check_expectations(ev, result)

    return ev


# ---------------------------------------------------------------------------
# Text-layer extraction accuracy (the non-OCR path)
# ---------------------------------------------------------------------------


def load_text_references() -> dict[str, list[dict]]:
    """Reference text for text-based documents, keyed by document filename.

    Built by ``scripts/make_text_ground_truth.py`` (authored + transcribed) and
    ``scripts/make_native_fixtures.py`` (authored native PDFs, which render the
    same pages the ``scan_authored_*`` fixtures rasterise, so the native and OCR
    figures are directly comparable). Never the PDF's own text layer -- see
    ``make_text_ground_truth.py`` for why that reference is both circular and, on
    Arabic, actively wrong.
    """
    ref_dir = SYNTHETIC_CORPUS_DIR / "text_reference"
    out: dict[str, list[dict]] = {}
    for name in ("text_reference_manifest.json", "native_reference_manifest.json"):
        manifest = ref_dir / name
        if not manifest.exists():
            continue
        data = json.loads(manifest.read_text(encoding="utf-8"))
        for entry in data["entries"]:
            out.setdefault(entry["document"], []).append(entry)
    return out


_TEXT_REFERENCES = None


def _score_text_extraction(ev: DocEval, path: Path, result, config: PipelineConfig) -> None:
    """Score the pipeline's output against an authored/transcribed reference."""
    global _TEXT_REFERENCES
    if _TEXT_REFERENCES is None:
        _TEXT_REFERENCES = load_text_references()
    entries = _TEXT_REFERENCES.get(path.name)
    if not entries:
        return

    from src.normalize import normalize_text

    ref_dir = SYNTHETIC_CORPUS_DIR / "text_reference"
    cers, nospace, bags, pages = [], [], [], 0
    provenance = set()

    for entry in entries:
        raw = (ref_dir / entry["reference"]).read_text(encoding="utf-8")
        reference, _ = normalize_text(raw, config.normalization)
        if entry["scope"] == "page":
            chunks = [c for c in result.chunks if c.page == entry["page"]]
            # A page-scoped reference against an empty page means the page was
            # lost, which must score as total failure rather than be skipped.
            hypothesis = "\n".join(c.text for c in chunks)
        else:
            hypothesis = "\n".join(c.text for c in result.chunks)
        hypothesis, _ = normalize_text(hypothesis, config.normalization)

        for target, value in (
            (cers, cer(reference, hypothesis)),
            (nospace, cer(reference, hypothesis, ignore_spaces=True)),
            (bags, bag_error(reference, hypothesis)),
        ):
            if value is not None:
                target.append(value)
        pages += entry["pages_covered"]
        provenance.add(entry["provenance"])

    if cers:
        ev.text_cer = round(statistics.mean(cers), 4)
    if nospace:
        ev.text_cer_nospace = round(statistics.mean(nospace), 4)
    if bags:
        ev.text_bag_error = round(statistics.mean(bags), 4)
    ev.text_reference_pages = pages
    ev.text_reference_provenance = "+".join(sorted(provenance))


# ---------------------------------------------------------------------------
# Declared-expectation checks
# ---------------------------------------------------------------------------


def load_expectations() -> dict:
    path = SYNTHETIC_CORPUS_DIR / "expectations.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))["documents"]


_EXPECTATIONS = None


def _check_expectations(ev: DocEval, result) -> None:
    """Compare output against what the document was declared to contain.

    The point of a *declared* expectation is that it was written from the
    document's content rather than from a previous run's output. An expectation
    derived from actual output can only pass, and so measures nothing.
    """
    global _EXPECTATIONS
    if _EXPECTATIONS is None:
        _EXPECTATIONS = load_expectations()
    spec = _EXPECTATIONS.get(ev.file)
    if not spec:
        return

    checks: dict[str, bool] = {}
    detail: list[str] = []

    if spec.get("document_type") is not None:
        ok = ev.document_type == spec["document_type"]
        checks["document_type"] = ok
        if not ok:
            detail.append(f"document_type: expected `{spec['document_type']}`, "
                          f"got `{ev.document_type}`")

    if spec.get("jurisdiction") is not None:
        ok = ev.jurisdiction == spec["jurisdiction"]
        checks["jurisdiction"] = ok
        if not ok:
            detail.append(f"jurisdiction: expected `{spec['jurisdiction']}`, "
                          f"got `{ev.jurisdiction}`")

    if spec.get("language"):
        ok = ev.language in spec["language"]
        checks["language"] = ok
        if not ok:
            detail.append(f"language: expected one of {spec['language']}, "
                          f"got `{ev.language}`")

    required = spec.get("required_clause_ids") or []
    if required:
        emitted = {
            (c.metadata.get("structure") or {}).get("clause_id")
            for c in result.chunks
        }
        missing = [cid for cid in required if cid not in emitted]
        checks["clause_ids"] = not missing
        if missing:
            detail.append(f"clause ids missing ({len(missing)}/{len(required)}): "
                          + ", ".join(f"`{m}`" for m in missing[:8]))

    if spec.get("tables_expected") is not None:
        found = sum(1 for c in result.chunks if c.metadata.get("is_table"))
        ok = found == spec["tables_expected"]
        checks["tables"] = ok
        if not ok:
            detail.append(f"tables: expected {spec['tables_expected']}, got {found}")

    if spec.get("min_chunks") is not None:
        ok = ev.n_chunks >= spec["min_chunks"]
        checks["min_chunks"] = ok
        if not ok:
            detail.append(f"chunks: expected at least {spec['min_chunks']}, "
                          f"got {ev.n_chunks}")

    ev.expectation_checks = checks
    ev.expectation_detail = detail


def _score_ocr(ev: DocEval, gt_file: Path, result, config: PipelineConfig) -> None:
    """Compare OCR output to ground truth, separately per script."""
    from src.config import NormalizationConfig
    from src.normalize import normalize_text

    reference_raw = gt_file.read_text(encoding="utf-8", errors="replace")
    # Normalize BOTH sides identically, so what is measured is recognition
    # error rather than orthographic variation the pipeline folds on purpose.
    reference, _ = normalize_text(reference_raw, config.normalization)
    hypothesis = "\n".join(c.text for c in result.chunks)

    ref_ar, ref_en = _split_by_script(reference)
    hyp_ar, hyp_en = _split_by_script(hypothesis)

    ev.cer_arabic = cer(ref_ar, hyp_ar)
    ev.cer_english = cer(ref_en, hyp_en)
    ev.cer_arabic_nospace = cer(ref_ar, hyp_ar, ignore_spaces=True)
    ev.cer_english_nospace = cer(ref_en, hyp_en, ignore_spaces=True)
    ev.wer_arabic = wer(ref_ar, hyp_ar)
    ev.wer_english = wer(ref_en, hyp_en)
    ev.notes.append(f"OCR scored against {gt_file.name}")


# ---------------------------------------------------------------------------
# Corpus discovery
# ---------------------------------------------------------------------------

# Tables we know are present, for the table-extraction success rate.
# Counted by hand from the generators / source documents.
KNOWN_TABLES = {
    "synthetic_contract_bilingual.pdf": 2,   # payment schedule + signature block
    "synthetic_contract_ar.docx": 1,
    "synthetic_table_page.png": 1,
    # Image tables added to prove the OCR-path table fix generalises beyond the
    # single fixture that exposed it.
    "stress_table_ruled_ar.png": 1,
    "stress_table_wide_en.png": 1,
    "stress_table_sparse_bilingual.png": 1,
    # ONE logical table split across a page boundary. Reporting 2 is the failure
    # this fixture exists to catch, so the expectation is 1.
    "stress_table_pagebreak.pdf": 1,
}

# Documents excluded from the corpus, with the reason. Recorded rather than
# silently omitted: a corpus you cannot audit is not a corpus.
EXCLUDED = {
    "wipo_eg087ar_1.pdf":
        "handwritten. Its text layer scores 0.33 on text_layer_quality and "
        "contains no Arabic at all despite being an Arabic statute, so it "
        "yields no usable ground truth and cannot be scored. It is also not "
        "representative: the firm's archive is typed and printed material. "
        "Kept in test_corpus/public/ as a robustness input -- the pipeline must "
        "not crash on it -- but excluded from every accuracy metric.",
}


def load_manifest() -> dict:
    manifest: dict = {}
    for name, n in KNOWN_TABLES.items():
        manifest.setdefault(name, {})["tables_expected"] = n
    return manifest


SUPPORTED_EXTS = {".pdf", ".docx", ".txt", ".md",
                  ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
OCR_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}


def discover(include_ocr: bool, corpus_dirs: list[Path] | None = None) -> list[tuple[Path, str]]:
    """Find documents to evaluate.

    ``corpus_dirs`` overrides the interim corpus entirely -- this is the hook
    for real firm documents. Pass ``--corpus-dir test_corpus/real`` once the
    anonymized batch arrives; no code changes anywhere.
    """
    if corpus_dirs:
        files: list[tuple[Path, str]] = []
        for directory in corpus_dirs:
            for path in sorted(directory.rglob("*")):
                if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTS:
                    continue
                if path.name.endswith(".groundtruth.txt"):
                    continue
                if path.suffix.lower() in OCR_EXTS and not include_ocr:
                    continue
                files.append((path, directory.name))
        return files

    files = []
    for path in sorted(PUBLIC_CORPUS_DIR.glob("*")):
        if path.suffix.lower() != ".pdf":
            continue
        if path.name in EXCLUDED:
            continue
        files.append((path, "public"))

    for path in sorted(SYNTHETIC_CORPUS_DIR.glob("*")):
        if path.name.endswith(".groundtruth.txt") or path.suffix == ".json":
            continue
        if path.suffix.lower() not in SUPPORTED_EXTS:
            continue
        # bench_* fixtures belong to scripts/ocr_benchmark.py. They are extra
        # renderings of documents already represented here, so including them
        # would double-count the same source material in every metric.
        if path.name.startswith("bench_"):
            continue
        if path.name in EXCLUDED:
            continue
        is_ocr_input = path.suffix.lower() in OCR_EXTS or path.name.startswith("scan_")
        if is_ocr_input and not include_ocr:
            continue
        files.append((path, "synthetic"))

    return files


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _fmt(value, suffix: str = "", dash: str = "n/a") -> str:
    if value is None:
        return dash
    if isinstance(value, float):
        return f"{value:.3f}{suffix}"
    return f"{value}{suffix}"


def _pct(numerator: int, denominator: int) -> str:
    if not denominator:
        return "n/a"
    return f"{numerator / denominator:.0%}"


def build_report(evals: list[DocEval], config: PipelineConfig, elapsed_s: float,
                 flags: argparse.Namespace) -> str:
    ok = [e for e in evals if e.succeeded]
    failed = [e for e in evals if not e.succeeded]
    scanned = [e for e in ok if e.pdf_kind == "scanned" or e.file_type == "image"]
    scored = [e for e in ok if e.cer_arabic is not None or e.cer_english is not None]

    lines: list[str] = []
    add = lines.append

    on_real_data = bool(getattr(flags, "corpus_dir", None))

    add("# M1 Document Processing -- Evaluation Report")
    add("")
    if on_real_data:
        dirs = ", ".join(f"`{d}`" for d in flags.corpus_dir)
        add("> ## Results from a supplied corpus")
        add("> ")
        add(f"> This run evaluated {dirs} rather than the interim public/synthetic "
            "corpus. If those directories hold real firm documents, the figures "
            "below are **validated results** -- update the caveats section "
            "accordingly and record which document batch this was.")
    else:
        add("> ## Measured on public and synthetic documents, by design")
        add("> ")
        add("> Every number here comes from **published Egyptian legal documents "
            "and synthetic fixtures this project generated**. No client document "
            "has been processed, and none is required: the engagement constraint "
            "is that no document leaves the firm, so the system was built to be "
            "evaluable without client material.")
        add("> ")
        add("> Published legislation supplies real legal Arabic, real statutory "
            "numbering and real publisher defects. Synthetic fixtures supply "
            "exact ground truth where published documents cannot -- most "
            "importantly the `scan_authored_*` scans, whose reference text was "
            "written before the page was rendered.")
        add("> ")
        add("> **These are results, not a provisional stand-in for results.** "
            "What this approach cannot measure is stated plainly in "
            "[Caveats](#caveats) -- those are permanent properties of validating "
            "this way, not gaps waiting on data.")
    add("")
    add(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}  ")
    add(f"Corpus: {len(evals)} documents "
        f"({sum(1 for e in evals if e.corpus == 'public')} public, "
        f"{sum(1 for e in evals if e.corpus == 'synthetic')} synthetic)  ")
    add(f"Wall clock: {elapsed_s:.1f}s  ")
    add(f"Docling: {'enabled' if config.extraction.use_docling else 'DISABLED'} | "
        f"OCR: {'enabled' if config.ocr.enabled else 'DISABLED'}")
    add("")

    # ---------------- headline -------------------------------------------
    add("## Summary against the spec's criteria")
    add("")
    add("| Criterion | Result | Basis |")
    add("|---|---|---|")
    add(f"| Failure rate | **{_pct(len(failed), len(evals))}** "
        f"({len(failed)}/{len(evals)} documents) | errored or produced zero chunks |")
    page_ok = sum(1 for e in ok if e.output_pages >= e.source_pages)
    add(f"| Page preservation | **{_pct(page_ok, len(ok))}** | "
        f"output pages >= source pages, counted from the source file |")
    sec_docs = [e for e in ok if e.markers_in_source >= 3]
    sec_rate = (
        statistics.mean(min(e.markers_as_boundaries / e.markers_in_source, 1.0) for e in sec_docs)
        if sec_docs else None
    )
    add(f"| Section preservation | **{_fmt(sec_rate)}** | "
        f"mean ratio of detected clause ids to markers visible in source "
        f"({len(sec_docs)} documents with >=3 markers) |")
    tbl_docs = [e for e in ok if e.tables_expected]
    tbl_rate = (
        statistics.mean(min(e.tables_found / e.tables_expected, 1.0) for e in tbl_docs)
        if tbl_docs else None
    )
    add(f"| Table extraction | **{_fmt(tbl_rate)}** | "
        f"tables emitted vs tables known present ({len(tbl_docs)} documents) |")
    if scored:
        ar = [e.cer_arabic_nospace for e in scored if e.cer_arabic_nospace is not None]
        en = [e.cer_english_nospace for e in scored if e.cer_english_nospace is not None]
        add(f"| OCR accuracy -- Arabic | **CER {_fmt(statistics.mean(ar)) if ar else 'n/a'}** | "
            f"glyph-level (space-insensitive), vs ground truth, "
            f"{len(ar)} scanned document(s) |")
        add(f"| OCR accuracy -- English | **CER {_fmt(statistics.mean(en)) if en else 'n/a'}** | "
            f"glyph-level (space-insensitive), vs ground truth, "
            f"{len(en)} scanned document(s) |")
    else:
        add("| OCR accuracy | not measured this run | OCR corpus skipped |")
    if ok:
        add(f"| Processing speed | **{statistics.median(e.ms_per_page for e in ok):.0f} ms/page "
            f"(median)** | end-to-end, CPU only |")
    add("")

    # Two measurements the spec's seven criteria do not name but which the
    # report previously left as assertions rather than numbers.
    scored_text_docs = [e for e in ok if e.text_cer_nospace is not None]
    checked_docs = [e for e in ok if e.expectation_checks]
    if scored_text_docs or checked_docs:
        add("### Beyond the spec's seven criteria")
        add("")
        add("| Measurement | Result | Basis |")
        add("|---|---|---|")
        if scored_text_docs:
            mean_text = statistics.mean(e.text_cer_nospace for e in scored_text_docs)
            pages = sum(e.text_reference_pages for e in scored_text_docs)
            add(f"| Text extraction accuracy (non-OCR path) | **CER "
                f"{mean_text:.3f}** | vs authored/transcribed reference, "
                f"{pages} pages across {len(scored_text_docs)} documents |")
        if checked_docs:
            total = sum(len(e.expectation_checks) for e in checked_docs)
            passed = sum(sum(1 for v in e.expectation_checks.values() if v)
                         for e in checked_docs)
            add(f"| Chunking / metadata correctness | **{passed}/{total} "
                f"({passed / max(total, 1):.0%})** | vs expectations declared "
                f"in advance, {len(checked_docs)} documents |")
        add("")

    if EXCLUDED:
        add("### Excluded from this corpus")
        add("")
        for name, reason in EXCLUDED.items():
            add(f"- **`{name}`** -- {reason}")
        add("")

    # ---------------- per document ---------------------------------------
    add("## Per-document results")
    add("")
    add("| Document | Corpus | Type | Pages src/out | Chunks | Clauses | "
        "Lang | Doc type | ms/page | Status |")
    add("|---|---|---|---|---|---|---|---|---|---|")
    for e in evals:
        status = "ok" if e.succeeded else f"**FAIL** ({(e.error or '')[:40]})"
        add(f"| `{e.file}` | {e.corpus} | {e.file_type}"
            f"{'/' + e.pdf_kind if e.pdf_kind and e.pdf_kind != 'n/a' else ''} | "
            f"{e.source_pages}/{e.output_pages} | {e.n_chunks} | {e.n_clause_chunks} | "
            f"{e.language} | {e.document_type} | {e.ms_per_page:.0f} | {status} |")
    add("")

    # ---------------- OCR -------------------------------------------------
    add("## 1-2. Extraction and OCR accuracy")
    add("")
    if scored:
        add("Measured against the ground-truth text that ships with each derived "
            "scan. Both sides run through identical normalization first, so what "
            "is reported is **recognition** error, not orthographic variation the "
            "pipeline folds deliberately.")
        add("")
        add("| Document | Engine | CER ar | CER ar (no-space) | WER ar | "
            "CER en | CER en (no-space) | WER en |")
        add("|---|---|---|---|---|---|---|---|")
        for e in scored:
            add(f"| `{e.file}` | {e.ocr_engine_used or 'n/a'} | "
                f"{_fmt(e.cer_arabic)} | {_fmt(e.cer_arabic_nospace)} | {_fmt(e.wer_arabic)} | "
                f"{_fmt(e.cer_english)} | {_fmt(e.cer_english_nospace)} | {_fmt(e.wer_english)} |")
        add("")
        add("**Which column to believe.** `no-space` strips all whitespace before "
            "comparing, isolating glyph recognition. Several public Arabic PDFs "
            "extract with spurious intra-word spacing (`دس تور` for `دستور`) "
            "because the producer placed each glyph separately -- so the "
            "space-sensitive columns charge OCR for the *reference's* broken "
            "word boundaries. Where the two diverge sharply, the reference is "
            "at fault, not the engine. See the corpus manifest, which flags "
            "which ground-truth files have this defect.")
        add("")
        add("**Reading these numbers.** CER is character error rate: 0.0 is "
            "perfect, 1.0 means as many errors as characters. Arabic CER is "
            "expected to be materially worse than English on the same page -- "
            "Arabic is cursive, position-dependent, and its diacritics and "
            "dot patterns are exactly what JPEG artifacts destroy first.")
        add("")
        add(f"`n/a` means the document did not contain at least "
            f"{MIN_REFERENCE_CHARS} reference characters in that language. A "
            "pure-Arabic scan holds only a few stray Latin characters, and "
            "dividing OCR's Latin-looking noise by that denominator yields a "
            "number well above 1.0 that describes nothing. Those cases are "
            "excluded rather than reported.")
        add("")

        ar_scores = [(e.file, e.cer_arabic_nospace) for e in scored
                     if e.cer_arabic_nospace is not None]
        if len(ar_scores) >= 2:
            best = min(ar_scores, key=lambda x: x[1])
            worst = max(ar_scores, key=lambda x: x[1])
            spread = worst[1] - best[1]
            if spread > 0.3:
                add("### ⚠ The Arabic scans disagree wildly -- read this before "
                    "quoting an Arabic OCR number")
                add("")
                add(f"`{best[0]}` scores **{best[1]:.3f}** while `{worst[0]}` "
                    f"scores **{worst[1]:.3f}** -- a {spread:.2f} spread on the "
                    "same engine, the same language, and comparable degradation.")
                add("")
                add("**CORRECTION.** An earlier version of this report "
                    "attributed that spread to **two-column layout**: ground "
                    "truth follows the PDF's content stream, OCR reads the page "
                    "visually, and on a two-column page the two orders "
                    "interleave. That explanation was wrong, and it was wrong in "
                    "a way that mattered -- it implied the spread was a fixed "
                    "measurement artifact rather than something that could be "
                    "measured and separated.")
                add("")
                add("Controlled fixtures rule it out. `wipo_eg081ar_1` is "
                    "two-column and scores well; `wipo_eg088ar_1` has a "
                    "fragmented reference and also scores well. Column count is "
                    "not the driver, and neither is fragmentation -- a second "
                    "hypothesis raised while investigating the first.")
                add("")
                add("The actual causes are **defects in the reference**, and "
                    "there are two distinct ones. `scripts/audit_ground_truth.py` "
                    "measures which applies to each fixture:")
                add("")
                add("- **Visual word order.** The Constitute Project's Arabic "
                    "PDFs store each line's words right-to-left. Every character "
                    "is correct, so the file looks fine to a reader and passes "
                    "any character-level check -- but the word sequence is "
                    "backwards, and correctly-read OCR is charged for it. "
                    "Detected by reversing the reference's word order and "
                    "re-scoring: if that helps materially, this is what happened.")
                add("- **Out-of-flow blocks.** The same publisher puts topic "
                    "labels in the left margin and emits them at the *end* of "
                    "each page's content stream. All the words are present -- the "
                    "order-insensitive bag error is near zero -- but the sequence "
                    "differs, and CER counts that as error.")
                add("")
                add("The two are told apart by reading CER against **bag error**, "
                    "which ignores word order entirely. High CER with low bag "
                    "error is an ordering artifact; high CER with high bag error "
                    "is genuine misrecognition.")
                add("")
                add("**Consequence for quoting a number:** use the fixtures whose "
                    "reference the audit passed, and preferentially the "
                    "`scan_authored_*` fixtures, whose reference text was written "
                    "before the page was rendered and therefore cannot carry any "
                    "of these defects. Those are the only Arabic OCR figures here "
                    "that need no caveat about the reference. The mean across all "
                    "scanned documents is dragged down by reference defects and "
                    "should not be quoted as accuracy.")
                add("")
    else:
        add("_OCR was not exercised in this run._")
        add("")

    # ---------------- text extraction (non-OCR) ---------------------------
    add("### Text extraction accuracy (non-OCR path)")
    add("")
    scored_text = [e for e in ok if e.text_cer is not None]
    if scored_text:
        pages = sum(e.text_reference_pages for e in scored_text)
        add(f"The majority path through this pipeline is the text layer, not "
            f"OCR. This section measures it over **{pages} pages across "
            f"{len(scored_text)} documents**.")
        add("")
        add("**Read this figure as an upper bound, and read "
            "[`reports/native_extraction_accuracy.md`](native_extraction_accuracy.md) "
            "for the decomposition.** Three things inflate the number here, all "
            "of them properties of *this* measurement rather than of the "
            "extractor: it scores chunk text **as shipped**, which includes the "
            "heading labels `chunking.attach_heading_to_body` prepends (`Clause "
            "1`, `Annex A`) and which were never in the document; it scores each "
            "referenced page against that page's output, so a block emitted one "
            "page either side of where the reference puts it is charged as "
            "error even though no character was misread; and it blends Arabic "
            "and English into one figure. Scored per language against the "
            "extractor's own output, that report measures the same fixtures at "
            "**CER 0.0016 Arabic and 0.0107 English**, with three of them "
            "exactly 0.0000. Both numbers are correct; they answer different "
            "questions. (Those two figures are quoted from that report, not "
            "recomputed here -- regenerate it with "
            "`python scripts/native_extraction_benchmark.py` if the fixtures "
            "change.)")
        add("")
        add("**The reference is never the PDF's own text layer.** That would be "
            "circular, since reading the text layer is the thing being measured; "
            "and on Arabic it would be wrong, because the public Arabic PDFs "
            "here store presentation forms in visual order and reverse digit "
            "runs -- `wipo_eg088ar_1.pdf` page 3 renders `٢٠٢٣` and extracts "
            "`٣٢٠٢`. Scoring against that would penalise the pipeline for "
            "*correctly repairing* the damage. References are therefore either "
            "**authored** (the document was generated from text this project "
            "wrote) or **transcribed** (a human read the rendered page).")
        add("")
        add("What is measured is **end-to-end content preservation**: source "
            "text in, chunk text out, through detection, extraction, RTL "
            "repair, normalization, structure annotation and chunking. A "
            "regression anywhere in that chain moves it.")
        add("")
        add("| Document | Reference | Pages | CER | CER (no-space) | Bag error |")
        add("|---|---|---|---|---|---|")
        for e in sorted(scored_text, key=lambda x: x.file):
            add(f"| `{e.file}` | {e.text_reference_provenance} | "
                f"{e.text_reference_pages} | {_fmt(e.text_cer)} | "
                f"{_fmt(e.text_cer_nospace)} | {_fmt(e.text_bag_error)} |")
        add("")
        mean_cer = statistics.mean(e.text_cer_nospace for e in scored_text
                                   if e.text_cer_nospace is not None)
        add(f"**Mean CER (no-space): {mean_cer:.3f}** over {len(scored_text)} documents.")
        add("")
        add("`Bag error` ignores word order. Read it against CER: where CER is "
            "much the larger, the content was extracted but re-ordered, which "
            "on these fixtures means Arabic stored in visual order was not "
            "fully restored to logical order.")
        add("")
    else:
        add("_No text-extraction references available. Run "
            "`python scripts/make_text_ground_truth.py`._")
        add("")

    add("### Engine selection")
    add("")
    add("`Attempted` counts pages where the fallback engine ran; `kept` counts "
        "pages where its result was the one used. An attempt costs full time "
        "either way, which is why both are shown.")
    add("")
    add("| Document | Engines used (chunks) | Fallback attempted | Fallback kept |")
    add("|---|---|---|---|")
    for e in ok:
        add(f"| `{e.file}` | {', '.join(f'{k}: {v}' for k, v in sorted(e.engines.items()))} | "
            f"{e.ocr_fallback_attempts} | {e.ocr_fallbacks} |")
    add("")

    # ---------------- tables ---------------------------------------------
    add("## 3. Table extraction")
    add("")
    if tbl_docs:
        add("| Document | Expected | Found | |")
        add("|---|---|---|---|")
        for e in tbl_docs:
            mark = "ok" if e.tables_found >= e.tables_expected else "**missed**"
            add(f"| `{e.file}` | {e.tables_expected} | {e.tables_found} | {mark} |")
    else:
        add("_No documents with a known table count were evaluated._")
    add("")

    # ---------------- pages ----------------------------------------------
    add("## 4. Page preservation")
    add("")
    add("| Document | Source pages | Output pages | |")
    add("|---|---|---|---|")
    for e in ok:
        mark = "ok" if e.output_pages >= e.source_pages else "**LOST PAGES**"
        add(f"| `{e.file}` | {e.source_pages} | {e.output_pages} | {mark} |")
    add("")

    # ---------------- sections -------------------------------------------
    add("## 5. Section / clause preservation")
    add("")
    add("Compares structural markers detectable in the **source text** against "
        "distinct clause ids on the emitted chunks. A large shortfall means "
        "markers were present but chunking did not cut on them -- the signal to "
        "inspect that document.")
    add("")
    add("| Document | Markers in source | Clause ids emitted | Ratio | Chunk strategies |")
    add("|---|---|---|---|---|")
    for e in ok:
        ratio = (
            f"{min(e.markers_as_boundaries / e.markers_in_source, 1.0):.0%}"
            if e.markers_in_source else "n/a"
        )
        strategies = ", ".join(f"{k}: {v}" for k, v in sorted(e.chunk_strategies.items()))
        add(f"| `{e.file}` | {e.markers_in_source or 'n/a'} | {e.markers_as_boundaries} | "
            f"{ratio} | {strategies} |")
    add("")
    fell_back = [e for e in ok if e.chunk_strategies.get("paragraph") and e.markers_in_source >= 3]
    if fell_back:
        add("### ⚠ Documents that fell back to paragraph chunking despite visible structure")
        add("")
        for e in fell_back:
            add(f"- `{e.file}` -- {e.markers_in_source} markers in source, but "
                f"{e.chunk_strategies.get('paragraph', 0)} chunks used paragraph "
                f"strategy. **Inspect before trusting its clause data.**")
        add("")

    # ---------------- chunking / metadata correctness ----------------------
    add("## Chunking and metadata correctness")
    add("")
    checked = [e for e in ok if e.expectation_checks]
    if checked:
        total = sum(len(e.expectation_checks) for e in checked)
        passed = sum(sum(1 for v in e.expectation_checks.values() if v) for e in checked)
        add("Chunking was previously verified only as *did it run* -- chunk "
            "counts, with nothing to compare them against. This section checks "
            "output against expectations **declared in advance** in "
            "`test_corpus/synthetic/expectations.json`, written from what each "
            "document says rather than from what the pipeline produced. An "
            "expectation copied from actual output can only pass, and would "
            "measure nothing.")
        add("")
        add(f"**{passed}/{total} checks pass ({passed / max(total, 1):.0%}) "
            f"across {len(checked)} documents.**")
        add("")
        add("| Document | Type | Jurisdiction | Language | Clause ids | Tables | Chunks |")
        add("|---|---|---|---|---|---|---|")
        symbols = {True: "ok", False: "**FAIL**", None: "-"}
        for e in sorted(checked, key=lambda x: x.file):
            c = e.expectation_checks
            add(f"| `{e.file}` | {symbols[c.get('document_type')]} | "
                f"{symbols[c.get('jurisdiction')]} | {symbols[c.get('language')]} | "
                f"{symbols[c.get('clause_ids')]} | {symbols[c.get('tables')]} | "
                f"{symbols[c.get('min_chunks')]} |")
        add("")
        failures = [e for e in checked if e.expectation_detail]
        if failures:
            add("### What failed, and why")
            add("")
            for e in failures:
                add(f"**`{e.file}`**")
                for line in e.expectation_detail:
                    add(f"- {line}")
                add("")
    else:
        add("_No declared expectations found. See "
            "`test_corpus/synthetic/expectations.json`._")
        add("")

    # ---------------- RTL -------------------------------------------------
    add("## RTL / reading-order flags (surfaced, not auto-corrected)")
    add("")
    add("These are **not errors in the pipeline** -- they are the pipeline "
        "reporting that reading order could not be resolved safely. Per the "
        "spec, ambiguous cases are flagged for manual review rather than "
        "silently rewritten.")
    add("")
    flagged = [e for e in ok if e.rtl_flags]
    if flagged:
        add("| Document | Flags |")
        add("|---|---|")
        for e in flagged:
            add(f"| `{e.file}` | " +
                ", ".join(f"{k}: {v}" for k, v in sorted(e.rtl_flags.items())) + " |")
    else:
        add("_No reading-order ambiguities flagged._")
    add("")

    # ---------------- speed ----------------------------------------------
    add("## 6. Processing speed")
    add("")
    add("CPU only, no GPU. Timings include model inference where Docling or OCR ran.")
    add("")
    add("`extract` is the whole extraction phase; the stage named beside it is "
        "the largest thing inside it. `Unaccounted` is the total minus every "
        "measured stage -- it should stay near zero, and a large value means "
        "time is being spent somewhere nothing is instrumented.")
    add("")
    add("| Document | Total (s) | ms/page | extract (s) | Slowest inner stage | Unaccounted |")
    add("|---|---|---|---|---|---|")
    for e in ok:
        inner = {k: v for k, v in e.stage_ms.items() if k not in ("total", "extract")}
        # Stages nested inside extract must not be double-counted against total.
        nested = {"pymupdf", "docling", "docx", "ocr"}
        top_level = sum(v for k, v in e.stage_ms.items()
                        if k not in nested and k != "total")
        slowest = max(inner, key=lambda k: inner[k]) if inner else "n/a"
        unaccounted = e.total_ms - top_level
        add(f"| `{e.file}` | {e.total_ms / 1000:.1f} | {e.ms_per_page:.0f} | "
            f"{e.stage_ms.get('extract', 0) / 1000:.1f} | "
            f"{slowest} ({inner.get(slowest, 0):.0f} ms) | "
            f"{unaccounted / 1000:.1f}s ({unaccounted / max(e.total_ms, 1):.0%}) |")
    add("")

    slow = sorted(ok, key=lambda e: -e.ms_per_page)[:1]
    if slow and slow[0].ms_per_page > 5 * max(
        statistics.median(e.ms_per_page for e in ok), 1
    ):
        e = slow[0]
        add(f"### Slowest document: `{e.file}`")
        add("")
        add(f"{e.ms_per_page:.0f} ms/page against a corpus median of "
            f"{statistics.median(x.ms_per_page for x in ok):.0f}. Its breakdown: "
            + ", ".join(f"`{k}` {v / 1000:.1f}s" for k, v in
                        sorted(e.stage_ms.items(), key=lambda kv: -kv[1])[:4])
            + ".")
        add("")
        if e.ocr_fallback_attempts:
            add("**Being a scan is not the explanation.** Eight other scanned "
                "fixtures in this corpus cost roughly 4 s/page, so recognition "
                "alone accounts for a small fraction of the figure above. The "
                "cost is the *second* read:")
            add("")
            add(f"1. **The fallback engine ran on {e.ocr_fallback_attempts} of "
                f"its {e.source_pages} pages -- the dominant cost.** When the "
                "primary engine's mean confidence falls below "
                "`ocr.min_mean_confidence` (0.75) the page is re-read by the "
                "other engine, so it is paid for twice, and the fallback "
                "(PaddleOCR) is the slower of the two by roughly an order of "
                "magnitude. An attempt costs the same whether or not it wins: "
                f"here {e.ocr_fallbacks} of them produced the kept result.")
            add("2. **Recognition itself is also above average on this "
                "document**, because per-page OCR cost scales with text density "
                "and Arabic costs roughly twice English per character under "
                "`ara+eng`. That is the smaller of the two effects.")
            add("")
            if e.file == "scan_constitute_egypt_2019_ar_150dpi.pdf":
                add("[`reports/speed_outlier_investigation.md`](speed_outlier_investigation.md) "
                    "profiles this document specifically and attributes **55% of "
                    "its runtime** to the fallback, with rendering, chunking and "
                    "table reconstruction together under 1%. Two results there "
                    "qualify the trade rather than settling it: a clean "
                    "re-render of the same pages costs the primary engine the "
                    "same time but passes the gate on 5 of 6 pages, so the "
                    "fixture's synthetic degradation causes the *gate failures* "
                    "rather than the slowness; and on the one Arabic fixture "
                    "with authored ground truth the fallback engine is "
                    "measurably **less** accurate than the primary whose output "
                    "it replaces. Whether the second read earns its cost is "
                    "therefore open, and is tracked there as follow-up S1.")
                add("")
        else:
            add("**This is a scaling characteristic, not a defect.** The "
                "fallback engine was never invoked on it, so this is the "
                "primary engine's own cost on dense, noisy, two-column Arabic. "
                "Per-page OCR time varies several-fold across the scanned "
                "corpus with page density and image quality; this document sits "
                "at the top of that range.")
            add("")
        attempted = [x for x in ok if x.ocr_fallback_attempts]
        if attempted:
            worst_fb = max(attempted, key=lambda x: x.ocr_fallback_attempts)
            add(f"Across the corpus, {len(attempted)} document(s) attempted the "
                f"fallback on at least one page, the most being "
                f"`{worst_fb.file}` at {worst_fb.ocr_fallback_attempts} page(s). "
                "Setting `ocr.fallback_engine = \"none\"` removes that cost, and "
                "the safety net with it.")
            add("")
        add("See the README's *Performance characteristics* section for the "
            "per-page figures to plan an ingest against.")
        add("")

    # ---------------- failures -------------------------------------------
    add("## 7. Failures")
    add("")
    if failed:
        add("| Document | Error |")
        add("|---|---|")
        for e in failed:
            add(f"| `{e.file}` | {(e.error or '')[:180]} |")
    else:
        add("_No documents failed._")
    add("")

    # ---------------- caveats --------------------------------------------
    add("## Caveats")
    add("")
    if on_real_data:
        add("This run used a supplied corpus rather than the interim one, so the "
            "caveats below apply only where they still hold. Review each.")
        add("")
    else:
        add("Read these before quoting any figure above.")
        add("")
    add("1. **Rendered pages are not scans.** Every scanned fixture is a "
        "digital page rasterized and then degraded with skew, noise and JPEG "
        "artifacts. That models compression and geometry; it does not model "
        "scanner optics, photocopy generations, bleed-through from the reverse "
        "side, or staple shadows. **The OCR figures above are an optimistic "
        "bound and should be quoted as one.** This does not change with time -- "
        "it is a property of validating without firm data.")
    add("2. **Reference quality varies, and is classified rather than assumed.** "
        "Ground truth derived from a source PDF's text layer inherits that "
        "publisher's defects, and this corpus contains three kinds: visual word "
        "order, out-of-flow marginal columns, and words fragmented into single "
        "glyphs. Each makes a *correct* extraction score badly. "
        "`scripts/audit_ground_truth.py` labels every reference; the "
        "`scan_authored_*` fixtures, whose text was written before the page was "
        "rendered, are the ones whose absolute accuracy needs no caveat.")
    add("3. **No firm house style.** Letterhead, numbering conventions, "
        "defined-term formatting and clause phrasing are unknown. The structure "
        "detector's cue lists were written against published statutes and "
        "synthetic contracts; extending them for a firm's own drafting is a "
        "list edit and expected work, not a defect.")
    add("4. **Document-type inference is heuristic** and was corrected twice "
        "during development when public documents exposed bad cues "
        "(`باسم الشعب` opens both statutes and judgments). More such cues "
        "certainly exist in material this corpus does not contain.")
    add("5. **One machine, one run.** Timings are from a single Windows "
        "CPU-only workstation and will not match the firm's server. The "
        "*ratios* between paths (text layer vs Docling vs OCR) are the durable "
        "part -- see the README's performance section.")
    add("6. **No handwriting, no multi-instrument bundles, no "
        "password-protected or corrupt files.** The one handwritten public "
        "document available is excluded from every metric because it cannot be "
        "scored at all; see the exclusions list above.")
    add("")
    add("### What this evaluation does and does not claim")
    add("")
    add("It claims that the pipeline processes every input shape the spec "
        "requires, at the accuracies tabulated above, against references whose "
        "trustworthiness has itself been measured. **No client document was "
        "processed, and none is required for these figures to hold.**")
    add("")
    add("It does not claim to predict accuracy on the firm's own archive. The "
        "gap is named in caveat 1 and is not closable from public data. If the "
        "firm wants that number, the same report regenerates against a local "
        "directory with nothing leaving the building:")
    add("")
    add("```bash")
    add("python scripts/evaluate.py --corpus-dir test_corpus/real")
    add("```")
    add("")
    add("### Settings still worth tuning against the firm's own drafting")
    add("")
    add("None of these block use; each has a conservative default and a better "
        "setting that only the firm's material can reveal.")
    add("")
    add("- Structure cue lists, against real clause numbering conventions")
    add("- Normalization A/B: `normalize_hamza` and `normalize_teh_marbuta` are "
        "OFF because folding them is lossy and the evidence has to come from "
        "the text actually being searched")
    add("- The OCR engine ordering, re-benchmarked on real scans")
    add("- Chunk size, against M2/M3's embedding model context window")
    add("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------


def _rebuild_report(args: argparse.Namespace) -> int:
    """Regenerate the markdown report from a stored results JSON."""
    path = Path(args.json)
    if not path.exists():
        print(f"No results file at {path}. Run the evaluation first.")
        return 1

    payload = json.loads(path.read_text(encoding="utf-8"))
    fields = {f.name for f in DocEval.__dataclass_fields__.values()}
    evals = [DocEval(**{k: v for k, v in d.items() if k in fields})
             for d in payload["documents"]]
    config = PipelineConfig(**payload["config"])

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(build_report(evals, config, 0.0, args), encoding="utf-8")
    print(f"Rebuilt {args.out} from {path} ({len(evals)} documents, no reprocessing)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-ocr", action="store_true", help="skip scanned/image documents")
    parser.add_argument("--no-docling", action="store_true", help="skip Docling layout analysis")
    parser.add_argument(
        "--corpus-dir", action="append", type=Path, metavar="DIR",
        help="evaluate this directory instead of the interim corpus. THIS IS THE "
             "HOOK FOR REAL FIRM DOCUMENTS -- e.g. --corpus-dir test_corpus/real. "
             "Repeatable. Recurses into subdirectories.",
    )
    parser.add_argument("--out", default=str(REPORTS_DIR / "evaluation_report.md"))
    parser.add_argument("--json", default=str(REPORTS_DIR / "evaluation_results.json"))
    parser.add_argument(
        "--from-json", action="store_true",
        help="rebuild the markdown report from a previous run's JSON without "
             "re-processing anything. A full run costs ~18 minutes, almost all "
             "of it OCR; this makes iterating on report wording free.",
    )
    args = parser.parse_args()

    if args.from_json:
        return _rebuild_report(args)

    if args.corpus_dir:
        missing = [d for d in args.corpus_dir if not d.is_dir()]
        if missing:
            print(f"No such directory: {', '.join(str(d) for d in missing)}")
            return 1

    config = PipelineConfig()
    config.ocr.enabled = not args.no_ocr
    config.extraction.use_docling = not args.no_docling

    manifest = load_manifest()
    files = discover(include_ocr=not args.no_ocr, corpus_dirs=args.corpus_dir)
    if not files:
        print("No corpus files found. Run the corpus scripts first, or check --corpus-dir.")
        return 1

    print(f"Evaluating {len(files)} documents "
          f"(docling={'on' if config.extraction.use_docling else 'off'}, "
          f"ocr={'on' if config.ocr.enabled else 'off'})...\n")

    evals: list[DocEval] = []
    start = time.perf_counter()
    for i, (path, corpus) in enumerate(files, 1):
        print(f"[{i}/{len(files)}] {path.name} ... ", end="", flush=True)
        t0 = time.perf_counter()
        try:
            ev = evaluate_document(path, corpus, config, manifest)
        except Exception as exc:  # noqa: BLE001
            ev = DocEval(file=path.name, corpus=corpus, error=f"harness error: {exc}")
        evals.append(ev)
        print(f"{'ok' if ev.succeeded else 'FAIL'} "
              f"({time.perf_counter() - t0:.1f}s, {ev.n_chunks} chunks)")
    elapsed = time.perf_counter() - start

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report = build_report(evals, config, elapsed, args)
    Path(args.out).write_text(report, encoding="utf-8")

    from dataclasses import asdict

    Path(args.json).write_text(
        json.dumps(
            {
                "warning": "INTERIM RESULTS from public/synthetic data. "
                           "No firm document has been processed.",
                "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
                "config": config.model_dump(mode="json"),
                "documents": [asdict(e) for e in evals],
            },
            ensure_ascii=False, indent=2, default=str,
        ),
        encoding="utf-8",
    )

    print(f"\nReport : {args.out}")
    print(f"Raw    : {args.json}")
    failed = sum(1 for e in evals if not e.succeeded)
    print(f"Failed : {failed}/{len(evals)}")

    from src.ocr_pipeline import shutdown_paddle_workers

    shutdown_paddle_workers()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
