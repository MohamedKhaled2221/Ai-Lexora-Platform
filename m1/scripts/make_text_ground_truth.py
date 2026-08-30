"""Ground truth for the **text-layer** extraction path, which was never measured.

THE GAP THIS FILLS
==================

OCR accuracy had ground truth. Text extraction did not. Every text-based
document in the corpus was reported as "produced plausible output" -- an
assertion, not a measurement -- which meant the majority path through the
pipeline had no accuracy number at all.

WHY THE OBVIOUS REFERENCE DOES NOT WORK
=======================================

The tempting reference for a text-based PDF is the PDF's own text layer. It is
worthless for this purpose, twice over:

1. **It is circular.** PyMuPDF *is* how we read the text layer. Scoring our
   extraction against it measures nothing but our ability to copy a string.

2. **On Arabic it is wrong.** The public Arabic PDFs in this corpus store
   Unicode *presentation forms* in visual order, and some reverse digit runs --
   ``wipo_eg088ar_1.pdf`` page 3 renders "٢٠٢٣" but extracts "٣٢٠٢". A reference
   like that would score the pipeline's **correct** repair of that damage as an
   error, and reward leaving it broken.

So references here come from one of two places, and each entry records which:

``authored``
    The document was generated from text this project wrote. The reference is
    that text. It is correct by construction, and because the generator paints
    Arabic as visually-ordered presentation forms, scoring against it measures
    the whole ``rtl_fix`` + ``normalize`` repair path end to end -- the very
    thing the PDF's own text layer cannot measure.

``transcribed``
    A human read the rendered page and typed what it says. Used for public
    pages, where nothing was authored. Slow, so it is spent on pages whose
    script makes transcription reliable.

WHAT THE RESULTING NUMBER MEANS
===============================

It is **end-to-end content preservation**: source text in, chunk text out,
through detection, extraction, RTL repair, normalization, structure annotation
and chunking. It is not a measurement of PyMuPDF's PDF parsing. A regression
anywhere in that chain moves it.

Run::

    python scripts/make_text_ground_truth.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.config import PUBLIC_CORPUS_DIR, SYNTHETIC_CORPUS_DIR  # noqa: E402

REFERENCE_DIR = SYNTHETIC_CORPUS_DIR / "text_reference"


# ---------------------------------------------------------------------------
# Transcribed pages -- typed from the rendered page, not extracted
# ---------------------------------------------------------------------------

GAZETTE_P2 = """UNOFFICIAL TRANSLATION

Law No (70) of 2017

The Law of Associations

And Other Foundations Working in the Field of Civil Work

In the name of the People

President of the Republic

The Parliament has issued the following law and we promulgate it:

Article One

Pursuant to the provisions of the regulations of associations established in
accordance with international agreements concluded by the Arab Republic of
Egypt, and without prejudice to the provisions of Law No. 91 of 1971, the
provisions of the attached law apply to civil associations and foundations and
other organizations regulated by it.

This law and the enclosed law shall organize the freedom of practice of civil
work for the associations and organizations. It is prohibited for any entity,
under any form or title, to practice any of the civil activities without being
subject to the provisions of the enclosed law.

Article Two

All entities performing civil activities, pursuant to the definition stipulated
in the enclosed law, of any legal form or naming, shall rectify their status
pursuant to this law within one year of its effectiveness; otherwise, the
competent court shall order its dissolution.

The funds of these associations shall be transferred to the fund to support
civil associations and foundations defined in the enclosed law. Every activity
in violation of the provisions of this article shall be ceased by the force of
law.

The rectification of the status of these entities is through notifying the
concerned ministry or the National Regulatory Agency for the Work of Foreign
Non-Governmental Organizations established pursuant to the provisions of the
enclosed law, as the case may be, of all data of the association, organization,
or entity and its activities, funding sources, programs, protocols, memoranda
of understanding, and other forms of cooperation of any title that are executed
by the Arab Republic of Egypt. That shall be done using the form prepared for
that purpose. The entity shall also amend its systems to conform with the
regulations and provisions of this law and the enclosed law.

Article Three

2"""

GAZETTE_P3 = """UNOFFICIAL TRANSLATION

The Administrative Entity shall undertake the responsibility of listing the
entities that have not rectified their status in accordance with the provisions
of the enclosed law. The concerned minister shall form one or more committees
comprising the staff of the Administrative Entity and others. The membership of
the committee shall include a representative of the governorate in which the
entity is based. The committee(s) shall be responsible for the implementation
and completion of the dissolution process after the issuance of a judicial
order of the dissolution of the entity. The resolution shall define the system
and period of work of the committee(s).

Article Four

It is prohibited for any entity to practice any of the activities of
associations, and other entities stipulated in the enclosed law, without being
subject to the provisions of the enclosed law. Any entity, other than the
competent Administrative Entity pursuant to the attached law, may not, under
any form or title, license the practicing of any activity of the activities of
associations and entities provided for in the enclosed law. Such a license
shall be void and invalid ab initio and may not bear any legal effect.

Article Five

Existing boards of directors of civil associations, foundations and federations
established pursuant to provisions of law No. 84 of 2002, and their executive
and administrative bodies, shall continue to operate until they are reformed
according to its provisions.

Article Six

The Prime Minister shall issue the Executive Regulations of the enclosed law
within two months as of the date of its promulgation. Until these regulations
are issued, the current Executive Regulations and resolutions may continue in
effect notwithstanding the provisions of the enclosed law.

Article Seven

The law of civil associations and foundations No. 84 of 2002 is hereby
abolished as well as any provision that contradicts with the provisions of the
enclosed law.

Article Eight

This law is published in the official gazette and becomes effective on the next
day following its publication.

Stamped by the State Stamp and executed as one of its laws.

Issued at the Presidency of the Republic on 27 Shaban 1438 Hijria

Corresponding to 24 May 2017

Abdel Fattah el-Sisi

3"""


def build() -> list[dict]:
    from make_stress_fixtures import (
        EXHIBITS_DOC,
        INLINE_BILINGUAL,
        NESTED_CLAUSES,
    )
    from make_synthetic_corpus import CONTRACT_CLAUSES_AR, CONTRACT_CLAUSES_EN

    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    entries: list[dict] = []

    def emit(ref_name: str, document: str, corpus: str, text: str, *,
             provenance: str, pages: int, page: int | None, note: str) -> None:
        (REFERENCE_DIR / ref_name).write_text(text.strip() + "\n", encoding="utf-8")
        entries.append({
            "reference": ref_name,
            "document": document,
            "corpus": corpus,
            "scope": "page" if page else "document",
            "page": page,
            "pages_covered": pages,
            "provenance": provenance,
            "reference_chars": len(text.strip()),
            "note": note,
        })
        print(f"  {ref_name}  ({len(text.strip())} chars, {provenance})")

    # --- authored: whole-document references --------------------------------
    contract = "\n".join(
        [
            "عقد توريد وتركيب",
            "SUPPLY AND INSTALLATION AGREEMENT",
        ]
        + [line for clause in CONTRACT_CLAUSES_AR for line in clause]
        + [line for clause in CONTRACT_CLAUSES_EN for line in clause]
    )
    emit("synthetic_contract_bilingual.reference.txt",
         "synthetic_contract_bilingual.pdf", "synthetic", contract,
         provenance="authored", pages=3, page=None,
         note="Reference is the clause text the generator was given. Scored at "
              "document level because the renderer, not the source, decides "
              "where the three pages break.")

    emit("stress_nested_clauses_ar.reference.txt",
         "stress_nested_clauses_ar.pdf", "synthetic", NESTED_CLAUSES,
         provenance="authored", pages=1, page=1,
         note="Five-level clause numbering. Tests that deep numbering survives "
              "extraction and chunking without being flattened or dropped.")

    emit("stress_inline_bilingual.reference.txt",
         "stress_inline_bilingual.pdf", "synthetic", INLINE_BILINGUAL,
         provenance="authored", pages=1, page=1,
         note="Direction switches several times per line. The hardest RTL repair "
              "case in the corpus, and the reference is exact.")

    emit("stress_exhibits_footnotes.reference.txt",
         "stress_exhibits_footnotes.pdf", "synthetic", EXHIBITS_DOC,
         provenance="authored", pages=1, page=1,
         note="Four parallel numbering systems plus footnote markers.")

    # --- transcribed: public pages ------------------------------------------
    emit("eg_official_gazette_excerpt.p2.reference.txt",
         "eg_official_gazette_excerpt.pdf", "public", GAZETTE_P2,
         provenance="transcribed", pages=1, page=2,
         note="Typed from the rendered page. English, single column, clean type.")

    emit("eg_official_gazette_excerpt.p3.reference.txt",
         "eg_official_gazette_excerpt.pdf", "public", GAZETTE_P3,
         provenance="transcribed", pages=1, page=3,
         note="Typed from the rendered page. Includes italicised Latin ('ab "
              "initio') and a signature block.")

    return entries


def main() -> int:
    print("Building text-extraction references...\n")
    entries = build()

    pages = sum(e["pages_covered"] for e in entries)
    docs = len({e["document"] for e in entries})
    manifest = {
        "note": "Reference text for the NON-OCR extraction path. Authored or "
                "hand-transcribed -- never taken from the PDF's own text layer, "
                "which is both circular and, on Arabic, wrong.",
        "pages_covered": pages,
        "documents": docs,
        "why_not_the_text_layer": [
            "Circular: PyMuPDF reading the text layer is what we are trying to "
            "measure.",
            "Wrong on Arabic: public Arabic PDFs here store presentation forms in "
            "visual order and reverse digit runs (wipo_eg088ar_1.pdf page 3 "
            "renders 2023 and extracts 3202), so such a reference would penalise "
            "the pipeline for repairing the damage correctly.",
        ],
        "entries": entries,
    }
    (REFERENCE_DIR / "text_reference_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n{len(entries)} references covering {pages} pages across "
          f"{docs} documents -> {REFERENCE_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
