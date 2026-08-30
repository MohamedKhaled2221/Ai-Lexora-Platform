# Schema Contract Verification — M1 `DocumentChunk` → M2

**Date:** 2026-08-17
**Scope:** Verification only. No pipeline or schema code was changed.

> **Superseded.** Everything from here to the "Recommendation" section
> describes the state *before* any fix, when 6 of 1,393 chunks were rejected.
> **M1's output now validates against M2's schema with 0 rejections** —
> recommendations 1 (`language`), 2 (`page`) and 3 (`clause`) have all been
> implemented. See the two addenda at the end for the current state.
> Recommendation 4 (one shared schema module) is the only item still open, and
> it needs M2's owner.

- **M1 (actual, produced by this pipeline):** [document_chunk_schema.py:325](../src/document_chunk_schema.py#L325)
- **M2 (expected, received from WhatsApp transfer):** copied into the repo for reference as [contracts/m2_expected_schema.py](../contracts/m2_expected_schema.py)

---

## Verdict

**Contracts have breaking mismatches — 2 breaking, 1 high silent risk, 2 cosmetic, plus 1 process risk.**

A live validation pass over **1,393 real chunks** from the pipeline's own test corpus found **6 chunks that M2's schema outright rejects**, and a constructed-but-reachable pipeline path that produces a second, different rejection. Everything else validates.

Issues in severity order:

1. **BREAKING — `language`: M1 emits `"mixed"`, M2's `Literal` has `"ar-en"`.** Confirmed live: 6/1393 chunks rejected with `literal_error`.
2. **BREAKING — `page`: M1 allows `None`, M2 requires `int`.** Not hit by the PDF corpus, but reachable through the Docling extraction path, which is **on by default** (`use_docling: bool = True`). Confirmed by driving the pipeline's real `chunk_document()`.
3. **SILENT RISK (high) — `clause`: M2 declares a top-level `clause` field that M1 never emits.** Validation passes (M2 defaults to `extra="ignore"`), so this fails silently: `clause` is `None` on 100% of chunks even though M1 *has* the data in `metadata["structure"]["clause"]`.
4. **COSMETIC — `document_type` default and type width.**
5. **COSMETIC — `text` / id constraints: M1 is stricter than M2 in the safe direction.**
6. **PROCESS RISK — the contract is two independently-maintained copies, not a shared module.** See "Contract ownership" below.

---

## Contract ownership: is this a shared module?

**No.** There is no shared schemas package. `grep` for `class DocumentChunk` across the repo returns exactly one definition — M1's, in [src/document_chunk_schema.py](../src/document_chunk_schema.py). M2's `schemas.py` was not present anywhere in the repo before this task; it arrived as a file transfer and has now been parked at `contracts/m2_expected_schema.py` **for reference only** (nothing imports it).

So the two sides are independently-maintained copies of the same contract, and they have already drifted — which is the concrete evidence for why this is worth fixing structurally, not just patching one value. M1's own module docstring even calls itself "the **stable interface** between M1 and the rest of the AI Core" and lists seven frozen fields; M2's copy has nine fields and different value vocabularies. Neither side can currently detect drift at commit time.

---

## Field-by-field comparison

| Field | Expected (M2) | Actual (M1 pipeline) | Match? | Severity |
|---|---|---|---|---|
| `document_id` | `str` (required) | `str`, required, `min_length=1`, no-whitespace validator | ✅ | — |
| `chunk_id` | `str` (required) | `str`, required, `min_length=1`, no-whitespace validator | ✅ | — |
| `text` | `str`, `min_length=1` | `str`, required, validator rejects empty **and** whitespace-only | ✅ | — (M1 stricter, safe) |
| `page` | **`int`, required, `ge=1`** | **`int \| None`, default `None`**, `ge=1` when present | ❌ | **Breaking** |
| `section` | `str \| None = None` | `str \| None = None` (truncated to 120 chars) | ✅ | — |
| `clause` | `str \| None = None` | **field does not exist** (lives at `metadata.structure.clause`) | ❌ | **Silent risk (high)** |
| `language` | `Literal["ar","en",**"ar-en"**,"unknown"]` | `Language` enum: `ar`, `en`, **`mixed`**, `unknown` | ❌ | **Breaking** |
| `document_type` | `str \| None = None` | `DocumentType` enum, default `"unknown"`, serialized as `str` | ⚠️ | Cosmetic |
| `metadata` | `dict`, default factory | `dict[str, Any]`, default factory | ✅ | — |

### Extra fields — not a problem

M1 emits exactly its 8 fields, all of which exist in M2's 9. M1 produces **no** field absent from M2's model, so there is nothing for M2 to reject as unknown.

Checked M2's config directly: `DocumentChunk.model_config == {}`, i.e. Pydantic's default **`extra="ignore"`** — *not* `extra="forbid"`. Verified live by passing a bogus key; M2 accepted and dropped it. So even if M1 later adds a top-level field, M2 will not fail validation on it — it will silently ignore it.

(For the record, the reverse direction is stricter: M1's own `DocumentChunk` is `extra="forbid"`. That doesn't affect M1→M2 flow, but it means anything M2 hands back with unknown keys would be rejected.)

---

## Live validation results

Method: ran `src.pipeline.ingest()` over the real test corpus, dumped each chunk with `model_dump(mode="json")`, and fed it to **M2's** `DocumentChunk.model_validate()`.

**Corpus run — 1,393 chunks from 8 documents:**

| File | Passed | Failed |
|---|---|---|
| `constitute_egypt_2014_ar.pdf` | 288 | **2** |
| `constitute_egypt_2014_en.pdf` | 343 | 0 |
| `constitute_egypt_2019_ar.pdf` | 96 | **4** |
| `eg_constitution_2014_en.pdf` | 228 | 0 |
| `eg_official_gazette_excerpt.pdf` | 134 | 0 |
| `wipo_eg081ar_1.pdf` | 274 | 0 |
| `wipo_eg088ar_1.pdf` | 24 | 0 |
| **Total** | **1,387** | **6** |

*(6 further corpus files produced 0 chunks — they are fully-scanned PDFs and OCR was disabled for this run, so they are neither pass nor fail.)*

**Result: NO — not all chunks pass.** 6 of 1,393 (0.43%) fail.

Every failure is the same mode:

```
language  literal_error  n=6  sample=['mixed', 'mixed', 'mixed']
```

Failing chunks: `constitute_egypt_2014_ar.pdf` → `chunk_001`, `chunk_002`; `constitute_egypt_2019_ar.pdf` → `chunk_001`, `chunk_003`, `chunk_061` (+1 more).

**Observed `language` value distribution across all 1,393 chunks:**
`en` 704 · `ar` 680 · **`mixed` 6** · `unknown` 3

**Other observed invariants (all clean):**
- chunks with `page = None`: **0** in this corpus run
- chunks with non-dict `metadata`: **0** — `metadata` was always a dict, never `None`, never missing
- `document_type` values observed: `"law"`, `"contract"` — always a string, never `None`

**Edge-case probes against M1's own model:**

| Case | M1 behaviour |
|---|---|
| empty `text` | REJECTS (`value_error`) |
| whitespace-only `text` | REJECTS (`value_error`) |
| `page = 0` | REJECTS (`greater_than_equal`) |
| `page = -3` | REJECTS (`greater_than_equal`) |
| `page` omitted | **ACCEPTS → `page = None`** |
| `metadata` omitted | ACCEPTS → `metadata = {}` |

---

## Issue detail

### 1. BREAKING — `language`: `"mixed"` vs `"ar-en"`

M1's vocabulary is defined at [document_chunk_schema.py:42-54](../src/document_chunk_schema.py#L42):

```python
class Language(str, Enum):
    AR = "ar"; EN = "en"; MIXED = "mixed"; UNKNOWN = "unknown"
```

M2 expects `Literal["ar", "en", "ar-en", "unknown"]`. Three of four values agree; the bilingual case does not.

Every code path that sets this field routes through the single detector `detect_language()` at [structure_preservation.py:100-118](../src/structure_preservation.py#L100), which returns only `AR`/`EN`/`MIXED`/`UNKNOWN`. The chunk field is assigned in exactly one place — [chunking.py:639](../src/chunking.py#L639) `language=detect_language(text)`. Because `use_enum_values=True` is set on M1's model, the serialized value is the raw string `"mixed"`.

So M1 can never emit `"arabic"`, `"eng"`, or `None` — the enum makes those impossible. The *only* divergent value is `"mixed"`, and it is unavoidable: it is emitted whenever the minority script holds ≥15% of the letters, which is exactly the bilingual Egyptian legal document this system is built for. Rate here is low (0.43%) only because this corpus is mostly single-language constitutions; a bilingual contract corpus would push it far higher.

This is a genuine two-sided decision: renaming M1's `MIXED = "mixed"` to `"ar-en"` changes a value M1's own `rtl_fix`, `normalize`, `ocr_pipeline`, and `extract_pymupdf_docling` modules compare against (`Language.MIXED` appears in ~8 call sites), while changing M2's `Literal` changes M2's handling. **Not changed here.**

### 2. BREAKING — `page` optional vs required

M1: `page: int | None = Field(default=None, ge=1)` — [document_chunk_schema.py:377](../src/document_chunk_schema.py#L377), documented as `None` for unpaginated formats.
M2: `page: int = Field(ge=1)` — required, no default.

The value comes from [chunking.py:536-537](../src/chunking.py#L536):

```python
pages = unit.pages
page = pages[0] if pages else None
```

`unit.pages` ([chunking.py:108-116](../src/chunking.py#L108)) returns `[]` when no block carries a page, and for tables returns `[]` when `table.page` is falsy.

**Reachability — confirmed, not theoretical.** The PDF/PyMuPDF and plaintext paths always stamp a page number (a TXT file test yielded `page=1`, not `None`), so the corpus run never hit it. But the Docling path builds blocks with `page=int(page) if page else None` ([extract_pymupdf_docling.py:584,593](../src/extract_pymupdf_docling.py#L584)) — provenance-less items get `None`, and `page_no == 0` also collapses to `None`. Docling is enabled by default (`use_docling: bool = True`, [config.py:461](../src/config.py#L461)).

Driving the pipeline's real `chunk_document()` with one Docling-style block whose `page is None`:

```
chunk_001 page=None
  -> M2 FAIL page: int_type (input=None)
```

M1 satisfies M2's `ge=1` constraint whenever `page` is present (it enforces `ge=1` itself, and rejects `0` and `-3`). The mismatch is purely required-vs-optional.

### 3. SILENT RISK (high) — `clause` is declared by M2 but never sent by M1

M2's model has `clause: str | None = None`. M1's `DocumentChunk` has no such field — clause data lives one level down, in `metadata["structure"]["clause"]` ([StructuralRef](../src/document_chunk_schema.py#L179)).

Because M2 is `extra="ignore"` and `clause` has a default, **this never raises**. It just quietly resolves to `None` on every single chunk. Verified:

```
M1 chunks with metadata.structure.clause set: 9/343
sample M1 metadata.structure.clause='Clause 1'  ->  M2 top-level clause=None
```

This is the most dangerous item in the report precisely because it is invisible. If any M2 logic filters or displays on `chunk.clause`, it is operating on an always-empty field while the real data sits untouched in `metadata`. Note M1's docstring asserts seven frozen fields and does not include `clause`, so the two sides disagree about whether this field is part of the contract at all.

### 4. COSMETIC — `document_type`

M2 types it `str | None` with default `None`; M1 uses a `DocumentType` enum with default `"unknown"`, serialized to a plain string. M2's type is strictly looser, so every M1 value validates. The only divergence is the *default*: a chunk of unknown type reaches M2 as `"unknown"`, not `None`. Worth a note only if M2 branches on `document_type is None` as its unknown sentinel — it would never fire.

### 5. COSMETIC — M1's stricter constraints

M1 enforces everything M2 does, plus more: `text` rejects whitespace-only (not just empty), and `document_id`/`chunk_id` require `min_length=1` and forbid embedded whitespace where M2 accepts any `str`. Strictness runs in the safe direction — anything M1 emits satisfies M2's constraints on these fields. M2's assumption that empty text and `page < 1` "cannot occur" **is** upheld by M1.

---

## Recommendation (for discussion — not applied)

1. Decide `"mixed"` vs `"ar-en"` jointly with M2's owner; whichever wins, one side changes and needs a regression pass.
2. Decide whether `page` may be `None`, or whether M1 should guarantee a page number for Docling-sourced chunks.
3. Decide whether `clause` is promoted to a top-level M1 field or dropped from M2's model.
4. Replace the two hand-maintained copies with one shared schema module both modules import, so the next drift is a merge conflict instead of a production failure.

---

# Addendum — 2026-08-17: items 2 and 3 resolved

The two single-sided items above (the ones M1 could fix without M2's input)
have been implemented and re-validated against M2's real schema. Items 1 and 6
are **untouched and still open** — both need M2's owner. Items 4 and 5 remain
cosmetic and were not addressed.

## Status after the fix

| # | Issue | Status |
|---|---|---|
| 1 | `language`: `"mixed"` vs `"ar-en"` | **Still open** — two-sided decision, deferred to M2 |
| 2 | `page`: optional vs required | **Resolved** — M1 now requires `page: int`, `ge=1` |
| 3 | `clause`: declared by M2, never sent | **Resolved** — M1 now emits it top-level |
| 4 | `document_type` default/width | Open, cosmetic |
| 5 | M1 stricter than M2 | Open, cosmetic (safe direction) |
| 6 | Two independently-maintained schema copies | **Still open** — needs joint ownership decision |

## Fix 1 — top-level `clause`

`DocumentChunk` gained `clause: str | None = None`, populated in
[chunking.py](../src/chunking.py) `_emit()` from the same `unit.struct.clause`
that already feeds `metadata.structure`. **Additive:** the nested value is
unchanged, and both are populated together. Chunks with no clause keep
`clause = None`, exactly as before.

No structure-detection logic was touched — the visual-order fix and fuzzy
marker matching are untouched. This only copies an already-computed value to a
second location in the output object.

**Verified live.** Across the corpus run, 126 chunks carry
`metadata.structure.clause`; all 126 now also carry an identical top-level
`clause`, and no chunk has one without the other:

| File | nested `clause` | top-level `clause` | identical |
|---|---|---|---|
| `constitute_egypt_2014_en.pdf` | 9 | 9 | 9 |
| `constitute_egypt_2019_ar.pdf` | 43 | 43 | 43 |
| `eg_constitution_2014_en.pdf` | 19 | 19 | 19 |
| `eg_official_gazette_excerpt.pdf` | 14 | 14 | 14 |
| `wipo_eg081ar_1.pdf` | 41 | 41 | 41 |
| **Total** | **126** | **126** | **126** |

The 9/343 case called out above (`constitute_egypt_2014_en.pdf`) reproduces
exactly: those 9 chunks now reach M2 with a non-`None` `clause` matching the
nested value.

## Fix 2 — no more `page=None`

**Root cause: one genuine edge case and one latent bug, in the same
expression.** `page=int(page) if page else None` in `_docling_tables()`
([extract_pymupdf_docling.py](../src/extract_pymupdf_docling.py)) conflated two
different situations:

1. **Genuine edge case.** Docling attaches no `prov` to tables for formats it
   reads without a page model — DOCX is the everyday one. There is no page
   number to lose; the source simply has no pagination. The rest of that module
   already treats such documents as a single page (`_docling_page_only` builds
   `ExtractedPage(page_number=1)`), so the table path was the only place that
   disagreed and emitted `None`.
2. **Latent bug.** The truthiness test (`if page`) also collapsed `page_no == 0`
   to `None`. Docling numbers pages from 1, so `0` is a broken value, not an
   absent one — and downstream could not tell the two apart. A non-int
   `page_no` would have raised inside `int()` and been swallowed by the
   surrounding `except`.

Both are now handled by `_prov_page_no()`, which coerces `page_no` to an `int`
and returns `None` only for genuinely absent or sub-1 values, logging the
difference. A table with no page provenance then falls back to page 1 —
matching what the rest of the DOCX path already does — rather than emitting
`None`. The same helper is now used in `_docling_items()`, where a `page_no` of
`0` would previously have produced `page=0` blocks that M1's own `ge=1` rejects.

**The invariant is now enforced by the schema, not patched at one call site.**
`DocumentChunk.page` changed from `int | None = None` to a required
`int = Field(..., ge=1)`, so a page-less chunk can no longer be constructed
anywhere in the pipeline — M1's own model raises before anything reaches M2.
The docstring's claim that `page` is `None` for unpaginated formats was already
false in practice (TXT yields `page=1`, DOCX yields `len(pages)`); that
docstring, [README.md](../README.md) and
[docs/public_api_reference.md](../docs/public_api_reference.md) were corrected
to match. `chunking._emit()` defaults a unit with no page provenance to page 1
and logs a warning, so a future extractor regression is loud rather than
silently invalid. `_Unit.pages` also stopped using a truthiness test on the
table page, for the same reason as above.

**Verified live.** The report's original repro — driving the real
`chunk_document()` with a Docling-style block whose `page is None` — now yields
`chunk_001 page=1`, which M2 accepts. `_docling_tables` was probed directly with
no-`prov`, `page_no=None`, `page_no=0` and `page_no="not-an-int"` tables: all
four return `page=1`, and a real `page_no=3` still returns `3`.

## Re-validation against M2's real schema

Same method as the original run: `src.pipeline.ingest()` over the test corpus
(OCR disabled, as before), each chunk dumped with `model_dump(mode="json")` and
fed to `contracts/m2_expected_schema.py`'s `DocumentChunk.model_validate()`.

| File | Passed | Failed |
|---|---|---|
| `constitute_egypt_2014_ar.pdf` | 288 | **2** |
| `constitute_egypt_2014_en.pdf` | 343 | 0 |
| `constitute_egypt_2019_ar.pdf` | 96 | **4** |
| `eg_constitution_2014_en.pdf` | 228 | 0 |
| `eg_official_gazette_excerpt.pdf` | 134 | 0 |
| `wipo_eg081ar_1.pdf` | 274 | 0 |
| `wipo_eg088ar_1.pdf` | 24 | 0 |
| **Total** | **1,387** | **6** |

- chunks with `page = None`: **0** — and now unconstructable
- remaining failure modes: `language literal_error` × 6 — **all six** are the
  deferred `"mixed"` vs `"ar-en"` mismatch, nothing else
- language distribution unchanged: `en` 704 · `ar` 680 · `mixed` 6 · `unknown` 3

Before/after on the original 6 rejected chunks: **0 of 6 now pass** — expected,
because every one of them was rejected for `language`, which is item 1 and out
of scope here. The rejection *count* is unchanged at 6/1,393 because the corpus
never hit the `page` path. What changed is that the second, separately-proven
rejection (Docling `page=None`) is now unreachable, and the silent `clause`
failure is fixed on 126 chunks that were previously validating "successfully"
with an empty field.

**Reaching 0 rejected chunks requires item 1**, and only M2's owner can settle
whether `"mixed"` or `"ar-en"` wins.

## Tests

Full suite: **496 passed**, up from the 481 baseline. No regressions.

New regression coverage (14 tests):

- `tests/test_chunking.py::TestSchemaContractRegressions` — top-level `clause`
  matches the nested value on every clause-anchored chunk, the nested value
  survives, `clause` stays `None` on unstructured chunks, page-less blocks
  yield `page == 1`, and no fixture chunk has a non-int page.
- `tests/test_document_chunk_schema.py::TestClauseField` — `clause` defaults to
  `None`, round-trips, is always present in the serialized shape (M2
  destructures the key), and coexists with `metadata.structure.clause`.
- `tests/test_extraction.py::TestDoclingTablePageProvenance` — a real page
  number survives; no-`prov`, `None`, `0` and non-int `page_no` all fall back to
  page 1.

Three existing tests were updated to the new contract, deliberately: the
top-level field set in `test_exact_field_set` and
`test_chunks_match_the_spec_shape` now includes `clause`, and
`test_page_may_be_none_for_unpaginated_formats` was replaced by
`test_page_is_required` / `test_page_none_rejected` (which is why the count
rises by 15, not 14).

## Still open — for M2's conversation

1. **`language`: `"mixed"` vs `"ar-en"`** (item 1). The only remaining source of
   validation failures. Two-sided: M1's `Language.MIXED` is compared against in
   ~8 call sites across `rtl_fix`, `normalize`, `ocr_pipeline` and
   `extract_pymupdf_docling`, so whichever side changes needs its own regression
   pass. **Not touched.**
2. **Two independently-maintained schema copies** (item 6).
   `contracts/m2_expected_schema.py` is still reference-only — nothing imports
   it, and adding `clause` to M1 by hand is itself an instance of the problem
   this item describes. A shared schema module needs joint ownership.
   **Not touched.**

---

# Addendum 2 — 2026-08-17: item 1 resolved, contract now validates clean

**M1's chunks now validate against M2's schema with 0 rejections: 1,393 / 1,393.**

Item 1 — the `"mixed"` vs `"ar-en"` mismatch — is fixed on M1's side. It was the
sole remaining source of validation failures, accounting for 100% of the 6
rejected chunks.

## Decision

M1 changes, not M2. The bilingual value is now `"ar-en"`, matching M2's
`Literal` exactly. Rationale: the value has one producer, so the change is
contained and needs no coordination; and `"ar-en"` names the actual pair rather
than the fact of mixing, which is the more precise label for a corpus whose
only realistic mix *is* Arabic and English.

## What changed

The rename is enforced by the type, not by find-and-replace. `Language` in
[document_chunk_schema.py](../src/document_chunk_schema.py) is the only place
these wire values are defined, and every producer routes through it, so
`"mixed"` is now unconstructable — the enum member no longer exists:

```python
class Language(str, Enum):
    AR = "ar"
    EN = "en"
    AR_EN = "ar-en"     # was: MIXED = "mixed"
    UNKNOWN = "unknown"
```

The member was renamed `MIXED` → `AR_EN` as well as its value, deliberately: an
attribute rename fails loudly at every call site, where changing only the value
would have left eight references reading `Language.MIXED` while emitting
`"ar-en"`. Detection logic is untouched — `detect_language()` still returns the
bilingual case on exactly the same threshold, it just labels it differently. The
`mixed_threshold` parameter keeps its name; it is the script-mixing *ratio* that
decides the call, not the label that comes out of it.

### Every site changed

| File | Line | What |
|---|---|---|
| `src/document_chunk_schema.py` | 63 | **The enum member** — `MIXED = "mixed"` → `AR_EN = "ar-en"` |
| `src/document_chunk_schema.py` | 49–58 | `Language` docstring, plus a note recording the old value |
| `src/document_chunk_schema.py` | 366 | `DocumentChunk.language` field docstring |
| `src/structure_preservation.py` | 121 | `detect_language()` return — the single producer |
| `src/structure_preservation.py` | 101–113 | `detect_language()` docstring |
| `src/extract_pymupdf_docling.py` | 336 | Arabic-context branch, `(Language.AR, Language.AR_EN)` |
| `src/normalize.py` | 236 | Arabic-context branch |
| `src/ocr_pipeline.py` | 794 | Bilingual-line branch, `lang is Language.AR_EN` |
| `src/ocr_pipeline.py` | 937 | Arabic-context branch |
| `src/rtl_fix.py` | 451 | Arabic-context branch |
| `src/rtl_fix.py` | 508 | Arabic-context branch |
| `tests/test_structure_preservation.py` | 88–91 | `test_mixed` → `test_bilingual_is_ar_en`, asserts `Language.AR_EN` |
| `tests/test_structure_preservation.py` | 95 | Docstring prose |
| `tests/test_pipeline.py` | 45 | Allowed-value set now `{"ar", "en", "ar-en", "unknown"}` |
| `tests/test_pipeline.py` | 65, 108 | `Language.AR_EN.value` |
| `tests/test_document_chunk_schema.py` | 114 | Parametrized accepted values |
| `docs/public_api_reference.md` | 69, 148, 822 | Field table, consumer example, enum vocabulary table |
| `README.md` | 138 | Chunk field table |
| `scripts/make_synthetic_corpus.py` | 498, 542 | Corpus manifest expectations |
| `scripts/make_stress_fixtures.py` | 361, 364 | Stress fixture expectations |

No magic-string comparison against `"mixed"` survives anywhere. The only
remaining occurrence of the word as a *language value* in the codebase is the
historical note in the `Language` docstring; other hits (`mixed_direction` RTL
flag kind, `synthetic_memo_mixed.txt`, prose about mixed-direction text) are
unrelated and were left alone. Fixture filenames were **not** renamed — that
would churn the corpus manifest for no contract benefit.

Not touched, per scope: `"ar"`, `"en"`, `"unknown"`, the detection thresholds,
and the classification logic itself.

## Re-validation against M2's real schema

Same method as before: `src.pipeline.ingest()` over the test corpus (OCR
disabled), each chunk dumped with `model_dump(mode="json")` and fed to
`contracts/m2_expected_schema.py`'s `DocumentChunk.model_validate()`.

| File | Passed | Failed |
|---|---|---|
| `constitute_egypt_2014_ar.pdf` | 290 | 0 |
| `constitute_egypt_2014_en.pdf` | 343 | 0 |
| `constitute_egypt_2019_ar.pdf` | 100 | 0 |
| `eg_constitution_2014_en.pdf` | 228 | 0 |
| `eg_official_gazette_excerpt.pdf` | 134 | 0 |
| `wipo_eg081ar_1.pdf` | 274 | 0 |
| `wipo_eg088ar_1.pdf` | 24 | 0 |
| **Total** | **1,393** | **0** |

**Result: YES — every chunk M1 produces validates against M2's schema.**

- rejected chunks: **0 / 1,393** (was 6 / 1,393)
- the original 6 rejected chunks: **6 of 6 now pass** — the 2 in
  `constitute_egypt_2014_ar.pdf` and the 4 in `constitute_egypt_2019_ar.pdf`,
  which is why those two files' pass counts rise from 288→290 and 96→100
- remaining failure modes: **none**
- language distribution: `en` 704 · `ar` 680 · **`ar-en` 6** · `unknown` 3 —
  identical counts to before, only the label changed, confirming the rename did
  not disturb detection
- chunks with `page = None`: 0; top-level `clause` still matches the nested
  value on all 126 clause-anchored chunks

## Tests

Full suite: **500 passed**, from the 496 baseline. No regressions — the +4 are
new tests; every pre-existing test still passes, none was weakened.

**New** — `tests/test_document_chunk_schema.py::TestLanguageWireValues` (4):
the enum's value set equals M2's `Literal` exactly; the bilingual value is
`"ar-en"`; `"mixed"` is neither a value of the enum nor accepted by
`DocumentChunk`; a bilingual chunk serializes as the plain string `"ar-en"`.
The first of these is the direct guard against this class of drift recurring.

**Changed** — expected values corrected, assertions otherwise unchanged:
`test_structure_preservation.py::test_mixed` (renamed
`test_bilingual_is_ar_en`), `test_pipeline.py` field-set and
`test_mixed_memo_raises_rtl_flags` / bilingual-document assertions,
`test_document_chunk_schema.py::test_all_languages_accepted` parametrization.

## Final status of the six original issues

| # | Issue | Status |
|---|---|---|
| 1 | `language`: `"mixed"` vs `"ar-en"` | **Resolved** — M1 emits `"ar-en"` |
| 2 | `page`: optional vs required | **Resolved** (addendum 1) |
| 3 | `clause`: declared by M2, never sent | **Resolved** (addendum 1) |
| 4 | `document_type` default/width | Open, cosmetic — M2's type is strictly looser, every M1 value validates |
| 5 | M1 stricter than M2 | Open, cosmetic — strictness runs in the safe direction |
| 6 | Two independently-maintained schema copies | **Still open — needs M2** |

Every breaking and silent-risk item is closed. Items 4 and 5 are cosmetic and
cause no validation failure.

## Still open — item 6, and why it isn't fixed here

`contracts/m2_expected_schema.py` remains a reference-only copy that nothing
imports. M1 and M2 still hold two hand-maintained definitions of the same
contract, and all three fixes in these addenda were applied to M1's copy by
hand against a snapshot of M2's — which is the very failure mode item 6
describes. The contract validates cleanly *today*; nothing prevents it drifting
again tomorrow, and neither side would detect it at commit time.

Fixing it means one shared schema module both modules import, which is a
decision about ownership, packaging and release cadence across two codebases —
**it needs M2's owner and is out of scope for this repo alone.** Until then,
`TestLanguageWireValues` and the page/clause regression tests are the
substitute: they pin M1's side of the contract so a change to it is at least
loud locally.
