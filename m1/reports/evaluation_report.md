# M1 Document Processing -- Evaluation Report

> ## Measured on public and synthetic documents, by design
> 
> Every number here comes from **published Egyptian legal documents and synthetic fixtures this project generated**. No client document has been processed, and none is required: the engagement constraint is that no document leaves the firm, so the system was built to be evaluable without client material.
> 
> Published legislation supplies real legal Arabic, real statutory numbering and real publisher defects. Synthetic fixtures supply exact ground truth where published documents cannot -- most importantly the `scan_authored_*` scans, whose reference text was written before the page was rendered.
> 
> **These are results, not a provisional stand-in for results.** What this approach cannot measure is stated plainly in [Caveats](#caveats) -- those are permanent properties of validating this way, not gaps waiting on data.

Generated: 2026-08-16 17:05:55  
Corpus: 35 documents (7 public, 28 synthetic)  
Wall clock: 1156.2s  
Docling: enabled | OCR: enabled

## Summary against the spec's criteria

| Criterion | Result | Basis |
|---|---|---|
| Failure rate | **0%** (0/35 documents) | errored or produced zero chunks |
| Page preservation | **100%** | output pages >= source pages, counted from the source file |
| Section preservation | **0.860** | mean ratio of detected clause ids to markers visible in source (15 documents with >=3 markers) |
| Table extraction | **1.000** | tables emitted vs tables known present (7 documents) |
| OCR accuracy -- Arabic | **CER 0.341** | glyph-level (space-insensitive), vs ground truth, 6 scanned document(s) |
| OCR accuracy -- English | **CER 0.113** | glyph-level (space-insensitive), vs ground truth, 5 scanned document(s) |
| Processing speed | **1502 ms/page (median)** | end-to-end, CPU only |

### Beyond the spec's seven criteria

| Measurement | Result | Basis |
|---|---|---|
| Text extraction accuracy (non-OCR path) | **CER 0.184** | vs authored/transcribed reference, 13 pages across 7 documents |
| Chunking / metadata correctness | **74/74 (100%)** | vs expectations declared in advance, 14 documents |

### Excluded from this corpus

- **`wipo_eg087ar_1.pdf`** -- handwritten. Its text layer scores 0.33 on text_layer_quality and contains no Arabic at all despite being an Arabic statute, so it yields no usable ground truth and cannot be scored. It is also not representative: the firm's archive is typed and printed material. Kept in test_corpus/public/ as a robustness input -- the pipeline must not crash on it -- but excluded from every accuracy metric.

## Per-document results

| Document | Corpus | Type | Pages src/out | Chunks | Clauses | Lang | Doc type | ms/page | Status |
|---|---|---|---|---|---|---|---|---|---|
| `constitute_egypt_2014_ar.pdf` | public | pdf/text | 44/44 | 290 | 281 | ar | law | 190 | ok |
| `constitute_egypt_2014_en.pdf` | public | pdf/text | 53/53 | 343 | 343 | en | law | 144 | ok |
| `constitute_egypt_2019_ar.pdf` | public | pdf/text | 50/50 | 100 | 100 | ar | law | 181 | ok |
| `eg_constitution_2014_en.pdf` | public | pdf/text | 47/47 | 228 | 222 | en | law | 82 | ok |
| `eg_official_gazette_excerpt.pdf` | public | pdf/text | 29/29 | 134 | 134 | en | law | 998 | ok |
| `wipo_eg081ar_1.pdf` | public | pdf/text | 94/94 | 274 | 274 | ar | law | 63 | ok |
| `wipo_eg088ar_1.pdf` | public | pdf/text | 13/13 | 24 | 24 | ar | law | 1106 | ok |
| `native_authored_award_en.pdf` | synthetic | pdf/text | 2/2 | 9 | 9 | en | contract | 1528 | ok |
| `native_authored_statute_ar.pdf` | synthetic | pdf/text | 3/3 | 12 | 11 | ar | law | 1284 | ok |
| `scan_authored_award_en_150dpi.pdf` | synthetic | pdf/scanned | 2/2 | 2 | 2 | en | contract | 3676 | ok |
| `scan_authored_award_en_300dpi.pdf` | synthetic | pdf/scanned | 2/2 | 2 | 2 | en | contract | 3455 | ok |
| `scan_authored_statute_ar_150dpi.pdf` | synthetic | pdf/scanned | 3/3 | 3 | 0 | ar | law | 2947 | ok |
| `scan_authored_statute_ar_300dpi.pdf` | synthetic | pdf/scanned | 3/3 | 4 | 2 | ar | law | 2841 | ok |
| `scan_constitute_egypt_2014_ar_200dpi.pdf` | synthetic | pdf/scanned | 6/6 | 8 | 2 | ar | law | 24514 | ok |
| `scan_constitute_egypt_2014_en_200dpi.pdf` | synthetic | pdf/scanned | 6/6 | 14 | 13 | en | law | 20688 | ok |
| `scan_constitute_egypt_2019_ar_150dpi.pdf` | synthetic | pdf/scanned | 6/6 | 11 | 11 | ar | law | 30057 | ok |
| `scan_eg_constitution_2014_en_150dpi.pdf` | synthetic | pdf/scanned | 6/6 | 10 | 10 | en | law | 5031 | ok |
| `scan_eg_official_gazette_excerpt_300dpi.pdf` | synthetic | pdf/scanned | 6/6 | 14 | 14 | en | law | 4971 | ok |
| `scan_wipo_eg081ar_1_300dpi.pdf` | synthetic | pdf/scanned | 6/6 | 6 | 1 | ar | law | 5094 | ok |
| `scan_wipo_eg088ar_1_150dpi.pdf` | synthetic | pdf/scanned | 6/6 | 6 | 0 | ar | law | 5378 | ok |
| `stress_exhibits_footnotes.pdf` | synthetic | pdf/text | 1/1 | 11 | 11 | en | contract | 1502 | ok |
| `stress_inline_bilingual.pdf` | synthetic | pdf/text | 1/1 | 6 | 5 | mixed | correspondence | 1418 | ok |
| `stress_nested_clauses_ar.pdf` | synthetic | pdf/text | 1/1 | 13 | 13 | mixed | contract | 1440 | ok |
| `stress_table_pagebreak.pdf` | synthetic | pdf/text | 1/1 | 3 | 0 | mixed | unknown | 9852 | ok |
| `stress_table_ruled_ar.png` | synthetic | image | 1/1 | 2 | 0 | mixed | unknown | 1000 | ok |
| `stress_table_sparse_bilingual.png` | synthetic | image | 1/1 | 2 | 0 | mixed | unknown | 1728 | ok |
| `stress_table_wide_en.png` | synthetic | image | 1/1 | 2 | 0 | en | unknown | 1371 | ok |
| `synthetic_contract_ar.docx` | synthetic | docx | 1/1 | 17 | 15 | mixed | contract | 296 | ok |
| `synthetic_contract_bilingual.pdf` | synthetic | pdf/text | 3/3 | 19 | 19 | mixed | contract | 2060 | ok |
| `synthetic_lease_bilingual.docx` | synthetic | docx | 1/1 | 18 | 18 | mixed | contract | 148 | ok |
| `synthetic_memo_mixed.txt` | synthetic | txt | 1/1 | 4 | 3 | mixed | correspondence | 16 | ok |
| `synthetic_stamped_page.png` | synthetic | image | 1/1 | 1 | 0 | ar | correspondence | 2837 | ok |
| `synthetic_statute_ar.txt` | synthetic | txt | 1/1 | 11 | 10 | ar | law | 18 | ok |
| `synthetic_table_page.png` | synthetic | image | 1/1 | 2 | 0 | mixed | unknown | 2199 | ok |
| `synthetic_visual_order_ar.txt` | synthetic | txt | 1/1 | 11 | 10 | ar | law | 27 | ok |

## 1-2. Extraction and OCR accuracy

Measured against the ground-truth text that ships with each derived scan. Both sides run through identical normalization first, so what is reported is **recognition** error, not orthographic variation the pipeline folds deliberately.

| Document | Engine | CER ar | CER ar (no-space) | WER ar | CER en | CER en (no-space) | WER en |
|---|---|---|---|---|---|---|---|
| `scan_authored_award_en_150dpi.pdf` | tesseract | n/a | n/a | n/a | 0.009 | 0.010 | 0.025 |
| `scan_authored_award_en_300dpi.pdf` | tesseract | n/a | n/a | n/a | 0.008 | 0.008 | 0.017 |
| `scan_authored_statute_ar_150dpi.pdf` | tesseract | 0.269 | 0.274 | 0.328 | n/a | n/a | n/a |
| `scan_authored_statute_ar_300dpi.pdf` | tesseract | 0.037 | 0.037 | 0.062 | n/a | n/a | n/a |
| `scan_constitute_egypt_2014_ar_200dpi.pdf` | tesseract | 0.679 | 0.697 | 0.970 | n/a | n/a | n/a |
| `scan_constitute_egypt_2014_en_200dpi.pdf` | tesseract | n/a | n/a | n/a | 0.273 | 0.282 | 0.288 |
| `scan_constitute_egypt_2019_ar_150dpi.pdf` | paddleocr | 0.689 | 0.719 | 0.981 | n/a | n/a | n/a |
| `scan_eg_constitution_2014_en_150dpi.pdf` | tesseract | n/a | n/a | n/a | 0.141 | 0.141 | 0.144 |
| `scan_eg_official_gazette_excerpt_300dpi.pdf` | tesseract | n/a | n/a | n/a | 0.123 | 0.123 | 0.123 |
| `scan_wipo_eg081ar_1_300dpi.pdf` | tesseract | 0.142 | 0.152 | 0.305 | n/a | n/a | n/a |
| `scan_wipo_eg088ar_1_150dpi.pdf` | tesseract | 0.175 | 0.168 | 0.306 | n/a | n/a | n/a |

**Which column to believe.** `no-space` strips all whitespace before comparing, isolating glyph recognition. Several public Arabic PDFs extract with spurious intra-word spacing (`دس تور` for `دستور`) because the producer placed each glyph separately -- so the space-sensitive columns charge OCR for the *reference's* broken word boundaries. Where the two diverge sharply, the reference is at fault, not the engine. See the corpus manifest, which flags which ground-truth files have this defect.

**Reading these numbers.** CER is character error rate: 0.0 is perfect, 1.0 means as many errors as characters. Arabic CER is expected to be materially worse than English on the same page -- Arabic is cursive, position-dependent, and its diacritics and dot patterns are exactly what JPEG artifacts destroy first.

`n/a` means the document did not contain at least 300 reference characters in that language. A pure-Arabic scan holds only a few stray Latin characters, and dividing OCR's Latin-looking noise by that denominator yields a number well above 1.0 that describes nothing. Those cases are excluded rather than reported.

### ⚠ The Arabic scans disagree wildly -- read this before quoting an Arabic OCR number

`scan_authored_statute_ar_300dpi.pdf` scores **0.037** while `scan_constitute_egypt_2019_ar_150dpi.pdf` scores **0.719** -- a 0.68 spread on the same engine, the same language, and comparable degradation.

**CORRECTION.** An earlier version of this report attributed that spread to **two-column layout**: ground truth follows the PDF's content stream, OCR reads the page visually, and on a two-column page the two orders interleave. That explanation was wrong, and it was wrong in a way that mattered -- it implied the spread was a fixed measurement artifact rather than something that could be measured and separated.

Controlled fixtures rule it out. `wipo_eg081ar_1` is two-column and scores well; `wipo_eg088ar_1` has a fragmented reference and also scores well. Column count is not the driver, and neither is fragmentation -- a second hypothesis raised while investigating the first.

The actual causes are **defects in the reference**, and there are two distinct ones. `scripts/audit_ground_truth.py` measures which applies to each fixture:

- **Visual word order.** The Constitute Project's Arabic PDFs store each line's words right-to-left. Every character is correct, so the file looks fine to a reader and passes any character-level check -- but the word sequence is backwards, and correctly-read OCR is charged for it. Detected by reversing the reference's word order and re-scoring: if that helps materially, this is what happened.
- **Out-of-flow blocks.** The same publisher puts topic labels in the left margin and emits them at the *end* of each page's content stream. All the words are present -- the order-insensitive bag error is near zero -- but the sequence differs, and CER counts that as error.

The two are told apart by reading CER against **bag error**, which ignores word order entirely. High CER with low bag error is an ordering artifact; high CER with high bag error is genuine misrecognition.

**Consequence for quoting a number:** use the fixtures whose reference the audit passed, and preferentially the `scan_authored_*` fixtures, whose reference text was written before the page was rendered and therefore cannot carry any of these defects. Those are the only Arabic OCR figures here that need no caveat about the reference. The mean across all scanned documents is dragged down by reference defects and should not be quoted as accuracy.

### Text extraction accuracy (non-OCR path)

The majority path through this pipeline is the text layer, not OCR. This section measures it over **13 pages across 7 documents**.

**Read this figure as an upper bound, and read [`reports/native_extraction_accuracy.md`](native_extraction_accuracy.md) for the decomposition.** Three things inflate the number here, all of them properties of *this* measurement rather than of the extractor: it scores chunk text **as shipped**, which includes the heading labels `chunking.attach_heading_to_body` prepends (`Clause 1`, `Annex A`) and which were never in the document; it scores each referenced page against that page's output, so a block emitted one page either side of where the reference puts it is charged as error even though no character was misread; and it blends Arabic and English into one figure. Scored per language against the extractor's own output, that report measures the same fixtures at **CER 0.0016 Arabic and 0.0107 English**, with three of them exactly 0.0000. Both numbers are correct; they answer different questions. (Those two figures are quoted from that report, not recomputed here -- regenerate it with `python scripts/native_extraction_benchmark.py` if the fixtures change.)

**The reference is never the PDF's own text layer.** That would be circular, since reading the text layer is the thing being measured; and on Arabic it would be wrong, because the public Arabic PDFs here store presentation forms in visual order and reverse digit runs -- `wipo_eg088ar_1.pdf` page 3 renders `٢٠٢٣` and extracts `٣٢٠٢`. Scoring against that would penalise the pipeline for *correctly repairing* the damage. References are therefore either **authored** (the document was generated from text this project wrote) or **transcribed** (a human read the rendered page).

What is measured is **end-to-end content preservation**: source text in, chunk text out, through detection, extraction, RTL repair, normalization, structure annotation and chunking. A regression anywhere in that chain moves it.

| Document | Reference | Pages | CER | CER (no-space) | Bag error |
|---|---|---|---|---|---|
| `eg_official_gazette_excerpt.pdf` | transcribed | 2 | 0.314 | 0.317 | 0.149 |
| `native_authored_award_en.pdf` | authored | 2 | 0.052 | 0.051 | 0.007 |
| `native_authored_statute_ar.pdf` | authored | 3 | 0.022 | 0.021 | 0.000 |
| `stress_exhibits_footnotes.pdf` | authored | 1 | 0.130 | 0.128 | 0.053 |
| `stress_inline_bilingual.pdf` | authored | 1 | 0.040 | 0.038 | 0.000 |
| `stress_nested_clauses_ar.pdf` | authored | 1 | 0.111 | 0.112 | 0.040 |
| `synthetic_contract_bilingual.pdf` | authored | 3 | 0.612 | 0.622 | 0.000 |

**Mean CER (no-space): 0.184** over 7 documents.

`Bag error` ignores word order. Read it against CER: where CER is much the larger, the content was extracted but re-ordered, which on these fixtures means Arabic stored in visual order was not fully restored to logical order.

### Engine selection

`Attempted` counts pages where the fallback engine ran; `kept` counts pages where its result was the one used. An attempt costs full time either way, which is why both are shown.

| Document | Engines used (chunks) | Fallback attempted | Fallback kept |
|---|---|---|---|
| `constitute_egypt_2014_ar.pdf` | pymupdf: 290 | 0 | 0 |
| `constitute_egypt_2014_en.pdf` | pymupdf: 343 | 0 | 0 |
| `constitute_egypt_2019_ar.pdf` | pymupdf: 100 | 0 | 0 |
| `eg_constitution_2014_en.pdf` | pymupdf: 228 | 0 | 0 |
| `eg_official_gazette_excerpt.pdf` | pymupdf: 82, pymupdf+docling: 52 | 0 | 0 |
| `wipo_eg081ar_1.pdf` | pymupdf: 274 | 0 | 0 |
| `wipo_eg088ar_1.pdf` | pymupdf: 7, pymupdf+docling: 17 | 0 | 0 |
| `native_authored_award_en.pdf` | pymupdf: 4, pymupdf+docling: 5 | 0 | 0 |
| `native_authored_statute_ar.pdf` | pymupdf+docling: 12 | 0 | 0 |
| `scan_authored_award_en_150dpi.pdf` | tesseract: 2 | 0 | 0 |
| `scan_authored_award_en_300dpi.pdf` | tesseract: 2 | 0 | 0 |
| `scan_authored_statute_ar_150dpi.pdf` | tesseract: 3 | 0 | 0 |
| `scan_authored_statute_ar_300dpi.pdf` | tesseract: 4 | 0 | 0 |
| `scan_constitute_egypt_2014_ar_200dpi.pdf` | pymupdf+docling: 5, tesseract: 3 | 2 | 2 |
| `scan_constitute_egypt_2014_en_200dpi.pdf` | paddleocr: 2, pymupdf+docling: 1, tesseract: 11 | 2 | 2 |
| `scan_constitute_egypt_2019_ar_150dpi.pdf` | paddleocr: 11 | 6 | 6 |
| `scan_eg_constitution_2014_en_150dpi.pdf` | tesseract: 10 | 0 | 0 |
| `scan_eg_official_gazette_excerpt_300dpi.pdf` | tesseract: 14 | 0 | 0 |
| `scan_wipo_eg081ar_1_300dpi.pdf` | tesseract: 6 | 0 | 0 |
| `scan_wipo_eg088ar_1_150dpi.pdf` | tesseract: 6 | 0 | 0 |
| `stress_exhibits_footnotes.pdf` | pymupdf: 11 | 0 | 0 |
| `stress_inline_bilingual.pdf` | pymupdf: 6 | 0 | 0 |
| `stress_nested_clauses_ar.pdf` | pymupdf: 13 | 0 | 0 |
| `stress_table_pagebreak.pdf` | docling: 1, pymupdf+docling: 2 | 0 | 0 |
| `stress_table_ruled_ar.png` | tesseract: 2 | 0 | 0 |
| `stress_table_sparse_bilingual.png` | tesseract: 2 | 0 | 0 |
| `stress_table_wide_en.png` | tesseract: 2 | 0 | 0 |
| `synthetic_contract_ar.docx` | docling: 17 | 0 | 0 |
| `synthetic_contract_bilingual.pdf` | docling: 2, pymupdf: 1, pymupdf+docling: 16 | 0 | 0 |
| `synthetic_lease_bilingual.docx` | docling: 18 | 0 | 0 |
| `synthetic_memo_mixed.txt` | plaintext: 4 | 0 | 0 |
| `synthetic_stamped_page.png` | tesseract: 1 | 0 | 0 |
| `synthetic_statute_ar.txt` | plaintext: 11 | 0 | 0 |
| `synthetic_table_page.png` | tesseract: 2 | 0 | 0 |
| `synthetic_visual_order_ar.txt` | plaintext: 11 | 0 | 0 |

## 3. Table extraction

| Document | Expected | Found | |
|---|---|---|---|
| `stress_table_pagebreak.pdf` | 1 | 1 | ok |
| `stress_table_ruled_ar.png` | 1 | 1 | ok |
| `stress_table_sparse_bilingual.png` | 1 | 1 | ok |
| `stress_table_wide_en.png` | 1 | 1 | ok |
| `synthetic_contract_ar.docx` | 1 | 1 | ok |
| `synthetic_contract_bilingual.pdf` | 2 | 2 | ok |
| `synthetic_table_page.png` | 1 | 1 | ok |

## 4. Page preservation

| Document | Source pages | Output pages | |
|---|---|---|---|
| `constitute_egypt_2014_ar.pdf` | 44 | 44 | ok |
| `constitute_egypt_2014_en.pdf` | 53 | 53 | ok |
| `constitute_egypt_2019_ar.pdf` | 50 | 50 | ok |
| `eg_constitution_2014_en.pdf` | 47 | 47 | ok |
| `eg_official_gazette_excerpt.pdf` | 29 | 29 | ok |
| `wipo_eg081ar_1.pdf` | 94 | 94 | ok |
| `wipo_eg088ar_1.pdf` | 13 | 13 | ok |
| `native_authored_award_en.pdf` | 2 | 2 | ok |
| `native_authored_statute_ar.pdf` | 3 | 3 | ok |
| `scan_authored_award_en_150dpi.pdf` | 2 | 2 | ok |
| `scan_authored_award_en_300dpi.pdf` | 2 | 2 | ok |
| `scan_authored_statute_ar_150dpi.pdf` | 3 | 3 | ok |
| `scan_authored_statute_ar_300dpi.pdf` | 3 | 3 | ok |
| `scan_constitute_egypt_2014_ar_200dpi.pdf` | 6 | 6 | ok |
| `scan_constitute_egypt_2014_en_200dpi.pdf` | 6 | 6 | ok |
| `scan_constitute_egypt_2019_ar_150dpi.pdf` | 6 | 6 | ok |
| `scan_eg_constitution_2014_en_150dpi.pdf` | 6 | 6 | ok |
| `scan_eg_official_gazette_excerpt_300dpi.pdf` | 6 | 6 | ok |
| `scan_wipo_eg081ar_1_300dpi.pdf` | 6 | 6 | ok |
| `scan_wipo_eg088ar_1_150dpi.pdf` | 6 | 6 | ok |
| `stress_exhibits_footnotes.pdf` | 1 | 1 | ok |
| `stress_inline_bilingual.pdf` | 1 | 1 | ok |
| `stress_nested_clauses_ar.pdf` | 1 | 1 | ok |
| `stress_table_pagebreak.pdf` | 1 | 1 | ok |
| `stress_table_ruled_ar.png` | 1 | 1 | ok |
| `stress_table_sparse_bilingual.png` | 1 | 1 | ok |
| `stress_table_wide_en.png` | 1 | 1 | ok |
| `synthetic_contract_ar.docx` | 1 | 1 | ok |
| `synthetic_contract_bilingual.pdf` | 3 | 3 | ok |
| `synthetic_lease_bilingual.docx` | 1 | 1 | ok |
| `synthetic_memo_mixed.txt` | 1 | 1 | ok |
| `synthetic_stamped_page.png` | 1 | 1 | ok |
| `synthetic_statute_ar.txt` | 1 | 1 | ok |
| `synthetic_table_page.png` | 1 | 1 | ok |
| `synthetic_visual_order_ar.txt` | 1 | 1 | ok |

## 5. Section / clause preservation

Compares structural markers detectable in the **source text** against distinct clause ids on the emitted chunks. A large shortfall means markers were present but chunking did not cut on them -- the signal to inspect that document.

| Document | Markers in source | Clause ids emitted | Ratio | Chunk strategies |
|---|---|---|---|---|
| `constitute_egypt_2014_ar.pdf` | n/a | 213 | n/a | size: 27, structural: 263 |
| `constitute_egypt_2014_en.pdf` | 315 | 263 | 83% | size: 27, structural: 316 |
| `constitute_egypt_2019_ar.pdf` | 9 | 31 | 100% | size: 80, structural: 20 |
| `eg_constitution_2014_en.pdf` | 273 | 207 | 76% | size: 14, structural: 214 |
| `eg_official_gazette_excerpt.pdf` | 105 | 125 | 100% | size: 14, structural: 120 |
| `wipo_eg081ar_1.pdf` | 266 | 261 | 98% | size: 6, structural: 268 |
| `wipo_eg088ar_1.pdf` | 3 | 17 | 100% | size: 3, structural: 21 |
| `native_authored_award_en.pdf` | 10 | 9 | 90% | structural: 9 |
| `native_authored_statute_ar.pdf` | 6 | 7 | 100% | structural: 12 |
| `scan_authored_award_en_150dpi.pdf` | n/a | 2 | n/a | paragraph: 2 |
| `scan_authored_award_en_300dpi.pdf` | n/a | 2 | n/a | paragraph: 2 |
| `scan_authored_statute_ar_150dpi.pdf` | n/a | 0 | n/a | structural: 3 |
| `scan_authored_statute_ar_300dpi.pdf` | n/a | 2 | n/a | structural: 4 |
| `scan_constitute_egypt_2014_ar_200dpi.pdf` | n/a | 2 | n/a | size: 4, structural: 4 |
| `scan_constitute_egypt_2014_en_200dpi.pdf` | n/a | 3 | n/a | size: 8, structural: 4, table: 2 |
| `scan_constitute_egypt_2019_ar_150dpi.pdf` | n/a | 1 | n/a | paragraph: 5, size: 4, table: 2 |
| `scan_eg_constitution_2014_en_150dpi.pdf` | n/a | 4 | n/a | size: 8, structural: 2 |
| `scan_eg_official_gazette_excerpt_300dpi.pdf` | n/a | 3 | n/a | size: 13, table: 1 |
| `scan_wipo_eg081ar_1_300dpi.pdf` | n/a | 1 | n/a | paragraph: 6 |
| `scan_wipo_eg088ar_1_150dpi.pdf` | n/a | 0 | n/a | paragraph: 6 |
| `stress_exhibits_footnotes.pdf` | 11 | 11 | 100% | structural: 11 |
| `stress_inline_bilingual.pdf` | n/a | 5 | n/a | structural: 6 |
| `stress_nested_clauses_ar.pdf` | 17 | 13 | 76% | structural: 13 |
| `stress_table_pagebreak.pdf` | n/a | 0 | n/a | paragraph: 2, table: 1 |
| `stress_table_ruled_ar.png` | n/a | 0 | n/a | paragraph: 1, table: 1 |
| `stress_table_sparse_bilingual.png` | n/a | 0 | n/a | paragraph: 1, table: 1 |
| `stress_table_wide_en.png` | n/a | 0 | n/a | paragraph: 1, table: 1 |
| `synthetic_contract_ar.docx` | 15 | 10 | 67% | structural: 16, table: 1 |
| `synthetic_contract_bilingual.pdf` | 6 | 12 | 100% | structural: 17, table: 2 |
| `synthetic_lease_bilingual.docx` | 18 | 18 | 100% | structural: 18 |
| `synthetic_memo_mixed.txt` | 6 | 3 | 50% | structural: 4 |
| `synthetic_stamped_page.png` | n/a | 0 | n/a | paragraph: 1 |
| `synthetic_statute_ar.txt` | 20 | 10 | 50% | structural: 11 |
| `synthetic_table_page.png` | n/a | 0 | n/a | paragraph: 1, table: 1 |
| `synthetic_visual_order_ar.txt` | n/a | 10 | n/a | structural: 11 |

## Chunking and metadata correctness

Chunking was previously verified only as *did it run* -- chunk counts, with nothing to compare them against. This section checks output against expectations **declared in advance** in `test_corpus/synthetic/expectations.json`, written from what each document says rather than from what the pipeline produced. An expectation copied from actual output can only pass, and would measure nothing.

**74/74 checks pass (100%) across 14 documents.**

| Document | Type | Jurisdiction | Language | Clause ids | Tables | Chunks |
|---|---|---|---|---|---|---|
| `stress_exhibits_footnotes.pdf` | ok | ok | ok | ok | ok | ok |
| `stress_inline_bilingual.pdf` | ok | ok | ok | ok | ok | ok |
| `stress_nested_clauses_ar.pdf` | ok | ok | ok | ok | ok | ok |
| `stress_table_pagebreak.pdf` | - | ok | ok | - | ok | ok |
| `stress_table_ruled_ar.png` | - | ok | ok | - | ok | ok |
| `stress_table_sparse_bilingual.png` | - | ok | ok | - | ok | ok |
| `stress_table_wide_en.png` | - | ok | ok | - | ok | ok |
| `synthetic_contract_ar.docx` | ok | ok | ok | ok | ok | ok |
| `synthetic_contract_bilingual.pdf` | ok | ok | ok | ok | ok | ok |
| `synthetic_lease_bilingual.docx` | ok | ok | ok | ok | ok | ok |
| `synthetic_memo_mixed.txt` | ok | ok | ok | ok | ok | ok |
| `synthetic_statute_ar.txt` | ok | ok | ok | ok | ok | ok |
| `synthetic_table_page.png` | - | ok | ok | - | ok | ok |
| `synthetic_visual_order_ar.txt` | ok | ok | ok | ok | ok | ok |

## RTL / reading-order flags (surfaced, not auto-corrected)

These are **not errors in the pipeline** -- they are the pipeline reporting that reading order could not be resolved safely. Per the spec, ambiguous cases are flagged for manual review rather than silently rewritten.

| Document | Flags |
|---|---|
| `constitute_egypt_2014_ar.pdf` | mixed_direction: 45, visual_order_repaired: 1909 |
| `constitute_egypt_2019_ar.pdf` | brackets_unmirrored: 2, mixed_direction: 51, neutral_order_mirrored: 2 |
| `wipo_eg081ar_1.pdf` | brackets_unmirrored: 1, neutral_order_mirrored: 1 |
| `wipo_eg088ar_1.pdf` | brackets_unmirrored: 35, digit_order_suspect: 18, neutral_order_mirrored: 299, presentation_forms_found: 299 |
| `native_authored_statute_ar.pdf` | visual_order_repaired: 24 |
| `scan_authored_statute_ar_150dpi.pdf` | high_switch_count: 1, mixed_direction: 2, numeral_direction_ambiguous: 1 |
| `scan_authored_statute_ar_300dpi.pdf` | high_switch_count: 1, mixed_direction: 2 |
| `scan_constitute_egypt_2014_ar_200dpi.pdf` | high_switch_count: 3, mixed_direction: 8, numeral_direction_ambiguous: 4 |
| `scan_constitute_egypt_2014_en_200dpi.pdf` | high_switch_count: 1, mixed_direction: 1 |
| `scan_constitute_egypt_2019_ar_150dpi.pdf` | mixed_direction: 2 |
| `scan_eg_constitution_2014_en_150dpi.pdf` | mixed_direction: 1, numeral_direction_ambiguous: 1 |
| `scan_wipo_eg081ar_1_300dpi.pdf` | high_switch_count: 8, mixed_direction: 11, numeral_direction_ambiguous: 2 |
| `scan_wipo_eg088ar_1_150dpi.pdf` | high_switch_count: 6, mixed_direction: 7 |
| `stress_exhibits_footnotes.pdf` | presentation_forms_found: 7 |
| `stress_inline_bilingual.pdf` | high_switch_count: 3, mixed_direction: 7, visual_order_repaired: 7 |
| `stress_nested_clauses_ar.pdf` | mixed_direction: 14, visual_order_repaired: 14 |
| `stress_table_pagebreak.pdf` | mixed_direction: 1, presentation_forms_found: 31 |
| `stress_table_ruled_ar.png` | mixed_direction: 6 |
| `stress_table_sparse_bilingual.png` | mixed_direction: 2 |
| `synthetic_contract_ar.docx` | mixed_direction: 3 |
| `synthetic_contract_bilingual.pdf` | mixed_direction: 8, numeral_direction_ambiguous: 2, visual_order_repaired: 46 |
| `synthetic_lease_bilingual.docx` | mixed_direction: 5 |
| `synthetic_memo_mixed.txt` | high_switch_count: 2, mixed_direction: 4, numeral_direction_ambiguous: 1 |
| `synthetic_stamped_page.png` | mixed_direction: 4, numeral_direction_ambiguous: 1 |
| `synthetic_table_page.png` | high_switch_count: 1, mixed_direction: 3, numeral_direction_ambiguous: 1 |
| `synthetic_visual_order_ar.txt` | presentation_forms_found: 16, visual_order_repaired: 16 |

## 6. Processing speed

CPU only, no GPU. Timings include model inference where Docling or OCR ran.

`extract` is the whole extraction phase; the stage named beside it is the largest thing inside it. `Unaccounted` is the total minus every measured stage -- it should stay near zero, and a large value means time is being spent somewhere nothing is instrumented.

| Document | Total (s) | ms/page | extract (s) | Slowest inner stage | Unaccounted |
|---|---|---|---|---|---|
| `constitute_egypt_2014_ar.pdf` | 8.3 | 190 | 6.9 | pymupdf (6535 ms) | 0.1s (1%) |
| `constitute_egypt_2014_en.pdf` | 7.6 | 144 | 6.4 | pymupdf (6234 ms) | 0.1s (2%) |
| `constitute_egypt_2019_ar.pdf` | 9.1 | 181 | 7.4 | pymupdf (7014 ms) | 0.1s (1%) |
| `eg_constitution_2014_en.pdf` | 3.8 | 82 | 3.2 | pymupdf (3098 ms) | 0.1s (2%) |
| `eg_official_gazette_excerpt.pdf` | 28.9 | 998 | 28.3 | docling (25396 ms) | 0.1s (0%) |
| `wipo_eg081ar_1.pdf` | 5.9 | 63 | 4.8 | pymupdf (4555 ms) | 0.1s (1%) |
| `wipo_eg088ar_1.pdf` | 14.4 | 1106 | 14.2 | docling (13440 ms) | 0.0s (0%) |
| `native_authored_award_en.pdf` | 3.1 | 1528 | 3.0 | docling (2980 ms) | 0.0s (0%) |
| `native_authored_statute_ar.pdf` | 3.9 | 1284 | 3.8 | docling (3772 ms) | 0.0s (0%) |
| `scan_authored_award_en_150dpi.pdf` | 7.4 | 3676 | 7.3 | ocr (7329 ms) | 0.0s (0%) |
| `scan_authored_award_en_300dpi.pdf` | 6.9 | 3455 | 6.9 | ocr (6890 ms) | 0.0s (0%) |
| `scan_authored_statute_ar_150dpi.pdf` | 8.8 | 2947 | 8.8 | ocr (8817 ms) | 0.0s (0%) |
| `scan_authored_statute_ar_300dpi.pdf` | 8.5 | 2841 | 8.5 | ocr (8503 ms) | 0.0s (0%) |
| `scan_constitute_egypt_2014_ar_200dpi.pdf` | 147.1 | 24514 | 147.0 | ocr (146974 ms) | 0.0s (0%) |
| `scan_constitute_egypt_2014_en_200dpi.pdf` | 124.1 | 20688 | 124.0 | ocr (124017 ms) | 0.0s (0%) |
| `scan_constitute_egypt_2019_ar_150dpi.pdf` | 180.3 | 30057 | 180.2 | ocr (180193 ms) | 0.0s (0%) |
| `scan_eg_constitution_2014_en_150dpi.pdf` | 30.2 | 5031 | 30.1 | ocr (30102 ms) | 0.0s (0%) |
| `scan_eg_official_gazette_excerpt_300dpi.pdf` | 29.8 | 4971 | 29.7 | ocr (29727 ms) | 0.0s (0%) |
| `scan_wipo_eg081ar_1_300dpi.pdf` | 30.6 | 5094 | 30.5 | ocr (30489 ms) | 0.0s (0%) |
| `scan_wipo_eg088ar_1_150dpi.pdf` | 32.3 | 5378 | 32.2 | ocr (32190 ms) | 0.0s (0%) |
| `stress_exhibits_footnotes.pdf` | 1.5 | 1502 | 1.5 | docling (1410 ms) | 0.0s (0%) |
| `stress_inline_bilingual.pdf` | 1.4 | 1418 | 1.4 | docling (1352 ms) | 0.0s (0%) |
| `stress_nested_clauses_ar.pdf` | 1.4 | 1440 | 1.4 | docling (1378 ms) | 0.0s (0%) |
| `stress_table_pagebreak.pdf` | 9.9 | 9852 | 9.8 | docling (9705 ms) | 0.0s (0%) |
| `stress_table_ruled_ar.png` | 1.0 | 1000 | 1.0 | ocr (994 ms) | 0.0s (0%) |
| `stress_table_sparse_bilingual.png` | 1.7 | 1728 | 1.7 | ocr (1723 ms) | 0.0s (0%) |
| `stress_table_wide_en.png` | 1.4 | 1371 | 1.4 | ocr (1366 ms) | 0.0s (0%) |
| `synthetic_contract_ar.docx` | 0.3 | 296 | 0.3 | docx (256 ms) | 0.0s (1%) |
| `synthetic_contract_bilingual.pdf` | 6.2 | 2060 | 6.1 | docling (5889 ms) | 0.0s (0%) |
| `synthetic_lease_bilingual.docx` | 0.1 | 148 | 0.1 | docx (134 ms) | 0.0s (1%) |
| `synthetic_memo_mixed.txt` | 0.0 | 16 | 0.0 | rtl_fix (9 ms) | 0.0s (9%) |
| `synthetic_stamped_page.png` | 2.8 | 2837 | 2.8 | ocr (2825 ms) | 0.0s (0%) |
| `synthetic_statute_ar.txt` | 0.0 | 18 | 0.0 | rtl_fix (12 ms) | 0.0s (9%) |
| `synthetic_table_page.png` | 2.2 | 2199 | 2.2 | ocr (2193 ms) | 0.0s (0%) |
| `synthetic_visual_order_ar.txt` | 0.0 | 27 | 0.0 | rtl_fix (19 ms) | 0.0s (6%) |

### Slowest document: `scan_constitute_egypt_2019_ar_150dpi.pdf`

30057 ms/page against a corpus median of 1502. Its breakdown: `total` 180.3s, `extract` 180.2s, `ocr` 180.2s, `rtl_fix` 0.1s.

**Being a scan is not the explanation.** Eight other scanned fixtures in this corpus cost roughly 4 s/page, so recognition alone accounts for a small fraction of the figure above. The cost is the *second* read:

1. **The fallback engine ran on 6 of its 6 pages -- the dominant cost.** When the primary engine's mean confidence falls below `ocr.min_mean_confidence` (0.75) the page is re-read by the other engine, so it is paid for twice, and the fallback (PaddleOCR) is the slower of the two by roughly an order of magnitude. An attempt costs the same whether or not it wins: here 6 of them produced the kept result.
2. **Recognition itself is also above average on this document**, because per-page OCR cost scales with text density and Arabic costs roughly twice English per character under `ara+eng`. That is the smaller of the two effects.

[`reports/speed_outlier_investigation.md`](speed_outlier_investigation.md) profiles this document specifically and attributes **55% of its runtime** to the fallback, with rendering, chunking and table reconstruction together under 1%. Two results there qualify the trade rather than settling it: a clean re-render of the same pages costs the primary engine the same time but passes the gate on 5 of 6 pages, so the fixture's synthetic degradation causes the *gate failures* rather than the slowness; and on the one Arabic fixture with authored ground truth the fallback engine is measurably **less** accurate than the primary whose output it replaces. Whether the second read earns its cost is therefore open, and is tracked there as follow-up S1.

Across the corpus, 3 document(s) attempted the fallback on at least one page, the most being `scan_constitute_egypt_2019_ar_150dpi.pdf` at 6 page(s). Setting `ocr.fallback_engine = "none"` removes that cost, and the safety net with it.

See the README's *Performance characteristics* section for the per-page figures to plan an ingest against.

## 7. Failures

_No documents failed._

## Caveats

Read these before quoting any figure above.

1. **Rendered pages are not scans.** Every scanned fixture is a digital page rasterized and then degraded with skew, noise and JPEG artifacts. That models compression and geometry; it does not model scanner optics, photocopy generations, bleed-through from the reverse side, or staple shadows. **The OCR figures above are an optimistic bound and should be quoted as one.** This does not change with time -- it is a property of validating without firm data.
2. **Reference quality varies, and is classified rather than assumed.** Ground truth derived from a source PDF's text layer inherits that publisher's defects, and this corpus contains three kinds: visual word order, out-of-flow marginal columns, and words fragmented into single glyphs. Each makes a *correct* extraction score badly. `scripts/audit_ground_truth.py` labels every reference; the `scan_authored_*` fixtures, whose text was written before the page was rendered, are the ones whose absolute accuracy needs no caveat.
3. **No firm house style.** Letterhead, numbering conventions, defined-term formatting and clause phrasing are unknown. The structure detector's cue lists were written against published statutes and synthetic contracts; extending them for a firm's own drafting is a list edit and expected work, not a defect.
4. **Document-type inference is heuristic** and was corrected twice during development when public documents exposed bad cues (`باسم الشعب` opens both statutes and judgments). More such cues certainly exist in material this corpus does not contain.
5. **One machine, one run.** Timings are from a single Windows CPU-only workstation and will not match the firm's server. The *ratios* between paths (text layer vs Docling vs OCR) are the durable part -- see the README's performance section.
6. **No handwriting, no multi-instrument bundles, no password-protected or corrupt files.** The one handwritten public document available is excluded from every metric because it cannot be scored at all; see the exclusions list above.

### What this evaluation does and does not claim

It claims that the pipeline processes every input shape the spec requires, at the accuracies tabulated above, against references whose trustworthiness has itself been measured. **No client document was processed, and none is required for these figures to hold.**

It does not claim to predict accuracy on the firm's own archive. The gap is named in caveat 1 and is not closable from public data. If the firm wants that number, the same report regenerates against a local directory with nothing leaving the building:

```bash
python scripts/evaluate.py --corpus-dir test_corpus/real
```

### Settings still worth tuning against the firm's own drafting

None of these block use; each has a conservative default and a better setting that only the firm's material can reveal.

- Structure cue lists, against real clause numbering conventions
- Normalization A/B: `normalize_hamza` and `normalize_teh_marbuta` are OFF because folding them is lossy and the evidence has to come from the text actually being searched
- The OCR engine ordering, re-benchmarked on real scans
- Chunk size, against M2/M3's embedding model context window
