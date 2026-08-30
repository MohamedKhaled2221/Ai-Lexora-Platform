"""Accuracy of the **native** (non-OCR) extraction path, by extractor and language.

WHAT THIS MEASURES, AND WHY IT IS NOT THE OCR NUMBER
====================================================

Every accuracy figure this project has published -- 0.095 Arabic, 0.013 English
in ``reports/paddleocr_vl_benchmark.md`` -- is for documents that arrive as
images and go through OCR. Documents that arrive as digitally-produced PDFs never
touch an OCR engine: their text is read straight out of the PDF's text layer.
That path had a single blended CER in ``evaluation_report.md`` and nothing else:
no split by language, no split by extractor, and no re-measurement since the
visual-order repair landed.

This script closes that. Same fixtures discipline, same scoring functions
(imported from ``scripts/evaluate.py``, never reimplemented), same
Arabic/English separation as every prior report.

THE THREE ARMS, AND WHY THE OBVIOUS TWO ARE NOT THE REAL COMPARISON
===================================================================

The brief asks for "PyMuPDF vs Docling". On this pipeline that framing does not
survive contact with the code, and the report says so:
:func:`src.extract_pymupdf_docling.extract_text_pdf` runs PyMuPDF for **all** PDF
text and then uses Docling only to stamp semantic labels onto PyMuPDF's blocks
by bbox overlap (:func:`_merge_docling_labels`, whose docstring states "Text is
never taken from Docling") and to supersede its tables. Docling is not a text
extractor on the PDF path at all.

So three arms are run:

``pymupdf``
    ``use_docling=False``. The text path stripped to PyMuPDF.

``pymupdf+docling``
    Production defaults. Differs from the above only in labels and tables -- so
    any CER difference between these two is a *chunking* consequence of the
    labels, not a difference in character recognition.

``docling-only``
    Docling's own text, via :func:`_pages_from_docling_only` -- the function the
    DOCX path uses -- monkeypatched over the PDF route for the duration of the
    run. This is the arm that answers "would Docling read these documents better
    if we let it?", and it is the only one that is a genuine second extractor.
    Nothing in ``src/`` is modified; the patch lives here.

REFERENCES
==========

From ``text_reference_manifest.json`` (authored + transcribed, built by
``make_text_ground_truth.py``) and ``native_reference_manifest.json`` (authored,
built by ``make_native_fixtures.py``). Neither takes its reference from a PDF's
own text layer, which would be circular for the PyMuPDF arms and, on Arabic,
wrong for all of them -- see ``make_text_ground_truth.py`` for that argument.

Run::

    python scripts/native_extraction_benchmark.py
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.config import PUBLIC_CORPUS_DIR, SYNTHETIC_CORPUS_DIR, PipelineConfig  # noqa: E402
from src.normalize import normalize_text  # noqa: E402
from src.pipeline import process_document  # noqa: E402

# The scoring functions are imported, never reimplemented -- the brief's
# requirement, and the only way these numbers stay comparable with the OCR ones.
from evaluate import _split_by_script, bag_error, cer, wer  # noqa: E402

REPORTS = Path(__file__).resolve().parent.parent / "reports"
REFERENCE_DIR = SYNTHETIC_CORPUS_DIR / "text_reference"

ARMS = ("pymupdf", "pymupdf+docling", "docling-only")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def load_references() -> dict[str, list[dict]]:
    """Every native-path reference, keyed by document filename."""
    out: dict[str, list[dict]] = {}
    for name in ("text_reference_manifest.json", "native_reference_manifest.json"):
        path = REFERENCE_DIR / name
        if not path.exists():
            continue
        for entry in json.loads(path.read_text(encoding="utf-8"))["entries"]:
            out.setdefault(entry["document"], []).append(entry)
    for entries in out.values():
        entries.sort(key=lambda e: (e.get("page") or 0))
    return out


def locate(document: str, corpus: str) -> Path | None:
    base = PUBLIC_CORPUS_DIR if corpus == "public" else SYNTHETIC_CORPUS_DIR
    path = base / document
    return path if path.exists() else None


# ---------------------------------------------------------------------------
# Arms
# ---------------------------------------------------------------------------


def config_for(arm: str, attach_heading: bool = True) -> PipelineConfig:
    cfg = PipelineConfig()
    # ``attach_heading_to_body`` prepends the governing clause label to every
    # chunk so a retrieved chunk is self-describing. It is a *retrieval* feature
    # and it puts text into the output that was never in the document -- a
    # word-level diff of the English fixtures shows the entire residual error is
    # "Clause 1", "Annex A" and friends. Measuring extraction accuracy on chunk
    # text therefore charges the extractor for the chunker's annotations, which
    # is what the single blended 0.376 in evaluation_report.md was doing. Both
    # variants are run: "as-shipped" for continuity with that figure, and
    # "extraction-only" for what the extractor actually read.
    cfg.chunking.attach_heading_to_body = attach_heading
    # OCR off across the board: this is the native path, and leaving OCR
    # reachable would let a mis-detected page contribute an OCR score to a
    # native-path number.
    cfg.ocr.enabled = False
    cfg.extraction.use_docling = arm != "pymupdf"
    if arm == "docling-only":
        # Docling must see the whole document, so the size guard that protects
        # the production path from its native-code aborts is relaxed here. Any
        # document it then kills is a finding, not an accident.
        cfg.extraction.docling_max_pages = 10_000
    return cfg


class DoclingOnly:
    """Context manager that routes PDF text extraction through Docling alone."""

    def __init__(self) -> None:
        self._saved = None

    def __enter__(self):
        import src.pipeline as pipeline
        from src import extract_pymupdf_docling as ex

        self._saved = pipeline.extract_text_pdf

        def extract_text_pdf_docling_only(path, doc, config, only_pages=None):
            t0 = time.perf_counter()
            dl_doc = ex._docling_convert(path, config.docling_timeout_s)
            pages = ex._pages_from_docling_only(dl_doc, config)
            if only_pages:
                wanted = set(only_pages)
                pages = [p for p in pages if p.page_number in wanted]
            ex._merge_pages(doc, pages)
            doc.timings_ms["docling"] = (time.perf_counter() - t0) * 1000
            doc.log_engine(None, "docling", status="ok", mode="docling-only",
                           pages=len(pages))
            # Deliberately NOT calling _resolve_reading_order: Docling returns no
            # per-glyph geometry, so there is no second reading to choose between.
            # That absence is itself a result -- see the report.
            return doc

        pipeline.extract_text_pdf = extract_text_pdf_docling_only
        return self

    def __exit__(self, *exc):
        import src.pipeline as pipeline

        pipeline.extract_text_pdf = self._saved
        return False


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


@dataclass
class Scored:
    document: str
    arm: str
    variant: str = "as-shipped"
    pages: int = 0
    provenance: str = ""
    error: str | None = None
    seconds: float = 0.0
    ms_per_page: float = 0.0
    n_chunks: int = 0
    n_tables: int = 0
    reading_order: dict = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)   # scope -> {cer, cer_nospace, wer, bag}
    ref_chars: dict = field(default_factory=dict)
    pages_missing: list[int] = field(default_factory=list)
    scope_used: str = ""


def _metrics(reference: str, hypothesis: str) -> dict:
    return {
        "cer": cer(reference, hypothesis),
        "cer_nospace": cer(reference, hypothesis, ignore_spaces=True),
        "wer": wer(reference, hypothesis),
        "bag": bag_error(reference, hypothesis),
    }


def score_document(path: Path, entries: list[dict], arm: str,
                   cfg: PipelineConfig, variant: str = "as-shipped") -> Scored:
    """Run one document through one arm and score it against its references.

    Pages are concatenated in page order before scoring, rather than scored
    per page and averaged. Both are defensible; concatenation is used because
    the per-language split needs a sample above ``evaluate.MIN_REFERENCE_CHARS``
    and a single page of a bilingual document rarely clears it in both scripts.
    The overall figures are unaffected in kind, only in weighting.
    """
    out = Scored(document=path.name, arm=arm, variant=variant)
    out.provenance = "+".join(sorted({e["provenance"] for e in entries}))
    out.pages = sum(e["pages_covered"] for e in entries)

    start = time.perf_counter()
    try:
        result = process_document(path, cfg)
    except Exception as exc:  # noqa: BLE001
        out.error = f"{type(exc).__name__}: {exc}"
        return out
    out.seconds = time.perf_counter() - start
    out.ms_per_page = out.seconds * 1000 / max(out.pages, 1)

    if not result.succeeded:
        out.error = result.errors[0] if result.errors else "produced no chunks"
        return out

    out.n_chunks = result.n_chunks
    out.n_tables = sum(1 for c in result.chunks if c.metadata.get("is_table"))
    for log in result.engine_log:
        if log.get("engine") == "reading_order":
            out.reading_order = {
                k: log.get(k) for k in
                ("repaired", "markers_before", "markers_after",
                 "score_before", "score_after", "reason")
            }

    # Page-scoped scoring assumes the extractor attributes text to the right
    # page. PyMuPDF does, because it reads a page at a time. Docling does not
    # reliably -- on native_authored_award_en.pdf it puts 10 of 12 items on page
    # 1 of 2 -- and charging it CER 1.0 for that would measure page attribution,
    # not reading. So where the references happen to cover **every** page of the
    # document, they are concatenated and scored against the whole output, which
    # is attribution-free and loses nothing. Where they cover only a slice (the
    # gazette's pages 2-3 of 29), page scope is the only option and is kept.
    doc_pages = {c.page for c in result.chunks if c.page}
    referenced = {e["page"] for e in entries if e["scope"] == "page" and e["page"]}
    covers_all = (
        bool(referenced)
        and all(e["scope"] == "page" for e in entries)
        and referenced >= doc_pages
    )
    out.scope_used = "document (references cover every page)" if covers_all else "page"

    ref_parts, hyp_parts = [], []
    if covers_all:
        for entry in entries:
            raw = (REFERENCE_DIR / entry["reference"]).read_text(encoding="utf-8")
            reference, _ = normalize_text(raw, cfg.normalization)
            ref_parts.append(reference)
        hypothesis, _ = normalize_text(
            "\n".join(c.text for c in result.chunks), cfg.normalization)
        hyp_parts.append(hypothesis)
    else:
        for entry in entries:
            raw = (REFERENCE_DIR / entry["reference"]).read_text(encoding="utf-8")
            reference, _ = normalize_text(raw, cfg.normalization)
            if entry["scope"] == "page":
                chunks = [c for c in result.chunks if c.page == entry["page"]]
                if not chunks:
                    # An extractor that emitted nothing at all for a referenced
                    # page did not read it badly -- it did not read it. Scoring
                    # that as CER 1.0 would fold a stability failure into an
                    # accuracy mean, which is exactly what the OCR reports keep
                    # separate. Record it and leave it out of the score.
                    out.pages_missing.append(entry["page"])
                    continue
            else:
                chunks = list(result.chunks)
            hypothesis, _ = normalize_text("\n".join(c.text for c in chunks),
                                           cfg.normalization)
            ref_parts.append(reference)
            hyp_parts.append(hypothesis)

    if not ref_parts:
        out.error = (f"extractor produced no output for any referenced page "
                     f"(dropped {out.pages_missing})")
        return out

    reference = "\n".join(ref_parts)
    hypothesis = "\n".join(hyp_parts)
    ref_ar, ref_en = _split_by_script(reference)
    hyp_ar, hyp_en = _split_by_script(hypothesis)

    out.metrics = {
        "all": _metrics(reference, hypothesis),
        "ar": _metrics(ref_ar, hyp_ar),
        "en": _metrics(ref_en, hyp_en),
    }
    out.ref_chars = {"all": len(reference), "ar": len(ref_ar), "en": len(ref_en)}
    return out


def aggregate(scored: list[Scored]) -> dict:
    """Mean of per-document scores -- the aggregation every prior report used."""
    out: dict = {}
    for arm, variant in sorted({(s.arm, s.variant) for s in scored}):
        rows = [s for s in scored
                if s.arm == arm and s.variant == variant and not s.error]
        key = f"{arm} | {variant}"
        out[key] = {}
        for scope in ("all", "ar", "en"):
            agg = {}
            for metric in ("cer", "cer_nospace", "wer", "bag"):
                vals = [s.metrics[scope][metric] for s in rows
                        if s.metrics.get(scope, {}).get(metric) is not None]
                agg[metric] = round(statistics.mean(vals), 4) if vals else None
                agg[f"{metric}_n"] = len(vals)
            out[key][scope] = agg
        out[key]["arm"], out[key]["variant"] = arm, variant
        out[key]["documents"] = len(rows)
        out[key]["failed"] = len([s for s in scored if s.arm == arm
                                  and s.variant == variant and s.error])
        out[key]["documents_with_dropped_pages"] = {
            s.document: s.pages_missing for s in scored
            if s.arm == arm and s.variant == variant and s.pages_missing
        }
        speeds = [s.ms_per_page for s in rows if s.ms_per_page]
        out[key]["ms_per_page_median"] = round(statistics.median(speeds), 1) if speeds else None
    return out


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", default=",".join(ARMS))
    ap.add_argument("--out", default=str(REPORTS / "native_extraction_accuracy.json"))
    args = ap.parse_args()
    arms = [a.strip() for a in args.arms.split(",") if a.strip()]

    references = load_references()
    documents: list[tuple[Path, list[dict]]] = []
    missing: list[str] = []
    for name, entries in sorted(references.items()):
        path = locate(name, entries[0]["corpus"])
        if path is None:
            missing.append(name)
            continue
        documents.append((path, entries))

    print(f"{len(documents)} documents with native-path ground truth "
          f"({sum(sum(e['pages_covered'] for e in en) for _, en in documents)} pages)")
    if missing:
        print(f"  missing from corpus, skipped: {missing}")

    scored: list[Scored] = []
    t_start = time.perf_counter()
    for arm in arms:
        ctx = DoclingOnly() if arm == "docling-only" else None
        if ctx:
            ctx.__enter__()
        try:
            for variant, attach in (("as-shipped", True), ("extraction-only", False)):
                cfg = config_for(arm, attach_heading=attach)
                print(f"\n=== arm: {arm} | {variant} ===")
                for path, entries in documents:
                    row = score_document(path, entries, arm, cfg, variant)
                    scored.append(row)
                    if row.error:
                        print(f"  {path.name:44s} FAILED: {row.error[:90]}")
                        continue
                    if row.pages_missing:
                        print(f"  {path.name:44s} dropped pages {row.pages_missing} "
                              f"(excluded from its score)")
                    m = row.metrics["all"]
                    print(f"  {path.name:44s} CER {m['cer']}  "
                          f"ar {row.metrics['ar']['cer']}  en {row.metrics['en']['cer']}  "
                          f"{row.seconds:.1f}s")
        finally:
            if ctx:
                ctx.__exit__(None, None, None)

    payload = {
        "note": "Accuracy of the native (non-OCR) extraction path. Scoring "
                "functions imported from scripts/evaluate.py.",
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "wall_clock_s": round(time.perf_counter() - t_start, 1),
        "arms": arms,
        "documents": [
            {
                "document": s.document, "arm": s.arm, "variant": s.variant,
                "pages": s.pages,
                "provenance": s.provenance, "error": s.error,
                "seconds": round(s.seconds, 2), "ms_per_page": round(s.ms_per_page, 1),
                "n_chunks": s.n_chunks, "n_tables": s.n_tables,
                "reading_order": s.reading_order, "ref_chars": s.ref_chars,
                "pages_missing": s.pages_missing, "scope_used": s.scope_used,
                "metrics": s.metrics,
            }
            for s in scored
        ],
        "aggregate": aggregate(scored),
    }
    Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                              encoding="utf-8")
    print(f"\n-> {args.out}")

    print("\n=== aggregate (mean of per-document CER, no-space) ===")
    for key, a in payload["aggregate"].items():
        print(f"{key:36s} all {a['all']['cer_nospace']}  "
              f"ar {a['ar']['cer_nospace']} (n={a['ar']['cer_nospace_n']})  "
              f"en {a['en']['cer_nospace']} (n={a['en']['cer_nospace_n']})  "
              f"docs {a['documents']} failed {a['failed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
