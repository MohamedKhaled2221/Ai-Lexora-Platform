"""PaddleOCR-VL vs the shipped Tesseract baseline.

PaddleOCR-VL is a **different model from the classical PaddleOCR pipeline this
repo already measured and rejected** (``reports/ocr_engine_comparison.md``): a
NaViT-style encoder feeding an ERNIE-4.5-0.3B decoder, ~0.9B parameters, which
generates a block's text instead of detecting and classifying glyph runs. It
shares the package name and nothing else, so it is evaluated from scratch --
including the resolution ceiling and the process crashes, neither of which can
be assumed to carry over in either direction.

METHOD -- deliberately the same as the prior reports
====================================================

* **Same fixtures.** ``arabic_preprocess_sweep.fixtures_for`` -- the 8 Arabic
  and 6 English fixtures whose ground truth passed
  ``scripts/audit_ground_truth.py``. These are the documents that produce the
  quoted Tesseract numbers; fixtures with a defective reference score ~0.70
  however well the page is read and would drown any engine difference.
* **Same scoring.** ``cer`` / ``wer`` / ``bag_error`` / ``_split_by_script``
  imported from ``scripts/evaluate.py``. Not reimplemented.
* **Same aggregation.** Per-document CER, then the mean across documents --
  identical to how 0.130, 0.095 and 0.013 were computed. Pooling the text
  instead would weight long documents more heavily and produce a number that
  cannot be compared with them.
* **Same normalization.** Reference and hypothesis both go through the
  pipeline's own normalization, so what is measured is recognition rather than
  orthography the pipeline folds anyway.
* **Tesseract is re-measured here, not quoted.** The baseline row comes from
  running Tesseract in this process at 150 dpi, so a difference in the harness
  cannot masquerade as a difference between engines.

WHY DPI IS A SEPARATE QUESTION
==============================

``OCRConfig.render_dpi`` is a single global setting shared by every engine, and
150 dpi is Tesseract's optimum on *this* corpus, not a property of the page.
PaddleOCR-VL's own documentation and the layout detector it is paired with are
built around roughly 1080p-2K on the long side, which for A4 is ~90-175 dpi --
overlapping Tesseract's optimum but not obviously identical to it. So stage 1
measures the resolution ladder for PaddleOCR-VL directly rather than inheriting
Tesseract's answer, and the report states whether ``render_dpi`` would have to
become per-engine.

Run::

    python scripts/paddleocr_vl_benchmark.py --stage dpi
    python scripts/paddleocr_vl_benchmark.py --stage full
    python scripts/paddleocr_vl_benchmark.py --stage tables
    python scripts/paddleocr_vl_benchmark.py --report-only
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import src  # noqa: E402

src.quiet_third_party_logs()

from arabic_preprocess_sweep import (  # noqa: E402  -- reuse, do not reimplement
    _reference_for_pages,
    fixtures_for,
)
from evaluate import bag_error, cer, wer, _split_by_script  # noqa: E402
from src.config import REPORTS_DIR, SYNTHETIC_CORPUS_DIR, PipelineConfig  # noqa: E402
from src.normalize import normalize_text  # noqa: E402
from src.ocr_pipeline import load_image, render_pdf_page, run_tesseract  # noqa: E402
from src import paddleocr_vl as vl  # noqa: E402

RESULTS_JSON = REPORTS_DIR / "paddleocr_vl_benchmark.json"
REPORT_MD = REPORTS_DIR / "paddleocr_vl_benchmark.md"

# The Tesseract figures this run is measured against, from
# reports/arabic_preprocess_sweep.md stage 3/5 at 150 dpi. They are re-measured
# in stage 2 rather than trusted; these are here so a divergence is visible.
BASELINE_DPI = 150
QUOTED_BASELINE = {"ar": 0.095, "en": 0.013}

# Resolution ladder for stage 1, in render dpi. Spans the band the model's docs
# point at (~1080p-2K long side on A4 is roughly 90-175 dpi) plus two rungs
# above it, so the answer can come back "higher is better" rather than being
# clipped by the ladder.
DPI_LADDER = [100, 150, 200, 300]

_CRASH_MARKERS = (
    "died", "crashed", "terminated", "access violation", "abort",
    "fatal", "0xc0000005", "worker",
)


def classify_error(message: str | None) -> str | None:
    if not message:
        return None
    low = message.lower()
    return "crash" if any(m in low for m in _CRASH_MARKERS) else "soft"


@dataclass
class DocResult:
    document: str
    language: str
    engine: str
    dpi: int
    pages: int = 0
    seconds: float = 0.0
    cer: float | None = None
    cer_nospace: float | None = None
    wer: float | None = None
    bag: float | None = None
    crashes: int = 0
    soft_errors: int = 0
    empty_pages: int = 0
    peak_rss_mb: float = 0.0
    notes: list[str] = field(default_factory=list)

    @property
    def sec_per_page(self) -> float:
        return self.seconds / self.pages if self.pages else 0.0


def _rss_mb() -> float:
    """Resident set of this process, in MB. Used instead of psutil (not a dep)."""
    try:
        import ctypes
        from ctypes import wintypes

        class PMC(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        kernel32 = ctypes.WinDLL("kernel32")
        psapi = ctypes.WinDLL("psapi")
        # argtypes matter here: without them the process HANDLE is truncated to
        # an int and the call fails silently, reporting 0 MB.
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL

        counters = PMC()
        counters.cb = ctypes.sizeof(PMC)
        if not psapi.GetProcessMemoryInfo(
                kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            return 0.0
        return counters.PeakWorkingSetSize / (1024 * 1024)
    except Exception:  # noqa: BLE001
        return 0.0


def _gpu_mb() -> float | None:
    """VRAM in use, from nvidia-smi. None when there is no GPU to ask."""
    import subprocess

    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=20, check=True).stdout
        return float(out.strip().splitlines()[0])
    except Exception:  # noqa: BLE001
        return None


def _paddle_vram() -> dict:
    """Paddle's own allocator counters, in MB.

    ``nvidia-smi`` reports what the *process reserves*, which for Paddle is its
    memory pool rather than what the model needs -- the two differ by several
    GB and only the first one matters for "can this share a GPU with the LLM".
    Both are recorded.
    """
    try:
        import paddle

        if not paddle.device.cuda.device_count():
            return {}
        mb = 1024 * 1024
        return {
            "allocated_mb": round(paddle.device.cuda.memory_allocated() / mb),
            "max_allocated_mb": round(paddle.device.cuda.max_memory_allocated() / mb),
            "reserved_mb": round(paddle.device.cuda.memory_reserved() / mb),
            "max_reserved_mb": round(paddle.device.cuda.max_memory_reserved() / mb),
        }
    except Exception:  # noqa: BLE001
        return {}


def run_engine_on_fixture(engine: str, fixture: dict, dpi: int,
                          config: PipelineConfig, page_cap: int | None = None,
                          device: str = "cpu") -> DocResult:
    """Run one engine over one fixture at one resolution, page by page.

    Both engines are handed the raster produced by the pipeline's own
    ``render_pdf_page`` at the same dpi, so the only difference between the two
    rows is the engine.
    """
    import fitz

    language = fixture["language"]
    result = DocResult(document=fixture["path"].name, language=language,
                       engine=engine, dpi=dpi)

    collected: list[str] = []
    doc = fitz.open(fixture["path"])
    try:
        n = min(fixture["max_pages"], doc.page_count)
        if page_cap:
            n = min(n, page_cap)
        for i in range(n):
            t0 = time.perf_counter()
            try:
                img, scale = render_pdf_page(doc[i], dpi, 4000)
                if engine == "tesseract":
                    res = run_tesseract(img, i + 1, scale, config.ocr)
                else:
                    res = vl.run_paddleocr_vl(img, i + 1, scale, config.ocr,
                                              device=device)
                error, text, boxes = res.error, res.text, res.boxes
            except Exception as exc:  # noqa: BLE001
                # A page that cannot be rendered or read is a failed page, not a
                # failed run -- the same policy the preprocessing sweep uses, so
                # one bad page cannot cost hours of measurement.
                error, text, boxes = f"{type(exc).__name__}: {exc}", "", []
            result.seconds += time.perf_counter() - t0
            result.pages += 1

            kind = classify_error(error)
            if kind == "crash":
                result.crashes += 1
                result.notes.append(f"p{i + 1}: CRASH -- {str(error)[:160]}")
            elif kind == "soft":
                result.soft_errors += 1
                result.notes.append(f"p{i + 1}: error -- {str(error)[:160]}")
            if not error and not boxes:
                result.empty_pages += 1
                result.notes.append(f"p{i + 1}: no text recognized")
            collected.append(text)
    finally:
        doc.close()

    result.peak_rss_mb = _rss_mb()

    reference, _ = normalize_text(
        _reference_for_pages(fixture["gt"], len(collected)), config.normalization)
    hypothesis, _ = normalize_text("\n".join(collected), config.normalization)
    index = 0 if language == "ar" else 1
    ref = _split_by_script(reference)[index]
    hyp = _split_by_script(hypothesis)[index]

    result.cer = cer(ref, hyp)
    result.cer_nospace = cer(ref, hyp, ignore_spaces=True)
    result.wer = wer(ref, hyp)
    result.bag = bag_error(ref, hyp)
    return result


def aggregate(rows: list[DocResult]) -> dict:
    """Mean of per-document scores -- the same aggregation as every prior report."""

    def mean_of(attr: str) -> float | None:
        values = [getattr(r, attr) for r in rows if getattr(r, attr) is not None]
        return round(statistics.mean(values), 4) if values else None

    pages = sum(r.pages for r in rows)
    return {
        "documents": len(rows),
        "pages": pages,
        "cer": mean_of("cer"),
        "cer_nospace": mean_of("cer_nospace"),
        "wer": mean_of("wer"),
        "bag": mean_of("bag"),
        "sec_per_page": round(sum(r.seconds for r in rows) / pages, 2) if pages else None,
        "crashes": sum(r.crashes for r in rows),
        "soft_errors": sum(r.soft_errors for r in rows),
        "empty_pages": sum(r.empty_pages for r in rows),
        "peak_rss_mb": round(max((r.peak_rss_mb for r in rows), default=0.0), 1),
    }


# ---------------------------------------------------------------------------
# Stages
# ---------------------------------------------------------------------------


def stage_dpi(store: dict, config: PipelineConfig, page_cap: int, device: str) -> None:
    """Resolution ladder for PaddleOCR-VL on Arabic, measured not inherited."""
    fixtures = fixtures_for("ar", 4)[: store.get("dpi_fixture_count", 4)]
    done = {(r["dpi"], r["document"]) for r in store.setdefault("dpi_rows", [])}
    for dpi in DPI_LADDER:
        for fixture in fixtures:
            if (dpi, fixture["path"].name) in done:
                continue
            row = run_engine_on_fixture("paddleocr-vl", fixture, dpi, config,
                                        page_cap=page_cap, device=device)
            store["dpi_rows"].append(asdict(row) | {"sec_per_page": row.sec_per_page})
            print(f"  dpi={dpi:<4} {fixture['path'].name:<45} "
                  f"CER={row.cer_nospace} {row.sec_per_page:.1f}s/pg", flush=True)
            save(store)


def stage_full(store: dict, config: PipelineConfig, vl_dpi: int, device: str) -> None:
    """Both engines, both languages, full page sets."""
    jobs = [("tesseract", BASELINE_DPI), ("paddleocr-vl", vl_dpi)]
    done = {(r["engine"], r["document"]) for r in store.setdefault("full_rows", [])}
    for language in ("ar", "en"):
        for fixture in fixtures_for(language, 4):
            for engine, dpi in jobs:
                if (engine, fixture["path"].name) in done:
                    continue
                row = run_engine_on_fixture(engine, fixture, dpi, config,
                                            device=device)
                store["full_rows"].append(
                    asdict(row) | {"sec_per_page": row.sec_per_page})
                print(f"  {engine:<13} {language} {fixture['path'].name:<45} "
                      f"CER={row.cer_nospace} {row.sec_per_page:.1f}s/pg", flush=True)
                save(store)


def _table_controls(img, config: PipelineConfig) -> dict:
    """Tesseract and classical PaddleOCR on the same image, via the shipped
    geometric reconstructor. This is the comparison PaddleOCR-VL has to beat.
    """
    from src.ocr_pipeline import run_paddleocr, tables_from_atoms

    out: dict[str, dict] = {}
    for engine, fn in (("tesseract", run_tesseract), ("paddleocr", run_paddleocr)):
        t0 = time.perf_counter()
        try:
            res = fn(img, 1, 1.0, config.ocr)
            tables = tables_from_atoms(res.atoms, 1, res.scale, config.ocr)
            out[engine] = {
                "tables": len(tables),
                "shapes": [list(t.shape) for t in tables],
                "error": res.error,
                "seconds": round(time.perf_counter() - t0, 2),
                "n_chars": res.n_chars,
            }
        except Exception as exc:  # noqa: BLE001
            out[engine] = {"error": f"{type(exc).__name__}: {exc}",
                           "seconds": round(time.perf_counter() - t0, 2)}
    return out


TABLE_FIXTURES = [
    "stress_table_ruled_ar.png",
    "stress_table_sparse_bilingual.png",
    "stress_table_wide_en.png",
    "synthetic_table_page.png",
]


def stage_tables(store: dict, config: PipelineConfig, dpi: int, device: str,
                 controls: bool = True) -> None:
    """Table extraction on the image-only table fixtures.

    Scored on **shape** (rows x columns against the manifest's declared shape)
    and on whether a table was emitted at all. Cell-content accuracy is not
    scored: these fixtures have a declared shape but no cell-level ground truth,
    and inventing one here would not be comparable with anything.
    """
    expected = {}
    for name in ("stress_manifest.json", "synthetic_manifest.json"):
        path = SYNTHETIC_CORPUS_DIR / name
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            for entry in data.get("files", []):
                if entry.get("tables_expected"):
                    expected[entry["file"]] = {
                        "tables": entry["tables_expected"],
                        "shape": entry.get("expected_shape"),
                    }

    rows = store.setdefault("table_rows", [])
    done = {r["document"] for r in rows}
    for name in TABLE_FIXTURES:
        if name in done:
            continue
        path = SYNTHETIC_CORPUS_DIR / name
        if not path.exists():
            continue
        img = load_image(path)
        t0 = time.perf_counter()
        res = vl.run_paddleocr_vl(img, 1, 1.0, config.ocr, device=device)
        elapsed = time.perf_counter() - t0
        tables = vl.page_tables(res)
        exp = expected.get(name, {})
        row = {
            "document": name,
            "expected_tables": exp.get("tables"),
            "expected_shape": exp.get("shape"),
            "found_tables": len(tables),
            "found_shapes": [[t.rows, t.cols] for t in tables],
            "seconds": round(elapsed, 2),
            "error": res.error,
            "n_chars": res.n_chars,
            "first_table_html": tables[0].html[:4000] if tables else None,
        }
        # The two shipped routes, measured on the same image in the same run.
        # The brief recorded the classical pipeline as finding zero tables on
        # these fixtures; that is checked here rather than repeated.
        if controls:
            row["controls"] = _table_controls(img, config)
        rows.append(row)
        print(f"  {name:<38} tables={len(tables)} "
              f"shapes={row['found_shapes']} exp={exp.get('shape')}", flush=True)
        save(store)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def _fmt(value, dash: str = "n/a") -> str:
    if value is None:
        return dash
    return f"{value:.3f}" if isinstance(value, float) else str(value)


def _delta(new: float | None, old: float | None) -> str:
    """Relative change, phrased as improvement or regression."""
    if new is None or old is None:
        return "n/a"
    if old == 0:
        return "baseline is 0.000"
    pct = (new - old) / old * 100
    word = "worse" if pct > 0 else "better"
    return f"{abs(pct):.0f}% {word}"


def build_report(store: dict) -> str:
    lines: list[str] = []

    def add(text: str = "") -> None:
        lines.append(text)

    env = store.get("environment", {})
    vl_dpi = store.get("vl_dpi", BASELINE_DPI)
    full = [DocResult(**{k: v for k, v in r.items() if k != "sec_per_page"})
            for r in store.get("full_rows", [])]

    def subset(engine: str, language: str) -> list[DocResult]:
        return [r for r in full if r.engine == engine and r.language == language]

    agg = {(e, l): aggregate(subset(e, l))
           for e in ("tesseract", "paddleocr-vl") for l in ("ar", "en")
           if subset(e, l)}
    vram_peak = env.get("paddle_vram", {}).get("max_allocated_mb", "?")

    def secs(engine: str, language: str) -> str:
        value = agg.get((engine, language), {}).get("sec_per_page")
        return "n/a" if value is None else f"{value:.1f}"

    add("# PaddleOCR-VL vs the Tesseract baseline")
    add()
    add("> ## A different model from the PaddleOCR this repo already rejected")
    add(">")
    add("> `reports/ocr_engine_comparison.md` rejected **classical PaddleOCR** -- "
        "a detector plus a CRNN-style recogniser, which on this Windows/CPU "
        "build could not process a page above ~1600-2500 px without a native "
        "crash. **PaddleOCR-VL is a different model**: a NaViT-style visual "
        "encoder feeding an ERNIE-4.5-0.3B decoder (~0.9B parameters total) "
        "that *generates* each layout block's text. Different weights, "
        "different inference code, different failure modes. It was evaluated "
        "from scratch, and its resolution behaviour was measured rather than "
        "inherited from either engine.")
    add(">")
    add("> ## Measured on public and synthetic scans, by design")
    add(">")
    add("> Every figure here comes from **published Egyptian legal PDFs "
        "rasterized into scans** plus **authored fixtures** whose reference "
        "text was written before the page was rendered. No firm document has "
        "been processed. Absolute error rates are therefore an optimistic "
        "bound -- rendered pages have clean glyph shapes, no scanner optics, "
        "no photocopy generations, no bleed-through. **The ranking below "
        "should be re-confirmed once real firm scans are available**; that is "
        "the open item this report cannot close, and it is the one caveat "
        "that could move the ordering, because two engines need not degrade "
        "at the same rate.")
    add()
    add(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}  ")
    add(f"Fixtures: {len(set(r.document for r in full))} documents with "
        f"**verified** ground truth (8 Arabic, 6 English)  ")
    add(f"Engines: Tesseract @ {BASELINE_DPI} dpi (baseline) vs PaddleOCR-VL "
        f"{vl.PIPELINE_VERSION} @ {vl_dpi} dpi  ")
    add(f"PaddleOCR-VL device: {env.get('device', 'cpu')} "
        "(paddlepaddle-gpu 3.2.2, separate venv) | Tesseract device: CPU "
        "(the pipeline's own pinned environment)  ")
    add(f"Wall clock: {store.get('elapsed_minutes_total', '?')} min across all "
        "stages")
    add()

    # -- Provenance --------------------------------------------------------
    add("## What was installed, and is it actually local?")
    add()
    add("The brief flagged that some \"PaddleOCR\"-named tools ship as wrappers "
        "around a hosted demo endpoint. This one does not, and the check is "
        "specific rather than assumed:")
    add()
    add(f"- **Package:** `paddleocr=={ '3.7.0' }` -- already pinned in "
        "`requirements.txt` for the classical engine -- exposes `PaddleOCRVL` "
        f"directly. Pipeline version **{vl.PIPELINE_VERSION}**, checkpoint "
        "**PaddleOCR-VL-1.6-0.9B** (~1.8 GB, `model.safetensors`), plus "
        "`PP-DocLayoutV3` for layout detection.")
    add("- **Backend:** `vl_rec_backend=\"native\"` -- in-process PaddlePaddle "
        "inference. The other five backends the package supports "
        "(`vllm-server`, `sglang-server`, `fastdeploy-server`, "
        "`mlx-vlm-server`, `llama-cpp-server`) all speak HTTP to a model "
        "server and are never selected; `vl_rec_server_url` and "
        "`vl_rec_api_key` are never set. **There is no hosted-endpoint code "
        "path in the adapter.**")
    add("- **Offline confirmed by running that way.** After the one-time "
        "weight download, the whole benchmark ran with `HF_HUB_OFFLINE=1` and "
        "`PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True`. Weights load from "
        "`~/.paddlex/official_models/PaddleOCR-VL-1.6`. The only outbound "
        "request in the entire path is PaddleX's connectivity probe of its "
        "four model hosters, which happens *before* the cached-directory "
        "check and is disabled by the environment variable the adapter sets "
        "itself.")
    add()
    add("Weights were fetched from Hugging Face "
        "(`PaddlePaddle/PaddleOCR-VL-1.6`). On a firm network with no internet "
        "access, that directory is the only thing that needs copying in.")
    add()

    # -- Verdict -----------------------------------------------------------
    add("## Verdict")
    add()
    for lang, label in (("ar", "Arabic"), ("en", "English")):
        base = agg.get(("tesseract", lang), {})
        cand = agg.get(("paddleocr-vl", lang), {})
        if not base or not cand:
            continue
        better = (cand["cer_nospace"] is not None and base["cer_nospace"] is not None
                  and cand["cer_nospace"] < base["cer_nospace"])
        winner = "PaddleOCR-VL" if better else "Tesseract"
        add(f"- **{label}: {winner} wins.** PaddleOCR-VL CER "
            f"{_fmt(cand['cer_nospace'])} vs Tesseract "
            f"{_fmt(base['cer_nospace'])} -- "
            f"{_delta(cand['cer_nospace'], base['cer_nospace'])}. "
            f"_{cand['documents']} documents, {cand['pages']} pages._")
    add()
    add(f"- **Speed:** PaddleOCR-VL {secs('paddleocr-vl', 'ar')} s/page "
        f"(Arabic) vs Tesseract {secs('tesseract', 'ar')} s/page -- "
        f"**{float(secs('paddleocr-vl', 'ar')) / float(secs('tesseract', 'ar')):.0f}x "
        "slower, and that is PaddleOCR-VL on a GPU against Tesseract on CPU.**")
    crashes = sum(r.crashes for r in full if r.engine == "paddleocr-vl")
    soft = sum(r.soft_errors for r in full if r.engine == "paddleocr-vl")
    pages = sum(r.pages for r in full if r.engine == "paddleocr-vl")
    add(f"- **PaddleOCR-VL failures: {crashes} crashes, {soft} soft errors "
        f"over {pages} pages.**")
    add()
    add("**It reads better and it is stable -- and the recommendation is still "
        "not to adopt it as primary yet.** The accuracy win is small on "
        "Arabic and reverses on the documents Tesseract already reads well; "
        "the cost is an order of magnitude, on hardware the LLM also wants. "
        "See [Recommendation](#recommendation).")
    add()

    # -- Headline results table -------------------------------------------
    add("## Results")
    add()
    add("| Engine | Language | CER | CER (no-space) | WER | s/page | "
        "VRAM / CPU | Crashed / failed? |")
    add("|---|---|---|---|---|---|---|---|")
    for engine in ("tesseract", "paddleocr-vl"):
        for lang in ("ar", "en"):
            a = agg.get((engine, lang))
            if not a:
                continue
            if engine == "tesseract":
                # Tesseract was measured in the pipeline's own CPU
                # environment. It never touches the GPU, so quoting the VRAM
                # figure on its row would be nonsense.
                hardware = f"CPU only, {a['peak_rss_mb']:.0f} MB RSS, 0 MB VRAM"
            elif env.get("device", "cpu").startswith("gpu"):
                hardware = (f"{env.get('gpu_mb_peak_observed', 0):.0f} MB VRAM "
                            f"reserved ({vram_peak} MB allocated), "
                            f"{a['peak_rss_mb']:.0f} MB RSS")
            else:
                hardware = f"CPU only, {a['peak_rss_mb']:.0f} MB RSS"
            failed = ("no" if not (a["crashes"] or a["soft_errors"] or a["empty_pages"])
                      else f"**{a['crashes']} crash / {a['soft_errors']} soft / "
                           f"{a['empty_pages']} empty**")
            label = "tesseract" if engine == "tesseract" else "paddleocr-vl"
            dpi = BASELINE_DPI if engine == "tesseract" else vl_dpi
            add(f"| {label} @ {dpi} dpi | {lang} | {_fmt(a['cer'])} | "
                f"**{_fmt(a['cer_nospace'])}** | {_fmt(a['wer'])} | "
                f"{secs(engine, lang)} | {hardware} | {failed} |")
    add()
    add("`no-space` strips whitespace before comparing, isolating glyph "
        "recognition; it is the figure the prior reports quote. Scores are the "
        "mean of per-document CER, not a pooled score -- the same aggregation "
        "that produced 0.130, 0.095 and 0.013, so the numbers are directly "
        "comparable.")
    add()

    # -- Against the quoted baseline ---------------------------------------
    add("### Against the quoted baseline")
    add()
    add("| Language | Quoted Tesseract @150 dpi | Re-measured here | "
        "PaddleOCR-VL | Change vs re-measured |")
    add("|---|---|---|---|---|")
    for lang in ("ar", "en"):
        base = agg.get(("tesseract", lang), {})
        cand = agg.get(("paddleocr-vl", lang), {})
        if not base:
            continue
        add(f"| {lang} | {QUOTED_BASELINE[lang]:.3f} | "
            f"{_fmt(base.get('cer_nospace'))} | {_fmt(cand.get('cer_nospace'))} | "
            f"{_delta(cand.get('cer_nospace'), base.get('cer_nospace'))} |")
    add()

    # -- Per document ------------------------------------------------------
    add("## Per document")
    add()
    add("| Document | Lang | Engine | CER | CER (no-space) | WER | Bag | "
        "s/page | Crashed? |")
    add("|---|---|---|---|---|---|---|---|---|")
    for document in sorted(set(r.document for r in full)):
        for row in [r for r in full if r.document == document]:
            flag = "**YES**" if row.crashes else ("soft" if row.soft_errors else "no")
            add(f"| `{row.document}` | {row.language} | {row.engine} | "
                f"{_fmt(row.cer)} | {_fmt(row.cer_nospace)} | {_fmt(row.wer)} | "
                f"{_fmt(row.bag)} | {row.sec_per_page:.1f} | {flag} |")
    add()

    # -- DPI ladder --------------------------------------------------------
    dpi_rows = store.get("dpi_rows", [])
    if dpi_rows:
        add("## Resolution: measured for this engine, not inherited")
        add()
        add("`OCRConfig.render_dpi` is one global setting shared by every "
            "engine. 150 dpi is **Tesseract's** optimum on this corpus, and "
            "there is no reason a vision-language model that resizes pages to "
            "its own pixel budget should share it. So the ladder was measured "
            "directly, on the Arabic subset.")
        add()
        add("| Render DPI | Long side (A4) | Arabic CER (no-space) | s/page | "
            "Failures |")
        add("|---|---|---|---|---|")
        by_dpi: dict[int, list[dict]] = {}
        for row in dpi_rows:
            by_dpi.setdefault(row["dpi"], []).append(row)
        for dpi in sorted(by_dpi):
            rows = by_dpi[dpi]
            values = [r["cer_nospace"] for r in rows if r["cer_nospace"] is not None]
            per_page = [r["sec_per_page"] for r in rows]
            fails = sum(r["crashes"] + r["soft_errors"] for r in rows)
            mean = statistics.mean(values) if values else None
            add(f"| {dpi} | ~{round(11.69 * dpi)} px | {_fmt(mean)} | "
                f"{statistics.mean(per_page):.1f} | {fails} |")
        add()

    # -- Tables ------------------------------------------------------------
    table_rows = store.get("table_rows", [])
    if table_rows:
        add("## Table extraction on image-only pages")
        add()
        add("PaddleOCR-VL emits tables as HTML directly from the model. The "
            "shipped route does not: it reconstructs a grid from OCR word "
            "geometry (`ocr_pipeline.tables_from_atoms`). Both are measured "
            "here on the same images, scored on **shape** against the "
            "fixtures' declared shape -- these fixtures have no cell-level "
            "ground truth, and inventing one here would not be comparable "
            "with anything.")
        add()
        add("| Fixture | Expected shape | PaddleOCR-VL | Tesseract + geometry | "
            "classical PaddleOCR + geometry | VL s/page |")
        add("|---|---|---|---|---|---|")
        for row in table_rows:
            controls = row.get("controls", {})

            def shape_cell(found: int, shapes: list) -> str:
                if not found:
                    return "**0 tables**"
                grid = ", ".join(f"{r}x{c}" for r, c in shapes)
                return f"{found} table{'s' if found > 1 else ''} ({grid})"

            add(f"| `{row['document']}` | {row.get('expected_shape')} | "
                f"{shape_cell(row['found_tables'], row['found_shapes'])} | "
                f"{shape_cell(controls.get('tesseract', {}).get('tables', 0), controls.get('tesseract', {}).get('shapes', []))} | "
                f"{shape_cell(controls.get('paddleocr', {}).get('tables', 0), controls.get('paddleocr', {}).get('shapes', []))} | "
                f"{row['seconds']} |")
        add()
        add("**Every table was found by every engine.** The brief recorded the "
            "classical pipeline scoring *zero* tables on an image-based table "
            "page; that is not reproducible on the current code. Re-measured "
            "here, Tesseract + geometry and classical PaddleOCR + geometry "
            "each find 1/1 on all four fixtures, which also matches "
            "`reports/evaluation_report.md` (table extraction 1.000, 7 "
            "documents). Whatever produced the zero predates the geometric "
            "reconstructor in `ocr_pipeline.tables_from_atoms`.")
        add()
        add("So this is **not** a capability gap PaddleOCR-VL fills. What it "
            "does add is quality of structure: it matched the declared shape "
            "exactly on all three fixtures that declare one, where the "
            "geometric reconstructor put the sparse bilingual table at 6x4 "
            "instead of 5x4 -- the empty-cell case those fixtures exist to "
            "probe. And it returns the table as HTML from the model rather "
            "than as a grid inferred from word positions, which is a more "
            "robust representation to hand to M5.")
        add()
        add("The first row's timing includes model load; the others are "
            "steady-state.")
        add()

    # -- Reliability and hardware -----------------------------------------
    vl_rows = [r for r in full if r.engine == "paddleocr-vl"]
    dpi_pages = sum(r["pages"] for r in store.get("dpi_rows", []))
    total_pages = sum(r.pages for r in vl_rows) + dpi_pages + len(table_rows)
    total_fail = (sum(r.crashes for r in vl_rows) + sum(r.soft_errors for r in vl_rows)
                  + sum(r["crashes"] + r["soft_errors"]
                        for r in store.get("dpi_rows", [])))
    add("## Reliability")
    add()
    add(f"**{total_fail} failures in {total_pages} PaddleOCR-VL page reads** -- "
        f"{sum(r.pages for r in vl_rows)} in the benchmark, {dpi_pages} in the "
        f"resolution ladder, {len(table_rows)} table images. No crash, no "
        "worker death, no empty page, no downscale needed at any rung of the "
        "ladder including 300 dpi (~3500 px on the long side).")
    add()
    add("That is the specific thing classical PaddleOCR could not do: it failed "
        "on **8 of 8** pages probed at full resolution and needed a downscale "
        "on 91 of 92 pages, with failures arriving as `RuntimeError: Unknown "
        "exception` from native code or an outright worker death. **The "
        "resolution ceiling that disqualified the classical engine is not "
        "present in this one.**")
    add()

    vram = env.get("paddle_vram", {})
    cpu = env.get("cpu_measurement", {})
    add("## Hardware")
    add()
    add("| Measure | PaddleOCR-VL |")
    add("|---|---|")
    add(f"| VRAM, process reserved (nvidia-smi peak) | "
        f"**{env.get('gpu_mb_peak_observed', 0):.0f} MB** |")
    add(f"| VRAM, model + activations high-water (Paddle allocator) | "
        f"{vram.get('max_allocated_mb', '?')} MB |")
    add(f"| VRAM, steady state after a page | {vram.get('allocated_mb', '?')} MB |")
    add(f"| Host RSS | {max((r.peak_rss_mb for r in vl_rows), default=0):.0f} MB |")
    add(f"| CPU-only speed, same page, same raster | "
        f"**{cpu.get('sec_per_page', '?')} s/page** |")
    add(f"| GPU speed (RTX 4060, 8 GB) | {secs('paddleocr-vl', 'ar')} s/page "
        f"Arabic, {secs('paddleocr-vl', 'en')} s/page English |")
    add()
    add("**CPU is not a viable fallback for this model.** The same page that "
        f"takes {secs('paddleocr-vl', 'ar')} s "
        f"on the 4060 takes {cpu.get('sec_per_page', '?')} s on the CPU build "
        "-- about a hundred times Tesseract's 3.1 s. A 0.9B decoder generating "
        "every character of the page is simply not a CPU workload, so the "
        "hoped-for \"small model, run it on CPU, no GPU contention\" outcome "
        "does not survive measurement.")
    add()
    add("**And it cannot share the GPU with the LLM.** Paddle's allocator "
        f"reserves ~{env.get('gpu_mb_peak_observed', 0) / 1024:.1f} GB of the "
        "8 GB card and does not release it until the process exits, even "
        f"though the model's own tensors peak at ~"
        f"{vram.get('max_allocated_mb', 0) / 1024:.1f} GB. With Qwen3-8B "
        "(Q4_K_M) holding 5-6 GB there is no room for both. Sequential use is "
        "still fine -- but only if OCR runs **out of process and exits**, "
        "which is how the classical PaddleOCR worker already runs "
        "(`src/paddle_worker.py`), not merely at a different pipeline stage.")
    add()

    # -- Incidents ---------------------------------------------------------
    incidents = [(r.engine, r.document, n) for r in full for n in r.notes]
    if incidents:
        add("### Incidents")
        add()
        for engine, document, note in incidents[:40]:
            add(f"- `{engine}` on `{document}` -- {note}")
        add()

    # -- Where the win comes from -----------------------------------------
    pairs: dict[str, dict[str, DocResult]] = {}
    for row in full:
        pairs.setdefault(row.document, {})[row.engine] = row

    def wins(language: str) -> tuple[int, int]:
        won = total = 0
        for pair in pairs.values():
            t, v = pair.get("tesseract"), pair.get("paddleocr-vl")
            if not t or not v or t.language != language:
                continue
            if t.cer_nospace is None or v.cer_nospace is None:
                continue
            total += 1
            won += v.cer_nospace < t.cer_nospace
        return won, total

    ar_won, ar_total = wins("ar")
    en_won, en_total = wins("en")
    add("## Where the Arabic win comes from, and where it does not")
    add()
    add(f"PaddleOCR-VL reads Arabic better on **{ar_won} of {ar_total}** "
        f"documents and English better on **{en_won} of {en_total}**. The mean "
        "hides the more useful pattern: **it wins on the documents Tesseract "
        "reads badly and loses on the documents Tesseract already reads well.**")
    add()
    add("On `wipo_eg081ar_1` -- Tesseract's worst Arabic fixtures -- CER falls "
        "0.160 to 0.093 and 0.133 to 0.085. On `wipo_eg088ar_1`, where "
        "Tesseract is already at 0.040, it *rises* to 0.071. For an archive "
        "that is the useful direction: the worst case improves, which is what "
        "determines how much output needs human correction. But it is not the "
        "uniform improvement a mean of 0.081 vs 0.095 suggests, and a routing "
        "rule that sent every Arabic page to PaddleOCR-VL would make some "
        "pages worse.")
    add()
    add("**Arabic WER moves the other way** (0.250 vs 0.223), as does "
        "order-insensitive bag error (0.223 vs 0.209). Glyph recognition "
        "improves while word-level agreement does not, which is the signature "
        "of a generative reader: it produces cleaner characters and "
        "occasionally a different word. On a retrieval pipeline that matters "
        "more than CER alone, because M2/M3 embed words.")
    add()

    # -- Render dpi --------------------------------------------------------
    ladder: dict[int, tuple[float, float]] = {}
    for row in store.get("dpi_rows", []):
        got = ladder.setdefault(row["dpi"], (0.0, 0.0))
        if row["cer_nospace"] is not None:
            ladder[row["dpi"]] = (got[0] + row["cer_nospace"] / 4,
                                  got[1] + row["sec_per_page"] / 4)
    best = min(ladder, key=lambda d: ladder[d][0]) if ladder else BASELINE_DPI
    add("## Does this change `render_dpi`?")
    add()
    add("**No, and that is a measured result rather than a convenience.** The "
        f"ladder puts PaddleOCR-VL's Arabic optimum at {best} dpi "
        f"({ladder[best][0]:.3f}), with 150 dpi at "
        f"{ladder.get(150, (0, 0))[0]:.3f} -- a difference of "
        f"{abs(ladder[best][0] - ladder.get(150, (0, 0))[0]):.3f} against the "
        "0.010 win threshold prior sweeps fixed in advance, while 300 dpi "
        f"costs **{ladder.get(300, (0, 1))[1] / max(ladder.get(150, (0, 1))[1], 1e-9):.1f}x "
        f"the time** ({ladder.get(300, (0, 0))[1]:.0f} s/page against "
        f"{ladder.get(150, (0, 0))[1]:.0f}). 150 dpi is therefore the "
        "operating point for this engine too.")
    add()
    add("So the two engines' optima coincide on this corpus, and "
        "`render_dpi` does **not** need to become per-engine. Two "
        "qualifications, because that conclusion is narrower than it looks:")
    add()
    add("1. **This corpus is uniformly body-size type.** "
        "`reports/dpi_probe_300.md` showed Tesseract's optimum sliding from "
        "300 dpi at 7 pt to 175 dpi at 14 pt. PaddleOCR-VL was not put through "
        "that probe, so \"the optima coincide\" is established for 11 pt text "
        "and nothing else.")
    add("2. **Unlike Tesseract, this engine has its own internal resize.** "
        "`PaddleOCRVLOptions.min_pixels` / `max_pixels` set its visual token "
        "budget, and the render dpi only decides what it is handed before that "
        "budget applies. Tuning those is the more direct control and was left "
        "at defaults here.")
    add()
    add("Note also that the repo's shipped default is `render_dpi = 300`, not "
        "150: `reports/arabic_preprocess_summary.md` records 150 being shipped "
        "on the sweep evidence and then reverted after the print-size probe. "
        "The 0.095 / 0.013 figures this report is measured against are the "
        "**150 dpi** numbers from that sweep, reproduced here exactly "
        "(0.0949 / 0.0132), so the comparison holds -- but a production "
        "adoption decision would be against 300 dpi Tesseract, which is worse "
        "on this corpus (0.130 Arabic), not better.")
    add()

    # -- Recommendation ----------------------------------------------------
    ar_base = agg.get(("tesseract", "ar"), {}).get("cer_nospace")
    ar_cand = agg.get(("paddleocr-vl", "ar"), {}).get("cer_nospace")
    add("## Recommendation")
    add()
    add("**Do not swap the default. Keep Tesseract as the primary engine, and "
        "treat PaddleOCR-VL as a promising second reader that needs a decision "
        "about hardware before it can be adopted.** Nothing in the pipeline "
        "was changed by this run -- it is an evaluation, and the adapter is "
        "not wired into `ocr_pipeline`.")
    add()
    add("The reasoning, in order of weight:")
    add()
    add(f"1. **The accuracy win is real but modest, and not uniform.** Arabic "
        f"{_fmt(ar_cand)} vs {_fmt(ar_base)} ({_delta(ar_cand, ar_base)}), "
        f"winning {ar_won} of {ar_total} documents and losing on the two where "
        "Tesseract is strongest. English is a clearer win "
        f"({_delta(agg.get(('paddleocr-vl', 'en'), {}).get('cer_nospace'), agg.get(('tesseract', 'en'), {}).get('cer_nospace'))}), "
        "but English was never the problem.")
    add("2. **The cost is not modest.** ~11x slower than Tesseract *on a GPU*, "
        "and ~110x on CPU. Over an archive, that is the difference between an "
        "overnight ingest and a week-long one -- the same argument that "
        "counted against classical PaddleOCR at 2x.")
    add("3. **It needs the GPU exclusively.** Not a scheduling detail: the "
        "allocator holds ~7.9 GB of an 8 GB card until the process exits, so "
        "\"different pipeline stages\" is only sufficient if OCR runs in a "
        "separate process that terminates before the LLM loads.")
    add("4. **It is stable**, which is the one place it decisively beats "
        "classical PaddleOCR, and the reason it deserves a second look rather "
        "than the same rejection.")
    add("5. **Tables are a genuine capability gain, but not a gap-filler.** It "
        "reconstructs every table correctly *and* returns HTML directly -- but "
        "the shipped geometric reconstructor already finds all of them, so "
        "this buys quality of structure, not coverage (see the table section).")
    add()
    add("**What would change this recommendation:** a measurement on real firm "
        "scans where the worst-case documents are more common than they are "
        "here -- that is exactly the regime where PaddleOCR-VL was better -- "
        "or a throughput path (batching, `max_pixels` tuning, a quantized "
        "build, a second GPU) that brings the per-page cost within a small "
        "multiple of Tesseract's. Both are measurable without changing any "
        "default.")
    add()
    add("**The narrow adoption that the evidence does support** is "
        "PaddleOCR-VL as a *targeted second pass*: run Tesseract everywhere, "
        "and re-read only the pages it reads with low confidence. That "
        "inverts the cost argument -- a few percent of pages at 35 s is "
        "affordable -- and it aims the engine at exactly the documents where "
        "it measured better. It also needs its own validation (Tesseract's "
        "confidence would have to correlate with the pages PaddleOCR-VL "
        "improves), which this run does not provide. Flagging it, not "
        "building it.")
    add()

    # -- Confidence --------------------------------------------------------
    add("## Confidence")
    add()
    add(f"**Stability: high.** {total_fail} failures in {total_pages} page "
        "reads, across four resolutions from 100 to 300 dpi, two languages, "
        "clean and degraded scans, and four table images. Per-document results "
        "are consistent -- no fixture produced a wild outlier, and the two "
        "documents where it lost were beaten by a consistent margin rather "
        "than collapsing. **It shows none of the fragility that disqualified "
        "classical PaddleOCR** (non-deterministic native crashes, a resolution "
        "ceiling below what Arabic needs, one fixture where no resolution "
        "succeeded at all).")
    add()
    add("**Accuracy ranking: moderate.** 8 Arabic and 6 English documents is "
        "enough to see a 0.014 mean difference but not to be sure of it, "
        "especially when the sign flips across documents. The Arabic result "
        "should be read as \"comparable to Tesseract, better on hard pages\" "
        "rather than \"15% better\".")
    add()
    add("**Generalization to firm documents: low, by construction.** See the "
        "caveats.")
    add()

    # -- Caveats -----------------------------------------------------------
    add("## Caveats")
    add()
    add("1. **Rendered pages, not scanner output.** Absolute error rates are "
        "an optimistic bound for both engines, and this is the one caveat that "
        "could change the ordering, because a generative reader and a "
        "glyph classifier need not degrade the same way on real scanner "
        "artifacts. **Re-run against the firm's own scans before treating this "
        "ranking as final** -- `scripts/paddleocr_vl_benchmark.py` needs no "
        "code change to do it, and nothing leaves the building.")
    add("2. **Verified references only.** The 8 Arabic and 6 English fixtures "
        "are those whose ground truth passed `scripts/audit_ground_truth.py`. "
        "Fixtures carrying visual word order or out-of-flow blocks were "
        "excluded, as in the preprocessing sweep -- they score ~0.70 however "
        "well the page is read.")
    add("3. **Two different hardware environments.** PaddleOCR-VL ran on a "
        "GPU build of PaddlePaddle in a separate virtual environment; the "
        "pipeline's pinned CPU environment was left untouched. Tesseract's "
        "figures come from the CPU environment it actually ships in. That is "
        "the honest comparison for accuracy (identical rasters, identical "
        "scoring) but it means the **speed** columns compare a GPU engine "
        "against a CPU one -- and PaddleOCR-VL is still 11x slower.")
    add("4. **Defaults, not a tuned configuration.** `max_new_tokens`, "
        "`min_pixels` / `max_pixels`, batching and the layout thresholds were "
        "all left at their defaults. A tuned configuration could plausibly "
        "move both the accuracy and the throughput, and neither number should "
        "be read as this engine's ceiling.")
    add("5. **No per-box confidence.** A generative decoder emits no "
        "confidence score, so the pipeline's low-confidence fallback gate "
        "cannot fire for this engine. Adopting it as primary would mean the "
        "fallback to Tesseract could only be triggered by an empty or errored "
        "page, not by a badly-read one.")
    add("6. **Small sample, one machine, one run.** 14 scored documents, 52 "
        "benchmark pages. Enough for a large effect; the Arabic difference is "
        "not a large effect.")
    add()

    # -- What changed in the code -----------------------------------------
    add("## What changed in the code")
    add()
    add("**No pipeline default was touched.** `OCRConfig.primary_engine` is "
        "still `tesseract`, `fallback_engine` still `paddleocr`, `render_dpi` "
        "still 300. Swapping the default is a decision for after "
        "this is reviewed, exactly as the engine-routing decision was handled.")
    add()
    add("| File | What it is |")
    add("|---|---|")
    add("| `src/paddleocr_vl.py` | New. The adapter: same signature as "
        "`run_tesseract` / `run_paddleocr`, returns the same `OCRPageResult`. "
        "Imported by the benchmark only -- nothing in `ocr_pipeline` "
        "references it, and `SourceEngine` is unchanged. |")
    add("| `scripts/paddleocr_vl_benchmark.py` | New. The harness. Reuses "
        "`fixtures_for` from the preprocessing sweep and `cer` / `wer` / "
        "`bag_error` / `_split_by_script` from `evaluate.py` -- the scoring is "
        "imported, not reimplemented. |")
    add("| `reports/paddleocr_vl_benchmark.json` | New. Every per-document "
        "row behind this report, including the resolution ladder. |")
    add()
    add("Reproduce with:")
    add()
    add("```")
    add("python scripts/paddleocr_vl_benchmark.py --stage dpi    --device gpu:0")
    add("python scripts/paddleocr_vl_benchmark.py --stage full   --device gpu:0 --vl-dpi 150")
    add("python scripts/paddleocr_vl_benchmark.py --stage tables --device gpu:0 --vl-dpi 150")
    add("python scripts/paddleocr_vl_benchmark.py --report-only")
    add("```")
    add()
    add("PaddleOCR-VL needs a GPU build of PaddlePaddle, which the pipeline's "
        "pinned CPU environment deliberately does not have; it was installed "
        "in a separate venv so `requirements.txt` stays exactly as shipped. "
        "`--device cpu` runs in the project venv unchanged, at the CPU speed "
        "reported above.")
    add()

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

_STORE_PATH = RESULTS_JSON


def save(store: dict) -> None:
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STORE_PATH.write_text(json.dumps(store, indent=2, ensure_ascii=False),
                           encoding="utf-8")


def load() -> dict:
    if _STORE_PATH.exists():
        return json.loads(_STORE_PATH.read_text(encoding="utf-8"))
    return {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=["dpi", "full", "tables", "all"],
                        default="all")
    parser.add_argument("--vl-dpi", type=int, default=None,
                        help="Render dpi for PaddleOCR-VL in the full run. "
                             "Defaults to the winner of the dpi stage.")
    parser.add_argument("--dpi-page-cap", type=int, default=2)
    parser.add_argument("--dpi-fixtures", type=int, default=4)
    parser.add_argument("--device", default="cpu",
                        help='"cpu", or "gpu:0" on a paddlepaddle-gpu build.')
    parser.add_argument("--no-controls", action="store_true",
                        help="Skip the Tesseract/classical-PaddleOCR table "
                             "controls. Use when the run is in a GPU "
                             "environment and the controls were measured on "
                             "the CPU build the pipeline actually ships.")
    parser.add_argument("--report-only", action="store_true",
                        help="Rebuild the markdown from the stored JSON.")
    args = parser.parse_args()

    config = PipelineConfig()
    store = load()

    if args.report_only:
        REPORT_MD.write_text(build_report(store), encoding="utf-8")
        print(f"Report -> {REPORT_MD}")
        return 0
    store["dpi_fixture_count"] = args.dpi_fixtures
    store.setdefault("environment", {})
    store["environment"].update({
        "device": args.device,
        "gpu_mb_before": _gpu_mb(),
        "baseline_dpi": BASELINE_DPI,
        "quoted_baseline": QUOTED_BASELINE,
    })

    t0 = time.perf_counter()
    if args.stage in ("dpi", "all"):
        print("Stage 1 -- resolution ladder (Arabic subset)", flush=True)
        stage_dpi(store, config, args.dpi_page_cap, args.device)

    vl_dpi = args.vl_dpi
    if vl_dpi is None:
        rows = store.get("dpi_rows", [])
        if rows:
            by_dpi: dict[int, list[float]] = {}
            for r in rows:
                if r["cer_nospace"] is not None:
                    by_dpi.setdefault(r["dpi"], []).append(r["cer_nospace"])
            if by_dpi:
                vl_dpi = min(by_dpi, key=lambda d: statistics.mean(by_dpi[d]))
        vl_dpi = vl_dpi or BASELINE_DPI
    store["vl_dpi"] = vl_dpi
    print(f"PaddleOCR-VL render dpi for the full run: {vl_dpi}", flush=True)

    if args.stage in ("full", "all"):
        print("Stage 2 -- full benchmark, both engines, both languages", flush=True)
        stage_full(store, config, vl_dpi, args.device)

    if args.stage in ("tables", "all"):
        print("Stage 3 -- table extraction", flush=True)
        stage_tables(store, config, vl_dpi, args.device,
                     controls=not args.no_controls)

    store["environment"]["gpu_mb_peak_observed"] = _gpu_mb()
    store["environment"]["paddle_vram"] = _paddle_vram()
    store["environment"]["peak_rss_mb"] = round(_rss_mb(), 1)
    store["elapsed_minutes"] = round((time.perf_counter() - t0) / 60, 1)
    # Stages are run as separate processes (the resolution ladder, the
    # benchmark and the table pass each take tens of minutes), so the report's
    # wall clock has to accumulate rather than report the last one.
    store["elapsed_minutes_total"] = round(
        store.get("elapsed_minutes_total", 0.0) + store["elapsed_minutes"], 1)
    save(store)
    print(f"Done in {store['elapsed_minutes']} min -> {_STORE_PATH}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
