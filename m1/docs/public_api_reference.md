# M1 Public API Reference

The integration surface of the **M1 Document Processing** pipeline — everything
M2/M3 (retrieval + QA) and M5 (contract intelligence) are expected to call, and
nothing else.

Read it top to bottom: **what comes out** (the `DocumentChunk` contract), then
**how you get it** (in-process entry points), then **how you get it over HTTP**
(the FastAPI endpoints), then the **types you may need to construct or read**.

Anything in `src/` not listed here — `extract_pymupdf_docling`, `ocr_pipeline`,
`paddle_worker`, `visual_order`, `rtl_fix`, `normalize`,
`structure_preservation`, `fuzzy_markers`, `chunking`, `type_detection`,
`preprocess`, `paddleocr_vl` — is internal pipeline machinery. It is called by
`process_document()` and is not part of the handoff contract; its signatures may
change without notice.

**Everything runs locally on firm infrastructure. No cloud APIs, no data egress.**

---

## Contents

1. [Schema — the output contract](#1-schema--the-output-contract)
   - [`DocumentChunk`](#documentchunk)
   - [`DocumentIngestResult`](#documentingestresult)
2. [Entry points — the pipeline functions](#2-entry-points--the-pipeline-functions)
   - [`ingest()`](#ingest)
   - [`process_document()`](#process_document)
   - [`ingest_batch()`](#ingest_batch)
   - [`get_clause_chunks()`](#get_clause_chunks)
   - [`clause_view()`](#clause_view)
3. [API endpoints](#3-api-endpoints)
   - [`POST /ingest`](#post-ingest)
   - [`POST /clauses`](#post-clauses)
   - [`GET /health`](#get-health)
   - [`GET /config`](#get-config)
4. [Supporting types](#4-supporting-types)
5. [Reliability notes every consumer should read](#5-reliability-notes-every-consumer-should-read)

---

# 1. Schema — the output contract

## `DocumentChunk`

**Location:** [`src/document_chunk_schema.py`](../src/document_chunk_schema.py)

One retrievable unit of a legal document. This is the **shared contract** — the
single object M1 hands to M2/M3 and M5. The top-level fields are frozen by
the team spec (plus `clause`, added to match M2's copy of the contract — see
`reports/schema_contract_verification.md`); `metadata` is deliberately an open
dict so M1 can add structural signal without breaking consumers.

**Pydantic config:** `extra="forbid"` (unknown *top-level* fields are rejected),
`use_enum_values=True` (so `language` and `document_type` serialize and read back
as plain strings, not enum objects).

### Top-level fields

| Field | Type | Required | Default | Meaning |
|---|---|---|---|---|
| `document_id` | `str` (min length 1, no whitespace) | **yes** | — | Stable id for the source document. Content-hashed (`doc_<sha1[:12]>`) by default, so re-ingesting the same file after a pipeline change yields the same id. Batch runs use the spec's literal `doc_001` form. Overridable to a firm DMS id. |
| `chunk_id` | `str` (min length 1, no whitespace) | **yes** | — | `chunk_017` style, 1-based, zero-padded to 3, ordered by reading position. Unique **within** a document — the globally unique key is `(document_id, chunk_id)`. |
| `text` | `str` (must not be blank/whitespace-only) | **yes** | — | The chunk text after RTL repair and Arabic normalization, in **logical order with base letters**. **This is what M2/M3 embed.** Never embed `metadata.display_text` instead (see [§5](#5-reliability-notes-every-consumer-should-read)). |
| `page` | `int` (≥ 1) | **yes** | — | 1-based page number where the chunk **starts**. `metadata.page_span` lists every page it touches. **Always present** — formats with no pagination (TXT, and DOCX with no explicit page break) are treated as a single page and report `1`. |
| `section` | `str \| None` | no | `None` | Human-readable section/heading label, e.g. `"Termination"` or `"المادة 12"`. Best-effort; `None` when no structure was detectable. Richer structure lives in `metadata.structure`. |
| `clause` | `str \| None` | no | `None` | The clause/article identifier this chunk is anchored to, e.g. `"Clause 1"` / `"البند 3"`. Mirrors `metadata.structure.clause`, surfaced at the top level because consumers filter on it. `None` when the chunk is not clause-anchored. |
| `language` | `Language` enum, serialized as `str` | no | `"unknown"` | `"ar"` \| `"en"` \| `"ar-en"` \| `"unknown"`. `"ar-en"` means Arabic and Latin script are both materially present — common in Egyptian bilingual contracts, and worth routing differently. |
| `document_type` | `DocumentType` enum, serialized as `str` | no | `"unknown"` | `"contract"` \| `"law"` \| `"court_ruling"` \| `"pleading"` \| `"power_of_attorney"` \| `"correspondence"` \| `"unknown"`. Coarse by design — fine-grained legal taxonomy is M5's job. |
| `metadata` | `dict[str, Any]` | no | `{}` | Open bag. Shape documented by `ChunkMetadata` below. **Treat unknown keys as additive** — adding keys is always backwards compatible. |

### `metadata` keys

Serialized as a plain dict (never a typed object) so consumers never have to
import M1's types. Documented by `ChunkMetadata` (`extra="allow"`).

**Provenance**

| Key | Type | Default | Meaning |
|---|---|---|---|
| `jurisdiction` | `str \| None` | `None` | Inferred from the text; falls back to `PipelineConfig.default_jurisdiction` (`"Egypt"`). |
| `source_file` | `str \| None` | `None` | Path/name of the file the chunk came from. |
| `source_engine` | `str` | `"unknown"` | Which extractor actually produced this text: `"pymupdf"`, `"docling"`, `"pymupdf+docling"`, `"paddleocr"`, `"tesseract"`, `"python-docx"`, `"plaintext"`, `"unknown"`. **Per chunk**, so OCR and text-layer quality can be judged separately — accuracy differs by roughly two orders of magnitude between them (see [§5](#5-reliability-notes-every-consumer-should-read)). |
| `pdf_kind` | `"text"` \| `"scanned"` \| `"hybrid"` \| `"n/a"` \| `None` | `None` | How the source PDF was classified. |
| `ingested_at` | `datetime \| None` | `None` | UTC ingestion timestamp. |

**Structure**

| Key | Type | Default | Meaning |
|---|---|---|---|
| `structure` | `object` (`StructuralRef`) | `{}` | Where the chunk sits in the document's legal structure. See [`StructuralRef`](#structuralref) below. |
| `block_type` | `str` | `"paragraph"` | Layout element the dominant content came from: `"paragraph"`, `"heading"`, `"table"`, `"list"`, `"signature"`, `"stamp"`, `"header_footer"`, `"unknown"`. |
| `bboxes` | `list[object]` | `[]` | All bounding boxes contributing to this chunk. See [`BoundingBox`](#boundingbox). |
| `bbox` | `object \| None` | `None` | Union of `bboxes` — convenience for highlighting a chunk in a viewer. |
| `page_span` | `list[int]` | `[]` | Every page this chunk's text came from (usually one). |
| `char_span` | `[int, int] \| None` | `None` | Offsets into the document's normalized full text. |

**Tables**

| Key | Type | Default | Meaning |
|---|---|---|---|
| `is_table` | `bool` | `false` | Chunk body is a table. Tables are **never split across chunks**. |
| `table_markdown` | `str \| None` | `None` | Markdown rendering of the table. |
| `table_shape` | `[int, int] \| None` | `None` | `(rows, cols)`. |

**Quality**

| Key | Type | Default | Meaning |
|---|---|---|---|
| `ocr_confidence` | `object \| None` | `None` | `{engine, mean, min, n_boxes, low_confidence_boxes, fallback_used, fallback_reason}`. **Absent for text-layer chunks** — its absence means "not OCR'd", not "confidence unknown". `mean`/`min` are 0.0–1.0. |
| `rtl_flags` | `list[object]` | `[]` | Reading-order ambiguities. **Surfaced, not fixed.** See [`RTLFlag`](#rtlflag). |
| `reading_order_repaired` | `bool` | `false` | `true` when the source text was stored in visual (screen) order and was reordered to logical order. Recorded rather than applied silently: the matching `visual_order_repaired` entry in `rtl_flags` carries the evidence, and `raw_text` still holds the text exactly as extracted. |
| `normalization_applied` | `list[str]` | `[]` | Normalization steps that actually changed **this** chunk. |
| `raw_text` | `str \| None` | `None` | Pre-normalization, pre-RTL-repair text. Roughly doubles payload size; disable with `keep_raw_text_in_metadata=False` / `keep_raw_text=false`. |
| `display_text` | `str \| None` | `None` | Reshaped + bidi **presentation form**, for rendering only. Off by default. **Never embed this** — see [§5](#5-reliability-notes-every-consumer-should-read). |

**Chunking provenance**

| Key | Type | Default | Meaning |
|---|---|---|---|
| `chunk_index` | `int \| None` | `None` | Position within the document. |
| `chunk_strategy` | `"structural"` \| `"paragraph"` \| `"size"` \| `"table"` \| `None` | `None` | **How good the boundary is.** `structural` = cut on a clause/article boundary the document itself declares. `paragraph` = no structure was detectable. `size` = a length-driven cut. |
| `split_from_unit` | `bool` | `false` | `true` means the parent structural unit exceeded max size and was cut — **this boundary is artificial**, and the chunk may begin or end mid-clause. |
| `n_chars` | `int \| None` | `None` | Character count of `text`. |
| `n_words` | `int \| None` | `None` | Word count of `text`. |

### Convenience members

| Member | Type | Purpose |
|---|---|---|
| `.structure` | property → `StructuralRef` | Typed view of `metadata["structure"]`. Always returns an object (empty if unset), never `None`. |
| `.is_clause` | property → `bool` | `True` when the chunk is anchored to an identifiable clause or article (`clause`, `article`, or `clause_id` present). **This is the filter M5 uses.** |
| `.preview(n=80)` | method → `str` | Whitespace-flattened first `n` characters plus `"..."` if truncated. For logs and eyeballing. |

### Usage

```python
from src.pipeline import ingest

for chunk in ingest("contract.pdf"):
    # M2/M3: embed `text`, carry the whole chunk as retrieval metadata
    index(
        text=chunk.text,
        doc_key=(chunk.document_id, chunk.chunk_id),
        page=chunk.page,
        section=chunk.section,
        language=chunk.language,          # plain str: "ar" / "en" / "ar-en" / "unknown"
        payload=chunk.model_dump(),       # JSON-safe
    )

    # Boundary quality is worth recording alongside the vector
    if chunk.metadata.get("split_from_unit"):
        mark_artificial_boundary(chunk.chunk_id)
```

```python
# M5: clause identity, via the typed view
for chunk in ingest("contract.pdf"):
    if chunk.is_clause:
        s = chunk.structure
        print(s.clause_id, s.article, s.heading_path, chunk.preview())
```

### Behavioural notes

- **Validation is strict on the way in.** Constructing a `DocumentChunk` with
  empty/whitespace-only `text`, whitespace inside `document_id`/`chunk_id`, a
  `page` of `0` or less, or an unknown top-level field raises Pydantic's
  `ValidationError`. Chunks produced by the pipeline always satisfy this — the
  constraints matter if you round-trip chunks through your own storage and
  rebuild them.
- **`language` and `document_type` come back as strings, not enums**
  (`use_enum_values=True`). Compare against `"contract"`, not
  `DocumentType.CONTRACT`, unless you import the enum — the enums are `str`
  subclasses, so `DocumentType.CONTRACT == "contract"` is also `True`.
- **`metadata` may gain keys at any time.** It will not silently *change the
  meaning* of an existing key.
- **`section` and `structure` are best-effort.** A document with no detectable
  markers yields `section=None` and an empty `structure` on every chunk; the
  chunks are still valid and still embeddable.

---

## `DocumentIngestResult`

**Location:** [`src/document_chunk_schema.py`](../src/document_chunk_schema.py)

Everything M1 knows about one processed document: the chunk payload plus the
diagnostics that make a failure debuggable without re-running. Returned by
`process_document()` and `ingest_batch()`; mirrored by `POST /ingest`.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `document_id` | `str` | — | Same id carried on every chunk. |
| `source_file` | `str` | — | Path the document was read from. |
| `file_type` | `str` | — | Detected input type (`pdf`, `docx`, `txt`, `image`, `unknown`). |
| `pdf_kind` | `"text"` \| `"scanned"` \| `"hybrid"` \| `"n/a"` \| `None` | `None` | Per-document PDF classification (decided per page underneath). |
| `document_type` | `str` | `"unknown"` | Document-level inference; each chunk carries the same value. |
| `language` | `str` | `"unknown"` | Document-level dominant language. |
| `n_pages` | `int` | `0` | Pages extracted. |
| `n_chunks` | `int` | `0` | **Kept in sync automatically** with `len(chunks)` by a model validator — do not set it yourself. |
| `chunks` | `list[DocumentChunk]` | `[]` | **The payload.** Empty list, never `None`, when nothing was produced. |
| `engine_log` | `list[dict]` | `[]` | Per-page record of which engine handled it and why, including both engines' results when an OCR fallback was attempted. |
| `rtl_flags` | `list[RTLFlag]` | `[]` | Document-level roll-up of reading-order ambiguities. |
| `warnings` | `list[str]` | `[]` | Degradations that did **not** stop processing (Docling unavailable, DOCX pagination synthesized, low-confidence OCR pages kept, hybrid page split). |
| `errors` | `list[str]` | `[]` | Failure message plus a truncated traceback, when something went wrong. |
| `timings_ms` | `dict[str, float]` | `{}` | Per-stage milliseconds: `detect`, `extract`, `rtl_fix`, `normalize`, `structure`, `chunking`, `total`. |
| `succeeded` | `bool` | `True` | `False` when the document errored **or** produced zero chunks. |

**Note:** `succeeded=False` with a non-empty `warnings` list and an empty
`chunks` list is the normal shape of a soft failure — check `succeeded` before
trusting `chunks`, and read `errors` when it is `False`.

---

# 2. Entry points — the pipeline functions

All of these live in [`src/pipeline.py`](../src/pipeline.py). **If you are in the
same Python process, call these directly and skip the HTTP hop** — the endpoints
in §3 are thin wrappers over exactly these functions.

## `ingest()`

**Location:** [`src/pipeline.py`](../src/pipeline.py)

**The M1 → M2/M3 handoff, in its thinnest form.** Path in, chunks out.

```python
def ingest(
    path: str | Path,
    config: PipelineConfig | None = None,
) -> list[DocumentChunk]
```

| Parameter | Type | Required | Default | Meaning |
|---|---|---|---|---|
| `path` | `str \| Path` | **yes** | — | PDF (text-based, scanned, or hybrid), DOCX, TXT/MD, or image (PNG/JPG/TIFF/BMP/WEBP — routed straight to OCR). |
| `config` | `PipelineConfig \| None` | no | `None` → defaults | See [`PipelineConfig`](#pipelineconfig). |

**Returns:** `list[DocumentChunk]` — **empty list, never `None`**, if the
document failed.

```python
from src.pipeline import ingest

chunks = ingest("contract.pdf")
if not chunks:
    # No diagnostics available here — re-run via process_document() to find out why
    log.warning("no chunks from contract.pdf")

for c in chunks:
    vector_store.add(embed(c.text), metadata=c.model_dump())
```

**Behavioural notes**

- **Raises nothing for a bad document** (with the default
  `PipelineConfig.fail_fast=False`) — the failure is swallowed and you get `[]`.
  When you need the reason, use `process_document()` instead; the diagnostics are
  only on the result object.
- `fail_fast=True` in the config **does** let exceptions propagate. Leave it off
  for batch work.
- Every chunk in the returned list is fully valid — no empty-text or
  malformed-id chunks reach you.

---

## `process_document()`

**Location:** [`src/pipeline.py`](../src/pipeline.py)

**The full M1 → M2/M3 handoff function.** Same work as `ingest()`, but returns
the chunks *and* everything needed to debug or audit the run.

```python
def process_document(
    path: str | Path,
    config: PipelineConfig | None = None,
    document_id: str | None = None,
) -> DocumentIngestResult
```

| Parameter | Type | Required | Default | Meaning |
|---|---|---|---|---|
| `path` | `str \| Path` | **yes** | — | Any supported input (as `ingest()`). |
| `config` | `PipelineConfig \| None` | no | `None` → defaults | Every stage is individually switchable. |
| `document_id` | `str \| None` | no | `None` → content-hashed `doc_<sha1[:12]>` | Override the generated id — use this to join chunks back to the firm's DMS. |

**Returns:** [`DocumentIngestResult`](#documentingestresult).

```python
from src.pipeline import process_document
from src.config import PipelineConfig

cfg = PipelineConfig()
cfg.chunking.target_chunk_chars = 800      # match your embedding context window

result = process_document("scan_of_statute.pdf", cfg, document_id="DMS-2024-01173")

if not result.succeeded:
    log.error("ingest failed for %s: %s", result.source_file, result.errors[:1])
else:
    if result.rtl_flags:
        queue_for_human_review(result.document_id, result.rtl_flags)
    for w in result.warnings:
        log.info("degraded: %s", w)
    index_all(result.chunks)

log.info("pdf_kind=%s pages=%d chunks=%d total_ms=%.0f",
         result.pdf_kind, result.n_pages, result.n_chunks,
         result.timings_ms.get("total", 0.0))
```

**Behavioural notes**

- **A failing document does not raise** unless `config.fail_fast=True`. It
  returns `succeeded=False` with the exception message and a truncated traceback
  in `.errors`, so one corrupt file cannot take down a batch.
- **Two failure modes are worth distinguishing:** an exception (`errors`
  non-empty) versus a document that processed cleanly but yielded zero chunks
  (`errors` empty, `warnings` contains `"document produced zero chunks (no
  extractable text)"`). Both give `succeeded=False`.
- **Known raise-turned-error cases** (recorded in `.errors`, not raised):
  unsupported file type; a scanned PDF when `config.ocr.enabled=False` (message
  names the pages and tells you to enable OCR); an image input with OCR
  disabled; extraction that produced no pages.
- **`engine_log` and `timings_ms` are diagnostics, not payload** — but
  `engine_log` is the only place the per-page engine choice and the reason for an
  OCR fallback are recorded.
- Content-hashed ids are computed from the **resolved path**, not the file
  bytes, when called through this function — moving a file changes its
  auto-generated id. Pass `document_id` explicitly if you need id stability
  across relocations.

---

## `ingest_batch()`

**Location:** [`src/pipeline.py`](../src/pipeline.py)

Process many documents; one failure does not stop the batch.

```python
def ingest_batch(
    paths: list[str | Path],
    config: PipelineConfig | None = None,
) -> list[DocumentIngestResult]
```

| Parameter | Type | Required | Default | Meaning |
|---|---|---|---|---|
| `paths` | `list[str \| Path]` | **yes** | — | Any mix of supported inputs. |
| `config` | `PipelineConfig \| None` | no | `None` → defaults | Applied to every document. |

**Returns:** `list[DocumentIngestResult]` — **one entry per input, in order**,
including for documents that failed.

```python
from src.pipeline import ingest_batch

results = ingest_batch(["a.pdf", "b.docx", "c.png"])   # ids doc_001, doc_002, doc_003

ok      = [r for r in results if r.succeeded]
failed  = [(r.source_file, r.errors[:1]) for r in results if not r.succeeded]
all_chunks = [c for r in ok for c in r.chunks]
```

**Behavioural notes**

- **Document ids are sequential, not content-hashed:** `doc_001`, `doc_002`, …
  in the order given, matching the spec's literal id format. **Re-running a batch
  with a different file order reassigns ids** — do not use batch ids as stable
  keys across runs. Use `process_document()` with an explicit `document_id` when
  you need stability.
- Sequential, single-process. There is no parallelism or progress callback here.

---

## `get_clause_chunks()`

**Location:** [`src/pipeline.py`](../src/pipeline.py)

**The M1 → M5 handoff.** Filters a chunk list down to clause-level chunks —
those anchored to an identifiable article or clause.

```python
def get_clause_chunks(
    chunks: list[DocumentChunk],
    *,
    include_tables: bool = True,
    document_types: list[str] | None = None,
) -> list[DocumentChunk]
```

| Parameter | Type | Required | Default | Meaning |
|---|---|---|---|---|
| `chunks` | `list[DocumentChunk]` | **yes** | — | Positional. Typically the output of `ingest()` or `result.chunks`. |
| `include_tables` | `bool` | no (**keyword-only**) | `True` | Keep table chunks that sit inside a clause (payment schedules, deliverable tables). On by default — they are usually the clause's operative content. |
| `document_types` | `list[str] \| None` | no (**keyword-only**) | `None` | Restrict to these `document_type` values, e.g. `["contract"]`. `None` keeps every type — Egyptian practice often needs the statute article a clause references. |

**Returns:** `list[DocumentChunk]` — a filtered subset of the input. **Empty
list, never `None`**, when nothing qualifies. The chunk objects are the same
instances, not copies.

```python
from src.pipeline import ingest, get_clause_chunks

chunks  = ingest("contract.pdf")
clauses = get_clause_chunks(chunks, document_types=["contract"], include_tables=True)

# The health signal — check this before trusting the result
if chunks and len(clauses) < 0.1 * len(chunks):
    log.warning("only %d clauses from %d chunks — structure detection likely failed",
                len(clauses), len(chunks))

for c in clauses:
    s = c.structure
    m5_store.add(clause_id=s.clause_id, article=s.article,
                 heading_path=s.heading_path, page=c.page, text=c.text)
```

**Behavioural notes**

- **Chunks that fell to paragraph chunking are excluded entirely.** A document
  with no detectable structure has no clause identity to report, so it
  contributes nothing here even though `ingest()` returned plenty of chunks.
- **`len(clauses)` vs `len(chunks)` is the health signal.** 200 chunks and 3
  clauses means that document's markers were not detected — check it before M5
  relies on it. It will also show up in the evaluation report's chunking-tier mix.
- `document_types` compares against the chunk's `document_type` **string** value.
  Pass `"contract"`, not the enum's repr.
- Pure filter — no I/O, no re-processing, no mutation of the input list.

---

## `clause_view()`

**Location:** [`src/pipeline.py`](../src/pipeline.py)

M5-shaped flattened view of one ingest result: clauses plus their identity, as a
plain dict. This is the shape `POST /clauses` serves over HTTP.

```python
def clause_view(result: DocumentIngestResult, **kwargs) -> dict
```

| Parameter | Type | Required | Default | Meaning |
|---|---|---|---|---|
| `result` | `DocumentIngestResult` | **yes** | — | From `process_document()`. |
| `**kwargs` | — | no | — | Passed straight through to `get_clause_chunks()`: `include_tables`, `document_types`. |

**Returns:** `dict` with keys:

| Key | Type | Meaning |
|---|---|---|
| `document_id` | `str` | |
| `source_file` | `str` | |
| `document_type` | `str` | |
| `language` | `str` | |
| `n_clauses` | `int` | |
| `clauses` | `list[dict]` | Each: `chunk_id`, `clause_id`, `article`, `clause`, `section`, `heading_path`, `page`, `language`, `is_table`, `text`. |

```python
from src.pipeline import process_document, clause_view

result = process_document("contract.pdf")
view   = clause_view(result, document_types=["contract"], include_tables=True)

for c in view["clauses"]:
    print(c["clause_id"], "|", c["article"], "|", c["text"][:60])

# Compare against the total to judge structure-detection health
print(view["n_clauses"], "of", result.n_chunks, "chunks carry clause identity")
```

**Behavioural notes**

- Returns a plain `dict`, not a Pydantic model — safe to `json.dumps()` directly.
- `clause_id`, `article`, `clause` and `heading_path` are read out of
  `metadata["structure"]` and are **`None` / `[]` when the document did not
  declare them**, even for a chunk that qualified as a clause on another field.
- `n_chunks_total` is **not** in this dict — it is added by the HTTP endpoint.
  In-process, compare `view["n_clauses"]` against `result.n_chunks` yourself.

---

# 3. API endpoints

**Location:** [`src/api.py`](../src/api.py). Run with:

```bash
uvicorn src.api:app --host 127.0.0.1 --port 8000
```

Interactive docs at `/docs`, OpenAPI JSON at `/openapi.json`.

> **Deployment note (from the module):** binds to `127.0.0.1` on purpose.
> **There is no authentication layer** because the service is not intended to be
> network-exposed. If it is ever put on the firm LAN, put it behind the firm's
> existing auth — do not add a second scheme here.

**Upload limits, shared by both POST endpoints:** max **200 MB**; extensions
accepted are `.pdf`, `.docx`, `.txt`, `.md`, `.png`, `.jpg`, `.jpeg`, `.tif`,
`.tiff`, `.bmp`, `.webp` (type detection re-checks by magic bytes anyway — the
extension check is a cheap early reject).

**Shared error responses:**

| Status | Meaning |
|---|---|
| `400` | Upload unreadable, or the file is empty. |
| `413` | File exceeds the 200 MB limit. |
| `415` | Unsupported file extension. |
| `422` | Document could not be processed — `detail` carries `{message, document_id, errors, warnings}`. Only raised when processing failed **and** produced zero chunks; a partial success returns `200` with `succeeded=false`. |

---

## `POST /ingest`

**The M1 → M2/M3 contract.** Process one document, return all its chunks.

**Request:** `multipart/form-data`

| Param | In | Type | Required | Default | Meaning |
|---|---|---|---|---|---|
| `file` | form | file | **yes** | — | PDF, DOCX, TXT, or image. |
| `document_id` | query | `str` | no | generated | Override the generated id (e.g. the firm DMS id). |
| `target_chunk_chars` | query | `int` (100–20000) | no | `1200` | Target chunk size. Tune against your embedding context window. |
| `max_chunk_chars` | query | `int` (200–40000) | no | `2000` | Hard cap; exceeding it forces an artificial split (`split_from_unit=true`). |
| `overlap_chars` | query | `int` (0–2000) | no | `150` | Overlap between size-split chunks. |
| `respect_structure` | query | `bool` | no | `true` | `false` = baseline paragraph chunking, for A/B tests. **Setting it false destroys clause identity** — `/clauses` will return nothing useful. |
| `keep_raw_text` | query | `bool` | no | `true` | Include `metadata.raw_text`. Roughly doubles response size. |
| `emit_display_form` | query | `bool` | no | `false` | Also emit `metadata.display_text` (reshaped/bidi presentation form). **For rendering only — never embed it.** |

**Response `200` — `IngestResponse`:**

`document_id`, `source_file` (basename only), `file_type`, `pdf_kind`,
`document_type`, `language`, `n_pages`, `n_chunks`, `succeeded`,
`chunks: list[DocumentChunk]`, plus the diagnostics `engine_log`, `rtl_flags`
(as dicts), `warnings`, `errors` (**truncated to the first 2**), `timings_ms`.

```bash
curl -F "file=@contract.pdf" http://127.0.0.1:8000/ingest

curl -F "file=@statute_ar.pdf" \
  "http://127.0.0.1:8000/ingest?document_id=DMS-2024-01173&target_chunk_chars=800&keep_raw_text=false"
```

```python
import requests

with open("contract.pdf", "rb") as fh:
    r = requests.post(
        "http://127.0.0.1:8000/ingest",
        files={"file": ("contract.pdf", fh)},
        params={"target_chunk_chars": 800, "keep_raw_text": False},
        timeout=600,           # scanned documents are slow — see note below
    )
r.raise_for_status()
payload = r.json()

if payload["rtl_flags"]:
    queue_for_human_review(payload["document_id"], payload["rtl_flags"])

for chunk in payload["chunks"]:
    index(chunk["text"], metadata=chunk["metadata"])
```

**Behavioural notes**

- **`succeeded: false` with a `200`** is possible: partial success (some chunks
  produced, something still went wrong). Check the field, not just the status.
- **`errors` is truncated to two entries** in the HTTP response. The full list is
  only available in-process via `process_document()`.
- **`rtl_flags` non-empty means "a human should look at these pages."** It does
  not mean the chunks are broken, and it does not mean they are fine.
- **Set a generous client timeout.** Scanned documents go through OCR at 300 dpi
  and can take minutes per document; there is no async job API.
- Uploaded files are written to a temp dir and deleted after the response is
  built, in a `finally` — nothing persists server-side.
- `warnings` is where quiet degradations surface (Docling unavailable, DOCX
  pagination synthesized, low-confidence OCR pages kept). **Log it.**

---

## `POST /clauses`

**The M1 → M5 contract.** Same pipeline as `/ingest`, then filtered to
clause-level chunks and flattened.

**Request:** `multipart/form-data`

| Param | In | Type | Required | Default | Meaning |
|---|---|---|---|---|---|
| `file` | form | file | **yes** | — | PDF, DOCX, TXT, or image. |
| `document_id` | query | `str` | no | generated | Override the generated id. |
| `include_tables` | query | `bool` | no | `true` | Keep table chunks that sit inside a clause. |
| `contracts_only` | query | `bool` | no | `false` | Restrict to documents classified as contracts. |

> Note: this endpoint exposes **no chunking overrides** — it always runs the
> process-wide config. If you need custom chunk sizing for M5, call
> `process_document()` + `clause_view()` in-process.

**Response `200` — `ClauseResponse`:**

| Field | Type | Meaning |
|---|---|---|
| `document_id` | `str` | |
| `source_file` | `str` | Basename only. |
| `document_type` | `str` | |
| `language` | `str` | |
| `n_clauses` | `int` | Clauses returned. |
| `n_chunks_total` | `int` | Total chunks in the document. **A large gap means structure detection found little — check that document.** |
| `clauses` | `list[ClauseItem]` | `chunk_id`, `clause_id`, `article`, `clause`, `section`, `heading_path`, `page`, `language`, `is_table`, `text`. |
| `warnings` | `list[str]` | |

```bash
curl -F "file=@contract.pdf" "http://127.0.0.1:8000/clauses?contracts_only=true"
```

```python
import requests

with open("contract.pdf", "rb") as fh:
    r = requests.post(
        "http://127.0.0.1:8000/clauses",
        files={"file": ("contract.pdf", fh)},
        params={"contracts_only": True, "include_tables": True},
        timeout=600,
    )
data = r.json()

if data["n_chunks_total"] and data["n_clauses"] < 0.1 * data["n_chunks_total"]:
    log.warning("structure detection weak: %d clauses / %d chunks",
                data["n_clauses"], data["n_chunks_total"])

for cl in data["clauses"]:
    m5_store.add(cl["clause_id"], cl["article"], cl["heading_path"], cl["text"])
```

**Behavioural notes**

- **Documents that fell back to paragraph chunking return `clauses: []`** with a
  large `n_chunks_total`. That is the documented signal, not an error — expect a
  `200`.
- `contracts_only=true` filters on the *document*'s inferred type. A misclassified
  contract (`document_type: "unknown"`) will silently return zero clauses — if you
  get an unexpected empty list, retry with `contracts_only=false` and check
  `document_type` in the response.
- Clause text is the same normalized `text` as the matching `DocumentChunk`.

---

## `GET /health`

Liveness plus which optional engines are actually usable in this install.

**Request:** no parameters.

**Response `200`:**

```json
{
  "status": "ok",
  "version": "0.1.0",
  "engines": {
    "pymupdf": true, "docling": true, "paddleocr": true, "tesseract": true,
    "pyarabic": true, "arabic_reshaper": true, "python_bidi": true
  },
  "missing_required": [],
  "note": "degraded means the pipeline still runs but falls back; see README"
}
```

```bash
curl http://127.0.0.1:8000/health
```

**Behavioural notes**

- `status` is `"ok"` only when all four of `pymupdf`, `docling`, `paddleocr`,
  `tesseract` are present; otherwise `"degraded"` with the gaps in
  `missing_required`.
- **`"degraded"` still returns `200`** and the pipeline still runs — it falls
  back quietly. **This is the only place a missing engine shows up before it
  silently costs you accuracy.** Worth checking after every deployment.

---

## `GET /config`

The active pipeline configuration, as a nested dict (`PipelineConfig.model_dump()`).

**Request:** no parameters. **Response `200`:** the full config tree —
`extraction`, `ocr`, `rtl`, `normalization`, `chunking`, plus
`default_jurisdiction`, `keep_raw_text_in_metadata`, `log_level`, `fail_fast`.

```bash
curl http://127.0.0.1:8000/config
```

**Behavioural note — this matters more than it looks.** Record this alongside
every batch you ingest. **Chunks produced under different normalization or
chunking settings are not comparable**, and there is nothing on an individual
chunk that tells you which settings produced it.

---

# 4. Supporting types

Types you may need to *read* off `metadata`, or *construct* to configure a run.
All in [`src/document_chunk_schema.py`](../src/document_chunk_schema.py) unless
noted.

## `PipelineConfig`

**Location:** [`src/config.py`](../src/config.py)

Top-level configuration threaded through the whole pipeline. Consumers construct
it to override defaults; every field has a documented rationale in the module.

| Field | Type | Default |
|---|---|---|
| `extraction` | `ExtractionConfig` | defaults |
| `ocr` | `OCRConfig` | defaults (`enabled=True`, `render_dpi=300`, `tesseract_lang="ara+eng"`) |
| `rtl` | `RTLConfig` | defaults (`repair_visual_order=True`, `emit_display_form=False`) |
| `normalization` | `NormalizationConfig` | defaults |
| `chunking` | `ChunkingConfig` | `target_chunk_chars=1200`, `max_chunk_chars=2000`, `min_chunk_chars=120`, `overlap_chars=150`, `respect_structure=True`, `keep_tables_whole=True` |
| `default_jurisdiction` | `str \| None` | `"Egypt"` — a practice-area default, **not** anything observed in a real firm document |
| `keep_raw_text_in_metadata` | `bool` | `True` |
| `log_level` | `str` | `"INFO"` |
| `fail_fast` | `bool` | `False` — when `False`, a document that errors is recorded as a failure and the batch continues |

Two alternate constructors:

```python
from src.config import PipelineConfig

cfg = PipelineConfig()                       # defaults
cfg.chunking.target_chunk_chars = 800

cfg = PipelineConfig.from_env()              # M1_CHUNKING__TARGET_CHUNK_CHARS=800
cfg = PipelineConfig.from_json("m1.json")
```

`from_env(prefix="M1_")` reads `M1_`-prefixed env vars; nested fields use a
double underscore (`M1_OCR__MIN_MEAN_CONFIDENCE=0.6`).

## `StructuralRef`

Read off `chunk.metadata["structure"]`, or typed via `chunk.structure`.
`extra="allow"`.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `book` | `str \| None` | `None` | الباب |
| `chapter` | `str \| None` | `None` | الفصل |
| `section` | `str \| None` | `None` | القسم / heading |
| `article` | `str \| None` | `None` | المادة — e.g. `"المادة 12"` / `"Article 12"` |
| `clause` | `str \| None` | `None` | البند — e.g. `"12.3"` / `"(أ)"` |
| `clause_id` | `str \| None` | `None` | Normalized, stable id, e.g. `"art_12.cl_3"` |
| `title` | `str \| None` | `None` | Heading text of the deepest open unit, **without** its identifier — `"Termination"` for `"Article 12. Termination"` |
| `heading_path` | `list[str]` | `[]` | Ordered heading ancestry, outermost first. Lets M5 reconstruct a contract's clause tree without re-parsing. |
| `heading_level` | `int \| None` | `None` | |
| `marker_language` | `"ar"` \| `"en"` \| `None` | `None` | Which language the structural marker was written in — bilingual contracts often number clauses in only one of the two. |
| `marker_fuzzy` | `bool` | `False` | `True` when the marker was recovered by OCR-tolerant matching rather than an exact one. **The chunk is still usable**; it is flagged so a rising share of fuzzy markers is visible as an OCR-quality signal rather than silently absorbed. |
| `marker_confidence` | `float` | `1.0` | `1.0` for an exact match, lower the further the text was from canonical form. |
| `marker_evidence` | `str \| None` | `None` | What the tolerant matcher had to do, for spot-checking. `None` for exact matches. |

Statutes typically fill `book`/`chapter`/`article`; contracts typically fill
`section`/`clause`.

## `BoundingBox`

Read off `metadata["bbox"]` / `metadata["bboxes"]`. Axis-aligned, in **PDF
points, origin top-left**, as PyMuPDF reports it. `extra="forbid"`.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `x0`, `y0`, `x1`, `y1` | `float` | required | Corners; automatically reordered so `x0 ≤ x1`, `y0 ≤ y1`. |
| `page` | `int \| None` | `None` | |
| `scale` | `float \| None` | `None` | Points-per-pixel; **set only when the box came from a rasterized OCR page.** For OCR pages the box is in the *rasterized* page's coordinate space — multiply by `scale` to map back to original page geometry. |

Also exposes `.width` / `.height` properties.

## `OCRConfidence`

Read off `metadata["ocr_confidence"]`. **Absent entirely for text-layer
extraction.** `extra="allow"`.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `engine` | `str` | required | Which OCR engine produced it. |
| `mean` | `float \| None` (0.0–1.0) | `None` | Mean box confidence. |
| `min` | `float \| None` (0.0–1.0) | `None` | Worst box. |
| `n_boxes` | `int \| None` | `None` | |
| `low_confidence_boxes` | `int \| None` | `None` | Boxes below `OCRConfig.drop_below_confidence` (default `0.30`). |
| `fallback_used` | `bool` | `False` | A second engine was tried. |
| `fallback_reason` | `str \| None` | `None` | Why. |

## `RTLFlag`

Read off `metadata["rtl_flags"]` (per chunk) and `result.rtl_flags` (per
document). A **surfaced, not silently fixed** reading-order concern.
`extra="allow"`.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `kind` | enum `str` | required | One of `mixed_direction`, `visual_order_suspected`, `visual_order_repaired`, `presentation_forms_found`, `numeral_direction_ambiguous`, `high_switch_count`, `neutral_order_mirrored`, `brackets_unmirrored`, `digit_order_suspect`. |
| `page` | `int \| None` | `None` | |
| `detail` | `str` | `""` | |
| `severity` | `"info"` \| `"warn"` | `"warn"` | |
| `sample` | `str \| None` | `None` | Short excerpt for eyeballing. |

## Enums

All are `str` subclasses, so they compare equal to their string values.

| Enum | Values |
|---|---|
| `Language` | `ar`, `en`, `ar-en`, `unknown` |
| `DocumentType` | `contract`, `law`, `court_ruling`, `pleading`, `power_of_attorney`, `correspondence`, `unknown` |
| `BlockType` | `paragraph`, `heading`, `table`, `list`, `signature`, `stamp`, `header_footer`, `unknown` |
| `SourceEngine` | `pymupdf`, `docling`, `pymupdf+docling`, `paddleocr`, `tesseract`, `python-docx`, `plaintext`, `unknown` |

## Id helpers

```python
def make_document_id(source: str | bytes, seq: int | None = None) -> str
def make_chunk_id(index: int) -> str
```

`make_document_id("...")` hashes the content → `doc_<sha1[:12]>`, stable across
runs and machines. `make_document_id("", seq=1)` gives the spec's literal
`doc_001` form for ordered batches. `make_chunk_id(17)` → `"chunk_017"`.

Both are called for you by the pipeline. You only need them to **reconstruct or
predict an id** — e.g. to check whether a document is already indexed before
re-ingesting.

---

# 5. Reliability notes every consumer should read

**1. Embed `text`, never `display_text`.** `arabic-reshaper` + `python-bidi`
produce *presentation forms* (U+FB50–U+FEFF) in visual order. Those are different
codepoints from base letters; feeding them to a tokenizer or embedding model
wrecks retrieval **silently**. `text` is always logical order with base letters.
`display_text` is off by default and exists only for rendering.

**2. Text-layer accuracy and OCR accuracy differ by two orders of magnitude —
check `metadata.source_engine` before deciding how much to trust a chunk.**

| Path | Arabic CER | English CER | Source |
|---|---|---|---|
| Native / text-layer (PyMuPDF; `source_engine` = `pymupdf` or `pymupdf+docling`) | **0.0016** | **0.011** | [`reports/native_extraction_accuracy.md`](../reports/native_extraction_accuracy.md) |
| OCR, verified references (Tesseract, the shipped Arabic primary) | **0.130** | 0.021 | [`reports/ocr_engine_comparison.md`](../reports/ocr_engine_comparison.md) |
| OCR, verified references (PaddleOCR, the fallback) | 0.399 | **0.003** | same |

Practical reading: **digitally-produced PDFs are essentially exact and can be
trusted verbatim; scanned Arabic carries roughly one error character in eight and
should not be quoted to a client without a human check.** Tesseract is the Arabic
primary on that evidence; PaddleOCR is better on English and is the fallback.
These figures are measured on published Egyptian legal documents and synthetic
fixtures — **no client document has been processed** — see the README's
*Known limitations*.

**3. A non-empty `rtl_flags` means "a human should look at this page."** It does
not mean the chunk is broken, and it does not mean it is fine. The design choice
is deliberate: repair what is provably wrong, **flag** what is ambiguous, never
quietly rewrite mixed Arabic/English/numeral content.

**4. `chunk_strategy` and `split_from_unit` tell you how much to trust a
boundary.** `structural` boundaries are declared by the document itself.
`paragraph` means no structure was detected at all. `split_from_unit=true` means
a long clause was cut artificially — the chunk may begin or end mid-clause, which
matters if you are citing it.

**5. `n_clauses` vs total chunk count is M5's health signal.** A document with
200 chunks and 3 clauses did not have its structure detected. Check it before
relying on it.

**6. Record `/config` (or your `PipelineConfig`) alongside every batch.** Chunks
produced under different normalization or chunking settings are not comparable,
and nothing on an individual chunk records which settings produced it.

**7. Word-level visual reversal is a known, unrepaired limitation.** A producer
that reverses each line's *words* while leaving each word's characters in logical
order gives the geometry-based repair nothing to work with. Documented as README
limitation #9. Affected documents will read as scrambled at the word level.

**8. Check `/health` after deployment.** The pipeline degrades quietly when
Docling or an OCR engine is missing — `status: "degraded"` still returns `200`
and still processes documents, just worse.

---

## Related reading

- [`README.md`](../README.md) — pipeline overview, setup, configuration, design
  decisions, known limitations
- [`src/document_chunk_schema.py`](../src/document_chunk_schema.py) — the contract, in code
- [`src/config.py`](../src/config.py) — every behavioural knob, with rationale
- [`reports/evaluation_report.md`](../reports/evaluation_report.md) — measured results against all spec criteria
- [`reports/native_extraction_accuracy.md`](../reports/native_extraction_accuracy.md) — non-OCR path accuracy by extractor × language
- [`reports/ocr_engine_comparison.md`](../reports/ocr_engine_comparison.md) — PaddleOCR vs Tesseract, and the engine decision
