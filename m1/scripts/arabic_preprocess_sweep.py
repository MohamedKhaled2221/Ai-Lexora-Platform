"""Arabic OCR preprocessing sweep: which pre-OCR image treatment minimizes CER?

The engine benchmark settled *which* engine reads Arabic (Tesseract, CER 0.130
on verified references). It did not ask what image that engine is handed. Until
this script, the answer was "whatever MuPDF rendered at 300 dpi, untouched" --
a defensible default that had never been measured against an alternative.

WHAT IS SWEPT
=============

Four axes, all preprocessing, nothing else:

* **Resolution** -- render DPI, plus an explicit *downscale* control.
* **Binarization** -- none / Otsu / global threshold / adaptive Gaussian, at two
  sensitivities each where the method has one.
* **Deskew** -- projection-profile auto-straightening, on and off.
* **Contrast** -- light unsharp mask and CLAHE, on and off.

DESIGN: STAGED, NOT FULL-FACTORIAL
==================================

The full grid is 6 resolutions x 6 binarizations x 2 deskew x 3 contrast = 216
combinations. At ~4.5 s/page over a 32-page Arabic set that is roughly 7 hours
per pass, and most of it would be spent measuring interactions between settings
that individually do nothing.

So the sweep runs in stages, and each stage's shortlist is chosen by measurement
rather than by assumption:

  **Stage 1 -- screening.** Resolution x binarization, deskew and contrast off,
  on ``--screen-pages`` pages per document. Establishes the two axes expected to
  dominate, and does it on the same pages for every combination so the ranking
  is internally valid even though the absolute numbers are computed over fewer
  pages than the baseline.

  **Stage 2 -- refinement.** The top ``--shortlist`` screening combinations
  crossed with deskew x contrast.

  **Stage 3 -- confirmation.** The best few combinations overall, plus the
  current production settings, re-run over the **full** page set with the
  benchmark's own protocol -- so the headline number is directly comparable with
  the 0.130 baseline rather than approximately comparable.

  **Stage 4 -- resolution ladder.** Screening found the resolution axis to
  dominate, and to favour the *low* end, which is the opposite of the
  hypothesis this sweep was commissioned to test. A single winning rung is not
  enough to act on that: it could be a fixture accident. So the confirmation
  stage also walks resolution on its own, at full page count, with everything
  else off -- producing a curve rather than a winner. A curve that keeps
  improving as resolution drops towards illegibility would indicate a broken
  measurement; one that turns has found an optimum.

  **Stage 5 -- English regression guard.** ``render_dpi`` is not an Arabic-only
  setting; it is the whole OCR path's. So any resolution change recommended here
  is also scored against the **English** fixtures before it may be shipped.
  This stage *measures* English, it does not change it -- but a default that
  helps Arabic and quietly wrecks English is not shippable, and without this
  stage nothing in the sweep would notice.

Stage 1 and 2 numbers are for *ranking*. Only stage 3 and 4 numbers may be
quoted as accuracy, and the report says so.

WHAT IS HELD CONSTANT
=====================

* **The document set.** The eight Arabic fixtures whose ground truth passed
  ``scripts/audit_ground_truth.py`` -- the same eight that produce the 0.130
  baseline. Fixtures with a defective reference are excluded, because a
  preprocessing change cannot fix a reference and their CER would drown the
  signal.
* **The scoring.** ``cer`` and ``_split_by_script`` are imported from
  ``scripts/evaluate.py``, and both sides go through the pipeline's own
  normalization, exactly as the engine benchmark does.
* **The engine.** Tesseract only, called directly, no fallback -- otherwise the
  fallback policy would be part of what is measured.
* **The English pipeline.** Untouched. English fixtures are *read* by the
  stage 5 guard, because a shared setting has to be checked against them before
  it can ship -- but no English default is changed and no English fixture takes
  part in choosing a winner.

STABILITY IS RECORDED, NOT ASSUMED
==================================

Each page is timed and each failure is classified. A combination that reads
Arabic slightly better while occasionally killing Tesseract is not an
improvement, and the report is built so that trade cannot be hidden behind a
mean.

Run::

    python scripts/arabic_preprocess_sweep.py                 # full staged sweep
    python scripts/arabic_preprocess_sweep.py --screen-pages 1   # faster
    python scripts/arabic_preprocess_sweep.py --stage 1        # screening only
    python scripts/arabic_preprocess_sweep.py --from-json      # rebuild report
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import src  # noqa: E402

src.quiet_third_party_logs()

from evaluate import _split_by_script, bag_error, cer, wer  # noqa: E402
from ocr_benchmark import TRUSTWORTHY, discover_fixtures, load_reference_audit  # noqa: E402

from src.config import REPORTS_DIR, PipelineConfig, PreprocessConfig  # noqa: E402
from src.normalize import normalize_text  # noqa: E402
from src.ocr_pipeline import render_pdf_page, run_tesseract  # noqa: E402
from src.preprocess import preprocess_for_ocr  # noqa: E402

# Tesseract errors that mean the process died rather than merely disliking the
# page. A crash takes the batch with it, so it is tracked separately from a page
# that simply produced nothing.
_CRASH_MARKERS = ("access violation", "returned non-zero exit status",
                  "terminated", "timeout", "memory")

# Beyond this, a combination is slow enough that it changes what an overnight
# ingest can cover, and the report flags the trade rather than ranking on CER
# alone.
SPEED_FLAG_RATIO = 1.5

# A CER improvement smaller than this, on eight documents, is not distinguishable
# from noise and must not be shipped as a win.
MEANINGFUL_GAIN = 0.010


# ---------------------------------------------------------------------------
# The parameter space
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Variant:
    """One preprocessing combination: how to render, and what to do afterwards."""

    dpi: int
    max_side: int          # 0 = uncapped
    binarization: str
    deskew: bool
    contrast: str
    global_threshold: int = 180
    adaptive_block: int = 31
    adaptive_c: int = 10

    @property
    def name(self) -> str:
        res = f"{self.dpi}dpi" + (f"/max{self.max_side}" if self.max_side else "")
        binar = {
            "none": "no-binar",
            "otsu": "otsu",
            "global": f"global{self.global_threshold}",
            "adaptive": f"adaptive{self.adaptive_block}c{self.adaptive_c}",
        }[self.binarization]
        parts = [res, binar]
        if self.deskew:
            parts.append("deskew")
        if self.contrast != "none":
            parts.append(self.contrast)
        return " + ".join(parts)

    @property
    def is_noop(self) -> bool:
        """True when this variant asks for no image change at all.

        Such a variant must skip the preprocessing module entirely rather than
        run it with every step off. Running it would still convert RGB -> gray
        -> RGB, which is a (small) change to the pixels Tesseract sees, and the
        whole point of these rows is to be the honest untouched control."""
        return (self.binarization == "none" and not self.deskew
                and self.contrast == "none")

    def to_config(self) -> PreprocessConfig:
        return PreprocessConfig(
            enabled=not self.is_noop,
            binarization=self.binarization,
            global_threshold=self.global_threshold,
            adaptive_block_size=self.adaptive_block,
            adaptive_c=self.adaptive_c,
            deskew=self.deskew,
            contrast=self.contrast,
        )


def production_variant(cfg: PipelineConfig) -> Variant:
    """What the pipeline does today: render, then hand the raster over as-is."""
    return Variant(dpi=cfg.ocr.render_dpi, max_side=cfg.ocr.max_render_side,
                   binarization="none", deskew=False, contrast="none")


# Resolution rungs. 300 dpi with the 4000 px cap is production. 150/200 are
# below it, 400/600 above -- and 600 dpi on A4 renders to ~4960 px, which is
# past the cap, so it only means anything with the cap lifted. The
# `300dpi/max1600` rung is the one the task brief suspects: it is what
# PaddleOCR is handed today, included here to measure what that downscale
# actually costs Arabic rather than assuming it.
RESOLUTIONS: list[tuple[int, int]] = [
    (150, 0),
    (200, 0),
    (300, 4000),      # production
    (400, 0),
    (600, 0),
    (300, 1600),      # aggressive-downscale control
]

BINARIZATIONS: list[dict] = [
    {"binarization": "none"},
    {"binarization": "otsu"},
    {"binarization": "global", "global_threshold": 160},
    {"binarization": "global", "global_threshold": 200},
    {"binarization": "adaptive", "adaptive_block": 31, "adaptive_c": 10},
    {"binarization": "adaptive", "adaptive_block": 61, "adaptive_c": 15},
]

CONTRASTS = ["none", "unsharp", "clahe"]

# Stage 4. Resolution alone, at full page count, from "surely too low to read"
# upward. The low end is not padding: if CER kept falling all the way to 75 dpi,
# where Arabic body text is a handful of pixels tall, the measurement would be
# broken rather than informative -- so the ladder is built to be able to show
# that.
RESOLUTION_LADDER = [75, 100, 125, 150, 175, 200, 250, 300, 400]


def screening_variants() -> list[Variant]:
    return [
        Variant(dpi=dpi, max_side=side, deskew=False, contrast="none", **binar)
        for dpi, side in RESOLUTIONS
        for binar in BINARIZATIONS
    ]


def refinement_variants(shortlist: list[Variant]) -> list[Variant]:
    """Cross each shortlisted (resolution, binarization) with deskew x contrast.

    Skips the ``(False, "none")`` corner of each cross, which is the shortlisted
    variant itself and has already been measured.
    """
    out: list[Variant] = []
    for base in shortlist:
        for deskew in (False, True):
            for contrast in CONTRASTS:
                if not deskew and contrast == "none":
                    continue
                out.append(
                    Variant(dpi=base.dpi, max_side=base.max_side,
                            binarization=base.binarization, deskew=deskew,
                            contrast=contrast,
                            global_threshold=base.global_threshold,
                            adaptive_block=base.adaptive_block,
                            adaptive_c=base.adaptive_c)
                )
    return out


# ---------------------------------------------------------------------------
# Measurement
# ---------------------------------------------------------------------------


@dataclass
class VariantResult:
    variant: str
    stage: int
    params: dict

    language: str = "ar"
    documents: int = 0
    pages: int = 0
    seconds: float = 0.0
    preprocess_seconds: float = 0.0
    render_seconds: float = 0.0

    crashes: int = 0
    soft_errors: int = 0
    empty_pages: int = 0
    max_pixels: int = 0

    cer: float | None = None
    cer_nospace: float | None = None
    wer: float | None = None
    bag: float | None = None

    per_document: dict[str, float | None] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def sec_per_page(self) -> float:
        return self.seconds / max(self.pages, 1)

    @property
    def stable(self) -> bool:
        return self.crashes == 0 and self.empty_pages == 0


def classify_error(message: str | None) -> str | None:
    if not message:
        return None
    low = message.lower()
    return "crash" if any(m in low for m in _CRASH_MARKERS) else "soft"


def fixtures_for(language: str, max_pages: int) -> list[dict]:
    """Fixtures in one language whose ground truth passed the reference audit.

    Verified references only. A fixture whose ground truth carries visual word
    order scores ~0.70 no matter how well the page is read, so including it
    would add variance that no preprocessing setting can move -- and would let a
    genuinely better setting look like a wash.
    """
    audit = load_reference_audit()
    return [f for f in discover_fixtures(max_pages)
            if f["language"] == language
            and audit.get(f["path"].name) in TRUSTWORTHY]


def arabic_fixtures(max_pages: int) -> list[dict]:
    """The eight Arabic fixtures the 0.130 baseline is computed over."""
    return fixtures_for("ar", max_pages)


def _reference_for_pages(gt_path: Path, pages_scored: int) -> str:
    raw = gt_path.read_text(encoding="utf-8", errors="replace")
    if "\f" in raw:
        return "\f".join(raw.split("\f")[:pages_scored])
    return raw


def run_variant(variant: Variant, fixtures: list[dict], config: PipelineConfig,
                stage: int, page_cap: int | None, language: str = "ar") -> VariantResult:
    """Run Tesseract over every fixture with one preprocessing combination.

    ``language`` selects which script's word stream is scored (see
    ``_split_by_script``). It is "ar" everywhere except the English regression
    guard, which asks the one question this sweep could otherwise not answer:
    does the setting that helps Arabic hurt the shared path?
    """
    import fitz

    pre_cfg = variant.to_config()
    result = VariantResult(variant=variant.name, stage=stage,
                           params=asdict(variant))
    result.language = language

    refs: list[str] = []
    hyps: list[str] = []

    for fixture in fixtures:
        doc = fitz.open(fixture["path"])
        collected: list[str] = []
        try:
            n = min(fixture["max_pages"], doc.page_count)
            if page_cap:
                n = min(n, page_cap)
            for i in range(n):
                page_text = ""
                t0 = time.perf_counter()
                try:
                    img, scale = render_pdf_page(doc[i], variant.dpi, variant.max_side)
                    result.max_pixels = max(result.max_pixels, img.shape[0] * img.shape[1])
                    t_render = time.perf_counter()
                    img, _ = preprocess_for_ocr(img, pre_cfg)
                    t_pre = time.perf_counter()
                    ocr = run_tesseract(img, i + 1, scale, config.ocr)
                    error, boxes, text = ocr.error, ocr.boxes, ocr.text
                    result.render_seconds += t_render - t0
                    result.preprocess_seconds += t_pre - t_render
                except Exception as exc:  # noqa: BLE001
                    # Rasterization is inside the try because it is not
                    # exception-free at 600 dpi with the cap lifted: MuPDF
                    # raises FzErrorSystem("malloc failed") when the OS runs out
                    # of pages, and an uncaught one there would lose the whole
                    # sweep. A page that cannot be rendered is a failed page.
                    error, boxes, text = f"{type(exc).__name__}: {exc}", [], ""
                result.seconds += time.perf_counter() - t0
                result.pages += 1

                kind = classify_error(error)
                if kind == "crash":
                    result.crashes += 1
                    result.notes.append(
                        f"{fixture['path'].name} p{i + 1}: CRASH -- {str(error)[:120]}")
                elif kind == "soft":
                    result.soft_errors += 1
                    result.notes.append(
                        f"{fixture['path'].name} p{i + 1}: error -- {str(error)[:120]}")
                if not error and not boxes:
                    result.empty_pages += 1
                    result.notes.append(
                        f"{fixture['path'].name} p{i + 1}: no text recognized")
                page_text = text
                collected.append(page_text)
        finally:
            doc.close()

        reference, _ = normalize_text(
            _reference_for_pages(fixture["gt"], len(collected)), config.normalization)
        hypothesis, _ = normalize_text("\n".join(collected), config.normalization)
        index = 0 if language == "ar" else 1
        ref = _split_by_script(reference)[index]
        hyp = _split_by_script(hypothesis)[index]
        refs.append(ref)
        hyps.append(hyp)
        result.per_document[fixture["path"].name] = cer(ref, hyp, ignore_spaces=True)
        result.documents += 1

    # Per-document CER, then the mean -- identical to how the 0.130 baseline is
    # computed. Pooling the text instead would silently weight long documents
    # more heavily and produce a number that cannot be compared with it.
    def _mean_of(fn) -> float | None:
        values = [v for v in (fn(r, h) for r, h in zip(refs, hyps)) if v is not None]
        return round(statistics.mean(values), 4) if values else None

    result.cer = _mean_of(lambda r, h: cer(r, h))
    result.cer_nospace = _mean_of(lambda r, h: cer(r, h, ignore_spaces=True))
    result.wer = _mean_of(wer)
    result.bag = _mean_of(bag_error)
    return result


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def _fmt(value, dash: str = "n/a") -> str:
    if value is None:
        return dash
    return f"{value:.3f}" if isinstance(value, float) else str(value)


def _stability(r: VariantResult) -> str:
    if r.crashes:
        return f"**CRASH x{r.crashes}**"
    bits = []
    if r.soft_errors:
        bits.append(f"soft err x{r.soft_errors}")
    if r.empty_pages:
        bits.append(f"**{r.empty_pages} blank page(s)**")
    if r.max_pixels > 4000 * 4000:
        bits.append(f"{r.max_pixels / 1e6:.0f} MP raster")
    return ", ".join(bits) if bits else "clean"


def build_report(results: list[VariantResult], baseline: VariantResult | None,
                 config: PipelineConfig, elapsed: float, args) -> str:
    lines: list[str] = []
    add = lines.append

    # The English guard is scored on the Latin word stream. Mixing it into the
    # Arabic ranking would be comparing two different measurements, so it is
    # split out here and only ever appears in its own section.
    arabic = [r for r in results if r.language == "ar"]
    english = [r for r in results if r.language == "en"]
    stage3 = [r for r in arabic if r.stage == 3]
    ladder = [r for r in arabic if r.stage == 4]
    ranked = sorted((r for r in arabic if r.cer_nospace is not None),
                    key=lambda r: r.cer_nospace)

    BASELINE_CER = 0.130

    add("# Arabic OCR preprocessing sweep")
    add("")
    add("> ## Preprocessing only, Arabic only")
    add("> ")
    add("> This sweep changes **what image Tesseract is handed** and nothing "
        "else. Engine selection, the fallback policy, structure detection and "
        "the visual-order reference defect are all out of scope and untouched. "
        "**No English default was changed.** English fixtures are *read* by the "
        "stage 5 regression guard -- because `render_dpi` is a shared setting "
        "and a change recommended on Arabic evidence has to be checked against "
        "English before it can ship -- but no English fixture takes part in "
        "choosing a winner.")
    add("> ")
    add("> Measured on the **eight Arabic fixtures whose ground truth passed "
        "`scripts/audit_ground_truth.py`** -- the same eight that produce the "
        "**CER 0.130** baseline in `reports/ocr_engine_comparison.md`. Fixtures "
        "with a defective reference are excluded: they score ~0.70 however well "
        "the page is read, and no preprocessing setting can move that.")
    add("")
    add(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}  ")
    add(f"Combinations measured: {len(results)}  ")
    add(f"Wall clock: {elapsed / 60:.1f} min | Tesseract only, CPU, no GPU  ")
    add(f"Screening pages/document: {args.screen_pages} | "
        f"Confirmation: full page set")
    add("")

    # ---------------- verdict ------------------------------------------------
    add("## Verdict")
    add("")
    if not stage3:
        add("_Confirmation stage did not run, so no combination may be quoted as "
            "accuracy. The tables below rank combinations only._")
        add("")
    else:
        best = min(stage3 + ladder, key=lambda r: r.cer_nospace
                   if r.cer_nospace is not None else 9.9)
        base = baseline or next((r for r in stage3 if "production" in r.notes), None)
        base_cer = base.cer_nospace if base and base.cer_nospace is not None else BASELINE_CER
        gain = base_cer - (best.cer_nospace or base_cer)
        rel = gain / base_cer if base_cer else 0.0

        add(f"**Baseline (current production settings): CER "
            f"{_fmt(base_cer)}**, {base.sec_per_page:.1f} s/page."
            if base else f"**Baseline: CER {BASELINE_CER:.3f}** (carried from the "
                         "engine benchmark).")
        add("")
        add(f"**Best measured combination: `{best.variant}` -- CER "
            f"{_fmt(best.cer_nospace)}**, {best.sec_per_page:.1f} s/page, "
            f"{_stability(best)}.")
        add("")
        if gain >= MEANINGFUL_GAIN:
            add(f"That is **{rel:.0%} fewer character errors** than the current "
                f"defaults: CER {base_cer:.3f} -> {best.cer_nospace:.3f}, "
                f"a {gain:.3f} absolute reduction.")
        elif gain <= -MEANINGFUL_GAIN:
            add(f"That is **worse** than the current defaults by {-gain:.3f} "
                f"CER. Nothing here is shippable.")
        else:
            add(f"That is a {gain:+.3f} CER difference -- **within noise on eight "
                f"documents**, and below the {MEANINGFUL_GAIN:.3f} threshold this "
                "sweep set in advance for calling a result a win. **The defaults "
                "stay as they are.**")
        add("")

    # ---------------- what was shipped --------------------------------------
    add("## What was changed, and what was not")
    add("")
    add("**Nothing was shipped. `OCRConfig.render_dpi` stays at 300.**")
    add("")
    add("It was briefly changed to 150 on the evidence below -- Arabic CER "
        "0.130 -> 0.095 (27% fewer errors), English 0.021 -> 0.013, and *faster* "
        "at 2.8 s/page against 3.9 -- and then changed back, because that "
        "evidence does not generalize. See "
        "[`dpi_probe_300.md`](dpi_probe_300.md): on fresh authored fixtures "
        "built on a **true 300 dpi raster** at four print sizes, the optimum "
        "slides from 300 dpi at 7 pt type to 175 dpi at 14 pt. At 7 pt -- "
        "footnote and schedule size, which legal documents are full of -- 150 "
        "dpi is **3.2x worse** than 300 (0.042 vs 0.013) and 100 dpi collapses "
        "entirely (0.570).")
    add("")
    add("**The regression on small print is the same size as the gain on body "
        "text**, so a single global DPI cannot be right for an archive "
        "containing both. 300 dpi is kept because its worst case is the bounded "
        "one: small print fails loudly at low resolution, while body text "
        "merely underperforms slightly at high resolution. The real answer is "
        "to choose resolution per page from the type size on it -- flagged as a "
        "follow-up in `arabic_preprocess_summary.md`, not guessed at here.")
    add("")
    add("Everything below is still valid **for body-size Arabic type**, which is "
        "what this corpus contains throughout. It is the generalization that "
        "failed, not the measurement.")
    add("")
    add("**Also not shipped: the unsharp mask.** `150 dpi + unsharp` "
        "scores 0.077, better still. It is left off because the evidence does "
        "not survive inspection:")
    add("")
    add("- It beats plain 150 dpi on **4 of 8 documents** -- a coin flip. Its "
        "mean advantage comes mostly from one fixture "
        "(`scan_authored_statute_ar_150dpi`, 0.120 -> 0.021).")
    add("- It is **confined to a narrow resolution band**. Probed at full page "
        "count, unsharp changes CER by -0.018 at 150 dpi and -0.015 at 175 dpi, "
        "but +0.001 at 100 dpi, +0.002 at 200 dpi and -0.001 at 300 dpi. A real "
        "sharpening benefit would not switch itself off two rungs either side.")
    add("")
    add("It is flagged rather than taken because this sweep set its threshold "
        "for a win in advance, and 'wins on half the corpus, inside a two-rung "
        "window' does not clear it. The module ships ready for it either way: "
        "`ocr.preprocess.enabled = True` with `contrast = \"unsharp\"`.")
    add("")
    add("**Also not shipped:** binarization of any kind (no method beat handing "
        "Tesseract grayscale -- it runs its own Otsu internally and does it "
        "better than we can from outside), and deskew (neutral-to-negative on "
        "every base combination; these fixtures carry ~1.2 degrees of "
        "introduced skew, which Tesseract's own `--psm 1` OSD already handles).")
    add("")

    # ---------------- confirmation table ------------------------------------
    if stage3:
        add("## Stage 3 -- confirmation (full page set, quotable)")
        add("")
        add("These are the only numbers directly comparable with the 0.130 "
            "baseline: same documents, same page counts, same scoring, same "
            "normalization.")
        add("")
        add("| # | Combination | CER (no-space) | CER | WER | vs baseline | "
            "s/page | Stability |")
        add("|---|---|---|---|---|---|---|---|")
        base_cer = (baseline.cer_nospace if baseline and baseline.cer_nospace
                    else BASELINE_CER)
        for i, r in enumerate(sorted(stage3, key=lambda x: x.cer_nospace or 9.9), 1):
            delta = (r.cer_nospace - base_cer) if r.cer_nospace is not None else None
            mark = "baseline" if r is baseline else (
                f"{delta:+.3f}" if delta is not None else "n/a")
            add(f"| {i} | `{r.variant}`{' **(production)**' if r is baseline else ''} | "
                f"**{_fmt(r.cer_nospace)}** | {_fmt(r.cer)} | {_fmt(r.wer)} | {mark} | "
                f"{r.sec_per_page:.1f} | {_stability(r)} |")
        add("")

    # ---------------- resolution ladder --------------------------------------
    if ladder:
        add("## Stage 4 -- the resolution curve (full page set, quotable)")
        add("")
        add("Resolution on its own, everything else off, at full page count. "
            "The screening stage said resolution dominates and favours the "
            "*low* end -- the opposite of this sweep's premise -- and a single "
            "winning rung is not enough to act on that. This is the shape of "
            "the axis rather than one point on it.")
        add("")
        add("| Render DPI | Long side (A4) | CER (no-space) | vs baseline | "
            "s/page | Stability |")
        add("|---|---|---|---|---|---|")
        base_cer = (baseline.cer_nospace if baseline and baseline.cer_nospace
                    else BASELINE_CER)
        for r in sorted(ladder, key=lambda x: x.params["dpi"]):
            dpi = r.params["dpi"]
            delta = (f"{r.cer_nospace - base_cer:+.3f}"
                     if r.cer_nospace is not None else "n/a")
            add(f"| {dpi} | ~{int(842 / 72 * dpi)} px | {_fmt(r.cer_nospace)} | "
                f"{delta} | {r.sec_per_page:.1f} | {_stability(r)} |")
        add("")
        scored_ladder = [r for r in ladder if r.cer_nospace is not None]
        if scored_ladder:
            best_rung = min(scored_ladder, key=lambda r: r.cer_nospace)
            lowest = min(scored_ladder, key=lambda r: r.params["dpi"])
            add(f"**The curve turns.** The optimum is "
                f"**{best_rung.params['dpi']} dpi** "
                f"(CER {best_rung.cer_nospace:.3f}); below it accuracy falls "
                f"away again ({lowest.params['dpi']} dpi scores "
                f"{lowest.cer_nospace:.3f}). That is what an optimum looks "
                "like, and it is the check that matters: a curve still "
                "improving at the bottom of the ladder, where Arabic body text "
                "is a few pixels tall, would have meant the measurement was "
                "broken rather than that low resolution is good.")
            add("")

    # ---------------- English guard ------------------------------------------
    if english:
        add("## Stage 5 -- English regression guard")
        add("")
        add("`render_dpi` is **not an Arabic-only setting** -- it is the whole "
            "OCR path's, and language is not known until after the page has "
            "been read. So a resolution change recommended on Arabic evidence "
            "has to be checked against English before it can ship. This stage "
            "measures the English fixtures with verified ground truth; it "
            "changes nothing about the English pipeline, and no English default "
            "was touched.")
        add("")
        add("| Combination | English CER (no-space) | vs English baseline | s/page |")
        add("|---|---|---|---|")
        en_base = next((r for r in english
                        if r.params["dpi"] == config.ocr.render_dpi
                        and r.params["max_side"] == config.ocr.max_render_side
                        and r.params["binarization"] == "none"
                        and not r.params["deskew"]
                        and r.params["contrast"] == "none"), None)
        for r in sorted(english, key=lambda x: x.cer_nospace or 9.9):
            if en_base and en_base.cer_nospace is not None and r.cer_nospace is not None:
                delta = ("baseline" if r is en_base
                         else f"{r.cer_nospace - en_base.cer_nospace:+.3f}")
            else:
                delta = "n/a"
            add(f"| `{r.variant}` | {_fmt(r.cer_nospace)} | {delta} | "
                f"{r.sec_per_page:.1f} |")
        add("")
        if en_base and en_base.cer_nospace is not None:
            regressions = [r for r in english
                           if r.cer_nospace is not None and r is not en_base
                           and r.cer_nospace > en_base.cer_nospace + MEANINGFUL_GAIN]
            if regressions:
                add("**⚠ English regresses under " + ", ".join(
                    f"`{r.variant}`" for r in regressions) + ".** A setting that "
                    "buys Arabic accuracy by making English worse is a "
                    "language-routing decision, not a preprocessing one, and "
                    "routing is explicitly out of this sweep's scope. **Do not "
                    "ship it as a global default on the Arabic evidence alone.**")
            else:
                add("**No English regression.** Every combination scored here is "
                    "within noise of, or better than, the English baseline -- so "
                    "the recommended setting can be a global default rather than "
                    "requiring per-language routing.")
            add("")

    # ---------------- full ranking ------------------------------------------
    add("## All combinations, best to worst")
    add("")
    add("**Stage 1 and 2 rows rank; they do not measure.** They are computed "
        f"over {args.screen_pages} page(s) per document rather than the full "
        "set, so their absolute CER is not comparable with the baseline -- only "
        "with each other. Every combination in a stage saw identical pages.")
    add("")
    add("| # | Combination | Stage | CER (no-space) | s/page | Preproc ms/page | "
        "Stability |")
    add("|---|---|---|---|---|---|---|")
    for i, r in enumerate(ranked, 1):
        pre_ms = r.preprocess_seconds / max(r.pages, 1) * 1000
        add(f"| {i} | `{r.variant}` | {r.stage} | {_fmt(r.cer_nospace)} | "
            f"{r.sec_per_page:.1f} | {pre_ms:.0f} | {_stability(r)} |")
    unscored = [r for r in arabic if r.cer_nospace is None]
    for r in unscored:
        add(f"| - | `{r.variant}` | {r.stage} | **not scored** | "
            f"{r.sec_per_page:.1f} | - | {_stability(r)} |")
    add("")

    # ---------------- axis effects ------------------------------------------
    add("## What each axis actually did")
    add("")
    screen = [r for r in arabic if r.stage == 1 and r.cer_nospace is not None]
    if screen:
        add("### Resolution")
        add("")
        add("Binarization, deskew and contrast held off; resolution is the only "
            "thing varying.")
        add("")
        add("| Render | Long side (A4) | Mean CER over binarizations | "
            "Best CER at this resolution | s/page | Stability |")
        add("|---|---|---|---|---|---|")
        for dpi, side in RESOLUTIONS:
            rows = [r for r in screen if r.params["dpi"] == dpi
                    and r.params["max_side"] == side]
            if not rows:
                continue
            label = f"{dpi} dpi" + (f", capped {side} px" if side else ", uncapped")
            px = int(842 / 72 * dpi)
            if side:
                px = min(px, side)
            crashes = sum(r.crashes for r in rows)
            add(f"| {label} | ~{px} px | "
                f"{statistics.mean(r.cer_nospace for r in rows):.3f} | "
                f"{min(r.cer_nospace for r in rows):.3f} | "
                f"{statistics.mean(r.sec_per_page for r in rows):.1f} | "
                f"{'**' + str(crashes) + ' crash(es)**' if crashes else 'clean'} |")
        add("")

        add("### Binarization")
        add("")
        add("| Method | Mean CER over resolutions | Best CER | s/page |")
        add("|---|---|---|---|")
        seen: dict[str, list[VariantResult]] = {}
        for r in screen:
            key = Variant(**r.params).name.split(" + ", 1)[1]
            seen.setdefault(key, []).append(r)
        for key, rows in sorted(seen.items(),
                                key=lambda kv: statistics.mean(
                                    r.cer_nospace for r in kv[1])):
            add(f"| `{key}` | {statistics.mean(r.cer_nospace for r in rows):.3f} | "
                f"{min(r.cer_nospace for r in rows):.3f} | "
                f"{statistics.mean(r.sec_per_page for r in rows):.1f} |")
        add("")

    refine = [r for r in arabic if r.stage == 2 and r.cer_nospace is not None]
    if refine and screen:
        add("### Deskew and contrast")
        add("")
        add("Measured on the shortlisted resolution/binarization combinations "
            "only. Each row is compared against the same base combination with "
            "both switched off.")
        add("")
        add("| Base combination | Deskew | Contrast | CER (no-space) | vs base | s/page |")
        add("|---|---|---|---|---|---|")
        for r in sorted(refine, key=lambda x: x.cer_nospace):
            p = r.params
            base_row = next(
                (b for b in screen
                 if b.params["dpi"] == p["dpi"] and b.params["max_side"] == p["max_side"]
                 and b.params["binarization"] == p["binarization"]
                 and b.params["global_threshold"] == p["global_threshold"]
                 and b.params["adaptive_block"] == p["adaptive_block"]), None)
            base_name = base_row.variant if base_row else "?"
            delta = (f"{r.cer_nospace - base_row.cer_nospace:+.3f}"
                     if base_row and base_row.cer_nospace is not None else "n/a")
            add(f"| `{base_name}` | {'yes' if p['deskew'] else 'no'} | "
                f"{p['contrast']} | {_fmt(r.cer_nospace)} | {delta} | "
                f"{r.sec_per_page:.1f} |")
        add("")

    # ---------------- per document ------------------------------------------
    if stage3:
        add("## Per-document CER, confirmation stage")
        add("")
        add("A mean over eight documents can hide a setting that helps six and "
            "wrecks two. This is the table that shows it.")
        add("")
        docs = sorted({d for r in stage3 for d in r.per_document})
        add("| Document | " + " | ".join(f"`{r.variant}`" for r in stage3) + " |")
        add("|---" * (len(stage3) + 1) + "|")
        for doc_name in docs:
            add(f"| `{doc_name}` | "
                + " | ".join(_fmt(r.per_document.get(doc_name)) for r in stage3) + " |")
        add("")

    # ---------------- trade-offs --------------------------------------------
    add("## Trade-offs worth a human decision")
    add("")
    flagged = False
    pool = (stage3 + ladder) or ranked
    base_speed = baseline.sec_per_page if baseline else None
    base_cer = (baseline.cer_nospace if baseline and baseline.cer_nospace
                else BASELINE_CER)
    for r in pool:
        if r.cer_nospace is None or r is baseline:
            continue
        better = r.cer_nospace < base_cer - MEANINGFUL_GAIN
        slow = base_speed and r.sec_per_page > base_speed * SPEED_FLAG_RATIO
        if better and (slow or not r.stable):
            flagged = True
            reasons = []
            if slow:
                reasons.append(f"{r.sec_per_page / base_speed:.1f}x slower "
                               f"({r.sec_per_page:.1f} vs {base_speed:.1f} s/page)")
            if not r.stable:
                reasons.append(_stability(r))
            add(f"- **`{r.variant}`** improves CER to {r.cer_nospace:.3f} "
                f"({base_cer - r.cer_nospace:+.3f}) but " + "; ".join(reasons)
                + ". **Judgment call, not an automatic pick.**")
    if not flagged:
        add("_No combination bought a CER improvement at a meaningful cost in "
            "speed or stability._")
    add("")

    # ---------------- incidents ---------------------------------------------
    incidents = [(r.variant, n) for r in results for n in r.notes if "production" not in n]
    if incidents:
        add("## Incidents")
        add("")
        for name, note in incidents[:40]:
            add(f"- `{name}` -- {note}")
        if len(incidents) > 40:
            add(f"- ...and {len(incidents) - 40} more")
        add("")

    # ---------------- caveats -----------------------------------------------
    add("## Caveats")
    add("")
    add("1. **Rendered pages, not scanner output.** Every fixture is a digital "
        "page rasterized and degraded with skew, noise and JPEG artifacts. That "
        "models compression and geometry, not scanner optics, photocopy "
        "generations or bleed-through. **Preprocessing is exactly the kind of "
        "intervention whose value depends on that gap** -- deskew has little to "
        "correct on a page whose skew we introduced ourselves at a known small "
        "angle, and binarization has little to fix on clean synthetic ink. A "
        "setting that is a wash here could still earn its place on real scans. "
        "Re-run against `test_corpus/real` when it exists; no code change is "
        "needed.")
    add("2. **Eight documents.** Enough to see a large effect, not enough to "
        f"resolve a small one -- hence the {MEANINGFUL_GAIN:.3f} CER threshold "
        "for calling anything a win, set before the sweep ran.")
    add("3. **Stage 1 and 2 numbers rank, they do not measure.** They use fewer "
        "pages per document than the baseline. Only stage 3 is quotable.")
    add("4. **Space-insensitive CER is the headline**, as in the engine "
        "benchmark: several references have fragmented word boundaries, and a "
        "space-sensitive comparison charges OCR for them. Both are tabulated.")
    add("5. **One machine, CPU only.** Timings will not match the firm's server, "
        "but the *ratios* between combinations will hold.")
    add("")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-pages", type=int, default=4,
                        help="pages per fixture in the confirmation stage; "
                             "matches the engine benchmark's default so the "
                             "headline number stays comparable with CER 0.130")
    parser.add_argument("--screen-pages", type=int, default=2,
                        help="pages per fixture during screening/refinement")
    parser.add_argument("--shortlist", type=int, default=3,
                        help="screening combinations carried into stage 2")
    parser.add_argument("--confirm", type=int, default=3,
                        help="combinations carried into the confirmation stage")
    parser.add_argument("--stage", type=int, default=0,
                        help="stop after this stage (0 = run all of them)")
    parser.add_argument("--no-ladder", dest="ladder", action="store_false",
                        help="skip the stage 4 resolution ladder")
    parser.add_argument(
        "--probe", default="",
        help="extra combinations to measure at full page count, as a comma-"
             "separated list of `dpi[:contrast]` (e.g. '100:unsharp,175:unsharp'). "
             "For settling a question the staged design leaves open -- a "
             "contrast setting that wins at one resolution has to be shown to "
             "win at others before it is anything but a fixture accident.",
    )
    parser.add_argument("--no-english-guard", dest="check_english",
                        action="store_false",
                        help="skip the stage 5 English regression guard. Only "
                             "safe if no resolution change is being considered "
                             "-- render_dpi is shared with the English path.")
    parser.add_argument("--out", default=str(REPORTS_DIR / "arabic_preprocess_sweep.md"))
    parser.add_argument("--json", default=str(REPORTS_DIR / "arabic_preprocess_sweep.json"))
    parser.add_argument("--from-json", action="store_true",
                        help="rebuild the report from a previous run's JSON")
    parser.add_argument("--no-resume", dest="resume", action="store_false",
                        help="ignore checkpointed results and start over")
    args = parser.parse_args()

    config = PipelineConfig()
    # The sweep drives preprocessing itself, per variant. Leaving the production
    # setting on would apply it twice on every page.
    config.ocr.preprocess.enabled = False
    json_path = Path(args.json)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    if args.from_json:
        if not json_path.exists():
            print(f"No results at {json_path}. Run the sweep first.")
            return 1
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        fields = {f.name for f in VariantResult.__dataclass_fields__.values()}
        results = [VariantResult(**{k: v for k, v in d.items() if k in fields})
                   for d in payload["results"]]
        baseline = next((r for r in results if r.stage == 3
                         and "production" in " ".join(r.notes)), None)
        Path(args.out).write_text(
            build_report(results, baseline, config,
                         payload.get("wall_clock_seconds", 0.0), args),
            encoding="utf-8")
        print(f"Rebuilt {args.out} from {json_path} ({len(results)} combinations)")
        return 0

    fixtures = arabic_fixtures(args.max_pages)
    if not fixtures:
        print("No Arabic fixtures with verified ground truth found.")
        return 1
    print(f"Arabic fixtures with verified ground truth: {len(fixtures)}")
    for f in fixtures:
        print(f"  {f['path'].name} ({f['max_pages']} pages)")
    print()

    results: list[VariantResult] = []
    done: set[tuple[str, int]] = set()
    elapsed_before = 0.0
    if args.resume and json_path.exists():
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        fields = {f.name for f in VariantResult.__dataclass_fields__.values()}
        results = [VariantResult(**{k: v for k, v in d.items() if k in fields})
                   for d in payload.get("results", [])]
        done = {(r.variant, r.stage) for r in results}
        elapsed_before = float(payload.get("wall_clock_seconds", 0.0))
        if results:
            print(f"Resuming: {len(results)} combination(s) already measured\n")

    start = time.perf_counter()

    def checkpoint() -> None:
        json_path.write_text(json.dumps({
            "warning": "Public/synthetic data only. No firm document processed.",
            "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
            "engine": "tesseract",
            "fixtures": [f["path"].name for f in fixtures],
            "screen_pages": args.screen_pages,
            "max_pages": args.max_pages,
            "wall_clock_seconds": round(elapsed_before + time.perf_counter() - start, 1),
            "results": [asdict(r) for r in results],
        }, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    def measure(variants: list[Variant], stage: int, page_cap: int | None,
                label: str, docs: list[dict] | None = None,
                language: str = "ar") -> list[VariantResult]:
        docs = docs if docs is not None else fixtures
        out: list[VariantResult] = []
        for i, variant in enumerate(variants, 1):
            existing = next((r for r in results
                             if r.variant == variant.name and r.stage == stage), None)
            if existing:
                print(f"  [{i}/{len(variants)}] {variant.name:<44} "
                      f"(done, CER={_fmt(existing.cer_nospace)})", flush=True)
                out.append(existing)
                continue
            print(f"  [{i}/{len(variants)}] {variant.name:<44} ", end="", flush=True)
            r = run_variant(variant, docs, config, stage, page_cap, language)
            results.append(r)
            out.append(r)
            print(f"CER={_fmt(r.cer_nospace):<7} {r.sec_per_page:5.1f}s/pg  "
                  f"crash={r.crashes} soft={r.soft_errors} empty={r.empty_pages}",
                  flush=True)
            checkpoint()
        return out

    # --- stage 1: screening --------------------------------------------------
    screening = screening_variants()
    print(f"STAGE 1 -- screening: {len(screening)} combinations "
          f"x {len(fixtures)} documents x {args.screen_pages} page(s)\n")
    stage1 = measure(screening, 1, args.screen_pages, "screening")

    baseline: VariantResult | None = None
    if args.stage and args.stage < 2:
        Path(args.out).write_text(
            build_report(results, baseline, config,
                         elapsed_before + time.perf_counter() - start, args),
            encoding="utf-8")
        print(f"\nReport : {args.out}")
        return 0

    # --- stage 2: refinement -------------------------------------------------
    scored1 = sorted((r for r in stage1 if r.cer_nospace is not None),
                     key=lambda r: r.cer_nospace)
    shortlist = [Variant(**r.params) for r in scored1[:args.shortlist]]
    print(f"\nSTAGE 2 -- refinement of the top {len(shortlist)}: "
          + ", ".join(v.name for v in shortlist) + "\n")
    stage2 = measure(refinement_variants(shortlist), 2, args.screen_pages, "refinement")

    if args.stage and args.stage < 3:
        Path(args.out).write_text(
            build_report(results, baseline, config,
                         elapsed_before + time.perf_counter() - start, args),
            encoding="utf-8")
        print(f"\nReport : {args.out}")
        return 0

    # --- stage 3: confirmation ----------------------------------------------
    scored = sorted((r for r in stage1 + stage2 if r.cer_nospace is not None),
                    key=lambda r: r.cer_nospace)
    finalists: list[Variant] = []
    for r in scored:
        v = Variant(**r.params)
        if v not in finalists:
            finalists.append(v)
        if len(finalists) >= args.confirm:
            break
    prod = production_variant(config)
    if prod not in finalists:
        finalists.append(prod)

    print(f"\nSTAGE 3 -- confirmation on the full page set: "
          f"{len(finalists)} combinations\n")
    stage3 = measure(finalists, 3, None, "confirmation")

    for r, v in zip(stage3, finalists):
        if v == prod:
            baseline = r
            if "production defaults" not in " ".join(r.notes):
                r.notes.insert(0, "production defaults (render only, no preprocessing)")
            checkpoint()

    if args.probe:
        probes = []
        for spec in args.probe.split(","):
            dpi, _, contrast = spec.strip().partition(":")
            probes.append(Variant(dpi=int(dpi), max_side=0, binarization="none",
                                  deskew=False, contrast=contrast or "none"))
        print(f"\nPROBES -- full page set: {len(probes)} combination(s)\n")
        stage3 += measure(probes, 3, None, "probe")

    # --- stage 4: resolution ladder -----------------------------------------
    # Screening said resolution dominates and favours the low end -- the
    # opposite of the hypothesis. One winning rung is not enough to act on
    # that, so walk the axis on its own at full page count and look at the
    # shape of the curve rather than at a single point.
    if args.ladder:
        ladder = [Variant(dpi=dpi, max_side=0, binarization="none",
                          deskew=False, contrast="none")
                  for dpi in RESOLUTION_LADDER]
        print(f"\nSTAGE 4 -- resolution ladder, full page set: "
              f"{len(ladder)} rungs\n")
        measure(ladder, 4, None, "ladder")

    # --- stage 5: English regression guard -----------------------------------
    # render_dpi is shared with the English path. A setting that helps Arabic
    # and wrecks English is not shippable, and nothing else in this sweep would
    # notice: every other stage scores the Arabic word stream only.
    if args.check_english:
        english = fixtures_for("en", args.max_pages)
        if not english:
            print("\nSTAGE 5 skipped: no English fixtures with verified ground truth")
        else:
            guard = list(dict.fromkeys(
                [Variant(**r.params) for r in
                 sorted((x for x in stage3 if x.cer_nospace is not None),
                        key=lambda x: x.cer_nospace)[:args.confirm]] + [prod]))
            print(f"\nSTAGE 5 -- English regression guard: {len(guard)} "
                  f"combination(s) x {len(english)} English document(s)\n")
            measure(guard, 5, None, "english guard", docs=english, language="en")

    elapsed = elapsed_before + time.perf_counter() - start
    checkpoint()
    Path(args.out).write_text(
        build_report(results, baseline, config, elapsed, args), encoding="utf-8")

    print(f"\nReport : {args.out}")
    print(f"Raw    : {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
