# M1 -- Document Processing Pipeline

Shared document-processing infrastructure for the Legal Intelligence Assistant.
Turns raw legal documents into standardized `DocumentChunk` objects for the rest
of the AI Core.

**Everything runs on firm infrastructure. No cloud APIs at runtime, no data
egress, no LangChain.**

> ### Status: complete and validated, without client data by design
>
> Every component is implemented, tested and measured. **The validation corpus
> contains no firm documents, and that is the design rather than a stage.** The
> engagement constraint is that no document leaves the firm, so the system was
> built to be evaluable without client material:
>
> - **published Egyptian legal documents** (WIPO Lex, Constitute Project, the
>   Official Gazette) supply real legal Arabic, real statutory numbering, and
>   real publisher defects -- including two that make a *correct* extraction
>   score badly, which is how they were found;
> - **synthetic fixtures** supply exact ground truth for the cases published
>   documents cannot: authored scans whose reference text was written before the
>   pixels existed, tables with known shapes, and documents built specifically to
>   break the pipeline.
>
> **This pipeline has not processed a real client document, and does not need to
> have done so for the numbers below to hold.** What the approach cannot measure
> is stated plainly in [Known limitations](#known-limitations) -- those are
> permanent properties of validating this way, not gaps waiting on data.
>
> The firm can regenerate the entire evaluation against its own documents, on
> its own hardware, without sending anything anywhere: see
> [Running the evaluation on your own documents](#running-the-evaluation-on-your-own-documents).
>
> Read [`reports/evaluation_report.md`](reports/evaluation_report.md) for the
> measurements, [`reports/ocr_engine_comparison.md`](reports/ocr_engine_comparison.md)
> for the OCR engine decision,
> [`reports/native_extraction_accuracy.md`](reports/native_extraction_accuracy.md)
> for the accuracy of the **non-OCR** path (Arabic CER 0.0016, English 0.011 —
> the majority path, and it was unmeasured until now), and
> [`test_corpus/manifest.md`](test_corpus/manifest.md) for what they were
> measured on.

---

## Contents

- [Pipeline](#pipeline)
- [Output contract: `DocumentChunk`](#output-contract-documentchunk)
- [Integration: M1 → M2/M3](#integration-m1--m2m3)
- [Integration: M1 → M5](#integration-m1--m5)
- [Setup](#setup)
- [Running](#running)
- [Performance characteristics](#performance-characteristics)
- [Running the evaluation on your own documents](#running-the-evaluation-on-your-own-documents)
- [Configuration](#configuration)
- [Design decisions to review](#design-decisions-to-review)
- [Known limitations](#known-limitations)
- [Repo layout](#repo-layout)

---

## Pipeline

```
Legal Document  (PDF / DOCX / TXT / image)
   │
   ├─ 1. Detect type ─────────── src/type_detection.py
   │     PDF scanned vs text-based, decided PER PAGE
   │     text layers that decode to mojibake are rejected → OCR
   │     DOCX / TXT routed directly; images routed straight to OCR
   │
   ├─ 2a. Text-layer path ────── src/extract_pymupdf_docling.py
   │      PyMuPDF  → text, page geometry, bounding boxes, fonts
   │      Docling  → layout labels, heading levels, table structure
   │
   ├─ 2b. OCR path ───────────── src/ocr_pipeline.py
   │      Tesseract (ara+eng)           → primary, on measured evidence
   │      PaddleOCR (Arabic)             → fallback, in a worker process
   │
   ├─ 3. RTL reading-order fix ─ src/rtl_fix.py
   │     repair what is provably wrong; FLAG what is ambiguous
   │
   ├─ 4. Arabic normalization ── src/normalize.py
   │     pyarabic, every step individually toggleable
   │
   ├─ 5. Structure annotation ── src/structure_preservation.py
   │     running headers/footers excluded, then
   │     page / section / heading / article / clause / table / bbox
   │
   ├─ 6. Legal chunking ──────── src/chunking.py
   │     cut on clause & article boundaries, not character counts
   │
   └─ 7. DocumentChunk ───────── src/document_chunk_schema.py
```

Orchestrated by [`src/pipeline.py`](src/pipeline.py); served by
[`src/api.py`](src/api.py).

**Why RTL repair and normalization sit between extraction and chunking:** both
extraction paths can produce reading-order and orthography damage, so one pass
over the shared representation covers both. Chunking must run *after*, because
an article header written `الـمـادة ١٢` only matches a marker pattern once
tatweel is stripped and digits are folded. Flip that order and structure
detection silently collapses to zero — there is a regression test pinning it
([`test_pipeline.py::test_normalization_runs_before_structure_detection`](tests/test_pipeline.py)).

---

## Output contract: `DocumentChunk`

The top-level fields are fixed by the team spec. `metadata` is an open
dict — **adding keys to it is always backwards compatible**, so treat unknown
keys as additive.

```json
{
  "document_id": "doc_001",
  "chunk_id": "chunk_017",
  "text": "Termination may occur...",
  "page": 12,
  "section": "Termination",
  "clause": "Clause 1",
  "language": "en",
  "document_type": "contract",
  "metadata": { "jurisdiction": "Egypt" }
}
```

| Field | Meaning |
|---|---|
| `document_id` | Stable per source file. Content-hashed, so re-ingesting after a pipeline change yields the same id. Override it to match a DMS id. |
| `chunk_id` | `chunk_NNN`, ordered by reading position. Globally unique key is `(document_id, chunk_id)`. |
| `text` | **Embed this.** Post-RTL-repair, post-normalization, logical order. |
| `page` | 1-based, where the chunk starts. Always present — unpaginated formats report `1`. |
| `section` | Human-readable heading, e.g. `"Termination"` / `"المادة 12"`. Richer structure in `metadata.structure`. |
| `clause` | Clause/article identifier the chunk is anchored to. Mirrors `metadata.structure.clause`. `None` when not clause-anchored. |
| `language` | `ar` \| `en` \| `ar-en` \| `unknown`. `ar-en` is common in Egyptian bilingual contracts. |
| `document_type` | `contract` \| `law` \| `court_ruling` \| `pleading` \| `power_of_attorney` \| `correspondence` \| `unknown` |

### `metadata` keys

Documented by `ChunkMetadata` in
[`src/document_chunk_schema.py`](src/document_chunk_schema.py).

| Key | Notes |
|---|---|
| `jurisdiction` | Inferred from text; falls back to `PipelineConfig.default_jurisdiction`. |
| `structure` | `{book, chapter, section, article, clause, clause_id, title, heading_path, heading_level, marker_language}` |
| `bbox` / `bboxes` | PDF points, origin top-left. For OCR pages, `scale` maps pixels back to points. |
| `page_span` | Every page the chunk touches. |
| `is_table`, `table_markdown`, `table_shape` | Tables are never split across chunks. |
| `ocr_confidence` | `{engine, mean, min, n_boxes, low_confidence_boxes, fallback_used, fallback_reason}`. Absent for text-layer chunks. |
| `rtl_flags` | Reading-order ambiguities. **Surfaced, not fixed** — see below. |
| `normalization_applied` | Steps that actually changed *this* chunk. |
| `raw_text` | Pre-normalization text, for A/B testing. Disable with `keep_raw_text_in_metadata=False`. |
| `display_text` | Reshaped/bidi presentation form. **Never embed this.** Off by default. |
| `chunk_strategy` | `structural` \| `paragraph` \| `size` \| `table` — tells you how good the boundary is. |
| `split_from_unit` | `True` means the boundary is artificial (a long clause was cut). |

### ⚠ Two things M2/M3 must know

1. **Embed `text`, never `display_text`.** `arabic-reshaper` + `python-bidi`
   produce *presentation forms* (U+FB50–U+FEFF) in visual order. Those are
   different codepoints from base letters; feeding them to a tokenizer or
   embedding model wrecks retrieval, silently. `text` is always logical order
   with base letters.

2. **A non-empty `rtl_flags` means "a human should look at this page."** It does
   not mean the chunk is broken, and it does not mean it is fine. See
   [Design decisions](#c-rtl-flag-rather-than-fix).

---

## Integration: M1 → M2/M3

### In-process (preferred)

```python
from src.pipeline import ingest, process_document
from src.config import PipelineConfig

# Simplest form: path in, chunks out. Never raises; returns [] on failure.
chunks = ingest("contract.pdf")
for c in chunks:
    index(c.text, metadata=c.model_dump())

# With diagnostics:
result = process_document("contract.pdf", PipelineConfig())
result.chunks        # list[DocumentChunk]
result.engine_log    # which engine handled each page, and why
result.rtl_flags     # reading-order ambiguities for manual review
result.warnings      # degradations that did not stop processing
result.succeeded     # False if it errored or produced nothing
```

Batch processing does not stop on a bad file:

```python
from src.pipeline import ingest_batch
results = ingest_batch(["a.pdf", "b.docx", "c.png"])   # ids doc_001, doc_002, doc_003
```

### Over HTTP

```bash
uvicorn src.api:app --host 127.0.0.1 --port 8000
curl -F "file=@contract.pdf" http://127.0.0.1:8000/ingest
```

`POST /ingest` → `{document_id, n_chunks, chunks: [...], engine_log, rtl_flags,
warnings, timings_ms, ...}`

Useful query params: `document_id`, `target_chunk_chars`, `max_chunk_chars`,
`overlap_chars`, `respect_structure` (set `false` for a baseline comparison),
`keep_raw_text`, `emit_display_form`.

Interactive docs at `/docs`. Engine availability at `/health`. Active settings
at `/config` — **record these alongside a batch; chunks produced under different
normalization or chunking settings are not comparable.**

---

## Integration: M1 → M5

M5 needs clause-granular contract data, not every paragraph.

```python
from src.pipeline import ingest, get_clause_chunks, process_document, clause_view

clauses = get_clause_chunks(ingest("contract.pdf"))            # list[DocumentChunk]
clauses = get_clause_chunks(chunks, document_types=["contract"], include_tables=True)

# Flattened view, same shape the HTTP endpoint returns:
view = clause_view(process_document("contract.pdf"))
```

```bash
curl -F "file=@contract.pdf" "http://127.0.0.1:8000/clauses?contracts_only=true"
```

Returns only chunks carrying a clause identity — those cut on an article or
clause boundary **the document itself declares**. Each clause has:

| Field | Notes |
|---|---|
| `clause_id` | Stable id, e.g. `art_12.cl_3` |
| `article` / `clause` | Labels as they appear, Arabic or English |
| `heading_path` | Full ancestry, outermost first |
| `page`, `language`, `is_table`, `text` | |

**`n_clauses` vs `n_chunks_total` is the health signal.** A document with 200
chunks and 3 clauses did not have its structure detected — check it before
relying on it. Documents that fell back to paragraph chunking are excluded
entirely, because they have no clause identity to report.

---

## Setup

### 1. Python packages

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -U pip setuptools wheel
.venv\Scripts\python -m pip install -r requirements.txt
```

Python 3.10 or 3.11. Roughly 4 GB of packages — Docling pulls torch and
transformers.

> The three Paddle packages are **version-locked to each other**. A mismatch
> raises `PaddlePredictorOption.__init__() takes 1 positional argument but 2
> were given`. Do not upgrade one alone.

### 2. Tesseract (native binary — pip does not install it)

**Windows**

```powershell
winget install --id UB-Mannheim.TesseractOCR -e
```

**Debian/Ubuntu**

```bash
sudo apt install tesseract-ocr tesseract-ocr-ara tesseract-ocr-eng
```

### 3. Arabic language data

A stock Tesseract install ships **English only**, which makes it useless as an
Arabic fallback. Fetch the high-accuracy models into the project-local
`tessdata/`, which the pipeline prefers automatically:

```bash
mkdir -p tessdata
curl -L -o tessdata/ara.traineddata https://github.com/tesseract-ocr/tessdata_best/raw/main/ara.traineddata
curl -L -o tessdata/eng.traineddata https://github.com/tesseract-ocr/tessdata_best/raw/main/eng.traineddata
curl -L -o tessdata/osd.traineddata https://github.com/tesseract-ocr/tessdata_best/raw/main/osd.traineddata
```

`tessdata_best` (LSTM) rather than `tessdata_fast` — the accuracy difference on
Arabic is large and OCR is not the pipeline's bottleneck.

### 4. Model weights (first run, needs internet — once)

Docling and PaddleOCR download weights on first use (~2 GB total), then run
fully offline. **Do this once during provisioning**, before the machine is
locked down:

```bash
.venv\Scripts\python -c "from src.extract_pymupdf_docling import _docling_convert; print('docling ok')"
.venv\Scripts\python -m pytest tests -m ocr -q
```

After that, nothing in the pipeline contacts the network.

### 5. Verify

```bash
.venv\Scripts\python -m pytest tests -q -m "not ocr and not docling"   # fast, ~60s
.venv\Scripts\python -m pytest tests -q                                # everything
curl http://127.0.0.1:8000/health                                      # engine availability
```

`/health` reports `degraded` if any of PyMuPDF, Docling, PaddleOCR or Tesseract
is missing. The pipeline still runs degraded — it never fails silently, but
check this after deployment.

---

## Running

```bash
# Rebuild the validation corpus (the fetch step needs internet; the rest is local)
python scripts/fetch_public_corpus.py       # published Egyptian legal PDFs
python scripts/make_synthetic_corpus.py     # first-wave fabricated fixtures
python scripts/make_stress_fixtures.py      # tables, edge cases, authored scans
python scripts/make_text_ground_truth.py    # reference text for the non-OCR path
python scripts/audit_ground_truth.py        # classify how far each reference is trustworthy
python scripts/build_manifest.py            # regenerate test_corpus/manifest.md

# Evaluate
python scripts/evaluate.py                        # full (slow: OCR + Docling)
python scripts/evaluate.py --no-ocr --no-docling  # fast structural check
python scripts/evaluate.py --from-json            # rebuild the report, no reprocessing
python scripts/ocr_benchmark.py                   # PaddleOCR vs Tesseract head-to-head
python scripts/spot_check.py                      # source-vs-pipeline excerpts

# Serve
uvicorn src.api:app --host 127.0.0.1 --port 8000
```

---

## Performance characteristics

Measured on one Windows workstation, CPU only, no GPU. Absolute numbers will
not match the firm's server; the **ratios** are what to plan against.

**Runtime is set by how many pages have no text layer, not by page count.**
Per-page cost differs by roughly two orders of magnitude between the two paths:

| Path | Order of magnitude | What dominates |
|---|---|---|
| Text layer, PyMuPDF only | ~100 ms/page | PDF parsing |
| Text layer + Docling | ~5 s/page | the layout and TableFormer models |
| OCR (scanned page) | ~5–15 s/page | recognition |

Consequences worth planning for:

- **A scanned document costs ~50–100x a text-based one of the same length.** A
  12-page scan takes longer than a 90-page statute with a text layer. This is
  the single largest driver of ingest time and it is inherent to OCR, not a
  defect. The evaluation report calls out its slowest document explicitly for
  this reason.
- **Docling is skipped above `docling_max_pages` (40) or on oversized pages**,
  because its preprocessing has aborted the interpreter from native code on
  long documents. Those documents get PyMuPDF-only extraction, which is
  ~50x faster and loses layout labels and borderless-table structure. The skip
  is recorded in `engine_log`, never silent.
- **The OCR engine choice is worth ~10x.** Tesseract runs roughly an order of
  magnitude faster per page than PaddleOCR on this stack, which is part of why
  it is primary.

Every stage is timed and reported (`timings_ms`), including OCR, and the
evaluation report shows an `Unaccounted` column — total minus every measured
stage. If that column is ever large, time is being spent somewhere nothing is
instrumented, which is a bug rather than a characteristic.

---

## Running the evaluation on your own documents

The system is validated without client data, and the evaluation is not
dependent on getting any. But the firm may still want to see these numbers
computed against its own material — and can, **on its own hardware, with
nothing leaving the building**. There is no code change; the corpus location is
a command-line argument:

```bash
# a git-ignored directory that already exists
cp /path/to/your/documents/* test_corpus/real/

# regenerate the whole report against them
python scripts/evaluate.py --corpus-dir test_corpus/real
```

`--corpus-dir` recurses into subdirectories, accepts every supported format,
and is repeatable. The report's banner switches automatically to say the run
used a supplied corpus.

This is the intended way to answer "how does it do on *our* documents" without
anyone sending a document anywhere. Expect OCR numbers to be worse than the
ones in the report: every scanned fixture here is a rendered page, and real
paper through a real scanner is harder. That gap is stated as a permanent
property of the corpus, not hidden.

For ingestion, nothing is aware of where documents come from at all —
`process_document()` takes a path:

```python
from src.pipeline import ingest_batch
from pathlib import Path

results = ingest_batch(sorted(Path("test_corpus/real").rglob("*.pdf")))
```

### Tuning against your own drafting

Nothing below is required for the system to work. These are the knobs whose
best setting depends on material this corpus cannot contain, so they ship at
conservative defaults and are worth revisiting against the firm's own
documents.

1. **Read the flagged documents first.** The report lists every document that
   fell back to paragraph chunking despite visible structure, and every
   `rtl_flags` entry. That list is the shortest route to which cue lists need
   extending.
2. **Extend structure detection** in
   [`src/structure_preservation.py`](src/structure_preservation.py):
   `_MARKER_PATTERNS`, `_UNNUMBERED_HEADINGS`, `_DOC_TYPE_CUES`. These are
   regex/keyword lists written against published statutes and synthetic
   contracts. A firm's house style will use conventions they do not cover;
   adding them is a list edit, not a rewrite.
3. **A/B the normalization toggles.** `normalize_hamza` and
   `normalize_teh_marbuta` are OFF because folding them is lossy and the
   evidence for doing so has to come from the text you actually search.
   `metadata.raw_text` holds the pre-normalization text, so both can be
   measured without re-running OCR:
   ```bash
   M1_NORMALIZATION__NORMALIZE_HAMZA=true python scripts/evaluate.py
   ```
4. **Re-run the engine benchmark on real scans.** Tesseract is primary on the
   evidence in [`reports/ocr_engine_comparison.md`](reports/ocr_engine_comparison.md);
   rendered pages and scanner output are not the same input, and the two
   engines may not degrade at the same rate. Flipping back is a two-line config
   change, and `engine_log` already records both engines' results per page.
5. **Tune chunk size with M2/M3** against their embedding model's context
   window: `target_chunk_chars` / `max_chunk_chars`.

---

## Configuration

Everything behavioural lives in [`src/config.py`](src/config.py). Three ways to
set it, later wins:

```python
cfg = PipelineConfig()                                  # 1. defaults
cfg = PipelineConfig(chunking={"target_chunk_chars": 800})   # 2. explicit
cfg = PipelineConfig.from_env()                         # 3. M1_-prefixed env vars
```

```bash
M1_OCR__MIN_MEAN_CONFIDENCE=0.6
M1_NORMALIZATION__NORMALIZE_TEH_MARBUTA=true
M1_CHUNKING__TARGET_CHUNK_CHARS=800
M1_EXTRACTION__USE_DOCLING=false
```

Most-adjusted knobs:

| Setting | Default | Why you'd change it |
|---|---|---|
| `chunking.target_chunk_chars` | 1200 | Match M2/M3's embedding context window |
| `chunking.overlap_chars` | 150 | Only applies to artificially split units |
| `ocr.min_mean_confidence` | 0.75 | Fallback trigger; raise if Paddle output is poor |
| `ocr.render_dpi` | 300 | Swept 75–600 dpi. 150 reads *body* Arabic better (CER 0.130 → 0.095) and faster, but is 3.2× worse on 7 pt print — 300 is kept because the downside is bounded. Lower it only for measured, uniformly body-text material: [`sweep`](reports/arabic_preprocess_sweep.md), [`print-size probe`](reports/dpi_probe_300.md) |
| `ocr.preprocess.enabled` | `False` | Binarization / deskew / sharpening. Off because the same sweep found no method beat handing Tesseract the raw grayscale; `contrast="unsharp"` is the one candidate worth re-testing on real scans |
| `normalization.normalize_hamza` | `False` | A/B against real documents |
| `extraction.docling_timeout_s` | 180 | Docling is slow on long documents |

---

## Design decisions to review

### (a) How PyMuPDF and Docling are split

They are not redundant, and neither is the other's fallback.

| | Owns |
|---|---|
| **PyMuPDF** | The text itself, page count/geometry, **bounding boxes**, font size and weight, per-page reading order |
| **Docling** | What each block *is* (title / section-header / list-item / caption / page-header / table), heading level, and **table structure** via TableFormer |

**The merge:** PyMuPDF's block list is the spine. Docling's items are matched
onto it **spatially, by bounding-box IoU** (≥ 0.30), and only the *label* and
*heading level* are copied across. **Text always stays PyMuPDF's.**

Why match on geometry rather than trust Docling's text: Docling's coordinate
origin, scaling and text normalization all vary between versions, and it
reflows text in ways that can disturb Arabic. Taking only the label is the
narrowest possible dependency on its internals, so a Docling upgrade cannot
silently corrupt our text. If Docling returns items but none match by bbox, that
is logged as a warning rather than accepted — a near-zero match count means the
coordinate spaces disagreed and the merge should be distrusted.

Tables: Docling's TableFormer wins where it finds tables, because it handles
**borderless** tables, which PyMuPDF's ruling-line heuristic cannot — and
borderless is the norm for Arabic contract payment schedules. PyMuPDF's
`find_tables()` covers the rest.

Docling is **optional at runtime**. Unavailable, failed, or over its
`docling_timeout_s` budget → PyMuPDF-only, recorded in `engine_log`, never
swallowed. Because Docling exposes no cancellation, the timeout runs the
conversion on a daemon thread and abandons it — without that, a 90-page statute
stalls a batch with no bound.

> **Worth your attention:** Docling costs roughly **5 s/page on CPU**, dominating
> total runtime. If that is too slow for the firm's ingest volume, the honest
> options are (i) run it only on contracts, where table structure matters most,
> or (ii) drop it and accept weaker borderless-table extraction. The pipeline
> already supports both via `extraction.use_docling`.

### (b) OCR engine order: Tesseract primary, PaddleOCR fallback

**This is a change from the spec's assumed ordering, made on measured
evidence.** The full head-to-head is in
[`reports/ocr_engine_comparison.md`](reports/ocr_engine_comparison.md); both
engines were run on identical rasters, scored with the same metric functions,
across Arabic and English fixtures at two quality levels each.

The reasoning, in order of weight:

1. **Arabic accuracy.** Tesseract reads Arabic materially better on every
   fixture in the corpus. Arabic is the majority of the firm's material, so
   this dominates.
2. **Reliability.** PaddleOCR on this stack (paddleocr 3.7 / paddlepaddle 3.2 /
   Windows / CPU) is intermittently unstable — it failed or killed its worker
   process on a substantial fraction of pages, and did so *non-deterministically*:
   the same image at the same resolution succeeded on one run and raised
   `RuntimeError: Unknown exception` on the next. Tesseract had no such
   failures on any page.
3. **Speed.** Tesseract is roughly an order of magnitude faster per page. Over
   an archive that is the difference between an overnight ingest and a
   week-long one.

**PaddleOCR is kept installed and wired as the fallback**, not removed. It is a
genuinely different architecture, so the pages it fails on are unlikely to be
the pages Tesseract fails on, and its process isolation already makes it safe
to attempt. Flipping the order back is two lines:

```python
cfg.ocr.primary_engine = "paddleocr"
cfg.ocr.fallback_engine = "tesseract"
```

> **The bug that made the first benchmark worthless — worth knowing about.**
> `PaddleOCR(lang="arabic", text_detection_model_name=...)` constructs without
> complaint and **silently substitutes the default Latin recogniser**. No
> exception, no warning. Arabic pages came back as a handful of stray Latin
> fragments, which reads exactly like "Arabic is hard" rather than "the wrong
> model is loaded". An entire engine benchmark was run and written up before it
> was caught, and its Arabic verdict was meaningless.
>
> The pipeline now verifies after construction that the recogniser actually
> matches the requested language, and refuses the instance if it does not
> (`src/paddle_worker.check_recogniser`). A test pins it. If you upgrade
> PaddleOCR, that check is the thing to watch: a renamed model family will
> disable PaddleOCR loudly, which is the intended failure.

> **PaddleOCR's resolution ceiling is mitigated, not just documented.** It could
> not process pages at the pipeline's 300 dpi render (~3500 px) — every page
> probed at full resolution failed — but succeeded once downscaled. Rather than
> paying a ~60 s failure per page and then re-reading it with Tesseract,
> `OCRConfig.paddle_max_side` (default 1600) hands PaddleOCR an image inside the
> range it can survive. **Tesseract still receives the full-resolution raster**,
> because it has no such ceiling and Arabic diacritics are worth the pixels. Set
> `paddle_max_side = 0` to disable, which is worth testing on the firm's own
> hardware — the ceiling may be specific to this Windows/CPU/oneDNN build.

#### The fallback gates

Whichever engine is primary, its result is accepted only if it clears **all
three** gates:

| Gate | Default | Catches |
|---|---|---|
| `min_mean_confidence` | 0.75 | generally poor recognition |
| `min_chars_per_page` | 40 | **detector collapse** — a dense page yielding almost nothing |
| `min_recognized_ratio` | 0.60 | many boxes detected, few recognized |

**Three gates rather than one, because mean confidence alone is a bad failure
signal on Arabic.** A page can fail catastrophically while the handful of boxes
it did read score 0.95 — mean confidence waves that straight through.

Blank pages are detected by ink ratio *before* OCR, so an empty result on a
genuinely blank page is recorded as `blank`, not a failure. Without this, the
failure-rate metric would be dominated by the blank separator pages that court
bundles are full of.

When both engines produce output, `prefer_higher_confidence_on_fallback`
(default on) keeps the better one rather than blindly preferring the fallback.

> **Still worth checking against your own scans:** the confidence comparison is
> approximate. PaddleOCR's score is a recognition softmax; Tesseract's word
> `conf` is a different quantity on a different scale, and rescaling 0–100 → 0–1
> is a unit change, not a calibration. It is on by default because the
> alternative failure — replacing a good primary result with a worse fallback —
> is the more damaging one. Both engines' full diagnostics stay in `engine_log`
> either way, so nothing is lost by the choice.

**PaddleOCR runs in a separate process** ([`src/paddle_worker.py`](src/paddle_worker.py)).
This is not defensive over-engineering: on this stack it terminated the
interpreter with a **native access violation** on some scanned pages — no Python
exception, no traceback, batch gone. A fallback that only handles Python
exceptions is not a fallback. The worker is persistent, so the ~30 s model load
is paid once per run, not per page; if it dies, the parent sees the pipe close,
logs it, and falls back to Tesseract. After two crashes PaddleOCR is disabled
for the run rather than reloaded forever.

### (c) RTL: flag rather than fix

`arabic-reshaper` and `python-bidi` convert *logical* Arabic into *visual-order
presentation forms* — correct for painting glyphs onto a canvas with no bidi
engine, and exactly wrong for a retrieval pipeline. So they are used for two
deliberately separated jobs:

- **Repair (on):** detect text that arrived *already* in visual order — a real
  artifact of OCR and older Arabic DTP — and put it back into logical order.
- **Display form (off):** produce the presentation string into
  `metadata.display_text`, never into `text`.

Two distinct damage patterns are distinguished, because the repair for one
destroys the other:

| Pattern | Symptom | Action |
|---|---|---|
| **Full character reversal** | word letters reversed (`ةداملا`) | reversed back, flagged `visual_order_repaired` |
| **Mirrored neutrals** | words *correct*, but brackets/digits/stops misplaced: `)طرف أول(`, `٦٢٠٢` for `٢٠٢٦` | **brackets un-mirrored only**; flagged `neutral_order_mirrored` |

Mirrored neutrals is the pattern that dominates in practice and the naive fix —
reversing the string — would destroy the *correct* word order. So only the
provably safe part is repaired: a span delimited `)` … `(` has exactly one
correct reading regardless of layout direction.

> **Digits are never reordered.** `٢١` is indistinguishable from `١٢` in
> extracted text. Guessing would silently corrupt article numbers, dates and
> contract amounts — the worst possible place to be quietly wrong. Affected
> blocks get a `digit_order_suspect` flag instead.

Mirrored layout is decided **per document**, not per block, because it is a
property of the producing software. A short heading rarely carries enough
evidence alone, yet that is exactly where the damage is most visible.

### (d) Chunking boundary logic

Three tiers. `metadata.chunk_strategy` records which produced each chunk, so
the evaluation report can show how often the good path was taken.

1. **Structural** — blocks grouped by the article/clause governing them. The
   boundary is one the *document declares*, so a retrieved chunk is exactly one
   clause. Granularity is chosen **per document**: statutes cut at ARTICLE
   (the atomic legal unit), contracts with sub-numbering at CLAUSE. Choosing
   globally would over-split statutes or under-split contracts. A level counts
   as "real" only with ≥3 distinct units — one stray `(a)` is a typo, not a
   scheme.
2. **Paragraph** — no usable markers. Applies to unstructured scans and
   documents whose markers OCR destroyed.
3. **Size** — a single unit over `max_chunk_chars`. Split at paragraph, then
   sentence, then whitespace; **never mid-word**.

> **Overlap applies only to tier 3.** Overlapping whole clauses would duplicate
> obligation text across chunks — which is precisely how contract QA ends up
> answering twice or citing the wrong clause number. When the boundary is real,
> the boundary is enough.

Two rules worth your sign-off:

- **A unit with its own `clause_id` is never merged away, however short.**
  `المادة (1) يعمل بأحكام القانون المرفق` is a complete article in ~80
  characters. `min_chunk_chars` governs *fragments* (bare `الباب الأول`
  headings), not *clauses*. Merging a short article would make M5 cite article
  1's text under article 2's number.
- **Tables are never split**, even when oversized. Half a payment schedule is
  worse than a long chunk.
- **A block's marker is looked for on its first *two* lines, not just the
  first.** Bilingual documents state each clause twice, once per language, in
  the same block. Where the Arabic comes first and the source stored it in
  visual order, the clause number has been pushed to the end of that line by
  bidi reordering, and a first-line-only search finds nothing — a page carrying
  fourteen numbered clauses produced two chunks and zero clause ids. Capped at
  two lines deliberately: a marker three lines into a block is far more likely
  to be an enumeration inside a paragraph than the clause the block belongs to.

### (e) How this system is validated without client data

A methodological decision, and the one with the widest blast radius, so it is
stated as a decision rather than left implicit.

No document leaves the firm. That rules out the usual approach — collect a
sample, hand-label it, measure — so accuracy is established from two sources
with complementary weaknesses:

- **Published Egyptian legal documents** give real legal Arabic, real statutory
  numbering, real publisher behaviour. What they do not give is a trustworthy
  reference: their text layers carry visual word order, out-of-flow marginal
  columns, and glyph-fragmented words, each of which makes a *correct*
  extraction score badly.
- **Authored fixtures** give an exact reference, because the text is written
  before the page exists. What they do not give is realism: a rendered page is
  not scanner output.

Neither alone is sufficient; together they bracket the answer. Three rules keep
that honest:

1. **Every reference is audited before any number is quoted against it.**
   [`scripts/audit_ground_truth.py`](scripts/audit_ground_truth.py) classifies
   each one and the reports mark which fixtures are quotable. This is not
   ceremony — it is what caught two wrong explanations that had already been
   written up as findings.
2. **Expectations are declared in advance**, in
   [`test_corpus/expectations.json`](test_corpus/synthetic/expectations.json),
   written from what each document says rather than from what the pipeline
   produced. An expectation derived from actual output can only pass.
3. **Known failures stay in the corpus as failing expectations** rather than
   being removed or quietly re-scoped. The chunking correctness score was below
   100% on purpose, and the failures were the visual-order limitation being
   measured rather than described — which is what made it possible to fix that
   limitation and *prove* it (see limitation #9 and
   [`reports/visual_order_arabic_fix.md`](reports/visual_order_arabic_fix.md)).
   The residual failures are the word-level reversal case and digit order, both
   still declared rather than removed.

---

## Corrections to earlier reports

Recorded rather than quietly overwritten, because two of them changed a
conclusion someone might already have read.

1. **"Two-column layout caused the bad Arabic OCR scores" — wrong.** An earlier
   `evaluation_report.md` explained a 0.67 CER spread between two Arabic scans
   as a reading-order artifact of two-column layout. Controlled fixtures rule
   that out: `wipo_eg081ar_1` is two-column and scores well. A second
   hypothesis raised while investigating — reference word *fragmentation* — is
   also wrong: `wipo_eg088ar_1` has a fragmented reference and scores best of
   all. The real causes are two distinct defects in the reference itself
   (visual word order, and a marginal annotation column emitted out of flow),
   and they are now measured per fixture by
   [`scripts/audit_ground_truth.py`](scripts/audit_ground_truth.py) rather than
   argued from intuition. The report carries the correction inline.
2. **The first PaddleOCR-vs-Tesseract benchmark was measuring the wrong
   model.** It scored PaddleOCR at CER 1.000 on every Arabic fixture, which
   looked like an engine failure and was in fact a silent recogniser
   substitution (see the OCR engine section above). Those numbers are void. The
   published comparison is a re-run with the Arabic recogniser verified, and
   PaddleOCR is competitive on some fixtures there — the recommendation did not
   change, but the evidence for it is now real.
3. **Processing-stage timings did not add up, and the reason was a missing
   instrument.** One document reported 531 s total with its slowest recorded
   stage at 147 ms. The OCR stage was never timed at all, so ~99.97% of that
   document's runtime was invisible. OCR and the extraction phase as a whole
   are now timed, and the evaluation report carries an `Unaccounted` column so
   the same blind spot cannot reopen unnoticed.
4. **"The slowest document is slow because it is a scan" — wrong, and it was
   the wrong explanation for a 6.5x gap.** Being a scan explains ~4 s/page;
   eight fixtures in this corpus are scans and none exceeds 4.7. Profiling
   attributes **55% of that document's runtime to the PaddleOCR fallback**,
   which fires on 6 of 6 pages because synthetic degradation pushed Tesseract's
   mean confidence just under the 0.75 gate — and a controlled re-render shows
   the degradation does not make Tesseract *slow*, only *unconfident*.
   **`evaluation_report.md` has been regenerated and now carries the correct
   explanation**; the detail is in
   [`reports/speed_outlier_investigation.md`](reports/speed_outlier_investigation.md).
5. **"Text extraction accuracy: CER 0.376" was measuring the chunker as much as
   the extractor.** That figure scored chunk text, which includes the heading
   labels `attach_heading_to_body` prepends (`Clause 1`, `Annex A`) and which
   were never in the document, and it charged page-attribution offsets as
   misreading. **The report has been regenerated** — the same measurement now
   reads 0.184 (the visual-order fix accounts for most of the drop) and the
   section states what it does and does not include. Scored per language against
   the extractor's own output, the same fixtures give **CER 0.0016 Arabic and
   0.0107 English**:
   [`reports/native_extraction_accuracy.md`](reports/native_extraction_accuracy.md).

---

## Known limitations

Things that are genuinely not solved, as opposed to merely untested.

1. **Docling costs ~5 s/page on CPU** and dominates runtime. It is skipped
   entirely on documents over `docling_max_pages` (40) or with oversized pages,
   because its preprocessing raised `std::bad_alloc` in native code and
   **aborted the interpreter** on a 94-page statute — which the thread-based
   timeout cannot protect against, since there is no process left to time out.
   Long documents therefore get PyMuPDF-only extraction (logged, not silent),
   losing Docling's layout labels and borderless-table handling.
2. **PaddleOCR is unstable on this build.** It crashes the process on some
   inputs; process isolation contains the damage but those pages fall back to
   Tesseract rather than being read by both.
   
   > Both of these are the same class of problem: **two of the four required
   > libraries can terminate the process from native code.** Neither is
   > catchable in Python. The mitigations (subprocess isolation for PaddleOCR,
   > pre-emptive size guards for Docling) are why the pipeline survives a batch,
   > and both are worth re-testing on the firm's actual server — different RAM
   > and a different BLAS build may move these thresholds substantially.
3. **Tables on the OCR path are reconstructed from geometry, not from a layout
   model.** Docling's TableFormer never sees a scanned page and PyMuPDF's
   `find_tables` needs ruling lines a raster does not have, so tables on OCR'd
   pages are rebuilt from the engine's own word boxes: lines are split into
   cells at gaps wider than 1.5 glyph-heights, and a run of lines is accepted as
   a table only if its columns recur and its cells mostly land in them
   (`OCRConfig.detect_tables` and the thresholds beside it). This recovers the
   grid on all four image-table fixtures. What it does not do is understand
   merged cells or spanning headers — it produces a rectangular grid, and a
   table that is not rectangular will be flattened into one.
4. **Structure detection tolerates one OCR error in a marker word, not two.**
   *(Was: "regex-based, misses mangled markers, silently demotes to paragraph
   chunking." The silent part is fixed; the ceiling is real and stated here.)*
   [`src/fuzzy_markers.py`](src/fuzzy_markers.py) matches `المادة` and its
   siblings at edit distance 1 after folding tatweel, diacritics and
   orthographic variants — so **one substitution, deletion, insertion or broken
   join is recovered, and two are not**. Split numbers (`1 2` for `12`) are
   rejoined, scoped to the marker's own digit run and never to the rest of the
   line. Measured: corrupted-marker detection **37.5% → 87.5%**, chunking
   identical to the clean document on every corruption caught, and **0 false
   positives** on 3,523 non-marker Arabic lines. The threshold cannot go to 2:
   `عادة`, `سادة`, `قادة` and `مدة` are all one edit from `مادة`.
   Every fuzzy match is flagged (`metadata.structure.marker_fuzzy`) and a
   document that finds no structure at all now raises
   `structure_detection_failed` instead of quietly returning paragraph chunks.
   See [`reports/fuzzy_structure_matching.md`](reports/fuzzy_structure_matching.md)
   and `tests/test_fuzzy_markers.py` —
   `TestNoFalsePositives`, `TestChunkingEquivalence`, `TestTwoErrorsAreNotHandled`,
   `TestFailuresAreVisible`.
5. **Document-type inference assumes one type per file.** Court bundles arrive
   as one PDF containing many instruments.
6. **No handwriting recognition.** Marginalia, initials and handwritten
   corrections are not read by any configured engine.
7. **Legacy binary `.doc` is unsupported** — detected and rejected loudly rather
   than misparsed. Convert with
   `soffice --headless --convert-to docx`.
8. **Some PDFs have a text layer that decodes to mojibake** (broken or custom
   font encodings with no usable ToUnicode CMap). One document in the corpus —
   a *published* Egyptian statute — is exactly this. Detection catches it via
   `text_layer_quality` and reroutes to OCR. The threshold (0.50) was calibrated
   on the documents available here; a firm archive spanning more producers and
   more decades will contain edge cases either side of it, and the threshold is
   a single config value.
9. **Arabic stored in visual order is detected and repaired — except when the
   reversal is at word level only.** *(Was: "flagged, not repaired.")*
   [`src/visual_order.py`](src/visual_order.py) reconstructs a PDF text layer's
   true painted order from glyph x-positions and inverts it with `python-bidi`,
   per run, so an embedded `(the Lessor)` keeps its English word order while the
   Arabic around it is put back. `stress_inline_bilingual.pdf` goes from **0 to
   5 of 5** clause markers and no longer demotes to paragraph chunking;
   `constitute_egypt_2014_ar.pdf` goes from **0 to 208** article-level clause
   ids. The OCR path had the same bug from the other side — sorting a mixed line
   right-to-left turned `(the Lessor)` into `(Lessor the)` — and now reorders at
   token granularity instead.

   A reading is accepted only when it **both** recovers at least as much legal
   structure **and** beats the original by 0.10 on an orthographic order score;
   `scripts/audit_ground_truth.py`'s `REVERSAL_HELPS` threshold and its
   `reverse_line_words` now live in the pipeline module and are imported by the
   audit, so the two cannot drift. Both criteria are load-bearing:
   `wipo_eg081ar_1.pdf` scores *better* reordered and is rejected because doing
   so would take its markers from 238 to 12. Every reordered span is still
   flagged (`metadata.reading_order_repaired`, `visual_order_repaired`), and
   `raw_text` keeps the text exactly as extracted — repaired *and* auditable,
   not one or the other.

   **What it still does not handle:** a producer that reverses each line's
   *words* while leaving every word's characters logical
   (`constitute_egypt_2019_ar.pdf`). Glyph geometry gives no extra information
   there and every signal in the order score is character-positional, so both
   readings look alike; detecting it needs a lexicon or a language model.
   Nesting deeper than the corpus's hardest fixture is untested rather than
   known-good. Digit *order* is untouched by design — see #14. See
   [`reports/visual_order_arabic_fix.md`](reports/visual_order_arabic_fix.md)
   and `tests/test_visual_order.py` — `TestBilingualInlineVisualOrder`,
   `TestGenuineErrorsAreNotReordered`, `TestLogicalTextIsNeverReordered`,
   `TestPipelineIntegration`.
10. **Ground truth derived from a PDF's text layer is not automatically
    trustworthy, and this corpus contains three ways it fails.**
    `scripts/audit_ground_truth.py` classifies every reference before any
    accuracy figure is quoted against it: some public Arabic PDFs store visual
    word order, some emit a marginal annotation column out of flow, and some
    fragment words into single glyphs. Each makes a *correct* extraction score
    badly. The mitigation is the `scan_authored_*` fixtures, whose reference
    text was written before the page was rendered and therefore cannot carry
    these defects — those are the fixtures whose absolute OCR accuracy is
    quotable without a caveat.

11. **Rendered pages are not scans, and no synthetic degradation closes that
    gap.** Every scanned fixture here is a digital page rasterized and then
    degraded with skew, noise and JPEG artifacts. That models compression and
    geometry; it does not model scanner optics, photocopy generations,
    bleed-through from the reverse side, staple shadows, or toner that ran out
    halfway down the page. **The OCR accuracy figures in the report are an
    optimistic bound and should be quoted as one.** This is permanent: it is a
    property of validating without firm data, and it does not resolve later.
    If the firm wants the number for its own archive, the evaluation runs
    against a local directory without anything leaving the building — see
    [Running the evaluation on your own documents](#running-the-evaluation-on-your-own-documents).
12. **No handwriting, and the corpus cannot measure how badly it fails.** The
    one handwritten public document available (`wipo_eg087ar_1.pdf`) is
    excluded from every metric: it has no usable text layer to score against,
    so it can establish that the pipeline does not crash on it and nothing
    more.
13. **No authentication on the API.** It is not intended to be network-exposed;
    if it goes on the firm LAN, put it behind the firm's existing auth rather
    than adding a second scheme here.
14. **Digit *order* in right-to-left numeric runs is flagged, never corrected —
    and this one does not get fixed later.** When a page was laid out visually,
    `٢١` and `١٢` are the same bytes in the same order and nothing in the
    extracted text distinguishes 12 from 21. Both reading-order repair (#9) and
    tolerant marker matching (#4) deliberately stop at this line: they move
    numeric runs as units and rejoin digits OCR *split*, but never reorder
    digits inside a run. The consequence is visible in the corpus —
    `wipo_eg088ar_1.pdf` yields `art_01` and `art_41` where the source means
    articles 10 and 14 — and those blocks carry `digit_order_suspect` so the
    affected article numbers, dates and amounts can be verified against the
    source. **A guess here silently changes what a contract says**, which is why
    it stays a flag rather than becoming a repair.
15. **The reading-order verdict is taken once per document, so a minority-script
    heading inside a majority-other-script document goes unrepaired.**
    `stress_exhibits_footnotes.pdf` is an English contract with Arabic annex
    headings. Its document-level verdict is *rejected* — reordering moves
    markers only 11 → 13, below the gain threshold — which is right for the
    document as a whole and wrong for those headings, which stay reversed
    (`التعريفات- 1` for `1 - التعريفات`). Its English stream scores **0.0000**
    and its overall CER is 0.0794, all of it there. The all-or-nothing design is
    deliberate and argued in `_resolve_reading_order`'s docstring; what is new is
    that its cost is now measured. A per-*script* verdict is the plausible shape
    of a fix and needs the same fixture-and-test care the original repair got.
    See [`reports/native_extraction_accuracy.md`](reports/native_extraction_accuracy.md)
    (follow-up F1).
16. **A page that fails the OCR confidence gate costs ~12x one that passes, and
    the engine that then wins is chosen on an uncalibrated comparison.**
    `OCRConfig.min_mean_confidence` (0.75) failing invokes the PaddleOCR
    fallback, so the page runs *both* engines: 38–46 s against 2–4 s. On
    `scan_constitute_egypt_2019_ar_150dpi.pdf` this fires on 6 of 6 pages and is
    **55% of the document's runtime**. `prefer_higher_confidence_on_fallback`
    then picks the winner by comparing `mean_conf` across two engines whose
    scales the code's own log entry flags as *"not calibrated between engines"* —
    and on the one Arabic fixture with authored ground truth, PaddleOCR is 2.8x
    less accurate and 5.9x slower than the Tesseract output it would replace.
    How often this fires on a real archive is unknown and is the thing to
    measure on firm material. See
    [`reports/speed_outlier_investigation.md`](reports/speed_outlier_investigation.md)
    (follow-up S1); `ocr.fallback_engine = "none"` removes the cost and the
    safety net together.
17. **One fixture's reference text is incomplete**, and it is the single largest
    contributor to the text-extraction CER in `evaluation_report.md`.
    `synthetic_contract_bilingual.pdf` scores CER 0.60 at **bag error 0.000** —
    every reference word is present, and the output additionally contains 265
    words of real document content (header banner, party block, table cells)
    that the reference omits, because the reference was built from the clause
    list rather than from what the generator draws. Fixing it is a change to
    `make_text_ground_truth.py`, not to the pipeline
    (follow-up F2 in [`reports/native_extraction_accuracy.md`](reports/native_extraction_accuracy.md)).

---

## Repo layout

```
m1-document-processing/
├── requirements.txt              pinned, with notes on why each pin matters
├── pytest.ini
├── README.md
├── src/
│   ├── config.py                 every behavioural knob, with rationale
│   ├── document_chunk_schema.py  THE OUTPUT CONTRACT
│   ├── type_detection.py         scanned vs text, per page; format routing
│   ├── extract_pymupdf_docling.py  text-layer path + the merge
│   ├── ocr_pipeline.py           PaddleOCR + Tesseract fallback + gates
│   ├── paddle_worker.py          crash isolation for PaddleOCR
│   ├── visual_order.py           visual→logical reading order + the live test
│   ├── rtl_fix.py                reading-order repair and flagging
│   ├── normalize.py              pyarabic, per-step toggles
│   ├── structure_preservation.py IR + legal marker detection
│   ├── fuzzy_markers.py          OCR-tolerant marker + split-digit matching
│   ├── chunking.py               three-tier legal chunking
│   ├── pipeline.py               orchestrator; M1→M2/M3 and M1→M5 functions
│   └── api.py                    POST /ingest, POST /clauses, /health, /config
├── scripts/
│   ├── fetch_public_corpus.py    download published Arabic legal PDFs
│   ├── make_synthetic_corpus.py  generate fabricated fixtures
│   ├── build_manifest.py         regenerate test_corpus/manifest.md
│   ├── make_native_fixtures.py   authored native (non-OCR) PDFs + references
│   ├── evaluate.py               the spec's evaluation criteria
│   ├── native_extraction_benchmark.py  non-OCR accuracy, by extractor x language
│   ├── speed_outlier_profile.py  per-page cost census, stage split, cProfile
│   └── spot_check.py             source-vs-pipeline excerpts for eyeballing
├── test_corpus/
│   ├── public/                   published legal documents
│   ├── synthetic/                fabricated fixtures + OCR ground truth
│   ├── real/                     empty; point --corpus-dir here to evaluate your own files
│   └── manifest.md               per-file source, format, language, quirks
├── tests/                        pytest suite
├── tessdata/                     Arabic/English Tesseract models
└── reports/
    ├── evaluation_report.md      measured results, all seven spec criteria
    ├── ocr_engine_comparison.md  PaddleOCR vs Tesseract, and the engine decision
    ├── visual_order_arabic_fix.md   limitation #9: what was repaired, and how
    ├── fuzzy_structure_matching.md  limitation #4: threshold, and its ceiling
    └── spot_check.md             extraction samples for manual review
```

## Where the interesting reading is

Each module's docstring explains the decisions inside it, not just what it
does. If you are reviewing rather than integrating, start with:

- [`src/document_chunk_schema.py`](src/document_chunk_schema.py) — the contract
- [`src/chunking.py`](src/chunking.py) — the three-tier boundary logic
- [`src/rtl_fix.py`](src/rtl_fix.py) — why ambiguity is flagged, not fixed
- [`src/visual_order.py`](src/visual_order.py) — why the reading-order repair is
  safe to run automatically, and the two criteria it takes to accept one
- [`src/fuzzy_markers.py`](src/fuzzy_markers.py) — why the edit-distance
  threshold is 1 and cannot be 2
- [`src/ocr_pipeline.py`](src/ocr_pipeline.py) — the three gates and the fallback
- [`src/config.py`](src/config.py) — every default, with the reason for it
