# Native (non-OCR) extraction accuracy

> ## The gap this closes
>
> Every accuracy figure this project has published is for the **OCR path** — documents that arrive as images. `reports/paddleocr_vl_benchmark.md` quotes CER 0.095 Arabic and 0.013 English; `reports/arabic_preprocess_sweep.md` and `reports/dpi_probe_300.md` tune that path. Documents that arrive as digitally-produced PDFs never touch an OCR engine at all: their text is read straight out of the PDF's text layer. That path had **one blended number** in `evaluation_report.md` — CER 0.376 when this work began, and 0.184 since that report was regenerated against current code — with no split by language and no split by extractor.
>
> This report measures it: by extractor, by language, against authored and transcribed references, using the scoring functions imported directly from `scripts/evaluate.py`.
>
> ## Measured on authored and transcribed references, by design
>
> No reference here is taken from a PDF's own text layer. That reference is circular for the PyMuPDF arms — PyMuPDF reading the text layer *is* what is being measured — and on Arabic it is actively wrong, because the corpus's Arabic publishers store presentation forms in visual order and a text-layer reference would score a **correct** repair as an error. See `scripts/make_text_ground_truth.py` for the full argument.

Generated: 2026-08-16 05:34:47
Fixtures: 7 documents (6 authored, 1 transcribed), 13 referenced pages
Scoring: `scripts/evaluate.py` — `cer`, `wer`, `bag_error`, `_split_by_script`, unmodified
Harness: [`scripts/native_extraction_benchmark.py`](../scripts/native_extraction_benchmark.py) · fixtures: [`scripts/make_native_fixtures.py`](../scripts/make_native_fixtures.py)

---

## Verdict

- **The native path is essentially exact on Arabic.** CER **0.0016** against authored ground truth — versus **0.095** for the same text read by Tesseract from a raster. Three of the six authored fixtures score **0.0000**, including the hardest bidi case in the corpus.
- **English is comparable to OCR, not better.** CER **0.011** native vs **0.013** OCR. Both are already near the floor; the difference is not meaningful.
- **PyMuPDF and PyMuPDF+Docling are byte-identical on text.** Not close — identical, to four decimals, on every fixture. This is not a surprise once the code is read, and the reason is in [Docling is not a text extractor here](#docling-is-not-a-text-extractor-on-the-pdf-path).
- **Docling as a standalone extractor is worse and less stable**: Arabic CER 0.1785 vs 0.0016, it collapses clause structure, and it dropped every referenced page of one document. **PyMuPDF stays primary.**
- **The visual-order fix is active on this path and is load-bearing.** It is not merely "also covered" — it is what takes the Arabic statute fixture from 0 structural markers to 13, and it is the reason the Arabic CER is 0.0016 rather than catastrophic. Details in [The visual-order question](#the-visual-order-question-answered-explicitly).

---

## Results

Mean of per-document CER, the aggregation every prior report uses. `no-space` strips whitespace before comparing, isolating glyph-level accuracy — the figure the OCR reports quote.

`synthetic_contract_bilingual.pdf` is excluded from these means and reported separately below: its reference is **demonstrably incomplete**, not its extraction (bag error 0.000 with 930 output words against 665 reference words — every reference word present, plus 265 words of real document content the reference omits). Including it would not measure extraction.

### Extraction accuracy — the extractor's own output

| Extractor | Language | CER | CER (no-space) | WER | Bag error | Docs |
|---|---|---|---|---|---|---|
| **PyMuPDF** | ar | 0.0054 | **0.0016** | 0.0365 | 0.0365 | 3 |
| **PyMuPDF** | en | 0.0094 | **0.0107** | 0.0112 | 0.0112 | 4 |
| **PyMuPDF + Docling** | ar | 0.0054 | **0.0016** | 0.0365 | 0.0365 | 3 |
| **PyMuPDF + Docling** | en | 0.0094 | **0.0107** | 0.0112 | 0.0112 | 4 |
| Docling only | ar | 0.1735 | **0.1785** | 0.2504 | 0.0391 | 3 |
| Docling only | en | 0.0220 | **0.0228** | 0.0267 | 0.0042 | 3 |

Docling-only covers one document fewer: it failed outright on `eg_official_gazette_excerpt.pdf` — see [Reliability](#reliability).

### As shipped — including the chunker's heading prefixes

| Extractor | Language | CER (no-space) | WER | Bag error |
|---|---|---|---|---|
| **PyMuPDF** | ar | 0.0077 | 0.0417 | 0.0365 |
| **PyMuPDF** | en | 0.0614 | 0.0610 | 0.0014 |
| PyMuPDF + Docling | ar | 0.0077 | 0.0417 | 0.0365 |
| PyMuPDF + Docling | en | 0.0614 | 0.0610 | 0.0014 |
| Docling only | ar | 0.1846 | 0.2555 | 0.0391 |
| Docling only | en | 0.0228 | 0.0267 | 0.0042 |

**Why two tables, and which one to quote.** `ChunkingConfig.attach_heading_to_body` prepends the governing clause label to each chunk so that a retrieved chunk is self-describing — `Clause 1`, `Annex A`, `المادة 3`. It is a retrieval feature, and it puts text into the output that was never in the document. A word-level diff of `native_authored_award_en.pdf` shows the **entire** residual error under "as shipped" is seven insertions, all of them heading labels:

```
insert  REF[31:31]=[]  HYP[31:33]=['Clause', '1']
insert  REF[90:90]=[]  HYP[92:94]=['Clause', '4']
insert  REF[134:134]=[] HYP[138:140]=['Clause', '6']
...
```

Turn the feature off and the same document scores **0.0000**. So the "as shipped" column charges the extractor for the chunker's annotations. **Quote the extraction table when asking how well the path reads a document**, and the as-shipped table only when comparing against `evaluation_report.md`'s blended figure, which is measured the same contaminated way.

### Reconciling with `evaluation_report.md`'s blended figure

`evaluation_report.md` reports **CER 0.184** over the same 7 documents and 13 pages. This report's as-shipped, all-7 equivalent is **0.138**. Same fixtures, same code, same run of the pipeline — the gap is one deliberate methodology choice:

- `evaluate.py` scores **each referenced page against that page's output**, then averages the per-page scores.
- This report **concatenates** a document's page references and scores once, wherever the references cover every page of the document (`scope_used` records which was used per row).

Page scope charges page *attribution* as if it were misreading. `eg_official_gazette_excerpt.pdf` is the clear case: scored per page it is 0.317, scored concatenated it is **0.012**, because a block near the page 2/3 boundary is emitted one page from where the transcription puts it — page 2's bag error is 0.009 (every word present) while page 3's is 0.289 (words missing, because they landed on page 2). Not one character differs.

Five of the seven documents score **identically** under both methods. Only the two whose references span a page boundary move.

**Both are legitimate; they answer different questions.** Page scope answers *"is a citation to page N going to retrieve page N's text?"* — which matters for a legal-retrieval product. Concatenation answers *"did the extractor read the document correctly?"* — which is what this report is about.

### Per document

Extractor: PyMuPDF (PyMuPDF+Docling is identical on every row). Extraction-only variant.

| Document | Ref | Pages | Lang | CER | CER (ns) | WER | Bag | Visual order repaired? |
|---|---|---|---|---|---|---|---|---|
| `native_authored_statute_ar.pdf` | authored | 3 | ar | **0.0000** | **0.0000** | 0.0000 | 0.0000 | **yes** (markers 0 → 13) |
| `native_authored_award_en.pdf` | authored | 2 | en | **0.0000** | **0.0000** | 0.0000 | 0.0000 | no Arabic |
| `stress_inline_bilingual.pdf` | authored | 1 | ar+en | **0.0000** | **0.0000** | 0.0000 | 0.0000 | **yes** (markers 0 → 5) |
| `eg_official_gazette_excerpt.pdf` | transcribed | 2 | en | 0.0114 | 0.0119 | 0.0085 | 0.0085 | no (rejected — no Arabic) |
| `stress_nested_clauses_ar.pdf` | authored | 1 | ar+en | 0.0497 | 0.0513 | 0.0800 | 0.0600 | **yes** (markers 17 → 22) |
| `stress_exhibits_footnotes.pdf` | authored | 1 | en+ar | 0.0801 | 0.0794 | 0.1233 | 0.0529 | no (rejected: 11 → 13 below gain threshold) |
| `synthetic_contract_bilingual.pdf` | authored* | 3 | ar+en | 0.6008 | 0.6103 | 0.7158 | **0.0000** | **yes** (markers 5 → 15) |

\* reference incomplete — see below.

### Against the OCR path, same text, same reference

The strongest comparison available: `make_native_fixtures.py` renders **the same authored pages** that `scan_authored_*` rasterises, so these rows differ only in whether the text was read from a text layer or recognised from an image.

The columns below are the **scan fixture's raster resolution**, not the render DPI the reader is OCR'd at — those are two different settings and conflating them is the easiest mistake to make here.

| Authored text | Native (this report) | Tesseract, `_150dpi` scan | Tesseract, `_300dpi` scan | PaddleOCR-VL |
|---|---|---|---|---|
| Arabic statute | **0.0000** | 0.120 | 0.015 | 0.096 / 0.011 |
| English award | **0.0000** | 0.013 | 0.009 | 0.000 / 0.000 |

OCR figures from `reports/paddleocr_vl_benchmark.md`, where every engine reads at a **150 dpi render**. **Native extraction of Arabic is exact where OCR of the identical page is not** — which is the expected direction, and it is now measured rather than assumed.

**`evaluation_report.md` reports higher numbers for the same fixtures, and the reason is the render DPI, not a disagreement.** It runs the shipped `ocr.render_dpi = 300`:

| Fixture | This table (render @150 dpi) | `evaluation_report.md` (render @300 dpi) |
|---|---|---|
| `scan_authored_statute_ar_150dpi.pdf` | 0.120 | 0.274 |
| `scan_authored_statute_ar_300dpi.pdf` | 0.015 | 0.037 |
| `scan_authored_award_en_150dpi.pdf` | 0.013 | 0.010 |
| `scan_authored_award_en_300dpi.pdf` | 0.009 | 0.008 |

English agrees to within a rounding step; Arabic roughly doubles, because rendering a 150 dpi scan at 300 dpi upsamples a raster that has no extra detail to recover. That is the same effect `reports/dpi_probe_300.md` measures directly, and it is why `render_dpi` stays at 300 for print-size reasons rather than for body-Arabic reasons. **Neither number is wrong; quote the render DPI alongside either.**

---

## The visual-order question, answered explicitly

The brief asked not to assume the earlier fix's coverage extends to native PDFs just because both use PyMuPDF. It does, and here is the specific evidence rather than an inference.

**The fix is on this exact code path.** `extract_pdf_pymupdf` — the only function that reads text from a native PDF — calls `page.get_text("rawdict", sort=True)` and builds two readings per block in `_block_readings`: MuPDF's content-stream reading, and a `geometric_text` reconstructed from per-glyph x-positions and inverted with `python-bidi`. `extract_text_pdf` then calls `_resolve_reading_order`, which chooses between them once per document. There is no separate, unpatched native route: `src/pipeline.py:202` routes every text page of every PDF through `extract_text_pdf`.

**It fires, and it decides both ways.** Across the seven fixtures the verdict was `repaired` on four and `rejected` on three, with the rejections reasoned rather than incidental — `stress_exhibits_footnotes.pdf` was rejected because reordering moved markers only 11 → 13, below the gain threshold. The document-level verdict is written to `engine_log` with its numbers on every run.

**It is load-bearing, not incidental.** On `native_authored_statute_ar.pdf` — Arabic drawn as presentation forms in visual order, which is what every Arabic PDF in `test_corpus/public/` does — the repair takes structural markers from **0 to 13** and the document's CER to **0.0000**. Without it the same file yields no clause structure at all.

**No new follow-up item.** The scope boundary said to flag rather than fix if the bug applied here uncovered. It does not apply uncovered: it applies, and it is covered.

### What could not be authored, and why it is worth recording

A logical-order Arabic control fixture was attempted — the same text drawn unshaped — to separate "the producer stored visual order" from "our extraction mangles Arabic". **It cannot be built with the tools pinned in this repo.** ReportLab has no bidi engine: `drawString` paints codepoints left-to-right in the order given, which for an RTL script *is* visual order. The result is a third thing no producer emits — visual order with unshaped glyphs — and PyMuPDF returns `مقر نوناق` for `قانون رقم`, with neither reading recovering a marker. The fixture was withdrawn rather than published as a false negative.

The corpus's real logical-order Arabic producers are the public PDFs that `scripts/audit_ground_truth.py` labels `reference_word_order = logical` (`wipo_eg088ar_1.pdf`, out-of-flow 0.000; `wipo_eg081ar_1.pdf`, 0.076). The pipeline already handles those correctly by **rejecting** the reorder — `wipo_eg081ar_1.pdf` scores better reordered on the orthographic test and is refused anyway, because doing so would take its markers from 238 to 12.

---

## Docling is not a text extractor on the PDF path

The brief framed this as "PyMuPDF vs Docling". On this pipeline that framing does not survive reading the code, and that is the single most useful finding here for anyone planning work on this path.

`extract_text_pdf` runs PyMuPDF for **all** PDF text. Docling then does exactly two things: `_merge_docling_labels` stamps semantic labels onto PyMuPDF's blocks by bbox overlap — its docstring states *"Text is never taken from Docling"* — and `_docling_tables` supersedes PyMuPDF's tables on pages where TableFormer found any. Docling's own text is used only for DOCX, via `_pages_from_docling_only`, because PyMuPDF cannot read DOCX at all.

That is why the two PyMuPDF arms are identical to four decimals on every fixture. **The ~5 s/page Docling costs on the PDF path buys layout labels and table structure — not one character of text accuracy.** That is a defensible trade, but it should be made knowingly.

The third arm answers the question the framing was really asking: *would Docling read these better if we let it?* It was run by monkeypatching `_pages_from_docling_only` over the PDF route inside the benchmark; nothing in `src/` was modified.

**It would not.** Arabic CER 0.1785 vs 0.0016 — two orders of magnitude worse — and the reasons are structural rather than incidental:

- **No glyph geometry, so no visual-order repair is possible.** Docling returns assembled text, not per-glyph positions, so there is no second reading to choose between. On `stress_inline_bilingual.pdf`, the corpus's hardest bidi fixture, PyMuPDF scores 0.0000 and Docling-only scores **0.589**.
- **Clause structure collapses.** On `stress_nested_clauses_ar.pdf` — five levels of clause numbering — PyMuPDF produces 13 chunks and Docling-only produces **1**. On the three-page Arabic statute, 12 chunks against 7.
- **Page attribution is unreliable.** On the two-page `native_authored_award_en.pdf` Docling puts 10 of 12 items on page 1. (The harness compensates: where references cover every page it concatenates and scores document-wide, so this costs Docling nothing in the numbers above.)

Where Docling-only *does* win is English prose with heavy annex structure — `stress_exhibits_footnotes.pdf` at 0.037 against PyMuPDF's 0.080, because it reflows the annex headings the reference expects. That is a real strength and it is why Docling earns its place as a **labeller**. It is not an argument for making it the extractor.

---

## Failure modes specific to native extraction

These are not OCR problems. None of them involves an image.

**1. Presentation forms in visual order — the dominant one, and it is repaired.** Arabic DTP producers shape text before writing it, so the content stream holds presentation forms in painted order. Left alone this destroys all clause structure. Covered by `src/visual_order.py`; see above. **Status: solved, measured at 0.0000 on authored ground truth.**

**2. Word-level visual reversal — not repaired, and not repairable from geometry.** A producer that reverses each line's *words* while leaving each word's characters logical (`constitute_egypt_2019_ar.pdf`) gives glyph geometry nothing to work with, because every signal in the order score is character-positional. **Status: known, already documented as README limitation #9, unchanged by this work.**

**3. Digit order in RTL numeric runs — flagged, never guessed.** `٢١` and `١٢` are the same bytes in the same order in a visually-laid-out page. **Status: deliberate; README limitation #14.**

**4. The visual-order verdict is per document, so a minority-script heading in a majority-other-script document goes unrepaired.** This is the one genuinely new defect this measurement found, and it accounts for most of the residual error.

`stress_exhibits_footnotes.pdf` is an English contract with Arabic annex headings. Its document-level verdict is **rejected** — reordering moves markers only 11 → 13, below the required gain — which is the right call for the document as a whole. But the Arabic headings inside it *are* stored in visual order, and they stay reversed:

```
REF:  1 - التعريفات            HYP:  التعريفات- 1
REF:  - السياسات المحاسبية      HYP:  السياسات المحاسبية-
```

Its English stream scores **0.0000** and its overall CER is 0.0794 — all of it in those headings. The all-or-nothing-per-document design is deliberate and well argued in `_resolve_reading_order`'s docstring (a two-line heading carries almost no evidence on its own, and half a document reversed is worse than either extreme). But its cost is now measured rather than assumed: **a document whose majority script does not need repair will not get it for the minority script that does.**

This is a **new follow-up item, not fixed here** — the scope boundary for this task was measurement, and changing the granularity of the reading-order verdict deserves the same care and test coverage the original fix received. See [Follow-ups](#follow-ups).

**5. Order-insensitive checking confirms nothing is being lost wholesale.** Bag error — which ignores word order entirely — is 0.0202 across the six scored fixtures against a CER of 0.0238. The two move together at this scale, which means the residual is a small amount of genuinely reordered or re-tokenised text (the Arabic headings above, and hyphen-joined tokens such as `التعريفات-`), not large-scale misreading. Under the as-shipped measurement the two diverge sharply — bag 0.0169 against CER 0.0573 — and that entire gap is the chunker's heading prefixes.

**6. No font-encoding or ligature damage was observed on this corpus.** Two failure modes the brief anticipated — broken ToUnicode CMaps and ligature mishandling — produced **zero** measurable error on these fixtures. That is not a claim they cannot occur: the corpus already contains one published statute whose text layer decodes to mojibake, and `type_detection.text_layer_quality` catches it and reroutes to OCR before extraction sees it (README limitation #8). The threshold (0.50) was calibrated on the documents available here. **Status: not observed, mitigated by detection rather than by extraction, and the threshold is the thing to re-check on firm material.**

**7. Native tables extract correctly, and this is unchanged.** `synthetic_contract_bilingual.pdf` declares 2 tables and all three arms found 2. The corpus-wide native table figure remains 1.000 (`evaluation_report.md`, 7 documents). PyMuPDF's `find_tables` needs ruling lines; Docling's TableFormer covers borderless ones — which is a second reason to keep Docling in the merge even though it contributes no text.

### The one document whose reference is wrong

`synthetic_contract_bilingual.pdf` scores CER 0.601 with **bag error 0.000**. Every word of the reference is present in the output. The output has 930 words against the reference's 665 — the extra 265 are real document content the reference omits, because the reference is the clause text handed to the generator and the generator also renders a header banner, a party/address block and table cells:

```
REF:  عقد توريد وتركيب SUPPLY AND INSTALLATION AGREEMENT تمهيد حيث ان الطرف الاول شركة …
HYP:  عقد توريد وتركيب SUPPLY AND INSTALLATION AGREEMENT [SYNTHETIC TEST DOCUMENT - FABRICATED DATA] 12 شارع النيل، الدقي، الجيزة …
```

This is a **reference defect of exactly the class `audit_ground_truth.py` exists to catch**, and it is the single largest contributor to `evaluation_report.md`'s blended figure — 0.622 of the seven per-document scores that average to 0.184. Fixing the fixture is a scoped follow-up: `make_text_ground_truth.py` should build this reference from the same block list the renderer draws, not from the clause list alone. Until then the document is reported and excluded, never silently averaged in.

---

## Reliability

| Arm | Documents | Failed | Pages dropped |
|---|---|---|---|
| PyMuPDF | 7 | 0 | 0 |
| PyMuPDF + Docling | 7 | 0 | 0 |
| Docling only | 7 | **1** | all referenced pages of `eg_official_gazette_excerpt.pdf` |

Docling-only raised `std::bad_alloc` from native code on the 29-page gazette and returned no output for the referenced pages. This is the failure mode README limitation #1 already documents, and it is why `docling_max_pages` exists — the benchmark deliberately raised that guard, because a document the guard would have skipped cannot be measured. **Production is unaffected**: PyMuPDF supplies the text, so a Docling failure there costs labels, not content.

A dropped page is recorded as a dropped page, never scored as CER 1.0. Folding a stability failure into an accuracy mean is precisely what the OCR reports refuse to do, and this one refuses too.

---

## Recommendation

**Keep PyMuPDF primary for native PDFs. Keep Docling in the merge for labels and tables. Do not promote Docling to extractor.**

The evidence is not close. Docling-only is 100x worse on Arabic, collapses clause structure to a single chunk on the deepest-numbered fixture, cannot participate in visual-order repair at all because it does not expose glyph geometry, mis-attributes pages, and is the only arm that failed a document outright. Its genuine strength — reflowing annex and heading structure in English prose — is already captured by using it as a labeller, which is what the pipeline does.

The one decision this report *does* put on the table is narrower: **Docling costs ~5 s/page on the PDF path and contributes zero text accuracy.** On an archive that is mostly native PDFs, `use_docling=False` would be roughly 50x faster at identical CER, at the cost of layout labels and borderless-table structure. That is a real trade with a real price on both sides, and it should be made against the firm's actual mix of documents rather than pre-empted here.

---

## Follow-ups

Two items this measurement opened and deliberately did **not** close, because both deserve to be scoped and tested rather than patched inline.

**F1 — Reading-order verdict granularity.** The visual-order repair decides once per document. A document whose majority script needs no repair therefore denies it to a minority script that does — measured on `stress_exhibits_footnotes.pdf`, where English scores 0.0000 and the Arabic annex headings stay reversed, giving an overall 0.0794. A plausible shape is a per-script verdict (decide separately over the Arabic blocks and the Latin blocks) rather than per-block, which would keep the "a heading carries no evidence on its own" argument intact while removing the cross-script coupling. Needs the same treatment the original fix got: a fixture that isolates it, a false-positive check against `wipo_eg081ar_1.pdf` (which must still be rejected), and tests in `test_visual_order.py`. **Not attempted here — the task's scope boundary was measurement.**

**F2 — `synthetic_contract_bilingual.pdf`'s reference is incomplete.** It omits the header banner, party block and table cells the generator actually renders, which is why the document scores CER 0.60 at bag error 0.000. `make_text_ground_truth.py` should build this reference from the same block list `make_contract_pdf` draws, not from `CONTRACT_CLAUSES_AR/EN` alone. Until it does, the document is excluded from headline means here and inflates the blended figure in `evaluation_report.md`.

---

## Caveats

1. **Seven documents, thirteen pages.** Small, and deliberately so: every reference is authored or hand-transcribed, and both are expensive. The Arabic figure rests on three documents. It is enough to establish that the path is not broken and that Arabic is exact on visually-ordered producers; it is not enough to characterise the long tail of PDF producers a firm archive contains.
2. **Authored fixtures are produced by ReportLab.** They model one producer's behaviour — shaped presentation forms in visual order — which is the dominant Arabic case in this corpus but not the only one in the world. The transcribed gazette pages are the only non-synthetic reference here.
3. **`synthetic_contract_bilingual.pdf` is excluded from the headline means** for the reference defect documented above. Both the with- and without- figures are given so the exclusion can be checked rather than trusted.
4. **The as-shipped/extraction-only split is a property of this measurement, not a config recommendation.** `attach_heading_to_body` should stay on; it exists for retrieval. It simply must not be measured as if it were extraction.
5. **One machine, one run per arm.** Timings here are incidental; for the durable per-path ratios see the README's performance section and `reports/speed_outlier_investigation.md`.

---

## Reproducing

```bash
python scripts/make_native_fixtures.py            # build the authored native PDFs
python scripts/native_extraction_benchmark.py     # 3 arms x 2 variants, ~5 min
```

Writes `reports/native_extraction_accuracy.json`. The new fixtures are registered in `text_reference/native_reference_manifest.json` and are picked up automatically by `scripts/evaluate.py`, so the main evaluation report's text-extraction figure now covers them too.
