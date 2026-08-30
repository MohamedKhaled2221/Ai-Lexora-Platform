# OCR-tolerant structure-marker matching

> ## Marker matching only
>
> This change affects **whether a damaged legal marker is recognised** and nothing else. The visual-order repair (`reports/visual_order_arabic_fix.md`), OCR engine selection, and preprocessing are out of scope and untouched. **Digit *reordering* is explicitly not addressed** — this handles digits OCR *split* (`"1 2"` → `"12"`), never digits whose order is ambiguous under RTL. The two are different questions with different answers; conflating them is how article numbers get silently corrupted.
>
> This closes README known limitation **#4**, which previously read *"Structure detection is regex-based and will miss markers OCR mangled… Such documents silently demote to paragraph chunking."*

Generated: 2026-08-16
Full test suite: **481 passed, 0 failed** (386 before this change)
New tests: `tests/test_fuzzy_markers.py` — 59 tests

---

## Verdict

**Corrupted-marker detection: 37.5% → 87.5%.** Measured over 160 synthetically corrupted marker lines derived from `synthetic_statute_ar.txt`, through the full pipeline including Arabic normalization.

**Chunking equivalence: exact.** On every corruption the tolerant matcher catches, the corrupted document produces the **identical set of clause ids** as the clean one (Jaccard 1.00). That is the real success criterion — "the regex matched" is not the goal, equivalent chunks are.

**False positives: 0.** Zero on 3,523 non-marker Arabic lines from the corpus ground truth, and zero on 250 constructed lines pairing 50 ordinary Arabic words with the five numbering shapes a marker can take.

**And the silent failure is gone**, which matters more than any of the above. See [The actual fix](#the-actual-fix-the-silence).

---

## Before / after on corrupted markers

`synthetic_statute_ar.txt`, 10 `المادة` markers, each corrupted the same way throughout the document, then run through the whole pipeline. "STRICT" is the previous behaviour (`detect_marker(..., allow_fuzzy=False)`); "TOLERANT" is what ships. `Jacc` is the Jaccard overlap of the resulting clause-id set against the clean document's.

| Corruption of `المادة` | written | STRICT detected | ids | Jacc | TOLERANT detected | ids | Jacc | flagged |
|---|---|---|---|---|---|---|---|---|
| teh marbuta → heh | `الماده` | 10/10 | 10 | 1.00 | 10/10 | 10 | 1.00 | 0 |
| dot added to dal | `الماذة` | **0/10** | **0** | **0.00** | 10/10 | 10 | **1.00** | 10 |
| dal read as reh | `المارة` | **0/10** | **0** | **0.00** | 10/10 | 10 | **1.00** | 10 |
| tatweel inserted | `المـادة` | 10/10 | 10 | 1.00 | 10/10 | 10 | 1.00 | 0 |
| spurious diacritic | `المَادة` | 10/10 | 10 | 1.00 | 10/10 | 10 | 1.00 | 0 |
| word split by broken join | `الما دة` | **0/10** | **0** | **0.00** | 10/10 | 10 | **1.00** | 10 |
| alef of `ال` dropped | `لمادة` | **0/10** | **0** | **0.00** | 10/10 | 10 | **1.00** | 10 |
| **two substitutions** | `الملاه` | 0/10 | 0 | 0.00 | **0/10** | **0** | **0.00** | 0 |
| **totals (×2, with and without split digits)** | | **60/160 (37.5%)** | | | **140/160 (87.5%)** | | | |

Four of the eight corruptions took the document from **10 clause ids to 0** — total structural failure from one substituted character — and now take it to 10. Two were already handled upstream (the pipeline's Arabic normalization strips tatweel and diacritics before structure annotation), so they are baseline, not gains. One is the documented ceiling.

### Split digits

Separate from the word, and a *wrong answer* rather than a miss: `المادة 1 2` matched the strict pattern happily and returned **article 1**, quietly discarding the second digit and folding article 12's text into article 1's chunk.

| Line | strict | tolerant |
|---|---|---|
| `المادة 1 2 - التعريفات` | `1` | **`12`** |
| `المادة (1 2) التعريفات` | `1` | **`12`** |
| `المادة ١ ٢ - التعريفات` | `1` | **`12`** |
| `المادة 1,2 - التعريفات` | `1` | **`12`** |
| `الماذة 1 2 - التعريفات` | *(no match)* | **`12`** |
| `المادة 12 المبلغ 1 500 جنيه` | `12` | `12` — amount untouched |

### Real corpus effect

Two published fixtures were carrying this damage already:

| Fixture | clause ids before | after | note |
|---|---|---|---|
| `wipo_eg081ar_1.pdf` | 79 | **261** | text layer writes `املادة` (alef/lam transposed); 213 chunks now carry a fuzzy marker |
| `wipo_eg088ar_1.pdf` | 33 (0 article-level) | 17 (**12 article-level**) | 28 junk `sec_مادة)1(_:` pseudo-sections replaced by real `art_N` ids |

---

## The actual fix: the silence

The miss rate was never the main problem. A regex miss caused `choose_granularity` to return `None`, the document dropped to paragraph chunking, every chunk lost its `clause_id`, the document vanished from the M1→M5 clause view — **and the output was indistinguishable from a document that genuinely has no clauses**. One bad character, a large invisible quality loss, and the only trace was a `chunk_strategy` value somebody had to think to go and look at.

Both outcomes now speak:

| Event | Surface |
|---|---|
| a marker needed tolerant matching | `metadata.structure.marker_fuzzy`, `marker_confidence`, `marker_evidence` on the chunk; a document warning naming up to three examples; `engine_log` `structure: {markers, fuzzy_markers}` |
| **structure detection failed entirely** | `structure_detection_failed` in `result.warnings`, and `engine_log` `chunking: {status: "structure_detection_failed", distinct_markers, marker_kinds}` |

The failure warning is deliberately informative rather than binary. It reports what markers *were* seen, because a document showing "2 markers found" is one damaged marker away from working, while a document showing zero across forty pages of statute has an extraction problem upstream. It is a warning and not an error because letters, memos and single-page notes legitimately have no structure.

`StructuralMarker.raw` keeps what was actually on the page rather than what it was matched to, so a flagged marker can be checked against the source without re-running anything.

---

## Threshold justification

**Edit distance 1, after normalization, on words of 4+ characters, with the first letter intact, followed by a number, and not on a deny-list.**

Distance 1 is a ceiling imposed by Arabic morphology, not a knob. `مادة` is four letters and its distance-1 neighbourhood is full of ordinary legal vocabulary:

`عادة` (custom/usually) · `سادة` (gentlemen) · `قادة` (leaders) · `مدة` (period) · `زيادة` (increase)

At distance 2 the neighbourhood also swallows `إفادة`, `شهادة`, `إعادة` and the matcher stops meaning anything. So distance 1 alone is not sufficient either, and three further constraints carry real weight:

1. **Normalization first, so the cheap errors cost nothing.** Tatweel, diacritics, alef/hamza variants, `ة`↔`ه` and `ى`↔`ي` are folded before comparison. These are the *most common* OCR errors on this word and they now cost **zero** of the distance-1 budget rather than consuming it — which is why the budget stretches as far as it does. `الماذه` has two errors as written and one after folding.
2. **The first letter must survive.** OCR damages dots, joins and final forms; it rarely destroys a word's leading letter. This single rule removes `عادة`, `سادة`, `قادة` and `فائدة` outright.
3. **A number must follow.** Every structural marker is numbered. This removes essentially all prose matches.
4. **A 12-word deny-list** (`CONFUSABLE_WORDS`) covers the residue. It is short by design — a long deny-list would be evidence the threshold is wrong rather than a fix for it. The entry that matters is `المدة` ("the period"): one deletion from `المادة`, and Egyptian contracts write `المدة 5 سنوات`, which is emphatically not article 5.

Words shorter than 4 characters (`بند`, `باب`, `فصل`) are matched **exactly only**. At three letters one edit reaches a third of the language.

### False-positive measurement

| Test set | Lines | False positives | Rate |
|---|---|---|---|
| Every non-marker line ≥8 chars in all corpus `*.groundtruth.txt` | 3,523 | **0** | **0.000%** |
| 50 ordinary Arabic words × 5 numbering shapes (`" 5"`, `" 12"`, `" (3)"`, `" ٥"`, `" الأول"`) | 250 | **0** | **0.000%** |

Both are asserted as tests, not just measured once: `TestNoFalsePositives::test_corpus_arabic_has_no_false_positives` and `::test_ordinary_words_before_a_number_are_not_markers`.

---

## Digit repair scope

The digit rule is drawn as tightly as it will go, because the repair is worth little and over-applying it corrupts a contract.

From the end of a matched marker word, the scan skips the punctuation a number may sit behind (`(`, `:`, space), then walks **one** digit-and-separator chain, dropping separators, and **stops at the first character that is neither** — with a hard cap of 4 digits. It cannot reach past the number it is repairing.

- Separators removed: space, tab, NBSP, `،`, `,`, `;`, `:` — at most two consecutive.
- Separators **never** removed: `/`, `-`, `.` — these are *meaningful* in legal numbering (`12/2019`, `5-3`, `5.2.1`), and collapsing them merges distinct components into one wrong number rather than repairing a split one.
- Never applied document-wide, and never applied on a character window. A window of any useful size reads `المادة 12 المبلغ 1 500 جنيه` and turns the amount into 1500.
- **Digit order is never changed.** `المادة ٢ ١` yields `21`, joined in the order found. `TestSplitDigits::test_digit_order_is_never_changed` pins this.

---

## Design note: one definition of a marker

The tolerant layer does not parse. It **rewrites the line into canonical form and hands it back to the same `_MARKER_PATTERNS`** that the strict path uses. There is still exactly one definition of what a structural marker is, and no second tolerant parser that can drift away from the strict one.

It also runs only after every exact pattern has already failed — with one deliberate exception, the split-digit case above, where the strict pattern *succeeds* and returns a truncated number. There, the tolerant reading wins only when it produces a strictly longer number. A clean document therefore never reaches this code and cannot be affected by it.

---

## Residual gaps

Stated plainly rather than implied.

1. **Two or more character errors in the marker word are not detected and will not be.** `الهاده` (first letter destroyed), `الملاه` (two unfolded substitutions), `الم ا دة` (split into three fragments), `الءاذة`. `TestTwoErrorsAreNotHandled` asserts these are missed, so a later change that quietly loosens the threshold has to delete an assertion rather than slip through. In practical terms: **one substitution, one deletion, one insertion, or one broken join — plus any amount of tatweel/diacritic/orthographic noise, which is free. Not two.** The alternative is a matcher that fires on ordinary Arabic words, and an invented clause boundary is worse than a missed one because it splits a real clause in half and nothing downstream flags it as wrong.

2. **Only Arabic marker words are tolerant.** `Article`, `Clause`, `Section` and the decimal outline patterns are unchanged and still exact. Latin OCR is far more reliable and the corpus shows no failures there, so there was no evidence to tune against — but the asymmetry is real and a badly-scanned English contract would still demote silently (though it would now *say* it had).

3. **The deny-list is drawn from Egyptian legal Arabic as represented in this corpus.** A firm archive spanning more drafters will contain words this list has not seen. The 0% false-positive rate is measured on 3,523 corpus lines, which is a real number but not a large one, and it is the figure to re-measure first on real documents.

4. **`marker_fuzzy` is reported for the deepest open unit only.** A chunk governed by a clean article containing a fuzzy sub-clause reports the sub-clause's status. Coarser than it could be; nothing depends on it yet.

5. **Detection quality is measured on synthetic corruption, not on real OCR output.** The corruption set models the failures Tesseract and PaddleOCR actually make on this word, but a controlled substitution is not the same thing as a real scan, and the 87.5% figure should be read as an estimate on realistic damage rather than a measurement on observed damage.

---

## Reproducing

```bash
pytest tests/test_fuzzy_markers.py -v         # 59 tests
pytest                                        # full suite, 481 tests
```

Strict-mode baseline for comparison:

```python
from src.structure_preservation import detect_marker
detect_marker(line, allow_fuzzy=False)        # pre-change behaviour
```
