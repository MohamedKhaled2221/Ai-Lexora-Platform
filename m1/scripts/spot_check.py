"""Emit side-by-side extraction samples for manual spot-checking.

The spec asks for "text extraction accuracy (spot-check against source)". For
the scanned fixtures that is measured automatically against ground truth by
``scripts/evaluate.py``. For documents with a real text layer there is no
reference transcription, so accuracy cannot be *computed* -- it has to be
eyeballed.

This script makes that eyeballing cheap: for each document it prints, side by
side, the raw text the extractor produced and the pipeline's final chunk text,
so you can open the PDF alongside and confirm the pipeline did not lose,
reorder or mangle anything.

It is deliberately separate from `evaluate.py` and fast (no OCR, no Docling),
so it can be re-run casually while tuning normalization.

Run::

    python scripts/spot_check.py
    python scripts/spot_check.py --corpus-dir test_corpus/real
    python scripts/spot_check.py --chars 600
"""

from __future__ import annotations

import argparse
import sys
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
from src.pipeline import process_document  # noqa: E402


def raw_source_text(path: Path, limit: int) -> str:
    """Text straight from the source, with no pipeline processing at all."""
    suffix = path.suffix.lower()
    try:
        if suffix == ".pdf":
            import fitz

            with fitz.open(path) as d:
                out = []
                for i in range(min(3, d.page_count)):
                    out.append(d[i].get_text("text"))
                    if sum(len(x) for x in out) > limit * 3:
                        break
                return "".join(out)
        if suffix in (".txt", ".md"):
            return path.read_text(encoding="utf-8", errors="replace")
        if suffix == ".docx":
            from docx import Document

            return "\n".join(p.text for p in Document(str(path)).paragraphs)
    except Exception as exc:  # noqa: BLE001
        return f"<could not read source: {exc}>"
    return "<binary format; no text layer to compare>"


def excerpt(text: str, limit: int) -> str:
    flat = " ".join(text.split())
    return flat[:limit] + ("..." if len(flat) > limit else "")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chars", type=int, default=400, help="excerpt length")
    parser.add_argument("--corpus-dir", type=Path, action="append")
    parser.add_argument("--out", default=str(REPORTS_DIR / "spot_check.md"))
    args = parser.parse_args()

    if args.corpus_dir:
        paths = [
            p for d in args.corpus_dir for p in sorted(d.rglob("*"))
            if p.is_file() and p.suffix.lower() in {".pdf", ".docx", ".txt"}
            and not p.name.endswith(".groundtruth.txt")
        ]
        label = ", ".join(str(d) for d in args.corpus_dir)
    else:
        paths = [
            p for p in sorted(PUBLIC_CORPUS_DIR.glob("*.pdf"))
        ] + [
            p for p in sorted(SYNTHETIC_CORPUS_DIR.glob("*"))
            if p.suffix.lower() in {".pdf", ".docx", ".txt"}
            and not p.name.startswith("scan_")
            and not p.name.endswith(".groundtruth.txt")
        ]
        label = "interim corpus (public + synthetic, text-layer documents only)"

    if not paths:
        print("No documents found.")
        return 1

    # Text-layer only: OCR accuracy is measured against ground truth elsewhere,
    # and disabling both engines keeps this script fast enough to re-run freely.
    config = PipelineConfig()
    config.ocr.enabled = False
    config.extraction.use_docling = False

    lines: list[str] = [
        "# Extraction spot-check",
        "",
        "> Manual verification aid. Open each source document alongside this "
        "table and confirm the pipeline neither lost nor reordered text.",
        "",
        f"Corpus: {label}  ",
        f"Excerpt length: {args.chars} characters  ",
        "Config: OCR off, Docling off (text-layer path only)",
        "",
        "**What to look for.** `SOURCE` is raw extractor output with no "
        "processing. `PIPELINE` is the finished chunk text after RTL repair and "
        "normalization. Differences between them should be *only*: folded "
        "Arabic orthography (أ→ا), folded digits (١٢→12), stripped tatweel and "
        "diacritics, collapsed whitespace, and an attached heading. Anything "
        "else -- missing sentences, reordered words, mangled numbers -- is a "
        "defect worth reporting.",
        "",
    ]

    print(f"Spot-checking {len(paths)} documents...")
    for path in paths:
        print(f"  {path.name}")
        result = process_document(path, config)
        source = raw_source_text(path, args.chars)
        first_chunk = result.chunks[0].text if result.chunks else "<no chunks produced>"

        lines.append(f"## `{path.name}`")
        lines.append("")
        lines.append(f"- type: `{result.file_type}`"
                     + (f" / `{result.pdf_kind}`" if result.pdf_kind not in (None, "n/a") else ""))
        lines.append(f"- detected: {result.document_type}, {result.language}, "
                     f"{result.n_pages} pages, {result.n_chunks} chunks")
        if result.warnings:
            lines.append(f"- warnings: {len(result.warnings)} "
                         f"(first: {result.warnings[0][:120]})")
        lines.append("")
        lines.append("**SOURCE** (raw extractor output)")
        lines.append("")
        lines.append("```")
        lines.append(excerpt(source, args.chars))
        lines.append("```")
        lines.append("")
        lines.append("**PIPELINE** (chunk 1 as delivered to M2/M3)")
        lines.append("")
        lines.append("```")
        lines.append(excerpt(first_chunk, args.chars))
        lines.append("```")
        lines.append("")
        if result.chunks:
            struct = result.chunks[0].metadata.get("structure") or {}
            lines.append(f"- `section`: {result.chunks[0].section!r} | "
                         f"`clause_id`: {struct.get('clause_id')!r} | "
                         f"`chunk_strategy`: {result.chunks[0].metadata.get('chunk_strategy')!r}")
            applied = result.chunks[0].metadata.get("normalization_applied")
            lines.append(f"- normalization applied: {applied}")
        lines.append("")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
