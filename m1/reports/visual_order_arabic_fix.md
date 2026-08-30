# Visual-order Arabic: detected and repaired

> ## Reading order only
>
> This change decides **which order a document's characters are consumed in** and nothing else. OCR engine selection, preprocessing, DPI, and fuzzy marker matching are out of scope and untouched. **Digit *order* is explicitly not addressed** — `٢١` and `١٢` are indistinguishable in extracted text and guessing would silently corrupt article numbers and amounts, so that stays flagged and unfixed (`digit_order_suspect`), as documented elsewhere.
>
> This closes README known limitation **#9**, which previously read *"Arabic stored in visual order inside a PDF is flagged, not repaired."*

Generated: 2026-08-16
Full test suite: **481 passed, 0 failed** (386 before this change)
New tests: `tests/test_visual_order.py` — 36 tests (95 new tests across both fixes)

---

## Verdict

**`stress_inline_bilingual.pdf`: 0 → 5 clause markers recovered.** The document has exactly five numbered memorandum paragraphs, so this is 0% → 100%, not merely "greater than zero". It no longer falls back to paragraph chunking.

Four further fixtures were affected and were not known to be:

| Fixture | Clause ids before | after | article-level ids before → after |
|---|---|---|---|
| `stress_inline_bilingual.pdf` | 0 (paragraph-only) | **5** | 0 → 5 |
| `synthetic_visual_order_ar.txt` | 0 (paragraph-only) | **10** | 0 → 10 |
| `constitute_egypt_2014_ar.pdf` | 248 | 213 | **0 → 208** |
| `synthetic_contract_bilingual.pdf` | 20 | 12 | **5 → 9** |
| `stress_nested_clauses_ar.pdf` | 13 | 13 | 13 → 13 (text corrected, count unchanged) |

The two rows where the raw id count *falls* are improvements, and the article column is why. Before the repair, an unparsed reversed heading like `( : غرامة التأخير5) المادة` was picked up by the typographic-heading heuristic and became a junk pseudo-section (`sec_(_:_غرامة_التاخير5)_المادة`). Those inflated the id count while carrying no legal identity. After the repair the same line parses as `المادة (5)` and becomes `art_5`. On the 2014 Egyptian constitution that is **0 article-level clause ids before, 208 after** — the document went from having no citable articles at all to having its actual article structure.

---

## What was actually wrong, and where

The bug is produced at **one** stage and merely propagated by the rest.

### Producing stage: PDF text-layer extraction

A PDF's glyphs are painted left to right at ascending x. A producer that shapes Arabic before writing it — Arabic DTP software, and every fixture this repo renders with ReportLab — stores the *visual* sequence. MuPDF then applies a bidi pass of its own on top, and on a bilingual file the result is a hybrid that **cannot be repaired from the string**:

```
source     1. بمراجعة البند الثالث (Clause 3) من العقد تبين أن التزام المؤجر (the Lessor) بالصيانة الدورية
PyMuPDF    ( بالصيانة الدوريةthe Lessor) ( من العقد تبين أن التزام المؤجرClause 3) . بمراجعة البند الثالث1
```

Each Arabic run is internally correct — MuPDF reversed them back — but the run *sequence* is still visual, the neutrals have been dragged into the wrong runs, and the whitespace between scripts has been lost (`الدوريةthe Lessor`). There is no string transform that recovers the original from that, and applying `get_display` to it produces garbage.

The glyph *positions*, however, never lied. Sorting a line's characters by x recovers the true painted order, and that string **is** cleanly invertible:

```
x-sorted   ةيرودلا ةنايصلاب (the Lessor) رجؤملا مازتلا نأ نيبت دقعلا نم (Clause 3) ثلاثلا دنبلا ةعجارمب .1
inverted   1. بمراجعة البند الثالث (Clause 3) من العقد تبين أن التزام المؤجر (the Lessor) بالصيانة الدورية
```

That is byte-identical to the source text of the fixture, on all 15 lines.

So `src/extract_pymupdf_docling.py` now reads `get_text("rawdict")` rather than `get_text("dict")` — same call, but it carries per-glyph boxes — and builds **two** candidate readings per block (`_block_readings`). Nothing is chosen at this point.

### Producing stage: OCR output assembly

`src/ocr_pipeline.py::_sort_reading_order` had the same class of bug from the other direction. OCR returns positioned words with no sequence; the function sorted a mixed Arabic/Latin line entirely right-to-left, which fixes the Arabic and **reverses any English inside it** — `(the Lessor)` came back as `(Lessor the)`. Egyptian legal drafting puts English defined terms inside Arabic clauses constantly, so this was not an edge case.

Mixed lines now go through `reorder_tokens_visual_to_logical`, which is the same Unicode Bidi Algorithm reordering one level up: reverse the token sequence for an RTL base, then reverse each embedded LTR run back. Pure-Arabic and pure-Latin lines are unchanged.

### Propagating stages (not fixed there, correctly)

Chunking, normalization, marker detection and metadata extraction all consume the damaged string and all produce wrong output from it. None of them is where the fix belongs.

---

## The decision: the audit's reversal test, promoted

`scripts/audit_ground_truth.py` already distinguished "this text is in visual order" from "this is a genuine extraction error" by reversing it and asking whether that helped by a material margin (`REVERSAL_HELPS = 0.10`). Offline it can score against OCR output. Live there is no reference, so `src/visual_order.py` runs the same shape of test against an intrinsic, dictionary-free measure — `order_score`, built from six positional signals:

| Signal | Logical | Visual |
|---|---|---|
| definite article `ال` | word-initial | appears as `لا` word-finally |
| final-form letters `ة` `ى` | close a token | open a token |
| Latin capitalisation | `Clause` | `esualC` |
| sentence punctuation | ends a line | leads a line |
| brackets | `(x)` | `)x(` |
| Arabic/Latin adjacency with no space | absent | `الدوريةthe Lessor` |

`REVERSAL_HELPS` and `reverse_line_words` now **live in `src/visual_order.py` and are imported by the audit script**, so the offline audit and the live repair cannot drift apart on what "reversed" means or on how much of an improvement counts. `tests/test_visual_order.py::TestSharedWithAudit` asserts they are the same objects.

### Two criteria, both required

The order score alone is **not sufficient**, and the corpus proves it. On `wipo_eg081ar_1.pdf` — a published statute the audit classifies as `logical` — the reordered reading scores *better* (+0.73 → +0.94), because that file has mirrored sentence punctuation which the reordering tidies up. Accepting on score alone would have reversed a correct document and corrupted its words (`الالزمة` → `االلزمة`, `مدة ال` → `مدةا ل`).

What exposes it is `marker_recovery`: the same reordering takes that file's recovered structural markers from **238 to 12**. Marker detection is anchored at line start, so it is *definitionally* sensitive to reading order, which makes it a better arbiter than any orthographic proxy — it measures the downstream consequence rather than a correlate of it.

A reading is accepted only when it **recovers at least as much legal structure** *and* **beats the original by 0.10 on the order score** *and* ends up positively scored *and* had at least 4 scoring observations. Each criterion vetoes a case the others miss:

| Fixture | markers | order score | outcome |
|---|---|---|---|
| `constitute_egypt_2014_ar.pdf` | 0 → 321 | +0.01 → +0.76 | **repaired** |
| `stress_inline_bilingual.pdf` | 0 → 5 | +0.43 → +0.72 | **repaired** |
| `synthetic_contract_bilingual.pdf` | 5 → 15 | +0.74 → +0.88 | **repaired** |
| `stress_nested_clauses_ar.pdf` | 17 → 22 | +0.68 → +0.80 | **repaired** |
| `wipo_eg081ar_1.pdf` | 238 → 12 | +0.73 → +0.94 | left alone — **markers veto** |
| `wipo_eg088ar_1.pdf` | 0 → 18 | +0.61 → +0.63 | left alone — **score veto** |
| `stress_exhibits_footnotes.pdf` | 11 → 13 | +0.86 → +0.86 | left alone — score veto |
| `constitute_egypt_2019_ar.pdf` | 9 → 28 | +0.98 → −0.22 | left alone — score veto |
| English fixtures | equal | equal | left alone |

The verdict is taken **once per document**, not per block. Visual layout is a property of the producing software, so it is all-or-nothing per file; a two-line heading carries almost no evidence on its own, and half a document reordered is worse than either extreme.

---

## The bilingual case

This was the hard part and it is handled by using `python-bidi` for what it is, rather than as a string reverser. `get_display` implements the UBA's *per-run* reordering: it reverses RTL runs, leaves LTR runs forward, and mirrors the neutrals between them. Applied to an already-visual string it is its own inverse, so an embedded `(the Lessor)` keeps its internal English word order and its brackets while the Arabic around it is put back. Nothing here reverses a whole line.

Two ordering details that were bugs before they were fixed:

**Lines with no Arabic keep the extractor's reading verbatim.** Forcing an RTL paragraph direction onto a pure-English line moves its clause number to the far end — `5.1 The scope includes...` → `.The scope includes... 5.1` — which trades one reading-order bug for another in exactly the bilingual documents this is meant to help. In an early measurement this alone cost `stress_nested_clauses_ar.pdf` its entire English clause ladder.

**Reordering happens before presentation forms are folded, not after.** `NFKC` decomposes the lam-alef ligature `ﻻ` into two characters. If that runs first, the reversal splits the pair the wrong way round and `الإيجار` comes back as `اإليجار` — corpus-wide corruption that no marker test would catch, because the marker words are unaffected. One ligature glyph is one position in a visual string; it stays one position through the reversal and is decomposed afterwards. `TestPureArabicVisualOrder::test_lam_alef_ligature_survives_the_reversal` pins this.

No new dependency was added. `arabic-reshaper` and `python-bidi` were already pinned in `requirements.txt`; this change uses `python-bidi` in the reverse direction the module docstring already described.

---

## Auditability: flagged *and* repaired, not flagged *or* repaired

The property the pipeline had before — "nothing is silently rewritten" — is preserved. Every reordered span records that it was reordered, and every *rejected* verdict records why.

| Surface | Contents |
|---|---|
| `metadata.reading_order_repaired` | `True` on every chunk whose text was reordered |
| `metadata.rtl_flags[]` `visual_order_repaired` | per block: the evidence and the scores it was accepted on |
| `metadata.raw_text` | the text exactly as extracted, unchanged |
| `result.warnings` | one document-level warning naming the block count and the before/after numbers |
| `result.engine_log` `engine="reading_order"` | the full verdict — scores, gain, marker counts, observations, reason — **whether accepted or rejected** |

The rejection path is logged deliberately: a document that *should* have been repaired and was not is now discoverable in the engine log rather than being an absence someone has to notice.

`ExtractionConfig.repair_visual_order` and `RTLConfig.repair_visual_order` turn the repair off (for glyph-geometry and string-only sources respectively) without silencing the verdict logging.

---

## False-positive check — the main risk of this change

The task's own framing: *false positives are worse than doing nothing*, because reversing correct text destroys it silently, where leaving a reversed document alone at least leaves it flagged.

### The audit itself is unchanged

`scripts/audit_ground_truth.py` was re-run over all 23 ground-truth fixtures after the change:

```
Verdicts: authored=4, logical=10, out_of_flow=3, unreliable=2, visual=4
```

**All 23 verdicts are identical to before the change**, fixture by fixture. This is the expected result and it is worth being explicit about why: the audit's logic was not touched, only `REVERSAL_HELPS` and `reverse_line_words` moved out of it and into `src/visual_order.py`, where the live pipeline imports the same objects. The re-run confirms the move was lossless.

### No genuine-error case was misclassified as visual order

The audit's fixtures are rasterized scans with no text layer, so they exercise the OCR path; the reading-order verdict for a text layer is taken on the *source* documents they were rendered from. Cross-referencing the two:

| Audit verdict on the reference | Source document with a text layer | Reordered by the pipeline? |
|---|---|---|
| `logical` | `wipo_eg081ar_1.pdf` | **no** — markers veto (238 → 12) |
| `logical` | `wipo_eg088ar_1.pdf` | **no** — score veto (+0.61 → +0.63) |
| `logical` | `eg_official_gazette_excerpt.pdf` | **no** |
| `logical` | `eg_constitution_2014_en.pdf` | **no** |
| `out_of_flow` (marginal column, not a reversal) | `constitute_egypt_2014_en.pdf` | **no** |
| `authored` (reference written before the pixels existed, so it cannot be visual) | — (no text layer by construction) | n/a |
| `unreliable` (high error reordering does not explain) | `constitute_egypt_2014_ar.pdf`, `constitute_egypt_2019_ar.pdf` | 1 repaired (also verdicted `visual`), 1 left alone |
| `visual` | `constitute_egypt_2014_ar.pdf`, `constitute_egypt_2019_ar.pdf` | **1 of 2 repaired**, 1 missed (see residual risk #1) |

**Zero fixtures with a `logical`, `authored` or `out_of_flow` reference were reordered.** The two rejections that carry the most weight are the ones where a single-criterion design would have failed: `wipo_eg081ar_1.pdf` scores *better* reordered and is saved only by the marker veto, and `wipo_eg088ar_1.pdf` recovers *more* markers reordered and is saved only by the score veto.

Three negative unit tests hold this in place, and they are the load-bearing tests of the module:

- `TestGenuineErrorsAreNotReordered` — realistic Tesseract damage on Arabic (dropped dots, split words, substituted letters) with correct word order, glyph-fragmented text, and mojibake. All left byte-identical. Damaged text is bad in *both* directions, so the margin is never met.
- `TestLogicalTextIsNeverReordered` — clean Arabic, clean bilingual, clean English, plus an explicit reconstruction of the `wipo_eg081ar_1` marker-veto case.
- `TestPipelineIntegration::test_english_only_document_is_not_touched`.

---

## Residual risk

Stated plainly rather than implied.

1. **Word-order-only visual storage is not detected.** `constitute_egypt_2019_ar.pdf` stores each line's *words* in reverse while every word's characters are logical (`الرحيم الرحمن الله بسم` for `بسم الله الرحمن الرحيم`). The audit classifies it `visual` and it is not repaired: the glyph geometry gives no additional information for that producer, and `order_score`'s signals are all character-positional, so both readings score alike. Detecting this needs word-level semantics — a lexicon or a language model — which is a different piece of work with a different risk profile. **The document still yields 31 clause ids**, so this is a quality ceiling rather than a structural failure.

2. **Nested/complex mixed-direction cases beyond the tested fixtures.** The corpus's hardest case is `stress_inline_bilingual.pdf` — direction switching several times per line around parenthesised English glosses, with quoted English inside Arabic inside brackets — and that is reconstructed exactly. Deeper nesting (three or more embedding levels, explicit bidi control characters such as LRE/RLO in the content stream, or an RTL run inside an LTR run inside an RTL paragraph) is **not represented in the corpus and therefore not measured**. `python-bidi` implements the full UBA and should handle them; that is an expectation, not a measurement, and it should be re-checked against real firm documents.

3. **Digit order remains unaddressed, by decision.** The repair moves numeric runs as units and never reorders digits inside one. `wipo_eg088ar_1.pdf` still produces `art_01` and `art_41` where the source means articles 10 and 14. That is the documented out-of-scope item, and it is visible: those blocks carry `digit_order_suspect`.

4. **Table cells are not reordered.** `apply_rtl_fix` folds presentation forms in table cells but the reading-order verdict is applied to text blocks only. No corpus fixture has a visual-order table, so there is nothing to measure; the gap is real.

5. **Cost.** `rawdict` is a heavier extraction mode than `dict` and the geometric candidate is built for every Arabic-bearing line. Measured on the corpus this is not material next to Docling and OCR, but it is not free, and it is paid on every PDF whether or not the repair is needed.

---

## Reproducing

```bash
pytest tests/test_visual_order.py -v          # 36 tests
pytest                                        # full suite, 481 tests
python scripts/audit_ground_truth.py          # reference verdicts, unchanged
```

Before/after on any fixture:

```python
from src.config import PipelineConfig
from src.pipeline import process_document

cfg = PipelineConfig()
cfg.extraction.repair_visual_order = False    # pre-repair behaviour
cfg.rtl.repair_visual_order = False
```
