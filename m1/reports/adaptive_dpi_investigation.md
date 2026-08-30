# Adaptive per-page render DPI -- investigation

**Status: investigation only. No pipeline code changed. `OCRConfig.render_dpi` remains 300.**

Generated 2026-08-20. Question: could choosing render DPI per page beat the fixed
global `render_dpi = 300`?

**Verdict in one line:** the hypothesis as posed (*pick DPI from the page's glyph
size*) is **not implementable cheaply** -- glyph size is not readable before
rendering, and probing for it costs more than it saves. But a *different*
predictor found in the same stored data -- **the native resolution of the source
raster, readable from PDF metadata in ~14 ms/file** -- separates the per-document
optima cleanly (p = 0.014) and yields a low-risk rule worth prototyping.

## What this investigation cost

**Zero new OCR.** Every accuracy number below is re-analysis of
`reports/arabic_preprocess_sweep.json` (74 variants, 8 fixtures, 8570 s to
produce) and `reports/dpi_probe_300.json`. The only new measurement was a
**PDF-metadata read of 8 fixtures, 0.11 s total**, which renders nothing.

## 1. What per-page data already existed

**None. The stored granularity is per-document, not per-page.** The sweep's
`per_document` map is document-level CER; there is no per-page breakdown in any
`reports/*.json`.

Two corrections to the brief's premises, both material:

- **The sweep does not report median word-box height.** The px column in
  `arabic_preprocess_sweep.md` (`~877 px`, `~1754 px`, `~3508 px`) is the **A4
  page long side** at each DPI, not glyph size. No glyph-size measurement is
  stored or computed anywhere in the repo. The "40-57 px at 300 dpi" figure has
  no source in this codebase. There is therefore no measurement code to reuse.

- **The sweep's DPI curve is contaminated across stages.** Stage 1/2 rows use 2
  pages/document; stage 3/4 use 4. Six parameter sets appear twice with
  identical config and different page counts. On
  `scan_wipo_eg088ar_1_150dpi.pdf` the same config scores **0.704 on pages 1-2
  and 0.121 on pages 1-4**. All analysis below is restricted to **stage 4**
  (consistent 4 pages/doc, resolution axis only).

That 0.70 -> 0.12 swing is itself a finding: **within-document page-to-page CER
variance (~0.6) dwarfs the entire DPI effect (~0.03-0.24 range per document).**
Any real per-page DPI rule is operating on a much smaller axis than the
page-quality noise it sits inside.

## 2. Feasibility: is glyph-size-driven DPI circular?

**For print size: yes, circular in practice.** All 8 OCR fixtures carry **0
characters of text layer** (measured). That is definitional -- a page with a
usable text layer is routed to `TEXT_LAYER` by `classify_pdf()` and never reaches
OCR. So for exactly the pages this would govern, there is no font metadata to
read. Print size can only be recovered by rendering and detecting text.

Cost of a probe render, from `dpi_probe_300.json`:

| approach | s/page |
|---|---|
| probe at 100 dpi (detection) | 2.05 |
| probe at 150 dpi | 2.27 |
| full run, fixed 300 dpi | 3.68 |

A 100 dpi probe costs **2.05 s/page** before the real pass begins. The entire
saving available from dropping 300 -> 175 dpi is **1.16 s/page**. **The probe
costs ~1.8x the gain it enables.** Glyph-size-driven adaptive DPI is not viable
on this evidence.

**For native scan resolution: no, not circular, and effectively free.** The
embedded raster's pixel dimensions and the page's point size are both in the PDF
dictionary. Measured on all 8 fixtures:

| fixture | page pts | raster px | native dpi | text chars |
|---|---|---|---|---|
| bench_wipo_eg081ar_1_clean | 595x842 | 2480x3508 | 300 | 0 |
| bench_wipo_eg081ar_1_poor | 595x842 | 1240x1754 | 150 | 0 |
| bench_wipo_eg088ar_1_clean | 595x842 | 2480x3509 | 300 | 0 |
| bench_wipo_eg088ar_1_poor | 595x842 | 1240x1755 | 150 | 0 |
| scan_authored_statute_ar_150dpi | 595x842 | 1240x1754 | 150 | 0 |
| scan_authored_statute_ar_300dpi | 595x842 | 2480x3508 | 300 | 0 |
| scan_wipo_eg081ar_1_300dpi | 595x842 | 2480x3508 | 300 | 0 |
| scan_wipo_eg088ar_1_150dpi | 595x842 | 1240x1755 | 150 | 0 |

**0.11 s for all 8 files (~14 ms/file), no rendering.** `classify_pdf()` already
calls `page.get_image_info()` per page for its raster-area ratio, so the data is
already being fetched on the existing routing path.

## 3. Does glyph size predict the optimal DPI?

**Print size predicts it, but only when source resolution is held constant --
and the two have been measured separately, never together.**

`dpi_probe_300.md` varied print size on a fixed 300 dpi paper. Its optima land on
a strikingly tight invariant -- **glyph height at the chosen render DPI**:

| print size | best rung | glyph px at best rung |
|---|---|---|
| 7 pt | 300 dpi | 29.2 |
| 9 pt | 250 dpi | 31.2 |
| 11 pt | 200 dpi | 30.6 |
| 14 pt | 175 dpi | 34.0 |

Across a 2x range of print size the optimum sits at **29-34 px of glyph height**.
That is a real physical relationship, and it is the strongest quantitative result
in either report.

The sweep varied the other axis: print size roughly constant (~11 pt, per
`dpi_probe_300.py`), source resolution varying. Per-document optima, stage 4:

| document | native dpi | best rung | CER range | adj. jitter | jitter/range |
|---|---|---|---|---|---|
| bench_wipo_eg081ar_1_clean | 300 | 125 | 0.086 | 0.023 | 0.26 |
| bench_wipo_eg088ar_1_clean | 300 | 150 | 0.037 | 0.007 | 0.19 |
| scan_authored_statute_ar_300dpi | 300 | 175 | 0.191 | 0.038 | 0.20 |
| scan_wipo_eg081ar_1_300dpi | 300 | 175 | 0.033 | 0.008 | 0.25 |
| bench_wipo_eg081ar_1_poor | 150 | 75 | 0.053 | 0.017 | 0.32 |
| bench_wipo_eg088ar_1_poor | 150 | 100 | 0.071 | 0.031 | 0.44 |
| scan_authored_statute_ar_150dpi | 150 | 100 | 0.237 | 0.074 | 0.31 |
| scan_wipo_eg088ar_1_150dpi | 150 | 100 | 0.086 | 0.022 | 0.26 |

**Native-150 optima: 75, 100, 100, 100. Native-300 optima: 125, 150, 175, 175.
Zero overlap.** Only 1 of the 70 possible 4/4 splits separates this cleanly, so
p = 0.014 (0.007 for the direction, which was predicted in advance).

The cleanest single comparison is `scan_authored_statute_ar_150dpi` vs
`_300dpi`: **the same authored content at the same print size**, differing only
in raster resolution. Optima 100 vs 175. If print size alone drove the optimum,
these would agree. They do not.

**Plain statement: glyph size in *points* does not predict the optimum. Glyph
size in *source pixels* does** -- and that is `print_size x native_scan_dpi`, of
which only the second factor is cheaply observable. Rendering above the native
resolution is pure upsampling: it adds no information and costs time.

Caveat on strength: adjacent-rung jitter is 19-44% of each curve's range, so any
*individual* document's argmax is uncertain by a rung or two. The group-level
separation is solid; the per-document optimum is not.

## 4. Candidate decision rules

- **Rule A (aggressive):** `render_dpi = 100 if native <= 150 else 175`
- **Rule C (conservative cap):** `render_dpi = min(300, native_scan_dpi)`

Both key on metadata only. Rule C never renders above the source resolution and
never changes behaviour on 300 dpi scans.

## 5. Simulated CER, from already-measured numbers

### Body-text corpus (sweep, ~11 pt, 8 docs x 4 pages)

| document | native | Rule A | Rule C | fixed-300 | fixed-150 |
|---|---|---|---|---|---|
| bench_wipo_eg081ar_1_clean | 300 | 0.154 | 0.136 | 0.136 | 0.133 |
| bench_wipo_eg081ar_1_poor | 150 | 0.159 | 0.160 | 0.184 | 0.160 |
| bench_wipo_eg088ar_1_clean | 300 | 0.043 | 0.047 | 0.047 | 0.040 |
| bench_wipo_eg088ar_1_poor | 150 | 0.033 | 0.054 | 0.046 | 0.054 |
| scan_authored_statute_ar_150dpi | 150 | 0.037 | 0.120 | 0.274 | 0.120 |
| scan_authored_statute_ar_300dpi | 300 | 0.011 | 0.039 | 0.039 | 0.015 |
| scan_wipo_eg081ar_1_300dpi | 300 | 0.116 | 0.149 | 0.149 | 0.117 |
| scan_wipo_eg088ar_1_150dpi | 150 | 0.082 | 0.121 | 0.168 | 0.121 |
| **MEAN** | | **0.080** | **0.103** | **0.130** | **0.095** |

### Small print -- the row 300 dpi exists to protect

`dpi_probe_300` fixtures, all native 300 paper. Rule A sends every one of these
to 175 dpi. Rule C leaves them at 300 dpi, unchanged by construction.

| print size | Rule A (175) | Rule C (300) | fixed-300 | fixed-150 |
|---|---|---|---|---|
| **7 pt** | 0.0236 | **0.0133** | 0.0133 | 0.0421 |
| **9 pt** | 0.0303 | **0.0229** | 0.0229 | 0.0340 |
| 11 pt | 0.0236 | 0.0303 | 0.0303 | 0.0140 |
| 14 pt | 0.0103 | 0.0347 | 0.0347 | 0.0369 |

**Rule A fails the test that matters.** At 7 pt it is 1.8x worse than fixed-300
(0.0236 vs 0.0133) and at 9 pt 1.3x worse. It is better than fixed-150 there, but
"better than the option we already rejected" is not the bar. Rule A repeats the
mistake that caused the original 150 dpi revert, because scan resolution carries
no information about print size.

**Rule C cannot fail it**, because it is identity on 300 dpi scans.

## 6. Throughput

| rule | s/page | note |
|---|---|---|
| fixed-300 | 3.68 | baseline |
| Rule A | 2.29 | 38% faster |
| Rule C | 3.68 on native-300; 2.27 on native-150 | faster only where it also improves CER |

Metadata probe: **~0.014 s/file**, ~0.4% of one page's OCR cost, and largely
already paid inside `classify_pdf()`.

## 7. Recommendation

**Do not implement glyph-size-driven adaptive DPI.** It is circular for scanned
pages -- the only pages it would govern -- and the probe render needed to break
the circularity costs ~1.8x the time it saves.

**Rule C (`render_dpi = min(300, native_scan_dpi)`) is worth prototyping.** On
stored numbers it cuts mean CER 0.130 -> 0.103 (-21%), improves 3 of 4 native-150
documents (one regresses by 0.008), is 38% faster on those pages, and is exactly
identity on 300 dpi scans -- so every small-print result that justifies the
current default is preserved unchanged. It is a strict-dominance argument
(never render above the source resolution), not an accuracy gamble.

**Before shipping even Rule C, three things need checking** -- this is a
prototype recommendation, not a ship recommendation:

1. **n = 8, and there is a confound.** In the `bench_*` pairs, `_clean`/`_poor`
   is perfectly correlated with 300/150 native, so degradation and resolution are
   not separable there. Only the `scan_authored_statute` pair isolates
   resolution cleanly. The real evidence is closer to n = 1 clean pair plus 3
   consistent-but-confounded pairs.
2. **Native DPI in this corpus is only ever 150 or 300**, because the fixtures
   were generated that way. Real firm scans will be 200, 240, 400, 600. The rule
   extrapolates into resolutions never measured.
3. **The corpus is entirely synthetic/public and ~11 pt throughout.** The firm's
   archive is unseen, and the small-print exposure that motivates
   `render_dpi = 300` has never been observed in real material -- only in
   authored probes.

The measurement that would settle it: render a small set of **real** scans at
their native DPI vs 300, with per-page CER recorded per page rather than per
document. At ~4 s/page, 40 pages is under 10 minutes and would be worth far more
than another synthetic sweep.

## Note on an unrelated correctness issue found in passing

`config.py` and `scripts/ocr_benchmark.py` both carried comments describing a
150 dpi default that was reverted. The `paddle_max_side` note claimed the 1600 px
cap "barely engages" -- at the shipped 300 dpi an A4 page is ~3500 px, so it
engages on essentially every page and PaddleOCR sees a materially smaller raster
than Tesseract. Both comments corrected; no behaviour change.
