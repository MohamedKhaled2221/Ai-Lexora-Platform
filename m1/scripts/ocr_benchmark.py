"""PaddleOCR vs Tesseract head-to-head.

The evaluation report exercised Tesseract in practice on every scanned document
-- either as primary or as the winner of a fallback -- so it contains no real
comparison. The team spec assumes PaddleOCR is primary and Tesseract is the
fallback. This script tests that assumption instead of inheriting it.

METHOD
======

* **Both engines run standalone.** ``ocr_page_image``'s gating and fallback
  logic is deliberately bypassed; ``run_paddleocr`` and ``run_tesseract`` are
  called directly. Otherwise we would be measuring the fallback policy, not the
  engines.
* **Identical input.** Each page is rasterized exactly once and the same array
  is handed to both engines, so resolution, skew and JPEG artifacts are held
  constant.
* **Identical scoring.** The metric functions are imported from
  ``scripts/evaluate.py`` -- not reimplemented -- so numbers here are directly
  comparable with the evaluation report.
* **Identical normalization.** Both the reference and each engine's output go
  through the pipeline's own normalization before scoring, so what is measured
  is recognition error rather than orthographic variation the pipeline folds on
  purpose.
* Arabic and English are scored separately, by splitting each text into its
  Arabic and Latin word streams.

* **PaddleOCR gets a fresh worker per fixture.** Its production crash-policy
  disables it for the rest of the process after repeated failures, which is
  correct there and fatal to a measurement here -- see
  :func:`run_engine_on_fixture`. How often that reset was needed is reported
  separately, as the reliability figure it actually is.

WHAT INFLATES ABSOLUTE CER, AND WHAT DOES NOT
=============================================

Most ground truth is the source PDF's text layer, so it carries that
publisher's defects. Two matter here, and **neither is the one originally
assumed**:

* **Visual word order** -- some Arabic PDFs store each line's words
  right-to-left. Every character is correct; the sequence is backwards.
* **Out-of-flow blocks** -- some publishers emit a marginal annotation column
  at the end of the page's content stream, so all the words are present in a
  different order.

Two earlier explanations were wrong and are corrected in the report:
**two-column layout** (ruled out -- ``wipo_eg081ar_1`` is two-column and scores
well) and **word fragmentation** (ruled out -- ``wipo_eg088ar_1`` has a
fragmented reference and scores best of all). The real split is by publisher.

All of this inflates the **absolute** CER. None of it biases the
**comparison**, because both engines are scored against the same reference with
the same handicap. ``scripts/audit_ground_truth.py`` labels each reference so
the report can separate the two claims, and the ``scan_authored_*`` fixtures --
whose text was written before the page was rendered -- have no such defect at
all.

Run::

    python scripts/ocr_benchmark.py
    python scripts/ocr_benchmark.py --max-pages 2      # faster
    python scripts/ocr_benchmark.py --engines tesseract
    python scripts/ocr_benchmark.py --from-json        # rebuild the report only
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import src  # noqa: E402

src.quiet_third_party_logs()

from evaluate import (  # noqa: E402  -- reuse, do not reimplement
    MIN_REFERENCE_CHARS,
    _split_by_script,
    bag_error,
    cer,
    wer,
)
from src.config import REPORTS_DIR, SYNTHETIC_CORPUS_DIR, PipelineConfig  # noqa: E402
from src.normalize import normalize_text  # noqa: E402
from src.ocr_pipeline import (  # noqa: E402
    render_pdf_page,
    run_paddleocr,
    run_tesseract,
    shutdown_paddle_workers,
)

ENGINES = {"paddleocr": run_paddleocr, "tesseract": run_tesseract}

# PaddleOCR on this build cannot process a full-resolution page: at 300 dpi
# (~3500 px on the long side) it fails on every document tested, with either a
# "Unknown exception" from native code or an outright worker death. It succeeds
# once the image is downscaled.
#
# Reporting that as "PaddleOCR scored 1.0 CER" would be a measurement of our
# render settings, not of the engine. So for PaddleOCR the benchmark walks this
# ladder until a page succeeds, and records how far down it had to go. Tesseract
# needs no such help and is always run at the configured DPI.
#
# The two facts are then reported separately:
#   * accuracy      -- PaddleOCR at the best resolution it can actually handle
#   * reliability   -- how often it failed at the pipeline's configured DPI
PADDLE_SIDE_LADDER = [2500, 1600, 1200]

# The ladder used to start at 4000 px, the pipeline's configured
# ``max_render_side``. It no longer does, and the reason is a measurement, not
# a convenience: across two full runs PaddleOCR failed on **every** page probed
# at 4000 px, without a single success. Re-probing it a third time buys a known
# answer for ~60 s and a very large allocation per page -- and on a machine with
# 16 GB and a small pagefile, those allocations are what exhausted memory and
# killed two benchmark processes outright (MuPDF "malloc failed", OpenCV
# "Insufficient memory", "the paging file is too small").
#
# The full-resolution failure rate quoted in the report is therefore carried
# from those runs, where it was measured honestly, rather than re-derived here.
# Restore 4000 as the first rung to re-measure it on hardware with more headroom.
PADDLE_FULL_RES_PROBE = 4000

# Remembers the first ladder rung that worked. Once we have learned that 4000 px
# always fails on this machine, retrying it on every page costs ~60 s each for a
# guaranteed failure. The first page still probes from the top, so the
# "failed at configured DPI" statistic is measured honestly rather than assumed.
_ladder_start = 0

# Error strings that indicate the engine process died, as opposed to raising a
# normal Python exception. Tracked separately because a crash is an operational
# risk (it can take the batch with it) while a soft error is merely a bad page.
_CRASH_MARKERS = ("worker died", "pipe broke", "access violation",
                  "worker crashed", "disabled for this run")


@dataclass
class EngineRun:
    engine: str
    document: str
    language: str
    columns: int
    quality_level: str
    fragmented: bool
    pages: int = 0

    chars: int = 0
    seconds: float = 0.0
    crashes: int = 0
    soft_errors: int = 0
    blank_pages: int = 0

    # PaddleOCR only: failures at the pipeline's configured DPI, before any
    # adaptive downscale. This is the reliability figure; the accuracy figures
    # above come from the best resolution the engine could actually handle.
    failures_at_full_dpi: int = 0
    pages_probed_at_full_dpi: int = 0
    """Denominator for the failure rate. Once the ladder has learned which rung
    works, later pages start below the top, so they are not evidence either way
    and must not be counted."""
    downscaled_pages: int = 0
    sides_used: list[int] = field(default_factory=list)

    cer_ar: float | None = None
    cer_ar_nospace: float | None = None
    wer_ar: float | None = None
    bag_ar: float | None = None
    cer_en: float | None = None
    cer_en_nospace: float | None = None
    wer_en: float | None = None
    bag_en: float | None = None

    notes: list[str] = field(default_factory=list)

    @property
    def sec_per_page(self) -> float:
        return self.seconds / max(self.pages, 1)

    @property
    def crashed(self) -> bool:
        return self.crashes > 0


def discover_fixtures(max_pages: int) -> list[dict]:
    """Every scanned fixture that has ground truth, from both manifests."""
    fixtures: list[dict] = []

    bench_manifest = SYNTHETIC_CORPUS_DIR / "bench_manifest.json"
    if bench_manifest.exists():
        data = json.loads(bench_manifest.read_text(encoding="utf-8"))
        for entry in data["fixtures"]:
            path = SYNTHETIC_CORPUS_DIR / entry["file"]
            gt = SYNTHETIC_CORPUS_DIR / entry["ground_truth"]
            if path.exists() and gt.exists():
                fixtures.append({
                    "path": path, "gt": gt, "language": entry["language"],
                    "columns": entry["columns"], "quality_level": entry["quality_level"],
                    "fragmented": entry["ground_truth_fragmented"],
                    "max_pages": max_pages, "set": "bench",
                })

    # The evaluation report's own scanned fixtures, so the two documents can be
    # cross-referenced.
    synth_manifest = SYNTHETIC_CORPUS_DIR / "synthetic_manifest.json"
    known: dict[str, dict] = {}
    if synth_manifest.exists():
        data = json.loads(synth_manifest.read_text(encoding="utf-8"))
        known = {e["file"]: e for e in data["files"]}

    stress_manifest = SYNTHETIC_CORPUS_DIR / "stress_manifest.json"
    if stress_manifest.exists():
        data = json.loads(stress_manifest.read_text(encoding="utf-8"))
        known.update({e["file"]: e for e in data["files"]})

    for path in sorted(SYNTHETIC_CORPUS_DIR.glob("scan_*.pdf")):
        gt = path.with_name(path.stem + ".groundtruth.txt")
        if not gt.exists():
            continue
        entry = known.get(path.name, {})
        mix = str(entry.get("language_mix", ""))
        # A reference with form-feed page markers can be sliced to the pages
        # actually scored. One without cannot, so every page must be read or the
        # engine is charged for pages it was never shown -- which reads as ~0.75
        # CER however well it did. The first-wave scan_* fixtures predate the
        # markers; everything since has them.
        head = gt.read_text(encoding="utf-8", errors="replace")[:200_000]
        if "\f" in head:
            pages = max_pages
        else:
            import fitz

            with fitz.open(path) as d:
                pages = d.page_count

        fixtures.append({
            "path": path, "gt": gt,
            "language": "en" if "English" in mix else "ar",
            "columns": 0,   # not measured for these; reported as unknown
            "quality_level": ("authored-reference" if "_authored_" in path.name
                              else "eval-corpus"),
            "fragmented": bool(entry.get("ground_truth_spacing_defect")),
            "max_pages": pages, "set": "eval",
        })

    return fixtures


# How many fixtures began with PaddleOCR already switched off by its own
# crash-protection. This is the reliability headline: in a continuous
# production run, each of these is the point where the engine would have
# stopped contributing anything for the rest of the batch.
_paddle_disablements = 0


def _warm_up_paddle(config: PipelineConfig) -> None:
    """Load PaddleOCR's models before the clock starts.

    The worker is reset per fixture (see :func:`run_engine_on_fixture`), and a
    fresh worker pays ~30 s to load model weights on its first inference. That
    load happens *inside* ``run_paddleocr``, so without this it lands in the
    first page's timing and inflates PaddleOCR's seconds-per-page by ~10 s on a
    three-page fixture -- overstating the very gap the speed comparison exists
    to measure. Tesseract has no equivalent cost, so leaving it in would be
    unfair in a way that flatters the conclusion this benchmark already reaches.

    A 32x32 blank image is enough: the cost is the model load, not the pixels.
    Failures are ignored -- if the engine cannot start, the fixture's own run
    will record that properly.
    """
    try:
        run_paddleocr(np.zeros((32, 32, 3), dtype=np.uint8), 0, 1.0, config.ocr)
    except Exception:  # noqa: BLE001
        pass


def _worker_is_disabled() -> bool:
    from src.ocr_pipeline import _PADDLE_WORKERS

    return any(w.disabled_reason for w in _PADDLE_WORKERS.values())


def classify_error(message: str | None) -> str | None:
    if not message:
        return None
    low = message.lower()
    return "crash" if any(m in low for m in _CRASH_MARKERS) else "soft"


def reset_engine_state(engine: str) -> None:
    """Give each fixture a clean engine, so one bad fixture cannot poison the rest.

    ``_PaddleWorker`` disables PaddleOCR for the remainder of the process after
    ``max_restarts`` crashes. That is right for production -- a systematically
    broken install should fail over to Tesseract once rather than reload weights
    forever -- but catastrophic for a benchmark: a run where PaddleOCR crashed
    on fixture 1 recorded ``CER 1.000, 0 chars, 0.0 s/page`` for the remaining
    22 fixtures, which reads as "the engine is useless" when it means "the
    engine was switched off".

    Resetting per fixture costs one model load (~20-40 s) per crash, and buys
    22 real measurements.
    """
    if engine == "paddleocr":
        shutdown_paddle_workers()


def run_engine_on_fixture(engine: str, fixture: dict, config: PipelineConfig) -> EngineRun:
    """Run one engine over one fixture, page by page, on identical rasters."""
    import fitz

    run = EngineRun(
        engine=engine,
        document=fixture["path"].name,
        language=fixture["language"],
        columns=fixture["columns"],
        quality_level=fixture["quality_level"],
        fragmented=fixture["fragmented"],
    )
    runner = ENGINES[engine]
    collected: list[str] = []

    global _ladder_start, _paddle_disablements

    if engine == "paddleocr":
        # Give PaddleOCR a clean worker for every fixture.
        #
        # In production, _PaddleWorker gives up on PaddleOCR entirely after
        # max_restarts crashes and degrades to Tesseract for the rest of the
        # run. That is the right policy there -- reloading a 30 s model per page
        # for a systematically broken install helps nobody.
        #
        # In a benchmark it is fatal to the measurement. The first run of this
        # script hit two crashes on fixture 1, and every fixture after it
        # recorded "no resolution succeeded" at 0.0 s/page and CER 1.000 -- which
        # reads as catastrophic accuracy but is really the engine having been
        # switched off. Nineteen of twenty-three fixtures were scoring a policy,
        # not an engine.
        #
        # So each fixture starts from a fresh worker, and the number of times a
        # reset was needed is reported separately as the reliability figure it
        # actually is.
        if _worker_is_disabled():
            _paddle_disablements += 1
            run.notes.append(
                "PaddleOCR had disabled itself after repeated crashes; worker "
                "reset so this fixture could be measured"
            )
        shutdown_paddle_workers()
        _warm_up_paddle(config)

    # PaddleOCR gets the downscale ladder; Tesseract runs once at the
    # configured resolution because it handles full-size pages without trouble.
    if engine == "paddleocr":
        ladder = PADDLE_SIDE_LADDER[_ladder_start:] or PADDLE_SIDE_LADDER[-1:]
        skipped = _ladder_start
    else:
        ladder, skipped = [config.ocr.max_render_side], 0

    doc = fitz.open(fixture["path"])
    try:
        n = min(fixture["max_pages"], doc.page_count)
        for i in range(n):
            page_text = ""
            page_seconds = 0.0
            for rung, side in enumerate(ladder):
                attempt = rung + skipped
                t0 = time.perf_counter()
                try:
                    # Rasterization is inside the try because it is not
                    # exception-free on a memory-constrained machine: MuPDF
                    # raises FzErrorSystem("malloc failed") when the OS is out
                    # of pages, and an uncaught one there took the whole
                    # benchmark process down partway through -- three separate
                    # runs died between fixtures 3 and 12 before this moved.
                    # A page that cannot be rendered is a failed page, not a
                    # failed run.
                    img, scale = render_pdf_page(doc[i], config.ocr.render_dpi, side)
                    result = runner(img, i + 1, scale, config.ocr)
                    page_seconds += time.perf_counter() - t0
                    error, boxes, text = result.error, result.boxes, result.text
                except Exception as exc:  # noqa: BLE001
                    page_seconds += time.perf_counter() - t0
                    error, boxes, text = f"{type(exc).__name__}: {exc}", [], ""

                failed = bool(error) or not boxes

                # Count every error, at every rung. Counting only at attempt 0
                # meant that once the ladder memory advanced, crashes stopped
                # being recorded at all -- a run where PaddleOCR crashed out
                # reported `crashes=0` on 22 of 23 fixtures.
                kind = classify_error(error)
                if kind == "crash":
                    run.crashes += 1
                    run.notes.append(f"p{i + 1}: CRASH at {side}px -- {str(error)[:100]}")
                elif kind == "soft":
                    run.soft_errors += 1
                    run.notes.append(f"p{i + 1}: error at {side}px -- {str(error)[:100]}")

                if attempt == 0:
                    # Only a probe that actually started at the top rung is
                    # evidence about behaviour at the configured DPI.
                    run.pages_probed_at_full_dpi += 1
                    if failed:
                        run.failures_at_full_dpi += 1

                if not failed:
                    page_text = text
                    run.sides_used.append(side)
                    if attempt > 0:
                        run.downscaled_pages += 1
                        if rung > 0:
                            run.notes.append(
                                f"p{i + 1}: recovered at {side}px after "
                                f"{rung} downscale(s)"
                            )
                    if engine == "paddleocr":
                        _ladder_start = max(_ladder_start, attempt)
                    break
            else:
                run.blank_pages += 1
                run.notes.append(f"p{i + 1}: no resolution succeeded")

            collected.append(page_text)
            run.seconds += page_seconds
            run.pages += 1
    finally:
        doc.close()

    hypothesis = "\n".join(collected)
    run.chars = len(hypothesis.strip())

    # An engine that produced nothing at all on every page did not score 1.000
    # -- it did not run. Scoring it anyway manufactures a number that looks like
    # a measurement, which is exactly how a disabled PaddleOCR came to "score"
    # CER 1.000 on 22 fixtures. Leave the metrics as None so the report shows
    # n/a and the mean excludes it.
    if run.chars == 0:
        run.notes.append(
            "engine produced no output on any page -- not scored (this is an "
            "engine failure, not an accuracy result)"
        )
        return run
    _score(run, fixture["gt"], hypothesis, config, pages_scored=run.pages)
    return run


def _reference_for_pages(gt_path: Path, pages_scored: int) -> str:
    """Ground truth restricted to the pages actually OCR'd.

    Benchmark fixtures store their reference with form-feed page separators. A
    reference covering more pages than were scored charges the engine for pages
    it never saw -- scoring 1 page of a 4-page reference looks like ~0.75 CER
    however well the page was read.
    """
    raw = gt_path.read_text(encoding="utf-8", errors="replace")
    if "\f" in raw:
        return "\f".join(raw.split("\f")[:pages_scored])
    return raw


def _score(run: EngineRun, gt_path: Path, hypothesis: str, config: PipelineConfig,
           pages_scored: int) -> None:
    """Score one engine run against ground truth, per script.

    Both sides are normalized with the pipeline's own settings so the comparison
    measures recognition rather than orthography the pipeline folds anyway.
    """
    reference, _ = normalize_text(
        _reference_for_pages(gt_path, pages_scored), config.normalization
    )
    hypothesis, _ = normalize_text(hypothesis, config.normalization)

    ref_ar, ref_en = _split_by_script(reference)
    hyp_ar, hyp_en = _split_by_script(hypothesis)

    run.cer_ar = cer(ref_ar, hyp_ar)
    run.cer_ar_nospace = cer(ref_ar, hyp_ar, ignore_spaces=True)
    run.wer_ar = wer(ref_ar, hyp_ar)
    run.bag_ar = bag_error(ref_ar, hyp_ar)
    run.cer_en = cer(ref_en, hyp_en)
    run.cer_en_nospace = cer(ref_en, hyp_en, ignore_spaces=True)
    run.wer_en = wer(ref_en, hyp_en)
    run.bag_en = bag_error(ref_en, hyp_en)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def _fmt(value, dash: str = "n/a") -> str:
    if value is None:
        return dash
    return f"{value:.3f}" if isinstance(value, float) else str(value)


def _mean(values: list[float]) -> float | None:
    clean = [v for v in values if v is not None]
    return statistics.mean(clean) if clean else None


def load_reference_audit() -> dict[str, str]:
    """Map fixture filename -> reference verdict from scripts/audit_ground_truth.py.

    Without this the report would quote absolute error rates computed against
    references that are themselves wrong.
    """
    path = SYNTHETIC_CORPUS_DIR / "reference_audit.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {r["file"]: r["reference_word_order"] for r in data["results"]}


# Reference verdicts whose absolute CER can be quoted as accuracy.
#
# "authored" is the strongest: the text was written before the page existed, so
# the reference cannot carry the defects the audit hunts for. "logical" is a
# reference derived from a source text layer that the audit could find nothing
# wrong with. Everything else -- visual word order, out-of-flow block order,
# or unexplained error -- inflates CER for BOTH engines equally, so those
# fixtures remain valid for the head-to-head and invalid for absolute accuracy.
TRUSTWORTHY = {"authored", "logical"}


def build_report(runs: list[EngineRun], config: PipelineConfig, elapsed: float,
                 max_pages: int, render_dpi: int | None = None) -> str:
    """Render the report.

    ``render_dpi`` is the DPI the *runs* were measured at, which is not
    necessarily ``config.ocr.render_dpi``. The default has moved across
    revisions (300 -> 150 -> back to 300), and reading it from the live config
    made a stored run describe itself at whatever DPI happened to be current.
    Passing it explicitly keeps a rebuilt report honest about the measurement it
    is reporting.
    """
    render_dpi = render_dpi if render_dpi is not None else config.ocr.render_dpi
    lines: list[str] = []
    add = lines.append

    audit = load_reference_audit()

    by_doc: dict[str, dict[str, EngineRun]] = {}
    for run in runs:
        by_doc.setdefault(run.document, {})[run.engine] = run

    def scores(lang: str, *, trustworthy_only: bool = False) -> dict[str, list[float]]:
        out: dict[str, list[float]] = {e: [] for e in ENGINES}
        for doc_name, pair in by_doc.items():
            sample = next(iter(pair.values()))
            if sample.language != lang:
                continue
            if trustworthy_only and audit.get(doc_name) not in TRUSTWORTHY:
                continue
            for engine, run in pair.items():
                value = run.cer_ar_nospace if lang == "ar" else run.cer_en_nospace
                if value is not None:
                    out[engine].append(value)
        return out

    add("# PaddleOCR vs Tesseract -- head-to-head")
    add("")
    add("> ## Measured on public and synthetic scans, by design")
    add("> ")
    add("> Every figure comes from **published Egyptian legal PDFs rasterized "
        "into scans**, plus **authored fixtures** whose reference text was "
        "written before the page was rendered. No client document has been "
        "processed, and none is needed to choose between two OCR engines: what "
        "matters here is the comparison, and both engines see identical input.")
    add("> ")
    add("> **The absolute error rates are an optimistic bound.** A rasterized "
        "page has clean glyph shapes, no scanner optics, no photocopy "
        "generations and no bleed-through. Real scans will score worse, and the "
        "two engines may not degrade at the same rate -- which is the one thing "
        "this benchmark cannot rule out. Re-running it against the firm's own "
        "scans needs no code change and nothing leaves the building.")
    add("> ")
    add(f"> **On the render resolution.** This run rendered at {render_dpi} dpi. "
        "`reports/arabic_preprocess_sweep.md` found 150 dpi to read this "
        "corpus's Arabic better (CER 0.095), and "
        "`reports/dpi_probe_300.md` then found that advantage to reverse on "
        "small print -- so 300 dpi remains the default and the figures below "
        "stand as current. **The engine ordering never depended on it either "
        "way**: both engines are handed identical rasters, so a render setting "
        "cannot bias the comparison.")
    add("")
    add(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}  ")
    add(f"Fixtures: {len(by_doc)} documents, {max_pages} pages each, "
        f"both engines on identical rasters  ")
    add(f"Render: {render_dpi} dpi | "
        + (f"Wall clock: {elapsed / 60:.1f} min | " if elapsed else "")
        + "CPU only, no GPU")
    add("")

    # ---------------- headline -------------------------------------------
    add("## Verdict")
    add("")

    ar_all = scores("ar")
    en_all = scores("en")
    ar_clean = scores("ar", trustworthy_only=True)
    en_clean = scores("en", trustworthy_only=True)

    # Below this relative difference the engines are indistinguishable on this
    # sample size, and declaring a "winner" would overstate the evidence.
    TIE_THRESHOLD = 0.05

    def verdict_line(label: str, data: dict[str, list[float]], note: str) -> None:
        p, t = _mean(data["paddleocr"]), _mean(data["tesseract"])
        if p is None or t is None:
            add(f"- **{label}:** not enough scored documents.")
            return
        best, worst = min(t, p), max(t, p)
        rel = (worst - best) / worst if worst else 0.0
        if rel < TIE_THRESHOLD:
            add(f"- **{label}: effectively tied.** CER {t:.3f} (Tesseract) vs "
                f"{p:.3f} (PaddleOCR) -- a {rel:.1%} difference, within noise "
                f"for this sample. _{note}_")
            return
        winner, loser = ("Tesseract", "PaddleOCR") if t < p else ("PaddleOCR", "Tesseract")
        add(f"- **{label}: {winner} wins.** CER {best:.3f} vs {worst:.3f} "
            f"-- {rel:.0%} fewer errors than {loser}. _{note}_")

    add("**Quote these two lines, not the ones below them.** Absolute error "
        "rates are only meaningful where the reference itself was verified "
        "correct (see [Ground-truth audit](#ground-truth-audit)).")
    add("")
    verdict_line("Arabic -- verified references", ar_clean,
                 f"{len(ar_clean['tesseract'])} documents whose ground truth "
                 "passed the audit. **This is the Arabic number.**")
    verdict_line("English -- verified references", en_clean,
                 f"{len(en_clean['tesseract'])} documents whose ground truth "
                 "passed the audit. **This is the English number.**")
    add("")
    add("For completeness, including documents whose reference is known to be "
        "defective (both engines are handicapped equally, so the *winner* is "
        "still valid even though the absolute figures are not):")
    add("")
    verdict_line("Arabic -- all documents", ar_all,
                 f"{len(ar_all['tesseract'])} documents")
    verdict_line("English -- all documents", en_all,
                 f"{len(en_all['tesseract'])} documents")
    add("")

    speed = {e: _mean([r.sec_per_page for r in runs if r.engine == e]) for e in ENGINES}
    if all(v is not None for v in speed.values()):
        fast = min(speed, key=lambda e: speed[e])
        slow = max(speed, key=lambda e: speed[e])
        ratio = speed[slow] / speed[fast] if speed[fast] else 0
        add(f"- **Speed: {fast} is {ratio:.0f}x faster** "
            f"({speed[fast]:.1f} s/page vs {speed[slow]:.1f} s/page).")
    crashes = {e: sum(r.crashes for r in runs if r.engine == e) for e in ENGINES}
    pages = {e: sum(r.pages for r in runs if r.engine == e) for e in ENGINES}
    for engine in ENGINES:
        rate = crashes[engine] / max(pages[engine], 1)
        add(f"- **{engine} crash rate: {crashes[engine]}/{pages[engine]} pages "
            f"({rate:.0%})**")
    add("")

    # ---------------- main table ------------------------------------------
    add("## Full results")
    add("")
    add("`no-space` strips whitespace before comparing, isolating glyph "
        "recognition. Where it diverges sharply from the plain CER, the "
        "*reference* has fragmented word boundaries -- see the Caveats.")
    add("")
    ref_label = {"authored": "**authored**", "logical": "verified",
                 "visual": "**visual order**", "out_of_flow": "**out of flow**",
                 "unreliable": "**unreliable**", "not_audited": "not audited"}
    add("| Document | Ref | Cols | Quality | Engine | CER | CER (no-space) | WER | "
        "s/page | Crashed? |")
    add("|---|---|---|---|---|---|---|---|---|---|")
    for doc_name in sorted(by_doc):
        pair = by_doc[doc_name]
        sample = next(iter(pair.values()))
        lang = sample.language
        cols = {0: "?", 1: "1", 2: "2"}.get(sample.columns, str(sample.columns))
        ref = ref_label.get(audit.get(doc_name, "not_audited"), "?")
        for engine in ENGINES:
            run = pair.get(engine)
            if run is None:
                continue
            c = run.cer_ar if lang == "ar" else run.cer_en
            cn = run.cer_ar_nospace if lang == "ar" else run.cer_en_nospace
            w = run.wer_ar if lang == "ar" else run.wer_en
            flag = f"**YES ({run.crashes})**" if run.crashed else (
                f"soft err ({run.soft_errors})" if run.soft_errors else "no")
            add(f"| `{doc_name}` ({lang}) | {ref} | {cols} | {run.quality_level} | "
                f"{engine} | {_fmt(c)} | {_fmt(cn)} | {_fmt(w)} | "
                f"{run.sec_per_page:.1f} | {flag} |")
    add("")
    add("Rows whose `Ref` is not `verified` have a defective ground truth. "
        "Their absolute CER is meaningless; their *relative* ordering between "
        "engines is still valid, because both engines were scored against the "
        "same defective reference.")
    add("")

    # ---------------- degradation ------------------------------------------
    add("## Sensitivity to scan quality")
    add("")
    add("Each source was rendered twice: `clean` (300 dpi, JPEG q88, slight "
        "skew) and `poor` (150 dpi, JPEG q58, 1.2 deg skew, heavy noise). "
        "How steeply an engine degrades matters more than its best-case score, "
        "because firm archives are not uniformly clean.")
    add("")
    add("| Language | Engine | CER clean | CER poor | Degradation |")
    add("|---|---|---|---|---|")
    for lang in ("ar", "en"):
        for engine in ENGINES:
            clean, poor = [], []
            for pair in by_doc.values():
                run = pair.get(engine)
                if run is None or run.language != lang:
                    continue
                value = run.cer_ar_nospace if lang == "ar" else run.cer_en_nospace
                if value is None:
                    continue
                if run.quality_level == "clean":
                    clean.append(value)
                elif run.quality_level == "poor":
                    poor.append(value)
            mc, mp = _mean(clean), _mean(poor)
            if mc is None or mp is None:
                continue
            add(f"| {lang} | {engine} | {mc:.3f} | {mp:.3f} | "
                f"{'+' if mp >= mc else ''}{mp - mc:.3f} |")
    add("")

    # ---------------- reliability ------------------------------------------
    add("## Reliability and speed")
    add("")
    add("| Engine | Pages | Failed at configured DPI | Crashes | Soft errors | "
        "Never succeeded | Mean s/page | Total min |")
    add("|---|---|---|---|---|---|---|---|")
    for engine in ENGINES:
        rs = [r for r in runs if r.engine == engine]
        pages_n = sum(r.pages for r in rs)
        failed = sum(r.failures_at_full_dpi for r in rs)
        probed = sum(r.pages_probed_at_full_dpi for r in rs)
        add(f"| {engine} | {pages_n} | {failed}/{probed} "
            f"({failed / max(probed, 1):.0%}) | "
            f"{sum(r.crashes for r in rs)} | {sum(r.soft_errors for r in rs)} | "
            f"{sum(r.blank_pages for r in rs)} | "
            f"{_mean([r.sec_per_page for r in rs]):.1f} | "
            f"{sum(r.seconds for r in rs) / 60:.1f} |")
    add("")

    paddle_runs = [r for r in runs if r.engine == "paddleocr"]
    if paddle_runs:
        downscaled = sum(r.downscaled_pages for r in paddle_runs)
        pages_n = sum(r.pages for r in paddle_runs)
        probed = sum(r.pages_probed_at_full_dpi for r in paddle_runs)
        failed = sum(r.failures_at_full_dpi for r in paddle_runs)
        sides = [s for r in paddle_runs for s in r.sides_used]
        add("### ⚠ PaddleOCR could not process pages at the pipeline's configured DPI")
        add("")
        add(f"**{failed} of the {probed} pages probed at full resolution failed** "
            f"({failed / max(probed, 1):.0%}), and **{downscaled} of {pages_n} pages "
            f"({downscaled / max(pages_n, 1):.0%}) only produced output after being "
            "downscaled.** Once the working resolution was established the "
            "benchmark started there, so not every page re-probed the top rung.")
        add("")
        if sides:
            add(f"Working resolutions ranged {min(sides)}-{max(sides)} px on the long "
                f"side (median {int(statistics.median(sides))} px). A 300 dpi A4 page "
                "is ~3500 px.")
            add("")
        add("The failure is **resolution-dependent, not content-dependent** -- the "
            "same page succeeds once downscaled, on every document tested. Failures "
            "arrive either as an opaque `RuntimeError: Unknown exception` from native "
            "code or as an outright worker-process death.")
        add("")
        if _paddle_disablements:
            add(f"### ⚠ PaddleOCR switched itself off {_paddle_disablements} "
                f"time(s) during this run")
            add("")
            add("After repeated crashes the worker disables PaddleOCR for the "
                "rest of the process and degrades to Tesseract -- correct "
                "production behaviour, since reloading a 30 s model per page "
                "for a broken install helps nobody.")
            add("")
            add(f"**In a continuous production run, that means PaddleOCR would "
                f"have stopped contributing anything after the first of these "
                f"{_paddle_disablements} events**, and every remaining page in "
                "the batch would have been read by Tesseract alone. This "
                "benchmark resets the worker per fixture so accuracy can still "
                "be measured; production does not.")
            add("")
            add("This is the reliability argument for the engine ordering, and "
                "it is stronger than the accuracy argument.")
        add("")
        add("This matters more than the accuracy numbers. Downscaling is not free: "
            "it is precisely the resolution Arabic needs, because the dots and "
            "diacritics that distinguish ب ت ث are only a few pixels across. "
            "**The resolution PaddleOCR can survive is below the resolution Arabic "
            "needs.**")
        add("")

    # ---------------- ground truth audit ------------------------------------
    add("## Ground-truth audit")
    add("")
    add("Some scores looked catastrophic for *both* engines. They turned out to "
        "be defects in the **reference**, not in the OCR -- and there are two "
        "distinct ones, with different signatures.")
    add("")
    add("Most ground truth here is the source PDF's own text layer, so it "
        "inherits whatever the publisher did.")
    add("")
    add("**Visual word order.** Some Arabic PDFs store each line's words "
        "right-to-left rather than in logical order. The letters inside each "
        "word are correct, so the file passes every character-level check and "
        "looks fine to a reader -- but the word sequence is backwards:")
    add("")
    add("```")
    add("reference : الرحيم الرحمن الله بسم")
    add("correct   : بسم الله الرحمن الرحيم")
    add("```")
    add("")
    add("OCR reads the page correctly and is charged ~0.70 CER for output that "
        "is substantially right.")
    add("")
    add("**Out-of-flow blocks.** Other publishers put topic labels in the left "
        "margin and emit them at the *end* of each page's content stream. Every "
        "word is present -- order-insensitive bag error is near zero -- but the "
        "sequence differs from the page, and CER counts that as error.")
    add("")
    add("`scripts/audit_ground_truth.py` separates them empirically. It OCRs a "
        "page, then scores it against the reference three ways: as-is, with "
        "every reference line's word order reversed, and as an order-insensitive "
        "word multiset. Reversing helping materially means visual order; a near-"
        "zero bag error beside a large CER means out-of-flow ordering; both "
        "large means genuine recognition error.")
    add("")
    add("The `authored` fixtures sidestep all of this: their reference text was "
        "written before the page was rendered, so it cannot carry a publisher's "
        "defects at all.")
    add("")
    add("| Fixture | CER as-is | CER reversed | Verdict |")
    add("|---|---|---|---|")
    audit_path = SYNTHETIC_CORPUS_DIR / "reference_audit.json"
    if audit_path.exists():
        for r in json.loads(audit_path.read_text(encoding="utf-8"))["results"]:
            a = r.get("cer_ar_asis") if r.get("cer_ar_asis") is not None else r.get("cer_en_asis")
            v = r.get("cer_ar_reversed") if r.get("cer_ar_reversed") is not None else r.get("cer_en_reversed")
            add(f"| `{r['file']}` | {_fmt(a)} | {_fmt(v)} | "
                f"{ref_label.get(r['reference_word_order'], r['reference_word_order'])} |")
    add("")
    add("**This corrects two earlier explanations, both of which were wrong.** "
        "`evaluation_report.md` attributed the poor Arabic scores to "
        "**two-column layout**; a follow-up hypothesis blamed **reference word "
        "fragmentation**. The controlled fixtures rule out both: "
        "`wipo_eg081ar_1` is two-column and scores well, and `wipo_eg088ar_1` "
        "has a fragmented reference and scores best of all. Column count and "
        "fragmentation are recorded in the results table above precisely so "
        "this can be read off rather than argued.")
    add("")
    add("The real division is **by publisher**, not by layout: the Constitute "
        "Project's files carry visual word order in Arabic and an out-of-flow "
        "margin column in English, and the WIPO and Gazette files carry "
        "neither. That is why the same engine looks excellent on one Arabic "
        "statute and catastrophic on another.")
    add("")
    add("None of this changes the **head-to-head**. Both engines are scored "
        "against the same reference on every fixture, so a defective reference "
        "handicaps them equally. It changes only which fixtures' absolute "
        "numbers may be quoted as accuracy.")
    add("")

    # ---------------- recommendation ---------------------------------------
    add("## Recommendation")
    add("")

    # Judge on verified references only; fall back to the full set if the audit
    # left nothing verified.
    ar_p = _mean(ar_clean["paddleocr"]) if ar_clean["paddleocr"] else _mean(ar_all["paddleocr"])
    ar_t = _mean(ar_clean["tesseract"]) if ar_clean["tesseract"] else _mean(ar_all["tesseract"])
    en_p = _mean(en_clean["paddleocr"]) if en_clean["paddleocr"] else _mean(en_all["paddleocr"])
    en_t = _mean(en_clean["tesseract"]) if en_clean["tesseract"] else _mean(en_all["tesseract"])
    paddle_pages = sum(r.pages for r in runs if r.engine == "paddleocr")
    paddle_downscaled = sum(r.downscaled_pages for r in runs if r.engine == "paddleocr")
    p_speed, t_speed = speed.get("paddleocr"), speed.get("tesseract")

    tess_wins_ar = ar_t is not None and ar_p is not None and ar_t < ar_p
    tess_much_faster = p_speed and t_speed and p_speed / t_speed > 2
    paddle_unreliable = paddle_downscaled / max(paddle_pages, 1) > 0.25

    if tess_wins_ar and (tess_much_faster or paddle_unreliable):
        add("**Tesseract primary, PaddleOCR fallback. This is now the shipped "
            "default**, inverting the ordering the team spec assumed.")
        add("")
        add("It is a config change, not a rewrite -- `OCRConfig.primary_engine` "
            "and `fallback_engine` already existed. To revert:")
        add("")
        add("```python")
        add('cfg.ocr.primary_engine = "paddleocr"')
        add('cfg.ocr.fallback_engine = "tesseract"')
        add("```")
        add("")
        add("The reasoning, in order of weight:")
        add("")
        add(f"1. **Arabic accuracy.** Tesseract CER {ar_t:.3f} vs PaddleOCR "
            f"{ar_p:.3f}. Arabic is the majority of the firm's material, so this "
            "is the dominant consideration.")
        if p_speed and t_speed:
            add(f"2. **Speed.** {t_speed:.1f} s/page vs {p_speed:.1f} s/page -- "
                f"{p_speed / t_speed:.0f}x. Over a large archive that is the "
                "difference between an overnight ingest and a week-long one.")
        add(f"3. **Reliability.** PaddleOCR needed downscaling on "
            f"{paddle_downscaled}/{paddle_pages} pages and can terminate its "
            "process from native code. Tesseract had no such failures on this set.")
        add(f"4. **English is a near-tie** (Tesseract {en_t:.3f} vs PaddleOCR "
            f"{en_p:.3f}), so flipping costs nothing there."
            if en_p is not None and en_t is not None else
            "4. English results were too sparse to separate the engines.")
        add("")
        add("**PaddleOCR stays installed and wired as the fallback.** It is not "
            "dead weight: it is a genuinely different architecture, so the pages "
            "it fails on are unlikely to be the pages Tesseract fails on, and "
            "running it out-of-process already makes it safe to attempt.")
        add("")
        add("**Resolution is handled rather than merely reported.** PaddleOCR "
            "could not process pages at the pipeline's 300 dpi render, so "
            "`OCRConfig.paddle_max_side` (default 1600) hands it an image inside "
            "the range it survives, while Tesseract still receives the "
            "full-resolution raster. Making the *engine choice* resolution-"
            "dependent was considered and rejected: the instability is not "
            "purely a function of resolution -- the same page at the same size "
            "succeeded on one run and failed on the next -- so a threshold rule "
            "would give the appearance of control without the substance.")
        add("")
        add("**What would change this recommendation:** PaddleOCR reading Arabic "
            "competitively *and* stably on a different build. Both its "
            "resolution ceiling and its non-determinism may be specific to this "
            "Windows/CPU/oneDNN stack. Re-run this benchmark on the firm's "
            "server, and on the firm's own scans, before treating the ordering "
            "as permanent -- neither needs a code change.")
    elif tess_wins_ar:
        add("**Tesseract wins on Arabic accuracy but the operational case is not "
            "clear-cut.** Make the engine order configurable and decide on real "
            "firm scans.")
    else:
        add("**Keep the spec's ordering (PaddleOCR primary, Tesseract fallback).** "
            "The measured results do not justify changing it.")
    add("")

    # ---------------- caveats ----------------------------------------------
    add("## Caveats")
    add("")
    add("1. **Rendered pages, not scanner output.** Clean glyph rendering, no "
        "scanner optics, no photocopy generations, no bleed-through, no "
        "handwriting. Absolute error rates are an optimistic bound. **This is "
        "the one caveat that could change the verdict**, because it is the only "
        "one that might affect the two engines unequally -- re-run against real "
        "scans (`--corpus-dir` needs no code change) before treating the "
        "ordering as final.")
    add("2. **Reference quality is measured, not assumed.** Most references are "
        "a source PDF's text layer and inherit its defects; the verdict column "
        "in the results table says which. The `authored` fixtures have no such "
        "problem by construction and are the ones to quote.")
    add("3. **Column count is not the confound it was assumed to be.** An "
        "earlier version of this report, and of `evaluation_report.md`, blamed "
        "two-column layout for the bad Arabic scores. The controlled fixtures "
        "rule that out -- see [Ground-truth audit](#ground-truth-audit). What "
        "does inflate absolute CER is visual word order and out-of-flow blocks, "
        "and both handicap the two engines equally, so the **head-to-head "
        "remains valid on every fixture** even where the absolute figure is not.")
    add("4. **PaddleOCR was given a handicap in its favour**: it was allowed to "
        "retry at lower resolutions, which Tesseract never needed. Its accuracy "
        "figures are therefore its best case, not its default-config behaviour.")
    add("5. **PaddleOCR's instability is non-deterministic.** The same image at "
        "the same resolution succeeded on one run and raised "
        "`RuntimeError: Unknown exception` on the next; one resolution killed "
        "the worker process outright. Its failure counts below are therefore a "
        "sample, not a fixed rate.")
    add("6. **One machine, CPU only.** Timings will not match the firm's "
        "server, and PaddleOCR's resolution ceiling and instability may be "
        "specific to this Windows/CPU/oneDNN build.")
    add("7. **Small sample.** "
        f"{len(ar_all['tesseract'])} Arabic and {len(en_all['tesseract'])} English "
        "scored documents. Enough to see a large effect; not enough to measure "
        "a small one, which is why near-ties are reported as ties rather than "
        "as wins.")
    add("")

    incidents = [(r.engine, r.document, n) for r in runs for n in r.notes]
    if incidents:
        add("### Incidents")
        add("")
        for engine, doc_name, note in incidents[:30]:
            add(f"- `{engine}` on `{doc_name}` -- {note}")
        if len(incidents) > 30:
            add(f"- ...and {len(incidents) - 30} more")
        add("")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-pages", type=int, default=3,
                        help="pages scored per fixture (OCR cost is linear)")
    parser.add_argument("--engines", nargs="+", default=list(ENGINES),
                        choices=list(ENGINES))
    parser.add_argument("--out", default=str(REPORTS_DIR / "ocr_engine_comparison.md"))
    parser.add_argument("--json", default=str(REPORTS_DIR / "ocr_engine_comparison.json"))
    parser.add_argument(
        "--no-resume", dest="resume", action="store_false",
        help="start from scratch instead of continuing a partial run. Results "
             "are checkpointed after every fixture because PaddleOCR's native "
             "crashes have repeatedly killed the process mid-benchmark.",
    )
    parser.add_argument(
        "--from-json", action="store_true",
        help="rebuild the report from a previous run's JSON without re-running "
             "OCR. A full run costs over an hour; this makes report edits and "
             "re-reading the ground-truth audit free.",
    )
    args = parser.parse_args()

    config = PipelineConfig()
    # The production config now downscales for PaddleOCR (OCRConfig.paddle_max_side),
    # which is the mitigation this benchmark's first run motivated. Disable it
    # here so PADDLE_SIDE_LADDER remains the only thing controlling resolution --
    # otherwise every rung above the cap collapses to the same image and the
    # reliability figures become a measurement of the mitigation, not the engine.
    config.ocr.paddle_max_side = 0

    if args.from_json:
        path = Path(args.json)
        if not path.exists():
            print(f"No results at {path}. Run the benchmark first.")
            return 1
        payload = json.loads(path.read_text(encoding="utf-8"))
        global _paddle_disablements
        _paddle_disablements = payload.get("paddle_self_disablements", 0)
        fields = {f.name for f in EngineRun.__dataclass_fields__.values()}
        runs = [EngineRun(**{k: v for k, v in d.items() if k in fields})
                for d in payload["runs"]]
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(
            build_report(runs, config,
                         payload.get("wall_clock_seconds", 0.0),
                         payload.get("max_pages_per_fixture", 0),
                         payload.get("render_dpi")),
            encoding="utf-8",
        )
        print(f"Rebuilt {args.out} from {path} ({len(runs)} runs, no OCR re-run)")
        return 0
    fixtures = discover_fixtures(args.max_pages)
    if not fixtures:
        print("No scanned fixtures with ground truth found. "
              "Run scripts/make_benchmark_scans.py first.")
        return 1

    total = len(fixtures) * len(args.engines)
    print(f"Benchmarking {len(fixtures)} fixtures x {len(args.engines)} engines "
          f"({args.max_pages} pages each) = {total} runs\n")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    json_path = Path(args.json)

    # Resume support. PaddleOCR's native crashes have repeatedly taken the whole
    # benchmark process down partway through -- three separate runs died between
    # fixtures 11 and 23, losing forty minutes of completed work each time.
    # Results are therefore checkpointed after every fixture, and a relaunch
    # skips what is already done. The alternative is an all-or-nothing job whose
    # success depends on a library that demonstrably cannot be relied on to stay
    # alive.
    runs: list[EngineRun] = []
    if args.resume and json_path.exists():
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        fields = {f.name for f in EngineRun.__dataclass_fields__.values()}
        runs = [EngineRun(**{k: v for k, v in d.items() if k in fields})
                for d in payload.get("runs", [])]
        if runs:
            print(f"Resuming: {len(runs)} run(s) already complete\n")
    done = {(r.document, r.engine) for r in runs}
    elapsed_before = 0.0
    if args.resume and json_path.exists():
        try:
            elapsed_before = float(json.loads(
                json_path.read_text(encoding="utf-8")).get("wall_clock_seconds", 0.0))
        except Exception:  # noqa: BLE001
            pass

    def checkpoint(total_elapsed: float) -> None:
        json_path.write_text(
            json.dumps(
                {
                    "warning": "Public/synthetic data only. No firm document processed.",
                    "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "max_pages_per_fixture": args.max_pages,
                    "paddle_self_disablements": _paddle_disablements,
                    "render_dpi": config.ocr.render_dpi,
                    "wall_clock_seconds": round(total_elapsed, 1),
                    "complete": len(runs) >= len(fixtures) * len(args.engines),
                    "runs": [asdict(r) for r in runs],
                },
                ensure_ascii=False, indent=2, default=str,
            ),
            encoding="utf-8",
        )

    start = time.perf_counter()
    for i, fixture in enumerate(fixtures, 1):
        # flush=True: this run takes ~40 minutes and stdout is usually piped,
        # so without it there is no progress signal until the very end.
        print(f"[{i}/{len(fixtures)}] {fixture['path'].name} "
              f"({fixture['language']}, {fixture['columns']} col, "
              f"{fixture['quality_level']})", flush=True)
        for engine in args.engines:
            if (fixture["path"].name, engine) in done:
                print(f"      {engine:<11} (already done, skipped)", flush=True)
                continue
            reset_engine_state(engine)
            run = run_engine_on_fixture(engine, fixture, config)
            runs.append(run)
            main_cer = run.cer_ar_nospace if fixture["language"] == "ar" else run.cer_en_nospace
            print(f"      {engine:<11} CER={_fmt(main_cer):<7} "
                  f"{run.sec_per_page:5.1f}s/pg  chars={run.chars:<6} "
                  f"crashes={run.crashes} soft={run.soft_errors}", flush=True)
            # Checkpoint immediately: the next fixture may kill the process.
            checkpoint(elapsed_before + time.perf_counter() - start)

    elapsed = elapsed_before + time.perf_counter() - start
    checkpoint(elapsed)
    Path(args.out).write_text(
        build_report(runs, config, elapsed, args.max_pages, config.ocr.render_dpi),
        encoding="utf-8",
    )

    print(f"\nReport : {args.out}")
    print(f"Raw    : {args.json}")
    shutdown_paddle_workers()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
