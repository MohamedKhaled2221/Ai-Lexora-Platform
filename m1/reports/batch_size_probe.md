# Batch size: what it controls here, and what it costs

> ## The short version, for anyone who just needs the number
>
> **`max_batch_documents = 50`**, in `src/config.py`.
>
> **There was no batch size setting before this.** Not a stale default, not a
> guessed one — the concept was absent from the config entirely.
>
> **It is not a GPU batch, not a concurrency level, and not an OCR parameter.**
> Nothing in this pipeline processes two documents, two pages, or two models at
> once. Batch size controls **how many results accumulate in memory before
> `ingest_batch` returns**, and therefore **how much work is lost if the run
> dies partway**. Changing it cannot make OCR faster or exhaust VRAM.
>
> **RAM turned out not to be the constraint.** Accumulation costs 54 KB/page and
> peak memory is set by the largest *single* document, not by how many there are
> — measured peak RSS was *higher* at batch 5 than at batch 25. The value is
> chosen for work-at-risk, and that is stated plainly below rather than dressed
> up as a memory limit.

Generated: 2026-08-17
Harness: [`scripts/batch_size_probe.py`](../scripts/batch_size_probe.py) ·
data: `reports/batch_size_probe.json`, `reports/batch_size_probe_fast.json`
Hardware: RTX 4060 (8 GB, shared with the LLM work packages), 15.7 GB RAM,
16 CPUs, Windows. **2.3–4.0 GB RAM actually free** during these runs — this box
is shared, and that is the number that matters, not the 15.7 GB total.

---

## What exists in the code, and what does not

| Question | Answer |
|---|---|
| Any `batch`/`batch_size` config field before this task? | **None**, anywhere in the repo |
| Any batching logic in chunking? | **None** — `chunk_document` is strictly per document |
| Any batching logic in OCR? | **None** — [`ocr_pdf_pages`](../src/ocr_pipeline.py) loops pages one at a time, rendering and discarding each raster before the next |
| The only batch construct | [`ingest_batch`](../src/pipeline.py) — a sequential `for` loop that appends every `DocumentIngestResult` to one list and returns at the end |

So "batch size" can only mean one thing here: **the length of the list handed to
`ingest_batch`**. That is what was measured.

### Why VRAM is not part of this answer

Not an assumption — three independent facts:

* **Tesseract, the primary engine, is CPU-only.** `reports/ocr_engine_comparison.md`
  measures it at 0 MB VRAM.
* **PaddleOCR-VL is not wired into the pipeline.** `src/paddleocr_vl.py` says so
  in its first line and nothing imports it outside the benchmark harness. When it
  *was* benchmarked it reserved 7943 MB — the whole card — for **one page at a
  time** (`reports/paddleocr_vl_benchmark.md`), which is why it cannot coexist
  with Qwen3-8B and why adopting it would be a sequencing question, never a
  batch-size one.
* **The probe sampled VRAM anyway** and recorded 0 MB across the mixed-corpus
  sweep. Later readings of 148–2200 MB in the second sweep are **another
  application on the shared GPU, not this pipeline** — `vram_used_mb_at_start`
  was already 101 MB before the run began, and this venv's torch is a CPU build
  (`cuda.is_available() == False`). Reported rather than quietly dropped, and
  explicitly not attributed to M1.

**If a page batch is ever fed to a GPU engine simultaneously, none of this
transfers and the question must be re-measured.** Today no such code path exists.

---

## How it was measured

Each batch size runs in a **fresh subprocess**, so peaks cannot leak between
sizes. The document list is a fixed pool cycled to length, so batch size is the
only variable.

**Peak RSS is sampled from the parent process, over the whole process tree.**
Both halves of that were learned the hard way and both change the numbers:

* An in-process sampler thread **under-reported peak RSS by ~5x** (271 MB where
  the same run externally showed ~1400 MB). Docling and Tesseract hold the GIL
  inside native calls, so the sampler was starved during precisely the
  allocation peak it existed to catch — it landed 1538 of an expected 2156
  samples, and every missing one was in the expensive window.
* **Tesseract and the PaddleOCR worker are separate processes.** `paddle_worker`
  is persistent for the whole run. Their memory is not in the parent's RSS at
  all, so a parent-only reading misses it.

The first sweep of this probe was discarded and re-run after that was fixed.

Two corpora, because they answer different halves:

* **Mixed pool** — text-layer and scanned, Arabic and English, 1–94 pages.
  Answers "what does a realistic batch peak at?"
* **Fast pool** — text-layer only. The mixed pool's wall clock is dominated by
  OCR, which buries the retention slope under the ~1 GB allocator/import floor
  every run reaches within its first few documents. Cheap documents make the
  cost of *accumulating results* visible.

---

## Results

### Mixed corpus (text + OCR)

| Batch | Docs | Pages | Chunks | Chunk payload | Wall (s) | Peak RSS | Failures |
|---|---|---|---|---|---|---|---|
| 1 | 1 | 12 | 24 | 1.46 MB | 519.7 | 2032 MB | 0 |
| 5 | 5 | 92 | 455 | 9.9 MB | 625.3 | **3043 MB** | 0 |
| 10 | 10 | 246 | 1102 | 14.2 MB | 666.0 | 2951 MB | 0 |
| 25 | 25 | 584 | 2659 | 38.2 MB | 2322.8 | 2135 MB | 0 |

### Text-layer corpus (isolates the retention slope)

| Batch | Docs | Pages | Chunks | Live results held | MB/page | Wall (s) | s/doc | Peak RSS | Failures |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 1 | 2 | 9 | 0.01 MB | 0.005 | 42.4 | 42.4 | 1006 MB | 0 |
| 10 | 10 | 122 | 425 | 6.59 MB | **0.054** | 225.2 | 22.5 | 1360 MB | 0 |
| 25 | 25 | 252 | 901 | 13.28 MB | **0.053** | 348.3 | 13.9 | 1567 MB | 0 |
| 50 | 50 | 610 | 2125 | 32.96 MB | **0.054** | 638.5 | 12.8 | 1663 MB | 0 |

"Live results held" is the serialized size of everything the batch is still
holding. RSS cannot answer "what does one more document cost to keep?", because
the allocator floor swamps it and is then *reused* rather than grown.

**Zero failures at every size on both corpora. No resource exhaustion, no
slowdown, no degradation of any kind.**

---

## What the numbers say

**1. Accumulation is cheap and exactly linear: 54 KB per page.** 0.054, 0.053,
0.054 MB/page at 10, 25 and 50 documents. Fifty documents hold 33 MB.

**2. Peak RSS does not track batch size.** 2032 → 3043 → 2951 → 2135 MB for
batches of 1, 5, 10, 25. Batch 25 peaked *lower* than batch 5 while processing
6x the pages. Peak is set by the **largest single document's working set** —
Docling's layout models plus the page raster — which is paid identically whether
the batch holds one document or fifty. Per-document "retained" RSS *falls* with
batch size (235 → 113 → 42 MB/doc) for the same reason: it is the fixed import
and allocator floor being divided by more documents.

**3. Wall clock scales linearly, and per-document actually improves** — 42.4 s
for one document, 12.8 s/doc at fifty, as the one-time model load amortizes.
Nothing degrades. (The mixed pool's per-document times swing because its first
document is `wipo_eg087ar_1.pdf`, the corpus's known handwritten outlier: text
layer quality 0.33 sends it to OCR, where it fails the confidence gate on every
page and runs *both* engines — the documented 38–46 s/page path. At 519 s it
dominates any batch it appears in, and batch 25 cycles the pool 2.5x so it
appears three times. That is content, not batch size.)

**4. RAM therefore does not bind the batch size**, and saying otherwise would be
inventing a constraint. Retention would only reach a conservative
10%-of-free-RAM line (~230 MB against the 2.3 GB measured free) at roughly
**4,300 pages ≈ 190 documents**.

---

## Recommendation: 50

**Chosen for work-at-risk, not for memory**, because memory does not bind.

`ingest_batch` returns only at the end, so anything that kills the run discards
the whole batch. Fifty documents is ~11 minutes of text-layer material, or ~75
minutes at the corpus's worst-case OCR mix (93 s/doc measured at batch 25) — a
tolerable amount to redo, and a natural checkpoint granularity.

Against every measured ceiling it is conservative:

| Against | At batch 50 | Headroom |
|---|---|---|
| Results held vs. minimum free RAM (2.29 GB) | 33 MB | **98.6%** |
| Results held vs. a 10%-of-free-RAM line (230 MB) | 33 MB | **~4x margin** (line is ~190 docs) |
| Peak RSS | 1663 MB measured; ~3.0 GB worst case | batch-size-independent — same at batch 1 |
| Failures observed, sizes 1–50 | 0 | — |

**Set it in `src/config.py` as `PipelineConfig.max_batch_documents`**, with the
reasoning in the docstring so the next reader does not meet a bare `50`.

### Two honest caveats

**It is advisory — no code enforces it.** `ingest_batch` accepts any list
length. Capping inside it would change that function's return contract, which is
outside this task's scope. Callers chunking a large corpus should read the value;
`GET /config` already exposes it, since the endpoint dumps the whole model.

**A long batch amplifies one existing hazard, which this value does not fix.**
[`_docling_convert`](../src/extract_pymupdf_docling.py) abandons its conversion
thread on timeout, and *the thread keeps running* — Docling exposes no
cancellation. Across a batch those abandoned threads accumulate and compete for
CPU and RAM. It did not produce a failure at any size tested, and it is a
property of the timeout design rather than of batch size, but it is the one
mechanism by which a longer batch is genuinely not equivalent to several short
ones. Worth a look if long batches ever behave worse than the arithmetic predicts.

### Re-running this

```bash
python scripts/batch_size_probe.py                 # mixed pool: 1, 5, 10, 25
python scripts/batch_size_probe.py --fast --sizes 1 10 25 50   # retention slope
```

Both re-run unchanged against `test_corpus/real` once firm documents arrive.
**Do that before trusting these numbers on the firm's own hardware** — free RAM
on this box was 2.3–4.0 GB with other work packages loaded, and that figure, not
the 15.7 GB installed, is what any future value has to respect.
