"""Native (non-OCR) text-layer PDF fixtures with authored ground truth.

WHY THESE EXIST
===============

The corpus already has authored ground truth for the OCR path: ``scan_authored_*``
renders :data:`make_stress_fixtures.AUTHORED_AR_PAGES` and
:data:`make_stress_fixtures.AUTHORED_EN_PAGES` to a raster, so the reference text
was written *before* the page existed and cannot inherit a publisher's defects.

The native path had no equivalent. Its references
(``test_corpus/synthetic/text_reference/``) cover five documents, but only one of
them is Arabic-dominant and none is a multi-page statute. This module renders the
**same authored pages** to a real text-layer PDF, so the native path can be scored
against exactly the reference the OCR path is scored against -- which makes the
two numbers directly comparable rather than merely adjacent.

THE TWO FIXTURES
================

``native_authored_statute_ar.pdf``
    Arabic, shaped with ``arabic_reshaper`` + ``python-bidi`` before drawing.
    This is what an Arabic DTP producer emits: **presentation forms stored in
    visual order**. It is the representative Arabic case -- both Arabic PDFs in
    ``test_corpus/public/`` that ``audit_ground_truth.py`` classifies behave this
    way -- and it is the case ``src/visual_order.py`` exists to repair.

``native_authored_award_en.pdf``
    English, no shaping involved. The Latin baseline -- what the path scores when
    bidi is not in play at all.

THE LOGICAL-ORDER CONTROL THAT COULD NOT BE AUTHORED
====================================================

A third fixture was attempted and withdrawn: the same Arabic text drawn
*unshaped*, intended as a logical-order control that would separate
"the producer stored visual order" from "our extraction mangles Arabic".

It does not work, and the reason is worth recording so nobody re-attempts it.
ReportLab has no bidi engine: ``drawString`` paints codepoints left-to-right in
the order given, which for an RTL script **is** visual order. The resulting text
layer is therefore not logical -- it is visual order with unshaped glyphs, a
third thing that no producer emits. Extraction confirmed it: PyMuPDF returns
``مقر نوناق`` for ``قانون رقم`` (each word character-reversed), and neither
reading of the block recovers a single structural marker.

**A logical-order Arabic native PDF cannot be authored with the tools pinned in
this repo.** The corpus's real examples of that producer behaviour are the public
PDFs ``audit_ground_truth.py`` labels ``reference_word_order = logical``
(``wipo_eg088ar_1.pdf``, ``wipo_eg081ar_1.pdf``), and those are what the report
uses for it.

Run::

    python scripts/make_native_fixtures.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.config import SYNTHETIC_CORPUS_DIR  # noqa: E402

from make_stress_fixtures import AUTHORED_AR_PAGES, AUTHORED_EN_PAGES  # noqa: E402
from make_synthetic_corpus import ARABIC_FONT, rtl_render  # noqa: E402

REFERENCE_DIR = SYNTHETIC_CORPUS_DIR / "text_reference"

# Layout constants. Chosen to match `_text_pdf` in make_stress_fixtures so the
# native fixtures and the scans differ in *rasterisation*, not in typography.
FONT_SIZE = 11
LEADING = 16
MARGIN = 56


def _render_pages(dest: Path, pages: list[str], *, shaped: bool, rtl: bool) -> None:
    """One authored page per PDF page, so page-scoped references stay aligned.

    ``shaped=False`` writes logical-order codepoints into the content stream --
    the diagnostic control described in the module docstring.
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    pdfmetrics.registerFont(TTFont("ArabicBody", str(ARABIC_FONT)))
    c = canvas.Canvas(str(dest), pagesize=A4)
    width, height = A4

    for page_index, page_text in enumerate(pages):
        if page_index:
            c.showPage()
        c.setFont("ArabicBody", FONT_SIZE)
        y = height - 72
        for line in page_text.splitlines():
            drawn = rtl_render(line) if shaped else line
            if rtl:
                # Right-align Arabic, as its producers do. The x origin differs
                # per line, which is what makes glyph-geometry reconstruction a
                # real test rather than a trivially-ordered one.
                c.drawRightString(width - MARGIN, y, drawn)
            else:
                c.drawString(MARGIN, y, drawn)
            y -= LEADING
    c.save()


def build() -> list[dict]:
    SYNTHETIC_CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    entries: list[dict] = []

    specs = [
        {
            "pdf": "native_authored_statute_ar.pdf",
            "pages": AUTHORED_AR_PAGES,
            "shaped": True,
            "rtl": True,
            "role": "representative",
            "note": "Arabic statute drawn as presentation forms in visual order, "
                    "the way Arabic DTP producers emit PDFs. Same authored text "
                    "as scan_authored_statute_ar_*, so the native and OCR numbers "
                    "are directly comparable.",
        },
        {
            "pdf": "native_authored_award_en.pdf",
            "pages": AUTHORED_EN_PAGES,
            "shaped": False,
            "rtl": False,
            "role": "representative",
            "note": "English arbitral award, no bidi involved. Same authored text "
                    "as scan_authored_award_en_*.",
        },
    ]

    for spec in specs:
        pdf_path = SYNTHETIC_CORPUS_DIR / spec["pdf"]
        _render_pages(pdf_path, spec["pages"], shaped=spec["shaped"], rtl=spec["rtl"])

        for page_no, page_text in enumerate(spec["pages"], start=1):
            ref_name = f"{pdf_path.stem}.p{page_no}.reference.txt"
            (REFERENCE_DIR / ref_name).write_text(
                page_text.strip() + "\n", encoding="utf-8"
            )
            entries.append({
                "reference": ref_name,
                "document": spec["pdf"],
                "corpus": "synthetic",
                "scope": "page",
                "page": page_no,
                "pages_covered": 1,
                "provenance": "authored",
                "role": spec["role"],
                "reference_chars": len(page_text.strip()),
                "note": spec["note"],
            })
        print(f"  {spec['pdf']}  ({len(spec['pages'])} pages, {spec['role']})")

    return entries


def main() -> int:
    print("Building native text-layer fixtures...\n")
    entries = build()
    manifest = {
        "note": "Authored native (non-OCR) PDFs. The reference is the text the "
                "generator was given, so it is correct by construction and "
                "carries none of the publisher defects that make text-layer "
                "references untrustworthy.",
        "shared_source_with": "scan_authored_statute_ar_*, scan_authored_award_en_* "
                              "(same authored pages, rasterised instead of drawn)",
        "entries": entries,
    }
    (REFERENCE_DIR / "native_reference_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    reps = sum(1 for e in entries if e["role"] == "representative")
    print(f"\n{len(entries)} page references ({reps} representative, "
          f"{len(entries) - reps} control) -> {REFERENCE_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
