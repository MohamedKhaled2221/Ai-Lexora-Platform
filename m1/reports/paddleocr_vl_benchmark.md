# PaddleOCR-VL vs the Tesseract baseline

> ## A different model from the PaddleOCR this repo already rejected
>
> `reports/ocr_engine_comparison.md` rejected **classical PaddleOCR** -- a detector plus a CRNN-style recogniser, which on this Windows/CPU build could not process a page above ~1600-2500 px without a native crash. **PaddleOCR-VL is a different model**: a NaViT-style visual encoder feeding an ERNIE-4.5-0.3B decoder (~0.9B parameters total) that *generates* each layout block's text. Different weights, different inference code, different failure modes. It was evaluated from scratch, and its resolution behaviour was measured rather than inherited from either engine.
>
> ## Measured on public and synthetic scans, by design
>
> Every figure here comes from **published Egyptian legal PDFs rasterized into scans** plus **authored fixtures** whose reference text was written before the page was rendered. No firm document has been processed. Absolute error rates are therefore an optimistic bound -- rendered pages have clean glyph shapes, no scanner optics, no photocopy generations, no bleed-through. **The ranking below should be re-confirmed once real firm scans are available**; that is the open item this report cannot close, and it is the one caveat that could move the ordering, because two engines need not degrade at the same rate.

Generated: 2026-08-16 02:38:57  
Fixtures: 14 documents with **verified** ground truth (8 Arabic, 6 English)  
Engines: Tesseract @ 150 dpi (baseline) vs PaddleOCR-VL v1.6 @ 150 dpi  
PaddleOCR-VL device: gpu:0 (paddlepaddle-gpu 3.2.2, separate venv) | Tesseract device: CPU (the pipeline's own pinned environment)  
Wall clock: 68.3 min across all stages

## What was installed, and is it actually local?

The brief flagged that some "PaddleOCR"-named tools ship as wrappers around a hosted demo endpoint. This one does not, and the check is specific rather than assumed:

- **Package:** `paddleocr==3.7.0` -- already pinned in `requirements.txt` for the classical engine -- exposes `PaddleOCRVL` directly. Pipeline version **v1.6**, checkpoint **PaddleOCR-VL-1.6-0.9B** (~1.8 GB, `model.safetensors`), plus `PP-DocLayoutV3` for layout detection.
- **Backend:** `vl_rec_backend="native"` -- in-process PaddlePaddle inference. The other five backends the package supports (`vllm-server`, `sglang-server`, `fastdeploy-server`, `mlx-vlm-server`, `llama-cpp-server`) all speak HTTP to a model server and are never selected; `vl_rec_server_url` and `vl_rec_api_key` are never set. **There is no hosted-endpoint code path in the adapter.**
- **Offline confirmed by running that way.** After the one-time weight download, the whole benchmark ran with `HF_HUB_OFFLINE=1` and `PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True`. Weights load from `~/.paddlex/official_models/PaddleOCR-VL-1.6`. The only outbound request in the entire path is PaddleX's connectivity probe of its four model hosters, which happens *before* the cached-directory check and is disabled by the environment variable the adapter sets itself.

Weights were fetched from Hugging Face (`PaddlePaddle/PaddleOCR-VL-1.6`). On a firm network with no internet access, that directory is the only thing that needs copying in.

## Verdict

- **Arabic: PaddleOCR-VL wins.** PaddleOCR-VL CER 0.081 vs Tesseract 0.095 -- 15% better. _8 documents, 32 pages._
- **English: PaddleOCR-VL wins.** PaddleOCR-VL CER 0.006 vs Tesseract 0.013 -- 57% better. _6 documents, 20 pages._

- **Speed:** PaddleOCR-VL 34.5 s/page (Arabic) vs Tesseract 3.1 s/page -- **11x slower, and that is PaddleOCR-VL on a GPU against Tesseract on CPU.**
- **PaddleOCR-VL failures: 0 crashes, 0 soft errors over 52 pages.**

**It reads better and it is stable -- and the recommendation is still not to adopt it as primary yet.** The accuracy win is small on Arabic and reverses on the documents Tesseract already reads well; the cost is an order of magnitude, on hardware the LLM also wants. See [Recommendation](#recommendation).

## Results

| Engine | Language | CER | CER (no-space) | WER | s/page | VRAM / CPU | Crashed / failed? |
|---|---|---|---|---|---|---|---|
| tesseract @ 150 dpi | ar | 0.095 | **0.095** | 0.223 | 3.1 | CPU only, 390 MB RSS, 0 MB VRAM | no |
| tesseract @ 150 dpi | en | 0.013 | **0.013** | 0.022 | 3.1 | CPU only, 394 MB RSS, 0 MB VRAM | no |
| paddleocr-vl @ 150 dpi | ar | 0.078 | **0.081** | 0.250 | 34.5 | 7943 MB VRAM reserved (6069 MB allocated), 4615 MB RSS | no |
| paddleocr-vl @ 150 dpi | en | 0.005 | **0.006** | 0.003 | 24.1 | 7943 MB VRAM reserved (6069 MB allocated), 4615 MB RSS | no |

`no-space` strips whitespace before comparing, isolating glyph recognition; it is the figure the prior reports quote. Scores are the mean of per-document CER, not a pooled score -- the same aggregation that produced 0.130, 0.095 and 0.013, so the numbers are directly comparable.

### Against the quoted baseline

| Language | Quoted Tesseract @150 dpi | Re-measured here | PaddleOCR-VL | Change vs re-measured |
|---|---|---|---|---|
| ar | 0.095 | 0.095 | 0.081 | 15% better |
| en | 0.013 | 0.013 | 0.006 | 57% better |

## Per document

| Document | Lang | Engine | CER | CER (no-space) | WER | Bag | s/page | Crashed? |
|---|---|---|---|---|---|---|---|---|
| `bench_eg_official_gazette_excerpt_clean.pdf` | en | tesseract | 0.000 | 0.000 | 0.000 | 0.000 | 3.8 | no |
| `bench_eg_official_gazette_excerpt_clean.pdf` | en | paddleocr-vl | 0.010 | 0.011 | 0.005 | 0.005 | 28.4 | no |
| `bench_eg_official_gazette_excerpt_poor.pdf` | en | tesseract | 0.014 | 0.014 | 0.016 | 0.004 | 3.5 | no |
| `bench_eg_official_gazette_excerpt_poor.pdf` | en | paddleocr-vl | 0.012 | 0.013 | 0.007 | 0.005 | 27.1 | no |
| `bench_wipo_eg081ar_1_clean.pdf` | ar | tesseract | 0.126 | 0.133 | 0.292 | 0.282 | 3.1 | no |
| `bench_wipo_eg081ar_1_clean.pdf` | ar | paddleocr-vl | 0.076 | 0.085 | 0.256 | 0.245 | 36.4 | no |
| `bench_wipo_eg081ar_1_poor.pdf` | ar | tesseract | 0.154 | 0.160 | 0.312 | 0.303 | 2.7 | no |
| `bench_wipo_eg081ar_1_poor.pdf` | ar | paddleocr-vl | 0.083 | 0.093 | 0.255 | 0.246 | 37.3 | no |
| `bench_wipo_eg088ar_1_clean.pdf` | ar | tesseract | 0.049 | 0.040 | 0.208 | 0.199 | 3.7 | no |
| `bench_wipo_eg088ar_1_clean.pdf` | ar | paddleocr-vl | 0.078 | 0.071 | 0.302 | 0.286 | 46.2 | no |
| `bench_wipo_eg088ar_1_poor.pdf` | ar | tesseract | 0.063 | 0.054 | 0.225 | 0.212 | 3.6 | no |
| `bench_wipo_eg088ar_1_poor.pdf` | ar | paddleocr-vl | 0.094 | 0.087 | 0.336 | 0.292 | 37.3 | no |
| `scan_authored_award_en_150dpi.pdf` | en | tesseract | 0.013 | 0.013 | 0.042 | 0.034 | 2.0 | no |
| `scan_authored_award_en_150dpi.pdf` | en | paddleocr-vl | 0.000 | 0.000 | 0.000 | 0.000 | 12.9 | no |
| `scan_authored_award_en_300dpi.pdf` | en | tesseract | 0.009 | 0.009 | 0.021 | 0.021 | 2.0 | no |
| `scan_authored_award_en_300dpi.pdf` | en | paddleocr-vl | 0.000 | 0.000 | 0.000 | 0.000 | 14.9 | no |
| `scan_authored_statute_ar_150dpi.pdf` | ar | tesseract | 0.117 | 0.120 | 0.154 | 0.116 | 1.7 | no |
| `scan_authored_statute_ar_150dpi.pdf` | ar | paddleocr-vl | 0.090 | 0.096 | 0.197 | 0.116 | 14.3 | no |
| `scan_authored_statute_ar_300dpi.pdf` | ar | tesseract | 0.014 | 0.015 | 0.035 | 0.035 | 1.9 | no |
| `scan_authored_statute_ar_300dpi.pdf` | ar | paddleocr-vl | 0.009 | 0.011 | 0.039 | 0.039 | 18.3 | no |
| `scan_eg_constitution_2014_en_150dpi.pdf` | en | tesseract | 0.044 | 0.043 | 0.053 | 0.045 | 2.9 | no |
| `scan_eg_constitution_2014_en_150dpi.pdf` | en | paddleocr-vl | 0.000 | 0.000 | 0.002 | 0.002 | 26.7 | no |
| `scan_eg_official_gazette_excerpt_300dpi.pdf` | en | tesseract | 0.000 | 0.000 | 0.000 | 0.000 | 3.1 | no |
| `scan_eg_official_gazette_excerpt_300dpi.pdf` | en | paddleocr-vl | 0.010 | 0.011 | 0.005 | 0.005 | 24.4 | no |
| `scan_wipo_eg081ar_1_300dpi.pdf` | ar | tesseract | 0.107 | 0.117 | 0.291 | 0.284 | 3.3 | no |
| `scan_wipo_eg081ar_1_300dpi.pdf` | ar | paddleocr-vl | 0.091 | 0.102 | 0.290 | 0.272 | 34.6 | no |
| `scan_wipo_eg088ar_1_150dpi.pdf` | ar | tesseract | 0.128 | 0.121 | 0.266 | 0.239 | 3.7 | no |
| `scan_wipo_eg088ar_1_150dpi.pdf` | ar | paddleocr-vl | 0.105 | 0.103 | 0.325 | 0.290 | 39.6 | no |

## Resolution: measured for this engine, not inherited

`OCRConfig.render_dpi` is one global setting shared by every engine. 150 dpi is **Tesseract's** optimum on this corpus, and there is no reason a vision-language model that resizes pages to its own pixel budget should share it. So the ladder was measured directly, on the Arabic subset.

| Render DPI | Long side (A4) | Arabic CER (no-space) | s/page | Failures |
|---|---|---|---|---|
| 100 | ~1169 px | 0.103 | 24.8 | 0 |
| 150 | ~1754 px | 0.083 | 30.8 | 0 |
| 200 | ~2338 px | 0.086 | 55.8 | 0 |
| 300 | ~3507 px | 0.082 | 127.5 | 0 |

## Table extraction on image-only pages

PaddleOCR-VL emits tables as HTML directly from the model. The shipped route does not: it reconstructs a grid from OCR word geometry (`ocr_pipeline.tables_from_atoms`). Both are measured here on the same images, scored on **shape** against the fixtures' declared shape -- these fixtures have no cell-level ground truth, and inventing one here would not be comparable with anything.

| Fixture | Expected shape | PaddleOCR-VL | Tesseract + geometry | classical PaddleOCR + geometry | VL s/page |
|---|---|---|---|---|---|
| `stress_table_ruled_ar.png` | [5, 3] | 1 table (5x3) | 1 table (5x3) | 1 table (5x3) | 48.8 |
| `stress_table_sparse_bilingual.png` | [5, 4] | 1 table (5x4) | 1 table (6x4) | 1 table (5x4) | 27.14 |
| `stress_table_wide_en.png` | [6, 6] | 1 table (6x6) | 1 table (6x6) | 1 table (6x6) | 55.69 |
| `synthetic_table_page.png` | None | 1 table (6x5) | 1 table (6x5) | 1 table (6x5) | 41.41 |

**Every table was found by every engine.** The brief recorded the classical pipeline scoring *zero* tables on an image-based table page; that is not reproducible on the current code. Re-measured here, Tesseract + geometry and classical PaddleOCR + geometry each find 1/1 on all four fixtures, which also matches `reports/evaluation_report.md` (table extraction 1.000, 7 documents). Whatever produced the zero predates the geometric reconstructor in `ocr_pipeline.tables_from_atoms`.

So this is **not** a capability gap PaddleOCR-VL fills. What it does add is quality of structure: it matched the declared shape exactly on all three fixtures that declare one, where the geometric reconstructor put the sparse bilingual table at 6x4 instead of 5x4 -- the empty-cell case those fixtures exist to probe. And it returns the table as HTML from the model rather than as a grid inferred from word positions, which is a more robust representation to hand to M5.

The first row's timing includes model load; the others are steady-state.

## Reliability

**0 failures in 88 PaddleOCR-VL page reads** -- 52 in the benchmark, 32 in the resolution ladder, 4 table images. No crash, no worker death, no empty page, no downscale needed at any rung of the ladder including 300 dpi (~3500 px on the long side).

That is the specific thing classical PaddleOCR could not do: it failed on **8 of 8** pages probed at full resolution and needed a downscale on 91 of 92 pages, with failures arriving as `RuntimeError: Unknown exception` from native code or an outright worker death. **The resolution ceiling that disqualified the classical engine is not present in this one.**

## Hardware

| Measure | PaddleOCR-VL |
|---|---|
| VRAM, process reserved (nvidia-smi peak) | **7943 MB** |
| VRAM, model + activations high-water (Paddle allocator) | 6069 MB |
| VRAM, steady state after a page | 2945 MB |
| Host RSS | 4615 MB |
| CPU-only speed, same page, same raster | **344.0 s/page** |
| GPU speed (RTX 4060, 8 GB) | 34.5 s/page Arabic, 24.1 s/page English |

**CPU is not a viable fallback for this model.** The same page that takes 34.5 s on the 4060 takes 344.0 s on the CPU build -- about a hundred times Tesseract's 3.1 s. A 0.9B decoder generating every character of the page is simply not a CPU workload, so the hoped-for "small model, run it on CPU, no GPU contention" outcome does not survive measurement.

**And it cannot share the GPU with the LLM.** Paddle's allocator reserves ~7.8 GB of the 8 GB card and does not release it until the process exits, even though the model's own tensors peak at ~5.9 GB. With Qwen3-8B (Q4_K_M) holding 5-6 GB there is no room for both. Sequential use is still fine -- but only if OCR runs **out of process and exits**, which is how the classical PaddleOCR worker already runs (`src/paddle_worker.py`), not merely at a different pipeline stage.

## Where the Arabic win comes from, and where it does not

PaddleOCR-VL reads Arabic better on **6 of 8** documents and English better on **4 of 6**. The mean hides the more useful pattern: **it wins on the documents Tesseract reads badly and loses on the documents Tesseract already reads well.**

On `wipo_eg081ar_1` -- Tesseract's worst Arabic fixtures -- CER falls 0.160 to 0.093 and 0.133 to 0.085. On `wipo_eg088ar_1`, where Tesseract is already at 0.040, it *rises* to 0.071. For an archive that is the useful direction: the worst case improves, which is what determines how much output needs human correction. But it is not the uniform improvement a mean of 0.081 vs 0.095 suggests, and a routing rule that sent every Arabic page to PaddleOCR-VL would make some pages worse.

**Arabic WER moves the other way** (0.250 vs 0.223), as does order-insensitive bag error (0.223 vs 0.209). Glyph recognition improves while word-level agreement does not, which is the signature of a generative reader: it produces cleaner characters and occasionally a different word. On a retrieval pipeline that matters more than CER alone, because M2/M3 embed words.

## Does this change `render_dpi`?

**No, and that is a measured result rather than a convenience.** The ladder puts PaddleOCR-VL's Arabic optimum at 300 dpi (0.082), with 150 dpi at 0.083 -- a difference of 0.000 against the 0.010 win threshold prior sweeps fixed in advance, while 300 dpi costs **4.1x the time** (128 s/page against 31). 150 dpi is therefore the operating point for this engine too.

So the two engines' optima coincide on this corpus, and `render_dpi` does **not** need to become per-engine. Two qualifications, because that conclusion is narrower than it looks:

1. **This corpus is uniformly body-size type.** `reports/dpi_probe_300.md` showed Tesseract's optimum sliding from 300 dpi at 7 pt to 175 dpi at 14 pt. PaddleOCR-VL was not put through that probe, so "the optima coincide" is established for 11 pt text and nothing else.
2. **Unlike Tesseract, this engine has its own internal resize.** `PaddleOCRVLOptions.min_pixels` / `max_pixels` set its visual token budget, and the render dpi only decides what it is handed before that budget applies. Tuning those is the more direct control and was left at defaults here.

Note also that the repo's shipped default is `render_dpi = 300`, not 150: `reports/arabic_preprocess_summary.md` records 150 being shipped on the sweep evidence and then reverted after the print-size probe. The 0.095 / 0.013 figures this report is measured against are the **150 dpi** numbers from that sweep, reproduced here exactly (0.0949 / 0.0132), so the comparison holds -- but a production adoption decision would be against 300 dpi Tesseract, which is worse on this corpus (0.130 Arabic), not better.

## Recommendation

**Do not swap the default. Keep Tesseract as the primary engine, and treat PaddleOCR-VL as a promising second reader that needs a decision about hardware before it can be adopted.** Nothing in the pipeline was changed by this run -- it is an evaluation, and the adapter is not wired into `ocr_pipeline`.

The reasoning, in order of weight:

1. **The accuracy win is real but modest, and not uniform.** Arabic 0.081 vs 0.095 (15% better), winning 6 of 8 documents and losing on the two where Tesseract is strongest. English is a clearer win (57% better), but English was never the problem.
2. **The cost is not modest.** ~11x slower than Tesseract *on a GPU*, and ~110x on CPU. Over an archive, that is the difference between an overnight ingest and a week-long one -- the same argument that counted against classical PaddleOCR at 2x.
3. **It needs the GPU exclusively.** Not a scheduling detail: the allocator holds ~7.9 GB of an 8 GB card until the process exits, so "different pipeline stages" is only sufficient if OCR runs in a separate process that terminates before the LLM loads.
4. **It is stable**, which is the one place it decisively beats classical PaddleOCR, and the reason it deserves a second look rather than the same rejection.
5. **Tables are a genuine capability gain, but not a gap-filler.** It reconstructs every table correctly *and* returns HTML directly -- but the shipped geometric reconstructor already finds all of them, so this buys quality of structure, not coverage (see the table section).

**What would change this recommendation:** a measurement on real firm scans where the worst-case documents are more common than they are here -- that is exactly the regime where PaddleOCR-VL was better -- or a throughput path (batching, `max_pixels` tuning, a quantized build, a second GPU) that brings the per-page cost within a small multiple of Tesseract's. Both are measurable without changing any default.

**The narrow adoption that the evidence does support** is PaddleOCR-VL as a *targeted second pass*: run Tesseract everywhere, and re-read only the pages it reads with low confidence. That inverts the cost argument -- a few percent of pages at 35 s is affordable -- and it aims the engine at exactly the documents where it measured better. It also needs its own validation (Tesseract's confidence would have to correlate with the pages PaddleOCR-VL improves), which this run does not provide. Flagging it, not building it.

## Confidence

**Stability: high.** 0 failures in 88 page reads, across four resolutions from 100 to 300 dpi, two languages, clean and degraded scans, and four table images. Per-document results are consistent -- no fixture produced a wild outlier, and the two documents where it lost were beaten by a consistent margin rather than collapsing. **It shows none of the fragility that disqualified classical PaddleOCR** (non-deterministic native crashes, a resolution ceiling below what Arabic needs, one fixture where no resolution succeeded at all).

**Accuracy ranking: moderate.** 8 Arabic and 6 English documents is enough to see a 0.014 mean difference but not to be sure of it, especially when the sign flips across documents. The Arabic result should be read as "comparable to Tesseract, better on hard pages" rather than "15% better".

**Generalization to firm documents: low, by construction.** See the caveats.

## Caveats

1. **Rendered pages, not scanner output.** Absolute error rates are an optimistic bound for both engines, and this is the one caveat that could change the ordering, because a generative reader and a glyph classifier need not degrade the same way on real scanner artifacts. **Re-run against the firm's own scans before treating this ranking as final** -- `scripts/paddleocr_vl_benchmark.py` needs no code change to do it, and nothing leaves the building.
2. **Verified references only.** The 8 Arabic and 6 English fixtures are those whose ground truth passed `scripts/audit_ground_truth.py`. Fixtures carrying visual word order or out-of-flow blocks were excluded, as in the preprocessing sweep -- they score ~0.70 however well the page is read.
3. **Two different hardware environments.** PaddleOCR-VL ran on a GPU build of PaddlePaddle in a separate virtual environment; the pipeline's pinned CPU environment was left untouched. Tesseract's figures come from the CPU environment it actually ships in. That is the honest comparison for accuracy (identical rasters, identical scoring) but it means the **speed** columns compare a GPU engine against a CPU one -- and PaddleOCR-VL is still 11x slower.
4. **Defaults, not a tuned configuration.** `max_new_tokens`, `min_pixels` / `max_pixels`, batching and the layout thresholds were all left at their defaults. A tuned configuration could plausibly move both the accuracy and the throughput, and neither number should be read as this engine's ceiling.
5. **No per-box confidence.** A generative decoder emits no confidence score, so the pipeline's low-confidence fallback gate cannot fire for this engine. Adopting it as primary would mean the fallback to Tesseract could only be triggered by an empty or errored page, not by a badly-read one.
6. **Small sample, one machine, one run.** 14 scored documents, 52 benchmark pages. Enough for a large effect; the Arabic difference is not a large effect.

## What changed in the code

**No pipeline default was touched.** `OCRConfig.primary_engine` is still `tesseract`, `fallback_engine` still `paddleocr`, `render_dpi` still 300. Swapping the default is a decision for after this is reviewed, exactly as the engine-routing decision was handled.

| File | What it is |
|---|---|
| `src/paddleocr_vl.py` | New. The adapter: same signature as `run_tesseract` / `run_paddleocr`, returns the same `OCRPageResult`. Imported by the benchmark only -- nothing in `ocr_pipeline` references it, and `SourceEngine` is unchanged. |
| `scripts/paddleocr_vl_benchmark.py` | New. The harness. Reuses `fixtures_for` from the preprocessing sweep and `cer` / `wer` / `bag_error` / `_split_by_script` from `evaluate.py` -- the scoring is imported, not reimplemented. |
| `reports/paddleocr_vl_benchmark.json` | New. Every per-document row behind this report, including the resolution ladder. |

Reproduce with:

```
python scripts/paddleocr_vl_benchmark.py --stage dpi    --device gpu:0
python scripts/paddleocr_vl_benchmark.py --stage full   --device gpu:0 --vl-dpi 150
python scripts/paddleocr_vl_benchmark.py --stage tables --device gpu:0 --vl-dpi 150
python scripts/paddleocr_vl_benchmark.py --report-only
```

PaddleOCR-VL needs a GPU build of PaddlePaddle, which the pipeline's pinned CPU environment deliberately does not have; it was installed in a separate venv so `requirements.txt` stays exactly as shipped. `--device cpu` runs in the project venv unchanged, at the CPU speed reported above.

