# The ~44 s/page speed outlier — investigated

> ## What was asked, and what was found
>
> A processing time of **~44 s/page** was flagged in the first M1 work session and never explained. The brief for this investigation required finding the original measurement rather than re-deriving one, reproducing it, profiling it, and classifying the cause as *expected*, *bug*, or *environmental*.
>
> **The original data point is not in any committed artifact.** That is reported first and honestly, in [Provenance](#provenance-the-original-measurement-is-not-in-the-repository), because it changes what the rest of this report can claim.
>
> **The behaviour it describes is real, reproduces, and is now fully explained.** A page that fails the OCR confidence gate runs *both* engines and costs **38–46 s** — and the corpus's worst such page costs **46.2 s**. That is what ~44 s/page is. The document-level outlier is `scan_constitute_egypt_2019_ar_150dpi.pdf` at **28.4 s/page against a corpus norm of 4.4**, and **55% of its runtime is the PaddleOCR fallback**.

Generated: 2026-08-16
Harness: [`scripts/speed_outlier_profile.py`](../scripts/speed_outlier_profile.py) · data: `reports/speed_outlier_investigation.json`
Method: per-page census over all 11 scanned fixtures at 2 repeats, then direct stage decomposition and `cProfile`, then two controlled experiments.

---

## Verdict

| Question | Answer |
|---|---|
| Does it reproduce? | **Yes.** 28.4 s/page median, two runs 169.2 s and 171.3 s — a 1.2% spread. Not environmental. |
| Where does the time go? | **98% inside two OCR subprocesses.** PaddleOCR 100.6 s (57%), Tesseract 72.5 s (41%). Rendering 0.6 s, chunking 3.4 ms, table reconstruction 43 ms. |
| Root cause | **Two compounding causes, both measured.** (1) Tesseract costs ~3x more per page on this document than on the English peer at an identical raster — a property of its *content*, not its scan quality. (2) The confidence gate fails on **6 of 6 pages**, invoking the PaddleOCR fallback for **+94.0 s**. |
| Classification | **(a) Expected — but not for the reason previously published.** An earlier `evaluation_report.md` explained this document as "it is a scan". That explains 4 s/page, not 28. The correct explanation is the fallback, and the report has since been regenerated to say so. Inside it sits one bounded inefficiency, filed as [S1](#follow-up-s1). |
| Fixed? | **No, deliberately.** The cause lies in OCR engine selection, which this task's scope boundary explicitly excludes. S1 is scoped rather than attempted. |

---

## Provenance: the original measurement is not in the repository

Searched exhaustively before measuring anything: the full working tree at the time — including reports and logs since removed from version control — with every JSON payload walked key-by-key for any numeric value in the 40–48 range under a time-like key, and `README.md` and `test_corpus/manifest.md` scanned by regex for any `NN s/page` form.

**No `~44 s/page` figure exists in any committed artifact.** The nearest recorded values, none of which is it:

| Value | Where | What it is |
|---|---|---|
| 43.2 s/page | A **voided** OCR engine comparison run, not in the repository | PaddleOCR on `bench_wipo_eg081ar_1_clean.pdf`. The run was invalidated because it was measuring the wrong recogniser, and was regenerated; the figure is recorded here only so it is not mistaken for the missing one. |
| 46.2 s/page | `paddleocr_vl_benchmark.md` | PaddleOCR-VL on `bench_wipo_eg088ar_1_clean.pdf`, GPU |
| 48.8 s/page | `paddleocr_vl_benchmark.md` | PaddleOCR-VL on `stress_table_ruled_ar.png`, includes model load |
| 31.8 s/page | `evaluation_results.json` (generated; regenerate with `scripts/evaluate.py`) | `scan_constitute_egypt_2019_ar_150dpi.pdf` — the highest document-level figure in the shipped evaluation |

So the figure was recorded somewhere outside the repository — a session note, not an artifact. Rather than treat that as a dead end, this investigation asked the answerable question instead: **what in this pipeline costs ~44 seconds for one page, and does it still?**

It has a precise answer, in [Where ~44 s/page comes from](#where-44-spage-comes-from).

---

## The census: every scanned fixture, twice

Current code, current config (`render_dpi=300`, `max_render_side=4000`, Tesseract primary on `ara+eng`, PaddleOCR fallback, preprocessing off). `primary` and `fallback` are read out of the pipeline's own `engine_log`, which already times both engines separately.

| Document | Lang | s/page | Primary (s) | Fallback (s) | Fallback pages | Run spread |
|---|---|---|---|---|---|---|
| `scan_authored_statute_ar_300dpi.pdf` | ar | 2.42 | 6.5 | 0.0 | 0 | 0.09 s |
| `scan_authored_statute_ar_150dpi.pdf` | ar | 2.52 | 6.8 | 0.0 | 0 | 0.16 s |
| `scan_authored_award_en_150dpi.pdf` | en | 2.96 | 5.2 | 0.0 | 0 | 0.24 s |
| `scan_authored_award_en_300dpi.pdf` | en | 3.07 | 5.9 | 0.0 | 0 | 0.69 s |
| `scan_eg_constitution_2014_en_150dpi.pdf` | en | 4.16 | 23.4 | 0.0 | 0 | 0.61 s |
| `scan_eg_official_gazette_excerpt_300dpi.pdf` | en | 4.57 | 26.1 | 0.0 | 0 | 0.78 s |
| `scan_wipo_eg088ar_1_150dpi.pdf` | ar | 4.62 | 26.3 | 0.0 | 0 | 0.40 s |
| `scan_wipo_eg081ar_1_300dpi.pdf` | ar | 4.69 | 26.7 | 0.0 | 0 | 0.39 s |
| `scan_constitute_egypt_2014_ar_200dpi.pdf` | ar | **16.97** | 70.0 | **33.1** | **2** | 6.27 s |
| `scan_constitute_egypt_2014_en_200dpi.pdf` | en | **17.64** | 72.8 | **31.9** | **2** | 1.76 s |
| `scan_constitute_egypt_2019_ar_150dpi.pdf` | ar | **28.38** | 73.1 | **94.0** | **6** | 2.09 s |

**The corpus splits cleanly in two, and the line is the fallback.** Eight documents never invoke it and sit at 2.4–4.7 s/page. Three invoke it and sit at 17.0–28.4 s/page. There is nothing in between.

Every figure reproduces: the largest run-to-run spread is 6.3 s on a 102 s document (6%), and the outlier's is 1.2%. **This is not environmental** — criterion (c) is ruled out by measurement, not by argument.

---

## The outlier characterised

`scan_constitute_egypt_2019_ar_150dpi.pdf`

| Property | Value |
|---|---|
| Pages | 6 |
| Type | image-only scan, no text layer — **OCR path**, never native extraction |
| Page size | 612 × 792 pt |
| Rendered raster | 2550 × 3300 px (8.4 MPix) at the pipeline's `render_dpi=300` |
| File size | 1.0 MB |
| Engine | Tesseract (`ara+eng`) primary, PaddleOCR fallback in an isolated subprocess |
| Language | Arabic |
| Provenance | `constitute_egypt_2019_ar.pdf` pages 1–6, rasterised at 150 dpi and degraded: skew −1.2°, noise 11, blur 0.8, JPEG q60 |
| Layout | two-column constitution; **pages 2–3 are the table of contents** |

The degradation parameters are the **heaviest in the corpus** — every other derived scan uses noise 4–9 and JPEG q60–85. That made it the obvious hypothesis, and it turned out to be half right in an instructive way (see the controlled tests).

Its raster is *not* unusual: every scanned fixture lands at 8.4–8.7 MPix after the `max_render_side=4000` cap. **Page size and DPI are ruled out as causes.**

---

## Profiling: where the time actually goes

### cProfile, whole document, 175.2 s

| Function | Cumulative | Share |
|---|---|---|
| `process_document` | 175.24 s | 100% |
| `ocr_page_image` (×6) | 174.06 s | 99.3% |
| → `run_paddleocr` (fallback) | **100.58 s** | **57.4%** |
|   → blocked on the isolated worker's stdout (`readline`) | 99.80 s | 56.9% |
|   → worker cold start (one-off) | 7.79 s | 4.4% |
| → `run_tesseract` (primary) | **72.52 s** | **41.4%** |
|   → the `tesseract` subprocess | 69.10 s | 39.4% |
| Everything else | ~1.2 s | 0.7% |

### Stage decomposition, measured directly rather than by subtraction

| Page | Raster | Render | Tesseract | Blocks | Tables | Boxes | Atoms | Chars | Conf |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 2550×3300 | 102 ms | 1 964 ms | 0.2 ms | 0.1 ms | 4 | 9 | 97 | 0.72 |
| 2 | 2550×3300 | 99 ms | **18 528 ms** | 0.6 ms | 8.4 ms | 49 | 354 | 2 149 | **0.39** |
| 3 | 2550×3300 | 102 ms | **13 032 ms** | 0.6 ms | 5.0 ms | 35 | 248 | 1 519 | **0.43** |
| 4 | 2550×3300 | 108 ms | 12 658 ms | 0.8 ms | 12.4 ms | 61 | 423 | 2 827 | 0.71 |
| 5 | 2550×3300 | 113 ms | 12 545 ms | 0.8 ms | 12.0 ms | 63 | 427 | 2 764 | 0.69 |
| 6 | 2550×3300 | 101 ms | 9 498 ms | 0.5 ms | 4.7 ms | 47 | 270 | 1 877 | 0.69 |

**Nothing outside OCR is remotely expensive.** Rendering is a flat ~105 ms/page. `boxes_to_blocks` totals 3.4 ms across the document. `tables_from_atoms` — the geometric table reconstructor, the most plausible candidate for quadratic behaviour — totals **42.6 ms**. There is no pathological regex, no quadratic loop, no redundant repeated work. The hypotheses the brief listed as worth checking are all excluded by measurement.

Note pages 2 and 3: the **slowest** pages produce the **fewest** characters at the **lowest** confidence. Time is not proportional to text recognised. These are the table-of-contents pages — short lines, leader dots, many small components — and every `constitute_*` fixture shows the same signature on the same pages.

---

## Two controlled experiments

### 1. Is the degradation causing the slowness? **No.**

The same six source pages were rendered **clean** — straight from `constitute_egypt_2019_ar.pdf`, no skew, noise, blur or JPEG — at 300 dpi, producing the identical 2550 × 3300 raster, and run through Tesseract alone.

| | Degraded fixture | Clean render |
|---|---|---|
| Tesseract | **12.04 s/page** | **11.67 s/page** |
| Mean confidence | 0.39 – 0.72 | 0.53 – 0.86 |
| Pages passing the 0.75 gate | **0 of 6** | **5 of 6** |

**Indistinguishable in time; decisive in confidence.** So the degradation does not make Tesseract slow — it makes Tesseract *unconfident*, which trips the gate, which invokes the fallback, which is where the time goes. That is a clean separation of the two causes, and it is the single most useful result in this report.

Tesseract's own cost on this document is therefore a property of its **content**. Normalised per character across the corpus:

| Document | Lang | ms/char (primary) |
|---|---|---|
| `scan_eg_official_gazette_excerpt_300dpi.pdf` | en | 1.89 |
| `scan_eg_constitution_2014_en_150dpi.pdf` | en | 2.23 |
| `scan_authored_award_en_150dpi.pdf` | en | 2.99 |
| `scan_wipo_eg088ar_1_150dpi.pdf` | ar | 3.91 |
| `scan_wipo_eg081ar_1_300dpi.pdf` | ar | 4.03 |
| `scan_authored_statute_ar_300dpi.pdf` | ar | 4.14 |
| `scan_constitute_egypt_2014_en_200dpi.pdf` | en | 4.66 |
| `scan_constitute_egypt_2014_ar_200dpi.pdf` | ar | 7.52 |
| `scan_constitute_egypt_2019_ar_150dpi.pdf` | ar | **8.71** |

Arabic costs roughly **2x** English per character under `ara+eng`, and the two `constitute_*` documents sit above their language's band because of their contents pages. The outlier is the top of both effects: Arabic, dense, with a table of contents.

*(Character counts here are the chosen engine's output, so rows where the fallback won are approximate. The English/Arabic separation is far larger than that imprecision.)*

### 2. Is the fallback earning its 55%? **Not demonstrably, and it may be actively harmful.**

The fallback fires only on documents whose ground truth `audit_ground_truth.py` classifies as `unreliable`, so its accuracy on those exact pages cannot be scored. The question was made answerable instead by running **both** engines over `scan_authored_statute_ar_150dpi.pdf` — Arabic, and the reference text was written before the page was rendered, so it is trustworthy — under identical treatment:

| Engine | CER (no-space) | Speed | Reported confidence |
|---|---|---|---|
| Tesseract | **0.296** | 2.36 s/page | 0.80 – 0.91 |
| PaddleOCR | 0.831 | 13.99 s/page | 0.44 – 0.49 |

*(Both scored on raw `boxes_to_blocks` output without the RTL-repair and normalisation stages, so these are not comparable to the published 0.120 — only to each other.)*

**PaddleOCR is 2.8x less accurate and 5.9x slower on Arabic here**, consistent with every prior measurement in `reports/ocr_engine_comparison.md`. On this fixture the confidence ordering agrees with the accuracy ordering, so `prefer_higher_confidence_on_fallback` would correctly keep Tesseract.

On the outlier it does the opposite: PaddleOCR reported 0.77–0.97 against Tesseract's 0.39–0.72 and **won all six pages**. The comparison that decided this is one the code itself flags in its own log entry — *"confidence scales are not calibrated between engines"*. So the pipeline spent 94 seconds replacing output from the engine this project measures as better on Arabic, on the strength of a comparison it documents as unreliable, and the corpus cannot tell us whether that was an improvement.

**A counter-datum, recorded for balance.** Regenerating `evaluation_report.md` after this investigation moved `scan_constitute_egypt_2019_ar_150dpi.pdf` from `tesseract` to `paddleocr` as its kept engine, and its Arabic CER **improved**, 0.756 → 0.719. So on this document the fallback's choice was not harmful. It is not decisive either: `audit_ground_truth.py` classifies that document's reference as `unreliable`, and a 0.04 movement against an unreliable reference cannot settle anything. The two observations together are the actual state of the evidence — the fallback helps slightly where we cannot trust the reference, and hurts substantially where we can. That is why S1 is *open* rather than *decided*.

That is [follow-up S1](#follow-up-s1). It is **not** fixed here.

---

## Where ~44 s/page comes from

The document-level figure is 28.4 s/page. But per-page costs are bimodal, and the flagged number matches the upper mode exactly. A page that fails the gate runs **both** engines end to end:

| Page | Tesseract | + PaddleOCR | = Total for that page |
|---|---|---|---|
| `scan_constitute_egypt_2014_ar_200dpi.pdf` p2 | 25.6 s | 20.5 s | **46.2 s** |
| `scan_constitute_egypt_2014_en_200dpi.pdf` p2 | 27.2 s | 15.5 s | **42.7 s** |
| `scan_constitute_egypt_2014_en_200dpi.pdf` p3 | 21.6 s | 16.4 s | **38.0 s** |
| `scan_constitute_egypt_2014_ar_200dpi.pdf` p3 | 18.3 s | 12.6 s | **30.9 s** |
| — any page that passes the gate — | 2–4 s | — | **2–4 s** |

**~44 s/page is the cost of one page that fails the OCR confidence gate.** It is not a mystery, not a bug in table reconstruction or chunking, and not a measurement artifact. It is the safety net running, and it is roughly **12x** the cost of a page that does not need it.

This also reconciles the historical figure with today's: an early session that timed a single contents page, or a document with a higher share of gate failures, would land on exactly this number.

---

## Root cause and classification

**Classified (a) — expected — with a bounded inefficiency inside it.**

The chain, each link measured rather than inferred:

1. The document is Arabic, dense, and includes two table-of-contents pages. Tesseract therefore costs **12.0 s/page** against a corpus norm of 4.4 — from content, not scan quality (experiment 1).
2. Synthetic degradation (noise 11, blur 0.8, JPEG q60 — the corpus's heaviest) drops mean confidence from 0.53–0.86 to 0.39–0.72.
3. `OCRConfig.min_mean_confidence = 0.75` therefore fails on **6 of 6** pages instead of 1 of 6.
4. Each failure invokes PaddleOCR in an isolated subprocess: **+15.7 s/page, +94.0 s, 55% of total runtime**.
5. `prefer_higher_confidence_on_fallback` then selects PaddleOCR on all six pages using an explicitly uncalibrated comparison.

**The previously published explanation was wrong, and has been corrected.** `evaluation_report.md` used to say of this document: *"This is a scaling characteristic, not a defect… it is a scan."* Being a scan explains 4 s/page — eight fixtures in this corpus are scans and none exceeds 4.7. It does not explain 28. The report's own `Unaccounted` column was working correctly; the attribution above it was not. It has since been regenerated with a narrative that leads with the fallback and cites this report.

**Steps 1–3 are expected.** Step 4 is expected *by design* and its price is now quantified. Step 5 is the inefficiency.

---

## Follow-up S1

**Not attempted here.** The scope boundary for this task was diagnostic-first, and explicitly excluded OCR engine selection unless the root cause was unavoidably inside it. It is inside it — so it is described rather than changed.

**Problem.** The fallback costs ~12x a normal page and fires on 3 of 11 fixtures. When it fires, the winner is chosen by comparing `mean_conf` across two engines whose confidence scales the code documents as not comparable. On the one Arabic fixture with trustworthy ground truth, PaddleOCR is 2.8x less accurate and 5.9x slower than Tesseract; on the outlier it nonetheless wins every page.

**What a fix would involve** (in increasing order of work):

1. **Calibrate, or stop comparing.** Either map each engine's confidence to a common scale on the authored fixtures, or replace the comparison with a rule that does not need calibration — e.g. prefer the primary unless it produced *no* usable text.
2. **Make the fallback language-aware.** Every measurement this project has published says PaddleOCR is worse than Tesseract on Arabic. `fallback_engine = "none"` for Arabic pages would remove 55% of this document's runtime and, on the available evidence, improve its accuracy.
3. **Re-examine the 0.75 gate.** On the clean render, five of six pages pass; degraded, none do. The threshold is doing what it was asked to, but it was never tuned against the *cost* of what it triggers.

**Verification any fix needs**: re-run `scripts/speed_outlier_profile.py` for the timing, and the full `scripts/evaluate.py` plus `reports/ocr_engine_comparison.md`'s fixtures for accuracy — because options 1 and 2 change which engine's text reaches the output, and that must not regress the published CER figures.

**Not undertaken now** because it touches engine selection, which deserves the same care and test coverage the visual-order fix received.

---

## Caveats

1. **One machine, one configuration.** Absolute timings are from a single Windows CPU-only workstation. The *ratios* — fallback ≈ 12x a normal page, Arabic ≈ 2x English per character, OCR ≈ 98% of runtime — are the durable part.
2. **These figures are isolated-run timings; `evaluation_report.md`'s are batch timings, and its are ~1.2–1.4x higher.** This report times one document at a time. `evaluate.py` processes 35 documents in one process, and everything runs slower in that context — uniformly, including the fast documents, so it is process-level overhead rather than anything specific to the outlier:

   | Document | This report (isolated) | `evaluation_report.md` (batch) | Ratio |
   |---|---|---|---|
   | `scan_constitute_egypt_2019_ar_150dpi.pdf` | 28.4 s/page | 30.1 s/page | 1.06x |
   | `scan_constitute_egypt_2014_ar_200dpi.pdf` | 17.0 s/page | 24.5 s/page | 1.44x |
   | `scan_constitute_egypt_2014_en_200dpi.pdf` | 17.6 s/page | 20.7 s/page | 1.17x |
   | `scan_eg_constitution_2014_en_150dpi.pdf` | 4.2 s/page | 5.0 s/page | 1.21x |
   | `scan_wipo_eg088ar_1_150dpi.pdf` | 4.6 s/page | 5.4 s/page | 1.16x |

   Two consecutive full `evaluate.py` runs reproduce their own figures closely and produce **bit-identical accuracy**, so this is a stable property of the measurement context, not noise. Quote the isolated figures for per-document cost and the batch figures for planning an ingest.
3. **The fixtures are rendered pages, not scans.** Their confidence distribution is synthetic. How often the 0.75 gate fires on the firm's real archive is unknown and is the number that determines whether S1 matters in practice. That is the single most useful thing to re-measure on firm material.
4. **The engine-comparison experiment used one fixture.** It is the only Arabic fixture with authored ground truth at a resolution where both engines run. It is consistent with `reports/ocr_engine_comparison.md`'s broader result, but it is one document.
5. **`ms/char` uses the chosen engine's character count**, which overstates the figure slightly on the three documents where the fallback won. The English/Arabic separation is much larger than that error.
6. **The original ~44 s/page measurement was never located**, so this report explains the *behaviour* the figure describes rather than confirming that specific number's origin. The reconciliation in [Where ~44 s/page comes from](#where-44-spage-comes-from) is strong but circumstantial.

---

## Reproducing

```bash
python scripts/speed_outlier_profile.py --repeat 2                                  # the census, ~23 min
python scripts/speed_outlier_profile.py --deep scan_constitute_egypt_2019_ar_150dpi.pdf   # stages + cProfile
python scripts/speed_outlier_profile.py --deep scan_eg_constitution_2014_en_150dpi.pdf    # the normal-speed peer
```

Writes `reports/speed_outlier_investigation.json`.
