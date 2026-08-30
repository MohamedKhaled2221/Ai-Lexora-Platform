"""Audit the ground-truth files before trusting any accuracy number scored against them.

WHY
===

Ground truth for every scanned fixture is the **source PDF's own text layer**.
That is the only reference available without hand-transcribing Arabic legal
pages, and it is usually excellent. But it is not neutral: it inherits whatever
the PDF's producer did, and two producers in this corpus did things that make a
correct OCR result score as a catastrophe.

Both were mistaken for OCR failures during this project, and both produced a
confidently-worded wrong explanation in an earlier report. This script exists so
that never has to be argued from intuition again -- it measures which it is.

WHAT IT MEASURES
================

For each fixture, one page is OCR'd once with Tesseract, then scored against the
reference **four** ways:

``cer_asis``
    Ordinary CER. This is what the reports quote.

``cer_reversed``
    CER after reversing the word order of every reference line. Some Arabic PDFs
    store each line's words in *visual* (right-to-left) order rather than
    logical order. Every character is correct, so the file looks fine to a
    reader and passes every character-level check -- but the word sequence is
    backwards, and OCR is then charged for it. If reversing helps materially,
    that is what happened.

``bag_error``
    Word-multiset error, which ignores order completely. This is the decisive
    one, because it separates the two things CER conflates:

        low bag error, high CER   -> every word was read; only the *order*
                                     differs. A layout artifact, not OCR error.
        high bag error            -> words genuinely were not read. Real
                                     recognition error, and no amount of
                                     reordering will fix the score.

``out_of_flow``
    Whether the page's text layer emits blocks in an order that does not match
    their position on the page -- the signature of a marginal annotation column.
    Measured directly from block geometry, independent of OCR.

VERDICTS
========

``logical``
    The reference is in reading order and its absolute CER is meaningful.
    **These are the only fixtures whose absolute accuracy should be quoted.**

``visual``
    Reversing the reference's word order helps materially. Absolute CER
    overstates error for both engines.

``out_of_flow``
    Words are all present (low bag error) but ordered differently, and the
    source's own blocks are out of flow. A reading-order artifact of the
    publisher's layout, not an OCR failure.

``unreliable``
    High error that reordering does not explain. Either genuinely hard input or
    a reference defect this script cannot characterise; either way, do not quote
    its absolute number.

A head-to-head *comparison* between engines stays valid on every fixture,
including the unreliable ones, because both engines face the same reference.
Only absolute accuracy is affected. The two claims are reported separately.

Run::

    python scripts/audit_ground_truth.py
    python scripts/audit_ground_truth.py --pages 2
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import src  # noqa: E402

src.quiet_third_party_logs()

from evaluate import bag_error, cer  # noqa: E402  -- reuse, do not reimplement
from evaluate import _split_by_script  # noqa: E402
from src.config import SYNTHETIC_CORPUS_DIR, PipelineConfig  # noqa: E402
from src.normalize import normalize_text  # noqa: E402
from src.ocr_pipeline import render_pdf_page, run_tesseract  # noqa: E402
from src.visual_order import REVERSAL_HELPS, reverse_line_words  # noqa: E402

# ``REVERSAL_HELPS`` and ``reverse_line_words`` now live in
# :mod:`src.visual_order` rather than here, because the pipeline runs the same
# test live: this script's "does reversing help by a material margin?" is what
# decides, at ingestion time, whether a document's text layer gets reordered.
# Importing them keeps the offline audit and the live repair from drifting
# apart on what "reversed" means or on how much of an improvement counts.

# Below this, essentially every reference word was found in the OCR output, so
# whatever CER remains is ordering, not recognition.
BAG_IS_CLEAN = 0.15

# Benchmark fixtures separate their reference pages with a form feed, so a
# reference can be sliced to just the pages that were actually OCR'd.
PAGE_BREAK = ""


def out_of_flow_ratio(pdf_path: Path) -> float | None:
    """How far the content stream's block order departs from reading order.

    Computed from the *source* PDF, with no OCR involved: sort blocks as a
    reader would (top to bottom, then left to right) and count what fraction of
    all block pairs the content stream puts in the opposite order -- Kendall
    tau distance, normalised. A publisher that emits the body column and then
    dumps the margin annotations at the end of the page scores high.

    Adjacent pairs alone are not enough: a page whose margin column is appended
    wholesale is locally ordered almost everywhere and only wrong in bulk.

    Sampled from a page in the middle of the document, because front matter and
    covers are laid out differently from the body.
    """
    import fitz

    try:
        with fitz.open(pdf_path) as doc:
            if not doc.page_count:
                return None
            page = doc[min(doc.page_count - 1, max(1, doc.page_count // 2))]
            blocks = [b for b in page.get_text("blocks") if str(b[4]).strip()]
    except Exception:  # noqa: BLE001
        return None
    if len(blocks) < 4:
        return None

    reading = sorted(range(len(blocks)), key=lambda i: (round(blocks[i][1]), blocks[i][0]))
    rank = {b: i for i, b in enumerate(reading)}
    n = len(blocks)
    inversions = sum(
        1 for i in range(n) for j in range(i + 1, n) if rank[i] > rank[j]
    )
    return round(inversions / (n * (n - 1) / 2), 4)


def audit_fixture(pdf: Path, gt: Path, pages: int, config: PipelineConfig) -> dict:
    import fitz

    raw_gt = gt.read_text(encoding="utf-8", errors="replace")
    doc = fitz.open(pdf)
    try:
        # A reference with no form-feed markers cannot be sliced to the pages
        # actually OCR'd, so every page must be read or the score charges the
        # engine for pages it never saw -- which is what made three fixtures
        # look "unreliable" on the first run of this audit.
        n = min(pages, doc.page_count) if PAGE_BREAK in raw_gt else doc.page_count
        hypothesis = []
        for i in range(n):
            img, scale = render_pdf_page(doc[i], config.ocr.render_dpi, config.ocr.max_render_side)
            hypothesis.append(run_tesseract(img, i + 1, scale, config.ocr).text)
    finally:
        doc.close()

    raw = raw_gt
    if PAGE_BREAK in raw:
        raw = PAGE_BREAK.join(raw.split(PAGE_BREAK)[:n])

    hyp, _ = normalize_text("\n".join(hypothesis), config.normalization)
    ref_asis, _ = normalize_text(raw, config.normalization)
    ref_rev, _ = normalize_text(reverse_line_words(raw), config.normalization)

    result: dict = {"file": pdf.name, "pages_scored": n}

    for label, ref_text in (("asis", ref_asis), ("reversed", ref_rev)):
        ar, en = _split_by_script(ref_text)
        hyp_ar, hyp_en = _split_by_script(hyp)
        result[f"cer_ar_{label}"] = cer(ar, hyp_ar, ignore_spaces=True)
        result[f"cer_en_{label}"] = cer(en, hyp_en, ignore_spaces=True)
        if label == "asis":
            result["bag_ar"] = bag_error(ar, hyp_ar)
            result["bag_en"] = bag_error(en, hyp_en)

    result["out_of_flow"] = out_of_flow_ratio(_source_for(pdf))

    # --- verdict -------------------------------------------------------------
    asis = _first_not_none(result["cer_ar_asis"], result["cer_en_asis"])
    rev = _first_not_none(result["cer_ar_reversed"], result["cer_en_reversed"])
    bag = _first_not_none(result["bag_ar"], result["bag_en"])

    flow = result["out_of_flow"] or 0.0

    if _is_authored(pdf.name):
        # The text was written before the pixels existed, so the reference
        # cannot be in visual order, fragmented, or out of flow. Whatever error
        # remains is the engine's, however large -- and calling a hard page's
        # honest score "unreliable" would quietly exclude the only fixtures
        # whose absolute accuracy is quotable. Authored references are trusted
        # by construction; that is the entire reason they exist.
        result["reference_word_order"] = "authored"
        return result

    if asis is None:
        verdict = "not_audited"
    elif rev is not None and asis - rev >= REVERSAL_HELPS:
        verdict = "visual"
    elif (bag is not None and bag <= BAG_IS_CLEAN
          and asis - bag >= REVERSAL_HELPS and flow >= 0.05):
        # Every reference word was found in the OCR output, yet CER is much
        # worse than the word error -- so the difference is ordering, and the
        # source's own blocks are out of flow. Checked BEFORE the CER threshold
        # below: a document can have a respectable-looking CER that is still
        # entirely an ordering artifact, and calling that "logical" would put an
        # unquotable number in the trustworthy pile.
        verdict = "out_of_flow"
    elif asis <= 0.25:
        verdict = "logical"
    else:
        verdict = "unreliable"

    result["reference_word_order"] = verdict
    return result


_AUTHORED: set[str] | None = None


def _is_authored(name: str) -> bool:
    """Was this fixture's reference written, rather than extracted?

    Read from the generator's own manifest rather than pattern-matched on the
    filename, so a fixture cannot claim a trusted reference by being named
    conveniently.
    """
    global _AUTHORED
    if _AUTHORED is None:
        _AUTHORED = set()
        manifest = SYNTHETIC_CORPUS_DIR / "stress_manifest.json"
        if manifest.exists():
            data = json.loads(manifest.read_text(encoding="utf-8"))
            _AUTHORED = {
                e["file"] for e in data["files"]
                if str(e.get("ground_truth_provenance", "")).startswith("AUTHORED")
            }
    return name in _AUTHORED


def _first_not_none(*values):
    for v in values:
        if v is not None:
            return v
    return None


def _source_for(bench_pdf: Path) -> Path:
    """The public PDF a bench fixture was rendered from.

    Out-of-flow order is a property of the *original* text layer; the rasterized
    fixture has no text layer at all.
    """
    from src.config import PUBLIC_CORPUS_DIR

    stem = bench_pdf.stem
    for prefix in ("bench_", "scan_"):
        if stem.startswith(prefix):
            stem = stem[len(prefix):]
    for suffix in ("_clean", "_poor", "_200dpi", "_150dpi", "_300dpi"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
    candidate = PUBLIC_CORPUS_DIR / f"{stem}.pdf"
    return candidate if candidate.exists() else bench_pdf


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pages", type=int, default=2,
                        help="pages OCR'd per fixture (the verdict is stable at 1-2)")
    parser.add_argument("--out", default=str(SYNTHETIC_CORPUS_DIR / "reference_audit.json"))
    args = parser.parse_args()

    config = PipelineConfig()
    fixtures: list[tuple[Path, Path]] = []
    for pdf in sorted(SYNTHETIC_CORPUS_DIR.glob("*.pdf")):
        gt = pdf.with_name(pdf.stem + ".groundtruth.txt")
        if gt.exists():
            fixtures.append((pdf, gt))

    if not fixtures:
        print("No fixtures with ground truth found.")
        return 1

    print(f"Auditing {len(fixtures)} ground-truth files ({args.pages} page(s) each)\n")
    results = []
    for i, (pdf, gt) in enumerate(fixtures, 1):
        print(f"[{i}/{len(fixtures)}] {pdf.name} ... ", end="", flush=True)
        r = audit_fixture(pdf, gt, args.pages, config)
        results.append(r)
        print(f"{r['reference_word_order']} "
              f"(cer {_first_not_none(r['cer_ar_asis'], r['cer_en_asis'])}, "
              f"bag {_first_not_none(r['bag_ar'], r['bag_en'])}, "
              f"out_of_flow {r['out_of_flow']})", flush=True)

    Path(args.out).write_text(
        json.dumps(
            {
                "note": "Ground-truth reference audit. Public/synthetic data only.",
                "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
                "pages_per_fixture": args.pages,
                "reversal_helps_threshold": REVERSAL_HELPS,
                "bag_is_clean_threshold": BAG_IS_CLEAN,
                "results": results,
            },
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nWrote {args.out}")
    counts: dict[str, int] = {}
    for r in results:
        counts[r["reference_word_order"]] = counts.get(r["reference_word_order"], 0) + 1
    print("Verdicts: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
