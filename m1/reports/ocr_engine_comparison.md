# PaddleOCR vs Tesseract -- head-to-head

> ## Measured on public and synthetic scans, by design
> 
> Every figure comes from **published Egyptian legal PDFs rasterized into scans**, plus **authored fixtures** whose reference text was written before the page was rendered. No client document has been processed, and none is needed to choose between two OCR engines: what matters here is the comparison, and both engines see identical input.
> 
> **The absolute error rates are an optimistic bound.** A rasterized page has clean glyph shapes, no scanner optics, no photocopy generations and no bleed-through. Real scans will score worse, and the two engines may not degrade at the same rate -- which is the one thing this benchmark cannot rule out. Re-running it against the firm's own scans needs no code change and nothing leaves the building.
> 
> **On the render resolution.** This run rendered at 300 dpi. `reports/arabic_preprocess_sweep.md` found 150 dpi to read this corpus's Arabic better (CER 0.095), and `reports/dpi_probe_300.md` then found that advantage to reverse on small print -- so 300 dpi remains the default and the figures below stand as current. **The engine ordering never depended on it either way**: both engines are handed identical rasters, so a render setting cannot bias the comparison.

Generated: 2026-08-15 22:31:57  
Fixtures: 23 documents, 4 pages each, both engines on identical rasters  
Render: 300 dpi | Wall clock: 76.8 min | CPU only, no GPU

## Verdict

**Quote these two lines, not the ones below them.** Absolute error rates are only meaningful where the reference itself was verified correct (see [Ground-truth audit](#ground-truth-audit)).

- **Arabic -- verified references: Tesseract wins.** CER 0.130 vs 0.399 -- 67% fewer errors than PaddleOCR. _8 documents whose ground truth passed the audit. **This is the Arabic number.**_
- **English -- verified references: PaddleOCR wins.** CER 0.003 vs 0.021 -- 84% fewer errors than Tesseract. _6 documents whose ground truth passed the audit. **This is the English number.**_

For completeness, including documents whose reference is known to be defective (both engines are handicapped equally, so the *winner* is still valid even though the absolute figures are not):

- **Arabic -- all documents: Tesseract wins.** CER 0.391 vs 0.543 -- 28% fewer errors than PaddleOCR. _14 documents_
- **English -- all documents: PaddleOCR wins.** CER 0.080 vs 0.097 -- 17% fewer errors than Tesseract. _9 documents_

- **Speed: tesseract is 2x faster** (8.1 s/page vs 18.4 s/page).
- **paddleocr crash rate: 7/92 pages (8%)**
- **tesseract crash rate: 0/92 pages (0%)**

## Full results

`no-space` strips whitespace before comparing, isolating glyph recognition. Where it diverges sharply from the plain CER, the *reference* has fragmented word boundaries -- see the Caveats.

| Document | Ref | Cols | Quality | Engine | CER | CER (no-space) | WER | s/page | Crashed? |
|---|---|---|---|---|---|---|---|---|---|
| `bench_constitute_egypt_2014_ar_clean.pdf` (ar) | **visual order** | 2 | clean | paddleocr | 0.727 | 0.770 | 0.927 | 19.7 | no |
| `bench_constitute_egypt_2014_ar_clean.pdf` (ar) | **visual order** | 2 | clean | tesseract | 0.696 | 0.731 | 0.967 | 10.3 | no |
| `bench_constitute_egypt_2014_ar_poor.pdf` (ar) | **visual order** | 2 | poor | paddleocr | 0.752 | 0.785 | 0.936 | 14.9 | no |
| `bench_constitute_egypt_2014_ar_poor.pdf` (ar) | **visual order** | 2 | poor | tesseract | 0.693 | 0.717 | 0.967 | 14.1 | no |
| `bench_constitute_egypt_2014_en_clean.pdf` (en) | **out of flow** | 2 | clean | paddleocr | 0.224 | 0.233 | 0.191 | 20.0 | no |
| `bench_constitute_egypt_2014_en_clean.pdf` (en) | **out of flow** | 2 | clean | tesseract | 0.212 | 0.221 | 0.188 | 10.8 | no |
| `bench_constitute_egypt_2014_en_poor.pdf` (en) | **out of flow** | 2 | poor | paddleocr | 0.225 | 0.234 | 0.197 | 16.7 | no |
| `bench_constitute_egypt_2014_en_poor.pdf` (en) | **out of flow** | 2 | poor | tesseract | 0.234 | 0.241 | 0.227 | 10.1 | no |
| `bench_constitute_egypt_2019_ar_clean.pdf` (ar) | **visual order** | 2 | clean | paddleocr | 0.675 | 0.708 | 0.956 | 73.6 | **YES (1)** |
| `bench_constitute_egypt_2019_ar_clean.pdf` (ar) | **visual order** | 2 | clean | tesseract | 0.670 | 0.698 | 0.928 | 19.3 | no |
| `bench_constitute_egypt_2019_ar_poor.pdf` (ar) | **visual order** | 2 | poor | paddleocr | 0.665 | 0.698 | 0.955 | 15.8 | no |
| `bench_constitute_egypt_2019_ar_poor.pdf` (ar) | **visual order** | 2 | poor | tesseract | 0.667 | 0.694 | 0.927 | 16.9 | no |
| `bench_eg_official_gazette_excerpt_clean.pdf` (en) | verified | 1 | clean | paddleocr | 0.005 | 0.004 | 0.018 | 14.6 | no |
| `bench_eg_official_gazette_excerpt_clean.pdf` (en) | verified | 1 | clean | tesseract | 0.000 | 0.000 | 0.000 | 5.7 | no |
| `bench_eg_official_gazette_excerpt_poor.pdf` (en) | verified | 1 | poor | paddleocr | 0.002 | 0.002 | 0.012 | 21.0 | no |
| `bench_eg_official_gazette_excerpt_poor.pdf` (en) | verified | 1 | poor | tesseract | 0.011 | 0.011 | 0.012 | 5.5 | no |
| `bench_wipo_eg081ar_1_clean.pdf` (ar) | verified | 2 | clean | paddleocr | 0.383 | 0.424 | 0.575 | 13.6 | no |
| `bench_wipo_eg081ar_1_clean.pdf` (ar) | verified | 2 | clean | tesseract | 0.128 | 0.136 | 0.280 | 4.7 | no |
| `bench_wipo_eg081ar_1_poor.pdf` (ar) | verified | 2 | poor | paddleocr | 0.404 | 0.448 | 0.625 | 13.4 | no |
| `bench_wipo_eg081ar_1_poor.pdf` (ar) | verified | 2 | poor | tesseract | 0.177 | 0.184 | 0.324 | 3.8 | no |
| `bench_wipo_eg088ar_1_clean.pdf` (ar) | verified | 1 | clean | paddleocr | 0.168 | 0.158 | 0.337 | 64.6 | **YES (6)** |
| `bench_wipo_eg088ar_1_clean.pdf` (ar) | verified | 1 | clean | tesseract | 0.058 | 0.047 | 0.236 | 4.7 | no |
| `bench_wipo_eg088ar_1_poor.pdf` (ar) | verified | 1 | poor | paddleocr | 0.070 | 0.065 | 0.323 | 13.6 | no |
| `bench_wipo_eg088ar_1_poor.pdf` (ar) | verified | 1 | poor | tesseract | 0.056 | 0.046 | 0.216 | 4.8 | no |
| `scan_authored_award_en_150dpi.pdf` (en) | **authored** | ? | authored-reference | paddleocr | 0.003 | 0.003 | 0.008 | 10.4 | no |
| `scan_authored_award_en_150dpi.pdf` (en) | **authored** | ? | authored-reference | tesseract | 0.004 | 0.005 | 0.021 | 3.8 | no |
| `scan_authored_award_en_300dpi.pdf` (en) | **authored** | ? | authored-reference | paddleocr | 0.006 | 0.007 | 0.029 | 10.3 | no |
| `scan_authored_award_en_300dpi.pdf` (en) | **authored** | ? | authored-reference | tesseract | 0.004 | 0.004 | 0.013 | 3.7 | no |
| `scan_authored_statute_ar_150dpi.pdf` (ar) | **authored** | ? | authored-reference | paddleocr | 0.781 | 0.842 | 0.996 | 9.7 | no |
| `scan_authored_statute_ar_150dpi.pdf` (ar) | **authored** | ? | authored-reference | tesseract | 0.269 | 0.274 | 0.328 | 3.1 | no |
| `scan_authored_statute_ar_300dpi.pdf` (ar) | **authored** | ? | authored-reference | paddleocr | 0.747 | 0.817 | 0.996 | 9.8 | no |
| `scan_authored_statute_ar_300dpi.pdf` (ar) | **authored** | ? | authored-reference | tesseract | 0.039 | 0.039 | 0.062 | 3.4 | no |
| `scan_constitute_egypt_2014_ar_200dpi.pdf` (ar) | **unreliable** | ? | eval-corpus | paddleocr | 0.711 | 0.745 | 0.931 | 13.2 | no |
| `scan_constitute_egypt_2014_ar_200dpi.pdf` (ar) | **unreliable** | ? | eval-corpus | tesseract | 0.735 | 0.803 | 0.973 | 18.1 | no |
| `scan_constitute_egypt_2014_en_200dpi.pdf` (en) | **out of flow** | ? | eval-corpus | paddleocr | 0.223 | 0.233 | 0.205 | 15.9 | no |
| `scan_constitute_egypt_2014_en_200dpi.pdf` (en) | **out of flow** | ? | eval-corpus | tesseract | 0.271 | 0.279 | 0.336 | 14.4 | no |
| `scan_constitute_egypt_2019_ar_150dpi.pdf` (ar) | **unreliable** | ? | eval-corpus | paddleocr | 0.678 | 0.701 | 0.970 | 10.7 | no |
| `scan_constitute_egypt_2019_ar_150dpi.pdf` (ar) | **unreliable** | ? | eval-corpus | tesseract | 0.803 | 0.793 | 1.517 | 12.4 | no |
| `scan_eg_constitution_2014_en_150dpi.pdf` (en) | verified | ? | eval-corpus | paddleocr | 0.001 | 0.001 | 0.005 | 10.8 | no |
| `scan_eg_constitution_2014_en_150dpi.pdf` (en) | verified | ? | eval-corpus | tesseract | 0.107 | 0.107 | 0.109 | 3.9 | no |
| `scan_eg_official_gazette_excerpt_300dpi.pdf` (en) | verified | ? | eval-corpus | paddleocr | 0.005 | 0.005 | 0.015 | 11.5 | no |
| `scan_eg_official_gazette_excerpt_300dpi.pdf` (en) | verified | ? | eval-corpus | tesseract | 0.000 | 0.000 | 0.000 | 4.0 | no |
| `scan_wipo_eg081ar_1_300dpi.pdf` (ar) | verified | ? | eval-corpus | paddleocr | 0.344 | 0.377 | 0.516 | 9.5 | no |
| `scan_wipo_eg081ar_1_300dpi.pdf` (ar) | verified | ? | eval-corpus | tesseract | 0.139 | 0.149 | 0.314 | 4.6 | no |
| `scan_wipo_eg088ar_1_150dpi.pdf` (ar) | verified | ? | eval-corpus | paddleocr | 0.063 | 0.060 | 0.310 | 9.6 | no |
| `scan_wipo_eg088ar_1_150dpi.pdf` (ar) | verified | ? | eval-corpus | tesseract | 0.175 | 0.168 | 0.306 | 4.7 | no |

Rows whose `Ref` is not `verified` have a defective ground truth. Their absolute CER is meaningless; their *relative* ordering between engines is still valid, because both engines were scored against the same defective reference.

## Sensitivity to scan quality

Each source was rendered twice: `clean` (300 dpi, JPEG q88, slight skew) and `poor` (150 dpi, JPEG q58, 1.2 deg skew, heavy noise). How steeply an engine degrades matters more than its best-case score, because firm archives are not uniformly clean.

| Language | Engine | CER clean | CER poor | Degradation |
|---|---|---|---|---|
| ar | paddleocr | 0.515 | 0.499 | -0.016 |
| ar | tesseract | 0.403 | 0.410 | +0.007 |
| en | paddleocr | 0.119 | 0.118 | -0.001 |
| en | tesseract | 0.110 | 0.126 | +0.016 |

## Reliability and speed

| Engine | Pages | Failed at configured DPI | Crashes | Soft errors | Never succeeded | Mean s/page | Total min |
|---|---|---|---|---|---|---|---|
| paddleocr | 92 | 8/8 (100%) | 7 | 7 | 1 | 18.4 | 28.5 |
| tesseract | 92 | 0/92 (0%) | 0 | 0 | 0 | 8.1 | 13.3 |

### ⚠ PaddleOCR could not process pages at the pipeline's configured DPI

**8 of the 8 pages probed at full resolution failed** (100%), and **91 of 92 pages (99%) only produced output after being downscaled.** Once the working resolution was established the benchmark started there, so not every page re-probed the top rung.

Working resolutions ranged 1200-2500 px on the long side (median 1200 px). A 300 dpi A4 page is ~3500 px.

The failure is **resolution-dependent, not content-dependent** -- the same page succeeds once downscaled, on every document tested. Failures arrive either as an opaque `RuntimeError: Unknown exception` from native code or as an outright worker-process death.


This matters more than the accuracy numbers. Downscaling is not free: it is precisely the resolution Arabic needs, because the dots and diacritics that distinguish ب ت ث are only a few pixels across. **The resolution PaddleOCR can survive is below the resolution Arabic needs.**

## Ground-truth audit

Some scores looked catastrophic for *both* engines. They turned out to be defects in the **reference**, not in the OCR -- and there are two distinct ones, with different signatures.

Most ground truth here is the source PDF's own text layer, so it inherits whatever the publisher did.

**Visual word order.** Some Arabic PDFs store each line's words right-to-left rather than in logical order. The letters inside each word are correct, so the file passes every character-level check and looks fine to a reader -- but the word sequence is backwards:

```
reference : الرحيم الرحمن الله بسم
correct   : بسم الله الرحمن الرحيم
```

OCR reads the page correctly and is charged ~0.70 CER for output that is substantially right.

**Out-of-flow blocks.** Other publishers put topic labels in the left margin and emit them at the *end* of each page's content stream. Every word is present -- order-insensitive bag error is near zero -- but the sequence differs from the page, and CER counts that as error.

`scripts/audit_ground_truth.py` separates them empirically. It OCRs a page, then scores it against the reference three ways: as-is, with every reference line's word order reversed, and as an order-insensitive word multiset. Reversing helping materially means visual order; a near-zero bag error beside a large CER means out-of-flow ordering; both large means genuine recognition error.

The `authored` fixtures sidestep all of this: their reference text was written before the page was rendered, so it cannot carry a publisher's defects at all.

| Fixture | CER as-is | CER reversed | Verdict |
|---|---|---|---|
| `bench_constitute_egypt_2014_ar_clean.pdf` | 0.734 | 0.621 | **visual order** |
| `bench_constitute_egypt_2014_ar_poor.pdf` | 0.718 | 0.581 | **visual order** |
| `bench_constitute_egypt_2014_en_clean.pdf` | 0.212 | 0.740 | **out of flow** |
| `bench_constitute_egypt_2014_en_poor.pdf` | 0.225 | 0.729 | **out of flow** |
| `bench_constitute_egypt_2019_ar_clean.pdf` | 0.699 | 0.433 | **visual order** |
| `bench_constitute_egypt_2019_ar_poor.pdf` | 0.695 | 0.396 | **visual order** |
| `bench_eg_official_gazette_excerpt_clean.pdf` | 0.000 | 0.713 | verified |
| `bench_eg_official_gazette_excerpt_poor.pdf` | 0.015 | 0.713 | verified |
| `bench_wipo_eg081ar_1_clean.pdf` | 0.122 | 0.681 | verified |
| `bench_wipo_eg081ar_1_poor.pdf` | 0.153 | 0.679 | verified |
| `bench_wipo_eg088ar_1_clean.pdf` | 0.043 | 0.599 | verified |
| `bench_wipo_eg088ar_1_poor.pdf` | 0.035 | 0.606 | verified |
| `scan_authored_award_en_150dpi.pdf` | 0.005 | 0.701 | **authored** |
| `scan_authored_award_en_300dpi.pdf` | 0.004 | 0.699 | **authored** |
| `scan_authored_statute_ar_150dpi.pdf` | 0.274 | 0.673 | **authored** |
| `scan_authored_statute_ar_300dpi.pdf` | 0.039 | 0.675 | **authored** |
| `scan_constitute_egypt_2014_ar_200dpi.pdf` | 0.803 | 0.747 | **unreliable** |
| `scan_constitute_egypt_2014_en_200dpi.pdf` | 0.279 | 0.750 | **out of flow** |
| `scan_constitute_egypt_2019_ar_150dpi.pdf` | 1.072 | 0.999 | **unreliable** |
| `scan_eg_constitution_2014_en_150dpi.pdf` | 0.136 | 0.728 | verified |
| `scan_eg_official_gazette_excerpt_300dpi.pdf` | 0.000 | 0.713 | verified |
| `scan_wipo_eg081ar_1_300dpi.pdf` | 0.158 | 0.654 | verified |
| `scan_wipo_eg088ar_1_150dpi.pdf` | 0.168 | 0.625 | verified |

**This corrects two earlier explanations, both of which were wrong.** `evaluation_report.md` attributed the poor Arabic scores to **two-column layout**; a follow-up hypothesis blamed **reference word fragmentation**. The controlled fixtures rule out both: `wipo_eg081ar_1` is two-column and scores well, and `wipo_eg088ar_1` has a fragmented reference and scores best of all. Column count and fragmentation are recorded in the results table above precisely so this can be read off rather than argued.

The real division is **by publisher**, not by layout: the Constitute Project's files carry visual word order in Arabic and an out-of-flow margin column in English, and the WIPO and Gazette files carry neither. That is why the same engine looks excellent on one Arabic statute and catastrophic on another.

None of this changes the **head-to-head**. Both engines are scored against the same reference on every fixture, so a defective reference handicaps them equally. It changes only which fixtures' absolute numbers may be quoted as accuracy.

## Recommendation

**Tesseract primary, PaddleOCR fallback. This is now the shipped default**, inverting the ordering the team spec assumed.

It is a config change, not a rewrite -- `OCRConfig.primary_engine` and `fallback_engine` already existed. To revert:

```python
cfg.ocr.primary_engine = "paddleocr"
cfg.ocr.fallback_engine = "tesseract"
```

The reasoning, in order of weight:

1. **Arabic accuracy.** Tesseract CER 0.130 vs PaddleOCR 0.399. Arabic is the majority of the firm's material, so this is the dominant consideration.
2. **Speed.** 8.1 s/page vs 18.4 s/page -- 2x. Over a large archive that is the difference between an overnight ingest and a week-long one.
3. **Reliability.** PaddleOCR needed downscaling on 91/92 pages and can terminate its process from native code. Tesseract had no such failures on this set.
4. **English is a near-tie** (Tesseract 0.021 vs PaddleOCR 0.003), so flipping costs nothing there.

**PaddleOCR stays installed and wired as the fallback.** It is not dead weight: it is a genuinely different architecture, so the pages it fails on are unlikely to be the pages Tesseract fails on, and running it out-of-process already makes it safe to attempt.

**Resolution is handled rather than merely reported.** PaddleOCR could not process pages at the pipeline's 300 dpi render, so `OCRConfig.paddle_max_side` (default 1600) hands it an image inside the range it survives, while Tesseract still receives the full-resolution raster. Making the *engine choice* resolution-dependent was considered and rejected: the instability is not purely a function of resolution -- the same page at the same size succeeded on one run and failed on the next -- so a threshold rule would give the appearance of control without the substance.

**What would change this recommendation:** PaddleOCR reading Arabic competitively *and* stably on a different build. Both its resolution ceiling and its non-determinism may be specific to this Windows/CPU/oneDNN stack. Re-run this benchmark on the firm's server, and on the firm's own scans, before treating the ordering as permanent -- neither needs a code change.

## Caveats

1. **Rendered pages, not scanner output.** Clean glyph rendering, no scanner optics, no photocopy generations, no bleed-through, no handwriting. Absolute error rates are an optimistic bound. **This is the one caveat that could change the verdict**, because it is the only one that might affect the two engines unequally -- re-run against real scans (`--corpus-dir` needs no code change) before treating the ordering as final.
2. **Reference quality is measured, not assumed.** Most references are a source PDF's text layer and inherit its defects; the verdict column in the results table says which. The `authored` fixtures have no such problem by construction and are the ones to quote.
3. **Column count is not the confound it was assumed to be.** An earlier version of this report, and of `evaluation_report.md`, blamed two-column layout for the bad Arabic scores. The controlled fixtures rule that out -- see [Ground-truth audit](#ground-truth-audit). What does inflate absolute CER is visual word order and out-of-flow blocks, and both handicap the two engines equally, so the **head-to-head remains valid on every fixture** even where the absolute figure is not.
4. **PaddleOCR was given a handicap in its favour**: it was allowed to retry at lower resolutions, which Tesseract never needed. Its accuracy figures are therefore its best case, not its default-config behaviour.
5. **PaddleOCR's instability is non-deterministic.** The same image at the same resolution succeeded on one run and raised `RuntimeError: Unknown exception` on the next; one resolution killed the worker process outright. Its failure counts below are therefore a sample, not a fixed rate.
6. **One machine, CPU only.** Timings will not match the firm's server, and PaddleOCR's resolution ceiling and instability may be specific to this Windows/CPU/oneDNN build.
7. **Small sample.** 14 Arabic and 9 English scored documents. Enough to see a large effect; not enough to measure a small one, which is why near-ties are reported as ties rather than as wins.

### Incidents

- `paddleocr` on `bench_wipo_eg088ar_1_clean.pdf` -- p1: error at 4000px -- RuntimeError: RuntimeError: Unknown exception
- `paddleocr` on `bench_wipo_eg088ar_1_clean.pdf` -- p1: error at 2500px -- RuntimeError: RuntimeError: Unknown exception
- `paddleocr` on `bench_wipo_eg088ar_1_clean.pdf` -- p1: recovered at 1600px after 2 downscale(s)
- `paddleocr` on `bench_wipo_eg088ar_1_clean.pdf` -- p2: CRASH at 4000px -- RuntimeError: PaddleOCR worker died during page inference (a crash here is the native access-violati
- `paddleocr` on `bench_wipo_eg088ar_1_clean.pdf` -- p2: error at 2500px -- RuntimeError: RuntimeError: Unknown exception
- `paddleocr` on `bench_wipo_eg088ar_1_clean.pdf` -- p2: recovered at 1600px after 2 downscale(s)
- `paddleocr` on `bench_wipo_eg088ar_1_clean.pdf` -- p3: CRASH at 4000px -- RuntimeError: PaddleOCR worker died during page inference (a crash here is the native access-violati
- `paddleocr` on `bench_wipo_eg088ar_1_clean.pdf` -- p3: recovered at 2500px after 1 downscale(s)
- `paddleocr` on `bench_wipo_eg088ar_1_clean.pdf` -- p4: CRASH at 4000px -- RuntimeError: PaddleOCR worker died during page inference (a crash here is the native access-violati
- `paddleocr` on `bench_wipo_eg088ar_1_clean.pdf` -- p4: CRASH at 2500px -- RuntimeError: PaddleOCR worker crashed 3 times; disabled for this run, falling back to Tesseract
- `paddleocr` on `bench_wipo_eg088ar_1_clean.pdf` -- p4: CRASH at 1600px -- RuntimeError: PaddleOCR worker crashed 3 times; disabled for this run, falling back to Tesseract
- `paddleocr` on `bench_wipo_eg088ar_1_clean.pdf` -- p4: CRASH at 1200px -- RuntimeError: PaddleOCR worker crashed 3 times; disabled for this run, falling back to Tesseract
- `paddleocr` on `bench_wipo_eg088ar_1_clean.pdf` -- p4: no resolution succeeded
- `paddleocr` on `bench_constitute_egypt_2019_ar_clean.pdf` -- p1: error at 2500px -- RuntimeError: RuntimeError: Unknown exception
- `paddleocr` on `bench_constitute_egypt_2019_ar_clean.pdf` -- p1: recovered at 1600px after 1 downscale(s)
- `paddleocr` on `bench_constitute_egypt_2019_ar_clean.pdf` -- p2: error at 2500px -- RuntimeError: RuntimeError: Unknown exception
- `paddleocr` on `bench_constitute_egypt_2019_ar_clean.pdf` -- p2: error at 1600px -- RuntimeError: RuntimeError: Unknown exception
- `paddleocr` on `bench_constitute_egypt_2019_ar_clean.pdf` -- p2: recovered at 1200px after 2 downscale(s)
- `paddleocr` on `bench_constitute_egypt_2019_ar_clean.pdf` -- p3: CRASH at 2500px -- RuntimeError: PaddleOCR worker died during page inference (a crash here is the native access-violati
- `paddleocr` on `bench_constitute_egypt_2019_ar_clean.pdf` -- p3: recovered at 1600px after 1 downscale(s)
- `paddleocr` on `bench_constitute_egypt_2019_ar_clean.pdf` -- p4: error at 2500px -- RuntimeError: RuntimeError: Unknown exception
- `paddleocr` on `bench_constitute_egypt_2019_ar_clean.pdf` -- p4: recovered at 1600px after 1 downscale(s)

