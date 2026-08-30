# Does the 150 dpi finding hold on true 300 dpi scans, and on small print?

> Follow-up to [`arabic_preprocess_sweep.md`](arabic_preprocess_sweep.md), testing the two caveats that report raised about its own result.

**The concern.** Half the sweep corpus is natively 150 dpi, so a 300 dpi render was upsampling it -- interpolating pixels carrying no information. If that were the whole story, 150 dpi should stop winning on genuinely 300 dpi scans. And the sweep's print is ~11 pt, where throwing away pixels is cheap; small print is where it should hurt.

**The fixtures.** New authored Arabic legal text (not reused from the corpus), painted onto a **true 300 dpi A4 raster (2480x3508)** at four print sizes, then degraded like a scan (0.4 deg skew, sigma-4 noise, 0.35 px blur, JPEG q88). The reference is authored -- written before the pixels existed -- so it carries none of the publisher defects that inflate absolute CER elsewhere in this project.

Generated: 2026-08-15 22:30:20 | Wall clock: 3.7 min | Tesseract, CPU

## The curves

CER (space-insensitive) per render DPI, per print size. **The paper is 300 dpi in every column** -- only the type gets smaller.

| Render DPI | 7 pt | 9 pt | 11 pt | 14 pt |
|---|---|---|---|---|
| 100 | 0.570 | 0.057 | 0.050 | 0.048 |
| 125 | 0.103 | 0.042 | 0.050 | 0.027 |
| 150 **(shipped)** | 0.042 | 0.034 | 0.014 | 0.037 |
| 175 | 0.024 | 0.030 | 0.024 | **0.010** |
| 200 | 0.039 | 0.027 | **0.009** | 0.018 |
| 250 | 0.014 | **0.015** | 0.043 | 0.036 |
| 300 *(previous default)* | **0.013** | 0.023 | 0.030 | 0.035 |
| 400 | 0.024 | 0.021 | 0.039 | 0.061 |

Bold marks the best rung for that print size.

## Verdict

- **7 pt:** best rung 300 dpi (CER 0.013). 150 dpi 0.042 vs 300 dpi 0.013 -- **300 dpi wins** (-0.029).
- **9 pt:** best rung 250 dpi (CER 0.015). 150 dpi 0.034 vs 300 dpi 0.023 -- **300 dpi wins** (-0.011).
- **11 pt:** best rung 200 dpi (CER 0.009). 150 dpi 0.014 vs 300 dpi 0.030 -- 150 dpi still wins (+0.016).
- **14 pt:** best rung 175 dpi (CER 0.010). 150 dpi 0.037 vs 300 dpi 0.035 -- the two are level (-0.002).

