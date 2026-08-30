"""Generate ``test_corpus/manifest.md`` from the corpus logs plus live probing.

Run after the corpus scripts::

    python scripts/fetch_public_corpus.py
    python scripts/make_synthetic_corpus.py
    python scripts/make_stress_fixtures.py
    python scripts/make_text_ground_truth.py
    python scripts/audit_ground_truth.py
    python scripts/build_manifest.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import src  # noqa: E402

src.quiet_third_party_logs()

from src.config import PUBLIC_CORPUS_DIR, SYNTHETIC_CORPUS_DIR, TEST_CORPUS_DIR  # noqa: E402
from src.structure_preservation import detect_language  # noqa: E402
from src.type_detection import detect  # noqa: E402

HEADER = """# Test Corpus -- Manifest

> ## THIS CORPUS CONTAINS NO FIRM DATA, BY DESIGN
>
> Everything here is either a publicly published legal document or a file this
> project fabricated for testing. Nothing came from a client, a matter, or the
> firm's archive.
>
> That is the design, not a stage. The engagement constraint is that no
> document leaves the firm, so the system was built and validated to be
> **evaluable without client material**: published Egyptian legislation supplies
> real legal Arabic and real publisher defects, and synthetic fixtures supply
> exact ground truth for the cases published documents cannot provide. **This
> pipeline has not processed a real client document and does not need to have
> done so for the numbers in the evaluation report to hold.**
>
> What the corpus cannot tell you is stated plainly in *Permanent limits of this
> corpus* below. Those are properties of the approach, not gaps awaiting data.

## Pointing the pipeline at other documents

Drop files into `test_corpus/real/` (git-ignored) and run
``python scripts/evaluate.py --corpus-dir test_corpus/real``. No code changes;
the corpus location is the only coupling. This exists so the firm can run the
evaluation **on its own hardware, on its own documents, without sending them
anywhere** -- not because the results below are provisional.

"""

QUIRK_LEGEND = """
## How to read the "expected quirks" column

Each file was built or chosen to exercise a specific failure mode. A quirk is
**a property of the file**, not a known bug: when the pipeline flags something
on one of these documents, that is usually the correct behaviour being
demonstrated.
"""


def probe(path: Path) -> dict:
    """Detect real properties of a file rather than trusting its generator."""
    info: dict = {"size_kb": round(path.stat().st_size / 1024)}
    try:
        det = detect(path)
        info["file_type"] = det.file_type.value
        info["route"] = det.route.value
        info["pdf_kind"] = det.pdf_kind
        if det.pdf_report:
            info["pages"] = det.pdf_report.n_pages
            info["text_layer_chars"] = det.pdf_report.total_chars
            info["scanned_pages"] = len(det.pdf_report.scanned_pages)
    except Exception as exc:  # noqa: BLE001
        info["probe_error"] = str(exc)[:120]

    # Language, sampled from the source itself.
    try:
        if path.suffix.lower() == ".pdf":
            import fitz

            with fitz.open(path) as d:
                sample = "".join(d[i].get_text() for i in range(min(5, d.page_count)))
        elif path.suffix.lower() in (".txt", ".md"):
            sample = path.read_text(encoding="utf-8", errors="replace")[:8000]
        elif path.suffix.lower() == ".docx":
            from docx import Document

            sample = "\n".join(p.text for p in Document(str(path)).paragraphs)[:8000]
        else:
            sample = ""
        if sample.strip():
            info["language_detected"] = detect_language(sample).value
    except Exception:  # noqa: BLE001
        pass
    return info


def main() -> int:
    lines: list[str] = [HEADER]
    lines.append(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")

    # ---------------- public --------------------------------------------
    log_path = PUBLIC_CORPUS_DIR / "download_log.json"
    public_log = (
        {e["file"]: e for e in json.loads(log_path.read_text(encoding="utf-8"))["files"]}
        if log_path.exists() else {}
    )

    lines.append("## `public/` -- published legal documents\n")
    lines.append(
        "Public-law texts from open repositories. Legislative text carries no "
        "copyright restriction. Downloaded by `scripts/fetch_public_corpus.py`, "
        "which re-runs idempotently.\n"
    )
    lines.append(
        "| File | Source | Description | Format | Language | Pages | Quirks / relevance |"
    )
    lines.append("|---|---|---|---|---|---|---|")

    from evaluate import EXCLUDED

    for path in sorted(PUBLIC_CORPUS_DIR.glob("*.pdf")):
        if path.name in EXCLUDED:
            continue
        entry = public_log.get(path.name, {})
        info = probe(path)
        quirks = []
        if info.get("pdf_kind") == "text":
            quirks.append("digitally native (text layer present)")
        if info.get("language_detected") == "ar":
            quirks.append("real published Arabic legal drafting")
        if "constitute" in path.name:
            quirks.append("article-per-section structure; two-column layout")
        if "wipo" in path.name:
            quirks.append("statute with المادة numbering; long (up to 94pp)")
        if "gazette" in path.name:
            quirks.append("official gazette formatting; unofficial translation")
        lines.append(
            f"| `{path.name}` | {entry.get('source', 'n/a')} | "
            f"{entry.get('description', 'n/a')} | PDF / {info.get('pdf_kind', '?')} | "
            f"{info.get('language_detected', '?')} | {info.get('pages', '?')} | "
            f"{'; '.join(quirks) or '-'} |"
        )
    lines.append("")

    # ---------------- exclusions ----------------------------------------
    if EXCLUDED:
        lines.append("### Present on disk, excluded from every metric\n")
        lines.append(
            "Listed rather than deleted. A document dropped silently is "
            "indistinguishable from a document nobody thought to test, and the "
            "reason for an exclusion is itself a finding about the corpus.\n"
        )
        lines.append("| File | Why excluded |")
        lines.append("|---|---|")
        for name, reason in EXCLUDED.items():
            lines.append(f"| `{name}` | {reason} |")
        lines.append("")

    # ---------------- synthetic -----------------------------------------
    synth: dict[str, dict] = {}
    for man_path in (SYNTHETIC_CORPUS_DIR / "synthetic_manifest.json",
                     SYNTHETIC_CORPUS_DIR / "stress_manifest.json"):
        if man_path.exists():
            synth.update({
                e["file"]: e
                for e in json.loads(man_path.read_text(encoding="utf-8"))["files"]
            })

    lines.append("## `synthetic/` -- fabricated test documents\n")
    lines.append(
        "**All data invented.** Party names, national IDs, addresses, amounts, "
        "dates and case numbers are fictional. The legal phrasing imitates the "
        "*shape* of standard-form Egyptian instruments so structure detection "
        "has something realistic to parse; it is not legal drafting.\n"
    )
    lines.append(
        "Generated deterministically by `scripts/make_synthetic_corpus.py` "
        "(seed 20260811), so the corpus is reproducible.\n"
    )
    lines.append("| File | Format | Language mix | Structure | Expected quirks |")
    lines.append("|---|---|---|---|---|")

    for path in sorted(SYNTHETIC_CORPUS_DIR.glob("*")):
        if path.suffix == ".json" or path.name.endswith(".groundtruth.txt"):
            continue
        if path.is_dir() or path.name in EXCLUDED:
            continue
        entry = synth.get(path.name, {})
        info = probe(path)
        fmt = entry.get("format", info.get("file_type", "?"))
        if entry.get("pdf_type"):
            fmt = f"{fmt} / {entry['pdf_type'].split('(')[0].strip()}"
        quirks = entry.get("quirks", [])
        quirk_text = "<br>".join(f"- {q}" for q in quirks) if quirks else "-"
        lines.append(
            f"| `{path.name}` | {fmt} | {entry.get('language_mix', info.get('language_detected', '?'))} | "
            f"{entry.get('structure', '-')} | {quirk_text} |"
        )
    lines.append("")

    # ---------------- ground truth --------------------------------------
    gts = sorted(SYNTHETIC_CORPUS_DIR.glob("*.groundtruth.txt"))
    audit_path = SYNTHETIC_CORPUS_DIR / "reference_audit.json"
    audit = (
        {r["file"]: r for r in
         json.loads(audit_path.read_text(encoding="utf-8"))["results"]}
        if audit_path.exists() else {}
    )
    if gts:
        lines.append("## Ground truth, and how far each reference can be trusted\n")
        lines.append(
            "Ground truth here comes from one of two places, and the difference "
            "decides what a score against it means.\n"
        )
        lines.append(
            "**Authored.** The text was written first and then painted onto a "
            "page (`scan_authored_*`). The reference is correct by construction. "
            "These are the only fixtures whose absolute OCR accuracy needs no "
            "caveat.\n"
        )
        lines.append(
            "**Derived.** The fixture was rasterized from a public PDF and that "
            "PDF's text layer is the reference. Cheap and plentiful, but it "
            "inherits the publisher's defects -- and two publishers in this "
            "corpus have serious ones. `scripts/audit_ground_truth.py` measures "
            "which, per fixture, so a bad reference is never mistaken for bad "
            "OCR:\n"
        )
        lines.append("- `authored` -- written, not extracted. Trusted.")
        lines.append("- `logical` -- derived, and the audit found nothing wrong. Trusted.")
        lines.append("- `visual` -- the publisher stored each line's words in "
                     "visual (right-to-left) order. Every character is correct, "
                     "so the file looks fine to a reader, but a correct OCR "
                     "result scores ~0.70 CER against it.")
        lines.append("- `out_of_flow` -- all the words are present (low bag error) "
                     "but the content stream emits them in a different order "
                     "from the page, typically because of a marginal annotation "
                     "column. Inflates CER without any recognition error.")
        lines.append("- `unreliable` -- high error that reordering does not "
                     "explain. Do not quote its absolute number.")
        lines.append("")
        lines.append(
            "A **head-to-head between engines stays valid on every fixture**, "
            "including the untrusted ones, because both engines face the same "
            "reference. Only absolute accuracy is affected.\n"
        )
        lines.append("| Ground truth | Scored document | Chars | Reference verdict |")
        lines.append("|---|---|---|---|")
        for gt in gts:
            target = gt.name.replace(".groundtruth.txt", ".pdf")
            n = len(gt.read_text(encoding="utf-8", errors="replace"))
            verdict = audit.get(target, {}).get("reference_word_order", "not audited")
            lines.append(f"| `{gt.name}` | `{target}` | {n:,} | {verdict} |")
        lines.append("")
        lines.append(
            "> **Derived scans remain an optimistic bound on real-world OCR.** A "
            "rasterized digital PDF has clean glyph rendering and no scanner "
            "optics, photocopy generations, bleed-through, staple shadows or "
            "marginalia. Scans made on real office hardware will score worse. "
            "This is a permanent property of validating without firm data, not "
            "a gap that later data closes.\n"
        )

    # ---------------- text-layer references -------------------------------
    text_manifest = SYNTHETIC_CORPUS_DIR / "text_reference" / "text_reference_manifest.json"
    if text_manifest.exists():
        data = json.loads(text_manifest.read_text(encoding="utf-8"))
        lines.append("## Reference text for the non-OCR path\n")
        lines.append(
            f"Built by `scripts/make_text_ground_truth.py`: "
            f"{data['pages_covered']} pages across {data['documents']} documents. "
            "This is what makes text-layer extraction accuracy measurable; "
            "before it existed, the majority path through the pipeline had no "
            "number at all.\n"
        )
        lines.append(
            "**The reference is never the PDF's own text layer.** That is "
            "circular -- reading the text layer is the thing being measured -- "
            "and on Arabic it is wrong: the public Arabic PDFs here store "
            "presentation forms in visual order and reverse digit runs "
            "(`wipo_eg088ar_1.pdf` page 3 renders `٢٠٢٣` and extracts `٣٢٠٢`). "
            "Such a reference would penalise the pipeline for repairing the "
            "damage correctly.\n"
        )
        lines.append("| Reference | Document | Scope | Pages | Provenance |")
        lines.append("|---|---|---|---|---|")
        for e in data["entries"]:
            lines.append(
                f"| `{e['reference']}` | `{e['document']}` | {e['scope']} | "
                f"{e['pages_covered']} | {e['provenance']} |"
            )
        lines.append("")

    # ---------------- coverage ------------------------------------------
    lines.append("## Coverage against the spec's required inputs\n")
    lines.append("| Required input | Covered by |")
    lines.append("|---|---|")
    lines.append("| Text-based PDF | all `public/*.pdf`, `synthetic_contract_bilingual.pdf` |")
    scans = sorted(SYNTHETIC_CORPUS_DIR.glob("scan_*.pdf"))
    lines.append(f"| Scanned (image-based) PDF | `scan_*.pdf` ({len(scans)} files, "
                 "all with ground truth) |")
    lines.append("| DOCX | `synthetic_contract_ar.docx`, `synthetic_lease_bilingual.docx` |")
    lines.append("| TXT | `synthetic_statute_ar.txt`, `synthetic_memo_mixed.txt`, "
                 "`synthetic_visual_order_ar.txt` |")
    lines.append("| Image | `synthetic_stamped_page.png`, `synthetic_table_page.png`, "
                 "`stress_table_*.png` |")
    lines.append("| Pure Arabic | `constitute_egypt_*_ar.pdf`, `wipo_*.pdf`, "
                 "`synthetic_statute_ar.txt` |")
    lines.append("| Pure English | `constitute_egypt_2014_en.pdf`, `eg_constitution_2014_en.pdf` |")
    lines.append("| Mixed Arabic/English | `synthetic_contract_bilingual.pdf`, "
                 "`synthetic_lease_bilingual.docx`, `synthetic_memo_mixed.txt` |")
    lines.append("| Tables (ruled) | `synthetic_contract_ar.docx`, "
                 "`stress_table_ruled_ar.png` |")
    lines.append("| Tables (borderless) | `synthetic_contract_bilingual.pdf`, "
                 "`synthetic_table_page.png`, `stress_table_wide_en.png` |")
    lines.append("| Tables (sparse / empty cells) | `stress_table_sparse_bilingual.png` |")
    lines.append("| Table across a page break | `stress_table_pagebreak.pdf` |")
    lines.append("| Multi-column layout | `constitute_egypt_*.pdf` |")
    lines.append("| Marginal annotation column | `constitute_egypt_*.pdf` (the "
                 "cause of their inflated CER; see the reference audit) |")
    lines.append("| Stamps / signatures | `synthetic_stamped_page.png` |")
    lines.append("| Damaged reading order | `synthetic_visual_order_ar.txt`, "
                 "`synthetic_contract_bilingual.pdf` |")
    lines.append("| Deeply nested clause numbering (5.2.1.b.ii) | "
                 "`stress_nested_clauses_ar.pdf` |")
    lines.append("| Arabic/English alternating mid-sentence | "
                 "`stress_inline_bilingual.pdf`, `synthetic_memo_mixed.txt` |")
    lines.append("| Exhibits, appendices, schedules, footnote markers | "
                 "`stress_exhibits_footnotes.pdf` |")
    lines.append("| Scan quality curve (300 dpi clean -> 150 dpi degraded) | "
                 "`bench_*_clean/poor.pdf`, `scan_authored_*_300dpi/150dpi.pdf` |")
    lines.append("")

    lines.append("## Permanent limits of this corpus\n")
    lines.append(
        "The engagement constraint is that no document leaves the firm, so this "
        "system is validated on public and synthetic material **by design**. "
        "The list below is therefore not a backlog. These are properties of the "
        "validation approach, and they will still be true after the system is "
        "in production -- they bound what the numbers in the evaluation report "
        "can be read to mean.\n"
    )
    lines.append("- **No genuine scans.** Every 'scanned' fixture is a rendered "
                 "page, not paper through a scanner: no feeder skew, no "
                 "photocopy generations, no bleed-through, no staple shadows. "
                 "Measured OCR accuracy is an optimistic bound and should be "
                 "read as one.")
    lines.append("- **No handwriting.** The one handwritten public document "
                 "available was excluded as unscoreable (see the exclusions "
                 "table). Handwritten margin notes and initials are not "
                 "supported by either engine as configured, and this corpus "
                 "cannot measure how badly they fail.")
    lines.append("- **No firm house style.** Letterhead, numbering conventions, "
                 "defined-term formatting and clause phrasing are unknown. The "
                 "structure detector's cue lists were written against published "
                 "statutes and synthetic contracts; retuning them against the "
                 "firm's own drafting is expected work, not a defect.")
    lines.append("- **No multi-document bundles.** Court files arrive as one PDF "
                 "containing many instruments; document-type inference assumes "
                 "one type per file and will label the bundle by whichever "
                 "instrument dominates.")
    lines.append("- **No password-protected or corrupt files.** Detection reports "
                 "them, but no end-to-end behaviour is tested.")
    lines.append("- **No pre-Unicode or fax-quality typesetting.**")
    lines.append("")
    lines.append(
        "Two of these are closable **by the firm, on the firm's own hardware, "
        "without sending anything anywhere**: point `scripts/evaluate.py "
        "--corpus-dir` at a directory of real documents and the same report "
        "regenerates against them. That is a capability the system provides, "
        "not a dependency it has.\n"
    )

    lines.append(QUIRK_LEGEND)

    out = TEST_CORPUS_DIR / "manifest.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
