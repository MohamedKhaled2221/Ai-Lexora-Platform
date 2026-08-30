"""Where the pipeline's per-page time actually goes, on every scanned fixture.

WHY THIS EXISTS
===============

A ``~44 s/page`` processing time was flagged in the first M1 work session and
never explained. The brief for this investigation says to find the original
measurement rather than re-derive it -- so the first thing this script's report
records is that **the original data point is not in any committed artifact**
(see ``reports/speed_outlier_investigation.md``). What *is* recoverable is the
family of documents it must have come from, because the current corpus still
contains a per-page spread of more than 6x between documents that the shipped
explanation ("it is a scan") does not account for:

    scan_constitute_egypt_2019_ar_150dpi.pdf   31.8 s/page
    scan_eg_constitution_2014_en_150dpi.pdf     4.9 s/page

Same engine, same render DPI, same ~8.5 MPix raster, same page count, similar
character count. "It is a scan" explains 5 s/page. It does not explain 32.

WHAT IT MEASURES
================

Three levels, cheapest first, because the cheap ones usually settle it:

1. **Per-page engine timings**, read out of the pipeline's own ``engine_log``.
   ``ocr_pipeline._summarize`` already records ``ms`` for the primary engine and
   for the fallback separately, so a fallback firing is visible without any new
   instrumentation -- and a fallback firing is the single most likely way a page
   costs 4x its neighbours, since PaddleOCR runs an order of magnitude slower
   than Tesseract.

2. **Stage decomposition** on one document: render, OCR, box->block conversion,
   table reconstruction, chunking. Measured by calling the stages directly on
   the same page images, so nothing is inferred from a difference of totals.

3. **cProfile** of the whole document, for the case where the time is in none of
   the places above -- a pathological regex, a quadratic loop, an import.

Run::

    python scripts/speed_outlier_profile.py                 # census, all scans
    python scripts/speed_outlier_profile.py --deep FILE      # stages + cProfile
    python scripts/speed_outlier_profile.py --repeat 3 --only FILE
"""

from __future__ import annotations

import argparse
import cProfile
import io
import json
import pstats
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.config import SYNTHETIC_CORPUS_DIR, PipelineConfig  # noqa: E402
from src.pipeline import process_document  # noqa: E402

REPORTS = Path(__file__).resolve().parent.parent / "reports"


# ---------------------------------------------------------------------------
# Level 1: per-page census from the pipeline's own log
# ---------------------------------------------------------------------------


def page_rows(result) -> list[dict]:
    """Flatten the per-page OCR log into rows, keeping both engines' timings."""
    rows = []
    for log in result.engine_log:
        if log.get("page") is None or "primary" not in log:
            continue
        primary = log.get("primary") or {}
        fallback = log.get("fallback") or {}
        rows.append({
            "page": log["page"],
            "chosen": log.get("engine"),
            "chars": log.get("chars"),
            "mean_conf": log.get("mean_conf"),
            "ink_ratio": log.get("ink_ratio"),
            "primary_engine": primary.get("engine"),
            "primary_ms": primary.get("ms"),
            "primary_passed": primary.get("passed_gates"),
            "primary_reason": primary.get("reason"),
            "primary_boxes": primary.get("boxes_detected"),
            "fallback_engine": fallback.get("engine"),
            "fallback_ms": fallback.get("ms"),
            "fallback_used": log.get("fallback_used"),
            "tables": len(log.get("tables") or []),
        })
    return rows


def census(paths: list[Path], cfg: PipelineConfig, repeat: int) -> list[dict]:
    out = []
    for path in paths:
        runs = []
        rows: list[dict] = []
        for i in range(repeat):
            t0 = time.perf_counter()
            result = process_document(path, cfg)
            runs.append(time.perf_counter() - t0)
            if i == 0:
                rows = page_rows(result)
                stage = dict(result.timings_ms)
                pages = result.n_pages
                chars = sum(len(c.text) for c in result.chunks)
        entry = {
            "file": path.name,
            "pages": pages,
            "chars": chars,
            "runs_s": [round(r, 2) for r in runs],
            "median_s": round(statistics.median(runs), 2),
            "s_per_page": round(statistics.median(runs) / max(pages, 1), 2),
            "spread_s": round(max(runs) - min(runs), 2) if len(runs) > 1 else 0.0,
            "stage_ms": {k: round(v, 1) for k, v in stage.items()},
            "fallbacks": sum(1 for r in rows if r["fallback_used"]),
            "fallback_ms_total": round(sum(r["fallback_ms"] or 0 for r in rows), 1),
            "primary_ms_total": round(sum(r["primary_ms"] or 0 for r in rows), 1),
            "pages_detail": rows,
        }
        out.append(entry)
        print(f"{path.name:46s} {entry['s_per_page']:7.2f} s/page  "
              f"median {entry['median_s']:7.2f}s  spread {entry['spread_s']:5.2f}s  "
              f"primary {entry['primary_ms_total']/1000:6.1f}s  "
              f"fallback {entry['fallback_ms_total']/1000:6.1f}s "
              f"({entry['fallbacks']} page(s))")
    return out


# ---------------------------------------------------------------------------
# Level 2: stage decomposition, measured directly rather than by subtraction
# ---------------------------------------------------------------------------


def stage_breakdown(path: Path, cfg: PipelineConfig) -> list[dict]:
    import fitz

    from src.ocr_pipeline import (
        boxes_to_blocks, render_pdf_page, run_tesseract, tables_from_atoms,
    )

    out = []
    doc = fitz.open(str(path))
    try:
        for pno, page in enumerate(doc, start=1):
            t = time.perf_counter()
            img, scale = render_pdf_page(page, cfg.ocr.render_dpi, cfg.ocr.max_render_side)
            render_ms = (time.perf_counter() - t) * 1000

            t = time.perf_counter()
            res = run_tesseract(img, pno, scale, cfg.ocr)
            ocr_ms = (time.perf_counter() - t) * 1000

            t = time.perf_counter()
            blocks = boxes_to_blocks(res.boxes, pno, res.scale)
            blocks_ms = (time.perf_counter() - t) * 1000

            t = time.perf_counter()
            tables = tables_from_atoms(res.atoms, pno, res.scale, cfg.ocr)
            tables_ms = (time.perf_counter() - t) * 1000

            row = {
                "page": pno,
                "px": [img.shape[1], img.shape[0]],
                "render_ms": round(render_ms, 1),
                "ocr_ms": round(ocr_ms, 1),
                "blocks_ms": round(blocks_ms, 1),
                "tables_ms": round(tables_ms, 1),
                "boxes_detected": res.detected_boxes,
                "boxes_kept": len(res.boxes),
                "atoms": len(res.atoms),
                "chars": res.n_chars,
                "mean_conf": round(res.mean_conf, 4) if res.mean_conf is not None else None,
                "blocks": len(blocks),
                "tables": len(tables),
            }
            out.append(row)
            print(f"  p{pno}: {row['px'][0]}x{row['px'][1]}  render {row['render_ms']:7.1f}  "
                  f"tesseract {row['ocr_ms']:8.1f}  blocks {row['blocks_ms']:6.1f}  "
                  f"tables {row['tables_ms']:7.1f}  | boxes {row['boxes_detected']:5d} "
                  f"atoms {row['atoms']:5d} chars {row['chars']:5d} conf {row['mean_conf']}")
    finally:
        doc.close()
    return out


# ---------------------------------------------------------------------------
# Level 3: cProfile
# ---------------------------------------------------------------------------


def profile(path: Path, cfg: PipelineConfig, top: int = 30) -> str:
    pr = cProfile.Profile()
    pr.enable()
    process_document(path, cfg)
    pr.disable()
    buf = io.StringIO()
    pstats.Stats(pr, stream=buf).sort_stats("cumulative").print_stats(top)
    return buf.getvalue()


# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None, help="substring filter on filename")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--deep", default=None, help="filename for stage breakdown + cProfile")
    ap.add_argument("--out", default=str(REPORTS / "speed_outlier_investigation.json"))
    args = ap.parse_args()

    cfg = PipelineConfig()
    payload: dict = {
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "config": {
            "render_dpi": cfg.ocr.render_dpi,
            "max_render_side": cfg.ocr.max_render_side,
            "primary_engine": cfg.ocr.primary_engine,
            "fallback_engine": cfg.ocr.fallback_engine,
            "tesseract_lang": cfg.ocr.tesseract_lang,
            "preprocess_enabled": cfg.ocr.preprocess.enabled,
        },
    }

    if args.deep:
        path = SYNTHETIC_CORPUS_DIR / args.deep
        print(f"=== stage breakdown: {path.name} ===")
        payload["stage_breakdown"] = {path.name: stage_breakdown(path, cfg)}
        print(f"\n=== cProfile: {path.name} ===")
        text = profile(path, cfg)
        payload["cprofile"] = {path.name: text}
        print(text[:4000])
    else:
        paths = sorted(SYNTHETIC_CORPUS_DIR.glob("scan_*.pdf"))
        if args.only:
            paths = [p for p in paths if args.only in p.name]
        print(f"=== per-page census: {len(paths)} scanned fixture(s), "
              f"repeat={args.repeat} ===")
        payload["census"] = census(paths, cfg, args.repeat)

    out = Path(args.out)
    if out.exists():
        try:
            existing = json.loads(out.read_text(encoding="utf-8"))
            existing.update(payload)
            payload = existing
        except Exception:  # noqa: BLE001
            pass
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n-> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
