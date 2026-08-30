# Arabic OCR preprocessing sweep

> ## Preprocessing only, Arabic only
> 
> This sweep changes **what image Tesseract is handed** and nothing else. Engine selection, the fallback policy, structure detection and the visual-order reference defect are all out of scope and untouched. **No English default was changed.** English fixtures are *read* by the stage 5 regression guard -- because `render_dpi` is a shared setting and a change recommended on Arabic evidence has to be checked against English before it can ship -- but no English fixture takes part in choosing a winner.
> 
> Measured on the **eight Arabic fixtures whose ground truth passed `scripts/audit_ground_truth.py`** -- the same eight that produce the **CER 0.130** baseline in `reports/ocr_engine_comparison.md`. Fixtures with a defective reference are excluded: they score ~0.70 however well the page is read, and no preprocessing setting can move that.

Generated: 2026-08-15 22:34:07  
Combinations measured: 74  
Wall clock: 142.8 min | Tesseract only, CPU, no GPU  
Screening pages/document: 2 | Confirmation: full page set

## Verdict

**Baseline (current production settings): CER 0.130**, 3.9 s/page.

**Best measured combination: `150dpi + no-binar + unsharp` -- CER 0.077**, 2.8 s/page, clean.

That is **41% fewer character errors** than the current defaults: CER 0.130 -> 0.077, a 0.053 absolute reduction.

## What was changed, and what was not

**Nothing was shipped. `OCRConfig.render_dpi` stays at 300.**

It was briefly changed to 150 on the evidence below -- Arabic CER 0.130 -> 0.095 (27% fewer errors), English 0.021 -> 0.013, and *faster* at 2.8 s/page against 3.9 -- and then changed back, because that evidence does not generalize. See [`dpi_probe_300.md`](dpi_probe_300.md): on fresh authored fixtures built on a **true 300 dpi raster** at four print sizes, the optimum slides from 300 dpi at 7 pt type to 175 dpi at 14 pt. At 7 pt -- footnote and schedule size, which legal documents are full of -- 150 dpi is **3.2x worse** than 300 (0.042 vs 0.013) and 100 dpi collapses entirely (0.570).

**The regression on small print is the same size as the gain on body text**, so a single global DPI cannot be right for an archive containing both. 300 dpi is kept because its worst case is the bounded one: small print fails loudly at low resolution, while body text merely underperforms slightly at high resolution. The real answer is to choose resolution per page from the type size on it -- flagged as a follow-up in `arabic_preprocess_summary.md`, not guessed at here.

Everything below is still valid **for body-size Arabic type**, which is what this corpus contains throughout. It is the generalization that failed, not the measurement.

**Also not shipped: the unsharp mask.** `150 dpi + unsharp` scores 0.077, better still. It is left off because the evidence does not survive inspection:

- It beats plain 150 dpi on **4 of 8 documents** -- a coin flip. Its mean advantage comes mostly from one fixture (`scan_authored_statute_ar_150dpi`, 0.120 -> 0.021).
- It is **confined to a narrow resolution band**. Probed at full page count, unsharp changes CER by -0.018 at 150 dpi and -0.015 at 175 dpi, but +0.001 at 100 dpi, +0.002 at 200 dpi and -0.001 at 300 dpi. A real sharpening benefit would not switch itself off two rungs either side.

It is flagged rather than taken because this sweep set its threshold for a win in advance, and 'wins on half the corpus, inside a two-rung window' does not clear it. The module ships ready for it either way: `ocr.preprocess.enabled = True` with `contrast = "unsharp"`.

**Also not shipped:** binarization of any kind (no method beat handing Tesseract grayscale -- it runs its own Otsu internally and does it better than we can from outside), and deskew (neutral-to-negative on every base combination; these fixtures carry ~1.2 degrees of introduced skew, which Tesseract's own `--psm 1` OSD already handles).

## Stage 3 -- confirmation (full page set, quotable)

These are the only numbers directly comparable with the 0.130 baseline: same documents, same page counts, same scoring, same normalization.

| # | Combination | CER (no-space) | CER | WER | vs baseline | s/page | Stability |
|---|---|---|---|---|---|---|---|
| 1 | `150dpi + no-binar + unsharp` | **0.077** | 0.077 | 0.206 | -0.053 | 2.8 | clean |
| 2 | `100dpi + no-binar + unsharp` | **0.082** | 0.081 | 0.212 | -0.049 | 2.5 | clean |
| 3 | `175dpi + no-binar + unsharp` | **0.084** | 0.084 | 0.211 | -0.046 | 3.0 | clean |
| 4 | `150dpi + no-binar` | **0.095** | 0.095 | 0.223 | -0.035 | 2.8 | clean |
| 5 | `300dpi/max1600 + no-binar + deskew` | **0.110** | 0.110 | 0.239 | -0.020 | 2.8 | clean |
| 6 | `200dpi + no-binar + unsharp` | **0.114** | 0.115 | 0.248 | -0.016 | 3.2 | clean |
| 7 | `300dpi + no-binar + unsharp` | **0.129** | 0.129 | 0.262 | -0.002 | 4.0 | clean |
| 8 | `300dpi/max4000 + no-binar` **(production)** | **0.130** | 0.130 | 0.258 | baseline | 3.9 | clean |

## Stage 4 -- the resolution curve (full page set, quotable)

Resolution on its own, everything else off, at full page count. The screening stage said resolution dominates and favours the *low* end -- the opposite of this sweep's premise -- and a single winning rung is not enough to act on that. This is the shape of the axis rather than one point on it.

| Render DPI | Long side (A4) | CER (no-space) | vs baseline | s/page | Stability |
|---|---|---|---|---|---|
| 75 | ~877 px | 0.126 | -0.004 | 2.2 | clean |
| 100 | ~1169 px | 0.081 | -0.049 | 2.5 | clean |
| 125 | ~1461 px | 0.100 | -0.030 | 2.6 | clean |
| 150 | ~1754 px | 0.095 | -0.035 | 2.8 | clean |
| 175 | ~2046 px | 0.099 | -0.031 | 3.0 | clean |
| 200 | ~2338 px | 0.112 | -0.018 | 3.1 | clean |
| 250 | ~2923 px | 0.117 | -0.013 | 4.3 | clean |
| 300 | ~3508 px | 0.130 | +0.000 | 4.1 | clean |
| 400 | ~4677 px | 0.114 | -0.016 | 4.3 | clean |

**The curve turns.** The optimum is **100 dpi** (CER 0.081); below it accuracy falls away again (75 dpi scores 0.126). That is what an optimum looks like, and it is the check that matters: a curve still improving at the bottom of the ladder, where Arabic body text is a few pixels tall, would have meant the measurement was broken rather than that low resolution is good.

## Stage 5 -- English regression guard

`render_dpi` is **not an Arabic-only setting** -- it is the whole OCR path's, and language is not known until after the page has been read. So a resolution change recommended on Arabic evidence has to be checked against English before it can ship. This stage measures the English fixtures with verified ground truth; it changes nothing about the English pipeline, and no English default was touched.

| Combination | English CER (no-space) | vs English baseline | s/page |
|---|---|---|---|
| `175dpi + no-binar + unsharp` | 0.002 | -0.019 | 2.9 |
| `300dpi/max1600 + no-binar + deskew` | 0.003 | -0.018 | 2.9 |
| `150dpi + no-binar + unsharp` | 0.011 | -0.010 | 2.8 |
| `100dpi + no-binar + unsharp` | 0.011 | -0.010 | 3.1 |
| `150dpi + no-binar` | 0.013 | -0.008 | 2.7 |
| `300dpi/max4000 + no-binar` | 0.021 | baseline | 3.8 |

**No English regression.** Every combination scored here is within noise of, or better than, the English baseline -- so the recommended setting can be a global default rather than requiring per-language routing.

## All combinations, best to worst

**Stage 1 and 2 rows rank; they do not measure.** They are computed over 2 page(s) per document rather than the full set, so their absolute CER is not comparable with the baseline -- only with each other. Every combination in a stage saw identical pages.

| # | Combination | Stage | CER (no-space) | s/page | Preproc ms/page | Stability |
|---|---|---|---|---|---|---|
| 1 | `150dpi + no-binar + unsharp` | 3 | 0.077 | 2.8 | 4 | clean |
| 2 | `100dpi + no-binar` | 4 | 0.081 | 2.5 | 0 | clean |
| 3 | `100dpi + no-binar + unsharp` | 3 | 0.082 | 2.5 | 29 | clean |
| 4 | `175dpi + no-binar + unsharp` | 3 | 0.084 | 3.0 | 5 | clean |
| 5 | `150dpi + no-binar` | 3 | 0.095 | 2.8 | 0 | clean |
| 6 | `150dpi + no-binar` | 4 | 0.095 | 2.8 | 0 | clean |
| 7 | `175dpi + no-binar` | 4 | 0.099 | 3.0 | 0 | clean |
| 8 | `125dpi + no-binar` | 4 | 0.100 | 2.6 | 0 | clean |
| 9 | `300dpi/max1600 + no-binar + deskew` | 3 | 0.110 | 2.8 | 80 | clean |
| 10 | `200dpi + no-binar` | 4 | 0.112 | 3.1 | 0 | clean |
| 11 | `400dpi + no-binar` | 4 | 0.114 | 4.3 | 0 | clean |
| 12 | `200dpi + no-binar + unsharp` | 3 | 0.114 | 3.2 | 6 | clean |
| 13 | `250dpi + no-binar` | 4 | 0.117 | 4.3 | 0 | clean |
| 14 | `75dpi + no-binar` | 4 | 0.126 | 2.2 | 0 | clean |
| 15 | `300dpi + no-binar + unsharp` | 3 | 0.129 | 4.0 | 10 | clean |
| 16 | `300dpi/max4000 + no-binar` | 3 | 0.130 | 3.9 | 0 | clean |
| 17 | `300dpi + no-binar` | 4 | 0.130 | 4.1 | 0 | clean |
| 18 | `300dpi/max1600 + no-binar + deskew` | 2 | 0.148 | 2.7 | 79 | clean |
| 19 | `150dpi + no-binar` | 1 | 0.148 | 2.7 | 0 | clean |
| 20 | `150dpi + no-binar + unsharp` | 2 | 0.152 | 2.8 | 5 | clean |
| 21 | `150dpi + otsu` | 1 | 0.153 | 2.5 | 6 | clean |
| 22 | `150dpi + no-binar + deskew + unsharp` | 2 | 0.156 | 3.0 | 93 | clean |
| 23 | `150dpi + no-binar + deskew` | 2 | 0.157 | 2.9 | 97 | clean |
| 24 | `150dpi + no-binar + deskew + clahe` | 2 | 0.158 | 3.0 | 98 | clean |
| 25 | `150dpi + otsu + deskew` | 2 | 0.158 | 2.7 | 99 | clean |
| 26 | `150dpi + otsu + deskew + clahe` | 2 | 0.159 | 2.6 | 85 | clean |
| 27 | `300dpi/max1600 + no-binar` | 1 | 0.160 | 2.6 | 0 | clean |
| 28 | `200dpi + adaptive31c10` | 1 | 0.160 | 2.7 | 21 | clean |
| 29 | `300dpi/max1600 + otsu` | 1 | 0.160 | 2.6 | 3 | clean |
| 30 | `150dpi + adaptive61c15` | 1 | 0.160 | 2.5 | 20 | clean |
| 31 | `300dpi/max1600 + adaptive31c10` | 1 | 0.160 | 2.6 | 11 | clean |
| 32 | `300dpi/max1600 + no-binar + deskew + unsharp` | 2 | 0.162 | 2.7 | 82 | clean |
| 33 | `200dpi + global200` | 1 | 0.163 | 2.6 | 3 | clean |
| 34 | `200dpi + adaptive61c15` | 1 | 0.163 | 2.7 | 36 | clean |
| 35 | `150dpi + no-binar + clahe` | 2 | 0.164 | 2.7 | 5 | clean |
| 36 | `400dpi + no-binar` | 1 | 0.164 | 4.1 | 0 | clean |
| 37 | `150dpi + otsu + clahe` | 2 | 0.165 | 2.4 | 7 | clean |
| 38 | `300dpi/max1600 + no-binar + deskew + clahe` | 2 | 0.165 | 2.7 | 81 | clean |
| 39 | `300dpi/max1600 + global200` | 1 | 0.165 | 2.4 | 2 | clean |
| 40 | `150dpi + otsu + unsharp` | 2 | 0.165 | 2.5 | 7 | clean |
| 41 | `150dpi + otsu + deskew + unsharp` | 2 | 0.166 | 2.7 | 102 | clean |
| 42 | `150dpi + global200` | 1 | 0.167 | 2.5 | 3 | clean |
| 43 | `150dpi + adaptive31c10` | 1 | 0.169 | 2.5 | 13 | clean |
| 44 | `300dpi/max1600 + no-binar + clahe` | 2 | 0.171 | 2.6 | 4 | clean |
| 45 | `300dpi/max1600 + no-binar + unsharp` | 2 | 0.174 | 2.6 | 3 | clean |
| 46 | `300dpi/max1600 + adaptive61c15` | 1 | 0.180 | 2.5 | 20 | clean |
| 47 | `600dpi + no-binar` | 1 | 0.180 | 5.5 | 0 | 35 MP raster |
| 48 | `200dpi + no-binar` | 1 | 0.182 | 3.1 | 0 | clean |
| 49 | `300dpi/max4000 + global200` | 1 | 0.182 | 2.8 | 5 | clean |
| 50 | `400dpi + otsu` | 1 | 0.183 | 3.6 | 16 | clean |
| 51 | `400dpi + global200` | 1 | 0.185 | 3.4 | 9 | clean |
| 52 | `300dpi/max4000 + no-binar` | 1 | 0.187 | 3.7 | 0 | clean |
| 53 | `300dpi/max1600 + global160` | 1 | 0.187 | 2.6 | 2 | clean |
| 54 | `300dpi/max4000 + otsu` | 1 | 0.187 | 3.1 | 9 | clean |
| 55 | `300dpi/max4000 + adaptive61c15` | 1 | 0.188 | 3.1 | 78 | clean |
| 56 | `200dpi + otsu` | 1 | 0.190 | 2.6 | 5 | clean |
| 57 | `600dpi + otsu` | 1 | 0.190 | 4.6 | 35 | 35 MP raster |
| 58 | `600dpi + global200` | 1 | 0.200 | 4.7 | 19 | 35 MP raster |
| 59 | `600dpi + adaptive61c15` | 1 | 0.201 | 5.0 | 316 | 35 MP raster |
| 60 | `300dpi/max4000 + global160` | 1 | 0.206 | 3.0 | 5 | clean |
| 61 | `200dpi + global160` | 1 | 0.207 | 2.7 | 4 | clean |
| 62 | `150dpi + global160` | 1 | 0.208 | 2.5 | 3 | clean |
| 63 | `400dpi + adaptive61c15` | 1 | 0.211 | 3.5 | 142 | clean |
| 64 | `300dpi/max4000 + adaptive31c10` | 1 | 0.212 | 3.1 | 46 | clean |
| 65 | `600dpi + global160` | 1 | 0.221 | 4.6 | 18 | 35 MP raster |
| 66 | `400dpi + global160` | 1 | 0.222 | 3.5 | 9 | clean |
| 67 | `400dpi + adaptive31c10` | 1 | 0.306 | 3.5 | 85 | clean |
| 68 | `600dpi + adaptive31c10` | 1 | 0.534 | 3.9 | 191 | **3 blank page(s)**, 35 MP raster |

## What each axis actually did

### Resolution

Binarization, deskew and contrast held off; resolution is the only thing varying.

| Render | Long side (A4) | Mean CER over binarizations | Best CER at this resolution | s/page | Stability |
|---|---|---|---|---|---|
| 150 dpi, uncapped | ~1754 px | 0.168 | 0.148 | 2.5 | clean |
| 200 dpi, uncapped | ~2338 px | 0.177 | 0.160 | 2.7 | clean |
| 300 dpi, capped 4000 px | ~3508 px | 0.194 | 0.182 | 3.1 | clean |
| 400 dpi, uncapped | ~4677 px | 0.212 | 0.164 | 3.6 | clean |
| 600 dpi, uncapped | ~7016 px | 0.254 | 0.180 | 4.7 | clean |
| 300 dpi, capped 1600 px | ~1600 px | 0.169 | 0.160 | 2.5 | clean |

### Binarization

| Method | Mean CER over resolutions | Best CER | s/page |
|---|---|---|---|
| `no-binar` | 0.170 | 0.148 | 3.6 |
| `global200` | 0.177 | 0.163 | 3.1 |
| `otsu` | 0.177 | 0.153 | 3.2 |
| `adaptive61c15` | 0.184 | 0.160 | 3.2 |
| `global160` | 0.208 | 0.187 | 3.1 |
| `adaptive31c10` | 0.257 | 0.160 | 3.1 |

### Deskew and contrast

Measured on the shortlisted resolution/binarization combinations only. Each row is compared against the same base combination with both switched off.

| Base combination | Deskew | Contrast | CER (no-space) | vs base | s/page |
|---|---|---|---|---|---|
| `300dpi/max1600 + no-binar` | yes | none | 0.148 | -0.012 | 2.7 |
| `150dpi + no-binar` | no | unsharp | 0.152 | +0.004 | 2.8 |
| `150dpi + no-binar` | yes | unsharp | 0.156 | +0.008 | 3.0 |
| `150dpi + no-binar` | yes | none | 0.157 | +0.009 | 2.9 |
| `150dpi + no-binar` | yes | clahe | 0.158 | +0.010 | 3.0 |
| `150dpi + otsu` | yes | none | 0.158 | +0.006 | 2.7 |
| `150dpi + otsu` | yes | clahe | 0.159 | +0.006 | 2.6 |
| `300dpi/max1600 + no-binar` | yes | unsharp | 0.162 | +0.002 | 2.7 |
| `150dpi + no-binar` | no | clahe | 0.164 | +0.016 | 2.7 |
| `150dpi + otsu` | no | clahe | 0.165 | +0.012 | 2.4 |
| `300dpi/max1600 + no-binar` | yes | clahe | 0.165 | +0.005 | 2.7 |
| `150dpi + otsu` | no | unsharp | 0.165 | +0.012 | 2.5 |
| `150dpi + otsu` | yes | unsharp | 0.166 | +0.013 | 2.7 |
| `300dpi/max1600 + no-binar` | no | clahe | 0.171 | +0.011 | 2.6 |
| `300dpi/max1600 + no-binar` | no | unsharp | 0.174 | +0.015 | 2.6 |

## Per-document CER, confirmation stage

A mean over eight documents can hide a setting that helps six and wrecks two. This is the table that shows it.

| Document | `300dpi/max1600 + no-binar + deskew` | `150dpi + no-binar` | `150dpi + no-binar + unsharp` | `300dpi/max4000 + no-binar` | `100dpi + no-binar + unsharp` | `175dpi + no-binar + unsharp` | `200dpi + no-binar + unsharp` | `300dpi + no-binar + unsharp` |
|---|---|---|---|---|---|---|---|---|
| `bench_wipo_eg081ar_1_clean.pdf` | 0.133 | 0.133 | 0.107 | 0.136 | 0.088 | 0.097 | 0.136 | 0.118 |
| `bench_wipo_eg081ar_1_poor.pdf` | 0.157 | 0.160 | 0.162 | 0.184 | 0.112 | 0.181 | 0.180 | 0.174 |
| `bench_wipo_eg088ar_1_clean.pdf` | 0.039 | 0.040 | 0.035 | 0.047 | 0.047 | 0.046 | 0.054 | 0.054 |
| `bench_wipo_eg088ar_1_poor.pdf` | 0.057 | 0.054 | 0.082 | 0.046 | 0.043 | 0.057 | 0.074 | 0.065 |
| `scan_authored_statute_ar_150dpi.pdf` | 0.169 | 0.120 | 0.021 | 0.274 | 0.086 | 0.011 | 0.210 | 0.245 |
| `scan_authored_statute_ar_300dpi.pdf` | 0.021 | 0.015 | 0.030 | 0.039 | 0.049 | 0.015 | 0.022 | 0.083 |
| `scan_wipo_eg081ar_1_300dpi.pdf` | 0.147 | 0.117 | 0.121 | 0.149 | 0.127 | 0.133 | 0.125 | 0.154 |
| `scan_wipo_eg088ar_1_150dpi.pdf` | 0.161 | 0.121 | 0.060 | 0.168 | 0.102 | 0.133 | 0.114 | 0.136 |

## Trade-offs worth a human decision

_No combination bought a CER improvement at a meaningful cost in speed or stability._

## Incidents

- `600dpi + adaptive31c10` -- bench_wipo_eg088ar_1_poor.pdf p2: no text recognized
- `600dpi + adaptive31c10` -- bench_wipo_eg081ar_1_poor.pdf p1: no text recognized
- `600dpi + adaptive31c10` -- bench_wipo_eg081ar_1_poor.pdf p2: no text recognized

## Caveats

1. **Rendered pages, not scanner output.** Every fixture is a digital page rasterized and degraded with skew, noise and JPEG artifacts. That models compression and geometry, not scanner optics, photocopy generations or bleed-through. **Preprocessing is exactly the kind of intervention whose value depends on that gap** -- deskew has little to correct on a page whose skew we introduced ourselves at a known small angle, and binarization has little to fix on clean synthetic ink. A setting that is a wash here could still earn its place on real scans. Re-run against `test_corpus/real` when it exists; no code change is needed.
2. **Eight documents.** Enough to see a large effect, not enough to resolve a small one -- hence the 0.010 CER threshold for calling anything a win, set before the sweep ran.
3. **Stage 1 and 2 numbers rank, they do not measure.** They use fewer pages per document than the baseline. Only stage 3 is quotable.
4. **Space-insensitive CER is the headline**, as in the engine benchmark: several references have fragmented word boundaries, and a space-sensitive comparison charges OCR for them. Both are tabulated.
5. **One machine, CPU only.** Timings will not match the firm's server, but the *ratios* between combinations will hold.

