"""Measure what a batch of documents actually costs, so ``max_batch_documents``
is a measured value rather than a guess.

WHAT IS BEING MEASURED, AND WHY THAT AND NOT SOMETHING ELSE
===========================================================

The pipeline has exactly one thing that can be called a batch:
:func:`src.pipeline.ingest_batch`, which loops over paths **sequentially** and
accumulates every :class:`DocumentIngestResult` in one list. OCR is likewise
sequential -- ``ocr_pipeline.ocr_pdf_pages`` renders and reads one page at a
time and drops the raster before the next -- and Tesseract is CPU-only. So no
batch size in this pipeline ever puts two pages, two documents, or two models
in flight at once.

That leaves **retention**, not concurrency, as the cost of a batch: the results
of every document processed so far stay live in RAM until the whole batch
returns. Batch size therefore controls peak RSS, and nothing else. This probe
measures that directly:

  * peak RSS across the run, sampled from a background thread
  * RSS retained after the batch returns and gc runs (the accumulation itself)
  * peak VRAM, sampled from ``nvidia-smi`` -- expected flat, and recorded so
    that "GPU is not on this path" is a measurement rather than an assertion
  * wall-clock, to show whether it scales linearly or degrades
  * any document that failed

Each batch size runs in a **fresh subprocess** so peaks do not leak between
them. The document list is a fixed mixed pool (text-layer and scanned, Arabic
and English, small and large) cycled to the requested length, so batch size is
the only variable across runs.

Usage::

    python scripts/batch_size_probe.py                    # 1, 5, 10, 25
    python scripts/batch_size_probe.py --sizes 1 5        # quick
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import PUBLIC_CORPUS_DIR, REPORTS_DIR, SYNTHETIC_CORPUS_DIR  # noqa: E402

# A deliberately mixed pool: text-layer PDFs (sub-second/page) and scanned PDFs
# (Tesseract, seconds/page), Arabic and English, 1 to 94 pages. Cycled to reach
# the requested batch size, so a batch of 25 is 25 real documents' worth of
# retained results even though the corpus has fewer distinct files.
POOL = [
    ("public", "wipo_eg087ar_1.pdf"),                     # text, 12p
    ("synthetic", "scan_authored_statute_ar_150dpi.pdf"),  # OCR, 3p
    ("public", "eg_official_gazette_excerpt.pdf"),         # text, 29p
    ("synthetic", "bench_wipo_eg088ar_1_poor.pdf"),        # OCR, 4p
    ("public", "constitute_egypt_2014_ar.pdf"),            # text, 44p
    ("synthetic", "native_authored_award_en.pdf"),         # text, 2p
    ("public", "wipo_eg081ar_1.pdf"),                      # text, 94p (largest)
    ("synthetic", "scan_authored_award_en_150dpi.pdf"),    # OCR, 2p
    ("public", "constitute_egypt_2014_en.pdf"),            # text, 53p
    ("synthetic", "synthetic_contract_bilingual.pdf"),     # text, 3p
]


# A second pool of *fast* text-layer documents only. The mixed pool above is
# dominated by OCR wall-clock, which is fine for the headline question but
# leaves the retention slope buried under the ~1 GB allocator/import floor that
# any run reaches within its first few documents. Running many cheap documents
# instead makes the per-document cost of *accumulating results* visible, which
# is the only thing batch size actually controls.
FAST_POOL = [
    ("synthetic", "native_authored_award_en.pdf"),
    ("synthetic", "native_authored_statute_ar.pdf"),
    ("synthetic", "stress_exhibits_footnotes.pdf"),
    ("synthetic", "stress_inline_bilingual.pdf"),
    ("synthetic", "stress_nested_clauses_ar.pdf"),
    ("synthetic", "stress_table_pagebreak.pdf"),
    ("synthetic", "synthetic_contract_bilingual.pdf"),
    ("public", "eg_constitution_2014_en.pdf"),
    ("public", "wipo_eg088ar_1.pdf"),
    ("public", "constitute_egypt_2019_ar.pdf"),
]


def _resolve_pool(pool=None) -> list[Path]:
    dirs = {"public": PUBLIC_CORPUS_DIR, "synthetic": SYNTHETIC_CORPUS_DIR}
    out = []
    for where, name in (pool or POOL):
        p = dirs[where] / name
        if p.exists():
            out.append(p)
    return out


def batch_paths(n: int, fast: bool = False) -> list[Path]:
    pool = _resolve_pool(FAST_POOL if fast else POOL)
    if not pool:
        raise SystemExit("no corpus documents found -- run scripts/fetch_public_corpus.py")
    return [pool[i % len(pool)] for i in range(n)]


# ---------------------------------------------------------------------------
# sampling
# ---------------------------------------------------------------------------


def _vram_used_mb() -> float | None:
    """Used VRAM in MiB via nvidia-smi, or None when there is no NVIDIA GPU."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode != 0:
            return None
        return float(out.stdout.strip().splitlines()[0])
    except Exception:
        return None


class Sampler(threading.Thread):
    """Poll a **different** process's RSS tree (and VRAM) and keep the maxima.

    Sampling from *outside* the measured process is not a stylistic choice --
    the first version of this probe sampled from a thread inside the worker and
    under-reported peak RSS by roughly 5x (271 MB measured against ~1400 MB
    observed externally for the same run). Docling and Tesseract spend their
    time in native code holding the GIL, so the in-process sampler was starved
    exactly during the allocation peak it existed to catch; it landed 1538 of an
    expected 2156 samples and every missing one was in the expensive window.

    Sampling the whole **process tree** matters for the same reason: Tesseract
    runs as a subprocess (pytesseract) and PaddleOCR runs in the persistent
    worker of :mod:`src.paddle_worker`, so their memory is not in the parent's
    RSS at all. What the machine has to supply is the sum.
    """

    def __init__(self, pid: int, interval: float = 0.1) -> None:
        super().__init__(daemon=True)
        import psutil

        self.psutil = psutil
        self.pid = pid
        self.interval = interval
        self.peak_rss = 0.0          # process tree total
        self.peak_rss_main = 0.0     # the worker alone
        self.peak_procs = 1          # widest the tree ever got
        self.peak_vram = None
        self.samples = 0
        # NOT ``_stop`` -- that name shadows ``threading.Thread._stop``, which
        # ``join`` calls internally, and the failure surfaces as a TypeError
        # from deep inside threading rather than from anything here.
        self._halt = threading.Event()

    def _tree_rss(self) -> tuple[float, float, int]:
        psutil = self.psutil
        try:
            proc = psutil.Process(self.pid)
            main = proc.memory_info().rss
            total = main
            n = 1
            for child in proc.children(recursive=True):
                try:
                    total += child.memory_info().rss
                    n += 1
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            return main / 2**20, total / 2**20, n
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return 0.0, 0.0, 0

    def run(self) -> None:
        vram_every = max(1, int(2.0 / self.interval))  # nvidia-smi is expensive
        i = 0
        while not self._halt.is_set():
            main, total, n = self._tree_rss()
            self.peak_rss_main = max(self.peak_rss_main, main)
            self.peak_rss = max(self.peak_rss, total)
            self.peak_procs = max(self.peak_procs, n)
            if i % vram_every == 0:
                v = _vram_used_mb()
                if v is not None:
                    self.peak_vram = v if self.peak_vram is None else max(self.peak_vram, v)
            self.samples += 1
            i += 1
            self._halt.wait(self.interval)

    def stop(self) -> None:
        self._halt.set()
        self.join(timeout=15)


# ---------------------------------------------------------------------------
# one batch, in this process (invoked as a subprocess by the driver)
# ---------------------------------------------------------------------------


def run_one(n: int, fast: bool = False) -> dict:
    import psutil

    from src.config import PipelineConfig
    from src.pipeline import ingest_batch

    proc = psutil.Process(os.getpid())
    paths = batch_paths(n, fast=fast)

    gc.collect()
    baseline = proc.memory_info().rss / 2**20

    # Peak RSS is sampled by the *parent* (see Sampler) -- an in-process thread
    # is GIL-starved during exactly the native calls that allocate the most.
    # What is measured here are point-in-time values, which are accurate.
    t0 = time.perf_counter()
    try:
        results = ingest_batch([str(p) for p in paths], PipelineConfig())
    except Exception as exc:  # noqa: BLE001
        return {
            "batch_size": n, "crashed": f"{type(exc).__name__}: {exc}",
            "wall_s": round(time.perf_counter() - t0, 1),
        }
    wall = time.perf_counter() - t0
    crashed = None

    held = proc.memory_info().rss / 2**20          # results still referenced
    n_chunks = sum(len(r.chunks) for r in results)
    n_pages = sum(r.n_pages for r in results)
    text_bytes = sum(
        len(c.text.encode("utf-8")) + len(json.dumps(c.metadata, default=str).encode("utf-8"))
        for r in results for c in r.chunks
    )
    failures = [
        {"doc": Path(r.source_file).name, "errors": r.errors[:1]}
        for r in results if not r.succeeded
    ]
    # Stage totals across the batch: shows whether a slow run is OCR, Docling,
    # or something else, so a wall-clock number is interpretable.
    stages: dict[str, float] = {}
    for r in results:
        for k, v in (r.timings_ms or {}).items():
            stages[k] = stages.get(k, 0.0) + v
    stages_s = {k: round(v / 1000, 1) for k, v in sorted(
        stages.items(), key=lambda kv: -kv[1])}

    # Serialized size of everything the batch is still holding. RSS cannot
    # answer "what does one more document cost to keep?" because the allocator
    # floor (~1 GB of imported extension modules and arenas) swamps it and is
    # then reused rather than grown. This number is the accumulation itself.
    import pickle
    try:
        live_mb = len(pickle.dumps(results, protocol=5)) / 2**20
    except Exception:  # noqa: BLE001
        live_mb = None

    del results
    gc.collect()
    released = proc.memory_info().rss / 2**20      # after the batch is dropped

    return {
        "batch_size": n,
        "crashed": crashed,
        "n_docs": len(paths),
        "n_pages": n_pages,
        "n_chunks": n_chunks,
        "chunk_payload_mb": round(text_bytes / 2**20, 2),
        "live_pickle_mb": round(live_mb, 2) if live_mb is not None else None,
        "live_pickle_mb_per_doc": (
            round(live_mb / max(1, len(paths)), 3) if live_mb is not None else None),
        "wall_s": round(wall, 1),
        "wall_s_per_doc": round(wall / max(1, len(paths)), 2),
        "baseline_rss_mb": round(baseline, 1),
        "held_rss_mb": round(held, 1),
        "released_rss_mb": round(released, 1),
        "retained_mb": round(held - baseline, 1),
        "retained_mb_per_doc": round((held - baseline) / max(1, len(paths)), 2),
        "stage_totals_s": stages_s,
        "failures": failures,
    }


# ---------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sizes", nargs="+", type=int, default=[1, 5, 10, 25])
    ap.add_argument("--out", default=str(REPORTS_DIR / "batch_size_probe.json"))
    ap.add_argument("--fast", action="store_true",
                    help="use the fast text-layer-only pool (isolates the "
                         "retention slope from OCR wall-clock)")
    ap.add_argument("--_child", type=int, default=None, help=argparse.SUPPRESS)
    args = ap.parse_args()

    if args._child is not None:
        print("@@RESULT@@" + json.dumps(run_one(args._child, fast=args.fast)))
        return 0

    import psutil

    vm = psutil.virtual_memory()
    env = {
        "ram_total_gb": round(vm.total / 2**30, 2),
        "ram_available_gb_at_start": round(vm.available / 2**30, 2),
        "cpu_count": psutil.cpu_count(),
        "vram_used_mb_at_start": _vram_used_mb(),
        "python": sys.version.split()[0],
    }
    print(json.dumps(env, indent=2), flush=True)

    rows = []
    for n in args.sizes:
        print(f"\n=== batch size {n} (fresh process) ===", flush=True)
        t0 = time.perf_counter()
        child_cmd = [sys.executable, __file__, "--_child", str(n)]
        if args.fast:
            child_cmd.append("--fast")
        child = subprocess.Popen(
            child_cmd,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            cwd=str(PROJECT_ROOT),
        )
        sampler = Sampler(child.pid)
        sampler.start()
        stdout, stderr = child.communicate()
        sampler.stop()
        outer_wall = time.perf_counter() - t0

        marker = [l for l in stdout.splitlines() if l.startswith("@@RESULT@@")]
        if not marker:
            rows.append({
                "batch_size": n,
                "crashed": f"child exited {child.returncode} with no result",
                "stderr_tail": stderr.strip().splitlines()[-5:],
                "wall_s": round(outer_wall, 1),
                "peak_rss_mb": round(sampler.peak_rss, 1),
            })
            print(f"  FAILED: exit {child.returncode}", flush=True)
            continue
        row = json.loads(marker[0][len("@@RESULT@@"):])
        # Externally observed, and therefore trustworthy, resource peaks.
        row["peak_rss_mb"] = round(sampler.peak_rss, 1)
        row["peak_rss_main_mb"] = round(sampler.peak_rss_main, 1)
        row["peak_subprocesses"] = sampler.peak_procs
        row["peak_vram_mb"] = sampler.peak_vram
        row["rss_samples"] = sampler.samples
        row["process_wall_s"] = round(outer_wall, 1)
        rows.append(row)
        print(
            f"  {row['n_docs']} docs / {row.get('n_pages')} pages  "
            f"wall {row['wall_s']}s  peak RSS {row['peak_rss_mb']} MB "
            f"(tree of {row['peak_subprocesses']}, main {row['peak_rss_main_mb']} MB)  "
            f"retained {row.get('retained_mb')} MB  "
            f"live {row.get('live_pickle_mb')} MB "
            f"({row.get('live_pickle_mb_per_doc')} MB/doc)  "
            f"peak VRAM {row.get('peak_vram_mb')} MB  "
            f"failures {len(row.get('failures') or [])}",
            flush=True,
        )

    payload = {"environment": env, "runs": rows}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
