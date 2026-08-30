# Arabic OCR preprocessing — what we tested, what won, what changed

**One-line result:** no preprocessing setting is worth shipping, and **the
defaults end up unchanged**. Binarization, deskew and sharpening were all neutral
or harmful. Render resolution *does* matter — a lot — but the best value depends
on the print size on the page, so a single global DPI cannot capture it, and 300
dpi stays as the setting whose worst case is bounded.

> **This conclusion reversed mid-investigation, and the reversal is the most
> useful thing in this document.** On the benchmark corpus, 150 dpi cut Arabic
> CER from 0.130 to 0.095 (27% fewer errors) while running 30% faster, and we
> shipped it. A follow-up probe on true 300 dpi paper at four print sizes then
> showed that advantage inverting on small print — at 7 pt, 150 dpi is **3.2×
> worse** than 300 dpi, and 100 dpi stops reading the page at all. The gain and
> the regression are the same size. We reverted.

Detail: [`arabic_preprocess_sweep.md`](arabic_preprocess_sweep.md) (the sweep),
[`dpi_probe_300.md`](dpi_probe_300.md) (the print-size probe).
Reproduce with `python scripts/arabic_preprocess_sweep.py` and
`python scripts/dpi_probe_300.py`.

---

## What was tested

74 combinations over four axes, Tesseract only, on the **eight Arabic fixtures
whose ground truth passed the reference audit** — the same eight that produce
the 0.130 baseline in the engine comparison, scored by the same imported
functions with the same normalization on both sides.

| Axis | Levels tested |
|---|---|
| Resolution | 75 / 100 / 125 / 150 / 175 / 200 / 250 / 300 / 400 / 600 dpi, plus a 1600 px downscale control |
| Binarization | none, Otsu, global (threshold 160 and 200), adaptive Gaussian (block 31/c10 and 61/c15) |
| Deskew | off / on (projection-profile auto-straightening) |
| Contrast | off / light unsharp mask / CLAHE |

Staged design — screening, refinement, full-page confirmation, a standalone
resolution ladder, and an English regression guard — rather than a
216-combination full factorial that would have cost ~7 hours mostly measuring
interactions between settings that do nothing. Sweep runtime ~2.9 hours; the
follow-up probe ~10 minutes.

## Result 1 — the benchmark corpus says 150 dpi

| Combination | Arabic CER | vs baseline | s/page | Stability |
|---|---|---|---|---|
| 150 dpi + unsharp mask | 0.077 | −41% | 2.8 | clean |
| 100 dpi, no preprocessing | 0.081 | −38% | 2.5 | clean |
| 150 dpi, no preprocessing | 0.095 | −27% | 2.8 | clean |
| 300 dpi + 1600 px downscale + deskew | 0.110 | −15% | 2.8 | clean |
| **300 dpi, no preprocessing** ← **the default, kept** | **0.130** | baseline | **3.9** | clean |

Nothing crashed, hung or timed out anywhere between 100 and 400 dpi. The only
stability finding in the whole sweep was **600 dpi + adaptive threshold (block
31)**, which returned three completely blank pages — the block is smaller than a
glyph at that resolution, so the inside of every stroke reads as background.

English was scored as a regression guard (it shares `render_dpi`, and language
isn't known until after a page is read): it *also* improved at 150 dpi, 0.021 →
0.013. No English default was touched.

This is a real, reproducible effect, and it is the opposite of what we
commissioned the sweep to check — we expected downscaling to be destroying the
dots that separate ب / ت / ث. Three things say it is genuine: the curve **turns**
at the bottom (75 dpi is bad again, so it is an optimum rather than a broken
metric); **glyph size explains it** (at 300 dpi these pages hand Tesseract a
median word box of 40–57 px, above the range its line recogniser works in, and
the embedded rasters are 150–300 dpi so the extra pixels are interpolation, not
information); and **bag error moves with CER** (0.238 → 0.209), so it is
recognition improving, not reading order getting luckier.

## Result 2 — a true 300 dpi document says it depends on the print size

The sweep corpus is ~11 pt throughout, and half of it is natively 150 dpi. So we
built fresh authored fixtures — new Arabic legal text on a **true 300 dpi A4
raster (2480×3508)** — at four print sizes, and ran the same ladder.

CER by render DPI. **The paper is 300 dpi in every column**; only the type shrinks.

| Render DPI | 7 pt | 9 pt | 11 pt | 14 pt |
|---|---|---|---|---|
| 100 | 0.570 | 0.057 | 0.050 | 0.048 |
| 125 | 0.103 | 0.042 | 0.050 | 0.027 |
| 150 | 0.042 | 0.034 | **0.014** | 0.037 |
| 175 | 0.024 | 0.030 | 0.024 | **0.010** |
| 200 | 0.039 | 0.027 | **0.009** | 0.019 |
| 250 | **0.014** | **0.016** | 0.043 | 0.036 |
| 300 | **0.013** | 0.023 | 0.030 | 0.035 |
| 400 | 0.024 | 0.021 | 0.039 | 0.061 |

**The optimum slides from 300 dpi at 7 pt to 175 dpi at 14 pt.** At 7 pt — the
size of footnotes, schedules and gazette notices, which legal documents are full
of — 150 dpi costs 0.029 CER against 300, as much as it gains on body text, and
100 dpi collapses outright. Above 11 pt the curve is flat and noisy (±0.02) and
the "low DPI wins" preference is barely distinguishable from jitter.

Read together: the 0.130 → 0.095 win is real **for the material it was measured
on**, and that material is uniformly body-size type.

## What we decided, and why

**Keep `render_dpi = 300`.** Not because it is optimal — it isn't, on either
corpus — but because its worst case is bounded. Small print fails loudly at low
DPI; body text merely underperforms slightly at high DPI. We cannot see the
firm's archive, and that asymmetry decides it.

**Ship nothing else.** Binarization lost across the board: none beat handing
Tesseract raw grayscale, which makes sense — it runs its own Otsu internally and
does it better from the inside than we can from outside, where we throw away the
grayscale it wants. Deskew was neutral-to-negative everywhere; `--psm 1` OSD
already corrects the ~1.2° these fixtures carry. The unsharp mask looked good
(0.077) but wins on only **4 of 8 documents**, draws most of its mean advantage
from one fixture, and exists only in a two-rung window (−0.018 at 150 dpi,
−0.015 at 175, but ±0.002 at 100, 200 and 300). A real sharpening benefit would
not switch itself off two rungs either side.

## The follow-up worth doing

**Choose the render resolution per page from the type size on it.** That is what
both results are pointing at, and neither number is a substitute for it. A cheap
version: render at 150, read the page, take the median word-box height, and
re-render at 300 only if it is below a threshold — paying double on small-print
pages, which are the minority, and nothing elsewhere. On this evidence it would
land near the best rung of both corpora at once.

It needs its own validation and should not be guessed at inside a preprocessing
sweep. Flagging it, not building it.

## What changed in the code

| File | Change |
|---|---|
| `src/config.py` | New `PreprocessConfig` — every swept knob, **all off by default**. `render_dpi` unchanged at 300, with both measurements recorded in its docstring |
| `src/preprocess.py` | New. Binarization, deskew, contrast. Inert unless enabled |
| `src/ocr_pipeline.py` | Calls preprocessing after the blank-page gate; records what it did in the engine log |
| `scripts/arabic_preprocess_sweep.py` | New. The sweep harness |
| `scripts/dpi_probe_300.py` | New. The print-size probe |
| `tests/test_preprocess.py` | New. 21 tests |
| `scripts/ocr_benchmark.py` | Two bug fixes found while regenerating reports — a broken blockquote, and the report printing the *current* DPI instead of the DPI its stored run used |

**No behavioural default changed.** The preprocessing module ships inert, so the
pipeline reads pages exactly as it did before this work; what is new is that the
settings now exist, are measured, and can be flipped in one line.

**Test suite: 372 passing, 0 failing** (351 before, plus the 21 new ones). The
task brief said 274 — the suite has grown since that number was recorded.

## Caveats worth stating at the meeting

1. **Rendered pages, not scanner output.** Preprocessing is precisely the kind of
   intervention whose value depends on that gap. Deskew has little to correct on
   a page whose skew we introduced ourselves at a known small angle, and
   binarization little to fix on clean synthetic ink. **Settings that are a wash
   here could still earn their place on real scans** — both scripts re-run
   unchanged against `test_corpus/real`.
2. **The print-size probe is synthetic type, not scanned small print.** Real 7 pt
   on a photocopied page will be worse than this models, which if anything
   strengthens the case for keeping 300.
3. **Eight documents in the sweep, two pages per probe fixture.** Enough for a
   0.035 effect, not for a 0.010 one — which is why 0.010 was fixed as the win
   threshold before the sweep ran.
4. **`reports/ocr_engine_comparison.md` remains current**, since the default it
   was measured at did not move. Its engine ordering never depended on the render
   setting anyway: both engines are handed identical rasters.

## Out of scope, unchanged

OCR engine selection and routing, structure-detection regex, and the
visual-order Arabic bug. All three remain open follow-ups.
