"""Generate additional scanned fixtures for the OCR engine head-to-head.

The main evaluation corpus has only two Arabic scans -- far too small a sample
to choose a production OCR engine from. This script grows it by rasterizing
several *different* public Arabic and English legal PDFs at *several* quality
levels, so the comparison covers both document variety and degradation
sensitivity.

Output is prefixed ``bench_`` and lives alongside the main corpus but is
excluded from ``scripts/evaluate.py``, so the evaluation report is unaffected.

SOURCE SELECTION RULES
======================

A derived scan is only usable as an OCR benchmark if its source text layer is
trustworthy -- that text *is* the ground truth. Two filters are applied:

1. ``text_layer_quality`` >= 0.5, which excludes PDFs whose embedded fonts have
   broken encodings (their "text" is mojibake).
2. Column count is recorded, not filtered. Multi-column sources inflate CER for
   *both* engines equally, because ground truth follows the PDF content stream
   while OCR reads visually. That biases the absolute number but **not the
   head-to-head comparison**, which is what this benchmark is for. Recording it
   lets the report separate the two claims.

Fragmentation (spurious intra-word spacing) is also recorded, since it makes
space-sensitive scores unreliable for that document.

Run::

    python scripts/make_benchmark_scans.py
    python scripts/make_benchmark_scans.py --pages 6
"""

from __future__ import annotations

import argparse
import io
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import src  # noqa: E402

src.quiet_third_party_logs()

from src.config import PUBLIC_CORPUS_DIR, SYNTHETIC_CORPUS_DIR  # noqa: E402
from src.structure_preservation import script_profile  # noqa: E402
from src.type_detection import text_layer_quality  # noqa: E402

# Reuse the degradation function from the main corpus generator rather than
# duplicating it -- the two corpora must degrade images identically or the
# benchmark is not comparable to the evaluation report.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_synthetic_corpus import _degrade, _has_broken_word_spacing  # noqa: E402

# (source file, language). Chosen to span single- and multi-column layouts and
# both scripts. Sources with broken text layers are rejected automatically.
SOURCES = [
    ("wipo_eg088ar_1.pdf", "ar"),
    ("wipo_eg081ar_1.pdf", "ar"),
    ("constitute_egypt_2019_ar.pdf", "ar"),
    ("constitute_egypt_2014_ar.pdf", "ar"),
    ("eg_official_gazette_excerpt.pdf", "en"),
    ("constitute_egypt_2014_en.pdf", "en"),
]

# (label, dpi, skew_deg, noise_sigma, blur, jpeg_quality)
# A clean/degraded pair per source gives a sensitivity curve without doubling
# runtime more than necessary. OCR is the expensive part of this benchmark.
QUALITY_LEVELS = [
    ("clean", 300, 0.3, 3, 0.3, 88),
    ("poor", 150, -1.2, 11, 0.9, 58),
]


def first_body_page(doc, max_probe: int = 15) -> int:
    """Index of the first page that is real prose, skipping front matter.

    Covers and tables of contents are pathological OCR benchmark material: a
    TOC page is dot leaders and page numbers, so its "ground truth" is almost
    entirely punctuation and digits and its error rate says nothing about how
    an engine reads legal prose. The constitution PDFs in this corpus carry two
    such pages before the text begins, and including them was distorting the
    OCR figures in the main evaluation report.

    A body page is identified by the fraction of whitespace-separated tokens
    that are real words (3+ letters). Prose sits at 0.4-0.9; a TOC sits at
    0.02-0.05.
    """
    for i in range(min(max_probe, doc.page_count)):
        tokens = doc[i].get_text().split()
        # A cover page can pass the word-ratio test on a handful of title words,
        # so a density floor is needed as well -- otherwise the "body" starts at
        # the cover and the TOC pages get pulled in behind it.
        if len(tokens) < 150:
            continue
        words = [t for t in tokens if sum(1 for c in t if c.isalpha()) >= 3]
        if len(words) / len(tokens) >= 0.30:
            return i
    return 0


def detect_columns(page) -> int:
    """Estimate column count from the x-centres of non-full-width text blocks.

    Crude but sufficient: we only need to know whether ground-truth reading
    order is likely to disagree with visual order, which is a yes/no question.
    """
    centres = []
    for block in page.get_text("dict", sort=True).get("blocks", []):
        if block.get("type") != 0:
            continue
        x0, _, x1, _ = block["bbox"]
        if (x1 - x0) < page.rect.width * 0.6:
            centres.append((x0 + x1) / 2)
    if len(centres) < 6:
        return 1
    mid = page.rect.width / 2
    left = sum(1 for x in centres if x < mid * 0.9)
    right = sum(1 for x in centres if x > mid * 1.1)
    return 2 if (left >= 3 and right >= 3) else 1


def main() -> int:
    import fitz

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pages", type=int, default=4,
                        help="pages per fixture (OCR cost is linear in this)")
    args = parser.parse_args()

    dest = SYNTHETIC_CORPUS_DIR
    dest.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []

    print(f"Generating benchmark scans ({args.pages} pages each)...\n")

    for fname, lang in SOURCES:
        src_path = PUBLIC_CORPUS_DIR / fname
        if not src_path.exists():
            print(f"  ! {fname} not present, skipped")
            continue

        with fitz.open(src_path) as probe:
            start = first_body_page(probe)
            n = min(args.pages, probe.page_count - start)
            pages = range(start, start + n)
            sample = "".join(probe[i].get_text() for i in pages)
            cols = statistics.mode([detect_columns(probe[i]) for i in pages])

        quality, note = text_layer_quality(sample)
        if quality < 0.5:
            print(f"  ! {fname} REJECTED as ground-truth source: {note}")
            continue

        fragmented = _has_broken_word_spacing(sample)
        profile = script_profile(sample)
        tokens = sample.split()
        word_ratio = (
            len([t for t in tokens if sum(1 for c in t if c.isalpha()) >= 3]) / len(tokens)
            if tokens else 0.0
        )
        print(f"  {fname}  ({lang}, {cols} column(s), pages {start + 1}-{start + n}, "
              f"quality {quality:.2f}, word_ratio {word_ratio:.2f}, "
              f"fragmented={fragmented})")

        for label, dpi, skew, noise, blur, jpeg_q in QUALITY_LEVELS:
            out_name = f"bench_{src_path.stem}_{label}.pdf"
            gt_name = f"bench_{src_path.stem}_{label}.groundtruth.txt"

            srcdoc = fitz.open(src_path)
            outdoc = fitz.open()
            gt_parts = []
            for i in pages:
                page = srcdoc[i]
                gt_parts.append(page.get_text("text"))
                pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), alpha=False)
                from PIL import Image

                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                img = _degrade(img, skew, noise, blur, jpeg_q)
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=jpeg_q)
                newpage = outdoc.new_page(width=page.rect.width, height=page.rect.height)
                newpage.insert_image(newpage.rect, stream=buf.getvalue())
            srcdoc.close()
            outdoc.save(str(dest / out_name))
            outdoc.close()
            # Form feed separates pages so a consumer can score a subset of the
            # fixture. Without a page marker, scoring 1 page against a 4-page
            # reference charges the engine for 3 pages it was never shown --
            # which looks like ~0.75 CER regardless of how well it read.
            (dest / gt_name).write_text("\f".join(gt_parts), encoding="utf-8")

            manifest.append({
                "file": out_name,
                "ground_truth": gt_name,
                "source": fname,
                "language": lang,
                "quality_level": label,
                "dpi": dpi,
                "skew_deg": skew,
                "noise_sigma": noise,
                "blur": blur,
                "jpeg_quality": jpeg_q,
                "pages": n,
                "source_pages": f"{start + 1}-{start + n}",
                "columns": cols,
                "source_text_quality": round(quality, 3),
                "source_word_ratio": round(word_ratio, 3),
                "ground_truth_fragmented": fragmented,
                "arabic_chars": profile["arabic"],
                "latin_chars": profile["latin"],
            })
            print(f"      -> {out_name} ({label}, {dpi} dpi, q{jpeg_q})")

    (dest / "bench_manifest.json").write_text(
        json.dumps(
            {
                "note": "Benchmark fixtures for the OCR engine head-to-head. "
                        "Derived from PUBLIC legal PDFs. No firm data.",
                "pages_per_fixture": args.pages,
                "fixtures": manifest,
            },
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    n_ar = sum(1 for m in manifest if m["language"] == "ar")
    n_en = sum(1 for m in manifest if m["language"] == "en")
    print(f"\nWrote {len(manifest)} fixtures ({n_ar} Arabic, {n_en} English) "
          f"-> {dest / 'bench_manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
