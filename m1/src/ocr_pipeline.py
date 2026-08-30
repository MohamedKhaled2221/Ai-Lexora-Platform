"""OCR path: Tesseract primary, PaddleOCR fallback.

Used for scanned PDF pages and for image inputs, which route here directly.

ENGINE ORDER
============

This **inverts the team spec's assumed ordering** (PaddleOCR primary), on
measured evidence -- see ``reports/ocr_engine_comparison.md`` and the docstring
on :attr:`~src.config.OCRConfig.primary_engine`. Tesseract reads Arabic better
on every fixture in the corpus, is roughly an order of magnitude faster, and
does not fail non-deterministically. PaddleOCR remains wired as the fallback
because it is a different architecture, so the pages it fails on are unlikely to
be the pages Tesseract fails on.

The order is config, not structure: both engines run through the same gates and
the same comparison, and swapping ``primary_engine`` / ``fallback_engine``
swaps their roles with no other change.

FALLBACK POLICY (flagged for review)
====================================

The primary engine runs first. Its result is accepted only if it clears **all
three** gates in :class:`~src.config.OCRConfig`:

  1. ``min_mean_confidence`` (default 0.75) -- mean recognition score across
     surviving boxes.
  2. ``min_chars_per_page`` (default 40) -- a non-blank page that yields almost
     no text is a failure, however confident the engine claims to be. This gate
     catches the common Arabic failure where the detector finds one box on a
     dense page.
  3. ``min_recognized_ratio`` (default 0.60) -- fraction of *detected* boxes
     that survived recognition above ``drop_below_confidence``. A page where
     the detector found 200 boxes and the recognizer produced usable text for
     40 of them is broken even if those 40 scored 0.95.

Three gates rather than one because mean confidence alone is not a good failure
signal on Arabic: a page can fail catastrophically (detector collapse) while
the handful of boxes it did read score very high, and mean confidence would
happily wave that through.

Blank pages are detected *before* OCR by ink ratio, so an empty result on a
genuinely blank page is recorded as ``blank``, not as a failure. Without this,
the failure-rate metric in the evaluation report would be dominated by the
blank separator pages that Egyptian court bundles are full of.

When any gate fails, the fallback engine runs on the same raster.

  **Caveat worth knowing.** PaddleOCR's per-box score is a recognition
  softmax confidence; Tesseract's word ``conf`` is a different quantity on a
  different scale (we rescale 0-100 to 0-1, but that is a unit change, not a
  calibration). Comparing them numerically -- which
  ``prefer_higher_confidence_on_fallback`` does -- is therefore approximate.
  It is on by default because in practice it avoids the worse failure of
  replacing a good primary result with a worse fallback, but the comparison
  should be re-checked against real firm scans before it is trusted. Both
  engines' full diagnostics are kept in the engine log either way, so nothing
  is lost by the choice.

TABLES
======

Tables on this path are reconstructed from OCR geometry by
:func:`tables_from_atoms`. Neither of the pipeline's table extractors can see an
OCR'd page -- Docling runs over the source file on the text-layer route only,
and PyMuPDF's ``find_tables`` reads ruling lines from a content stream a raster
does not have -- so without it every scanned table was silently flattened into
loose paragraph text.

Every page records which engine won and why, in ``ExtractedDocument.engine_log``
(spec: "Log which engine handled each document/page for later comparison").
"""

from __future__ import annotations

import atexit
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np

from .config import OCRConfig
from .document_chunk_schema import BlockType, BoundingBox, OCRConfidence, SourceEngine
from .structure_preservation import (
    ExtractedDocument,
    ExtractedPage,
    ExtractedTable,
    TextBlock,
    clean_control_chars,
    detect_language,
)

logger = logging.getLogger(__name__)

# One PaddleOCR instance per language, built lazily and cached: construction
# loads model weights and costs seconds, so it must not happen per page.
_PADDLE_CACHE: dict[str, Any] = {}


@dataclass
class OCRBox:
    """One recognized text box, engine-agnostic."""

    text: str
    conf: float
    bbox: BoundingBox
    engine: SourceEngine
    lang_model: str | None = None


@dataclass
class OCRPageResult:
    """Result of running one engine over one page image."""

    engine: SourceEngine
    boxes: list[OCRBox] = field(default_factory=list)
    atoms: list[OCRBox] = field(default_factory=list)
    """The finest-granularity units the engine reported, before they were joined
    into lines: individual words for Tesseract, individual detection boxes for
    PaddleOCR.

    ``boxes`` is line-granular because that is what the rest of the pipeline
    wants -- the marker detector reads the first line of a block, so
    line-per-block would make every line look like a heading. But joining a
    table row into one line destroys the column geometry that identifies it as
    a table at all. Keeping the atoms costs nothing and is what
    :func:`tables_from_atoms` reads."""

    detected_boxes: int = 0
    dropped_boxes: int = 0
    elapsed_ms: float = 0.0
    error: str | None = None

    scale: float = 1.0
    """Points-per-pixel for this result's boxes. Not always the page's own
    scale: PaddleOCR is fed a downscaled image (``paddle_max_side``), so its
    boxes live in a coarser pixel space and carry a correspondingly larger
    factor."""

    @property
    def text(self) -> str:
        return "\n".join(b.text for b in self.boxes if b.text.strip())

    @property
    def n_chars(self) -> int:
        return len(self.text.strip())

    @property
    def mean_conf(self) -> float | None:
        if not self.boxes:
            return None
        return float(np.mean([b.conf for b in self.boxes]))

    @property
    def min_conf(self) -> float | None:
        if not self.boxes:
            return None
        return float(min(b.conf for b in self.boxes))

    @property
    def recognized_ratio(self) -> float:
        if not self.detected_boxes:
            return 0.0
        return len(self.boxes) / self.detected_boxes


# ---------------------------------------------------------------------------
# Rasterization
# ---------------------------------------------------------------------------


def render_pdf_page(page, dpi: int, max_side: int = 4000) -> tuple["np.ndarray", float]:
    """Rasterize a PyMuPDF page to an RGB array.

    Returns ``(image, scale)`` where ``scale`` is points-per-pixel, so OCR boxes
    in pixel space can be mapped back to PDF point space and stay comparable
    with text-layer bounding boxes.

    ``max_side`` caps the output resolution. Legal PDFs are not all A4 --
    Egyptian court bundles include A3 and oversized scans, and one of the
    interim corpus files renders to 6487x4712 at 300 dpi. PaddleOCR refuses
    anything over 4000px on a side and its internal downscale path crashes the
    process with a native access violation on some builds, so we reduce the
    effective DPI here instead and record it in the returned scale.
    """
    import fitz

    zoom = dpi / 72.0
    longest = max(page.rect.width, page.rect.height) * zoom
    if max_side and longest > max_side:
        zoom *= max_side / longest
        logger.info(
            "page %s would render to %.0fpx; reducing effective dpi to %.0f",
            getattr(page, "number", "?") , longest, zoom * 72,
        )
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n == 4:
        img = img[:, :, :3]
    elif pix.n == 1:
        img = np.repeat(img, 3, axis=2)

    # ``frombuffer`` gives a READ-ONLY view over PyMuPDF's own pixmap memory,
    # which is freed when the pixmap goes out of scope. Both OCR engines pass
    # the buffer straight into C++ that may write to it. Note ascontiguousarray
    # alone is not enough -- it returns the same read-only view when the array
    # is already contiguous. An explicit copy is required.
    return np.array(img, dtype=np.uint8, copy=True), 1.0 / zoom


def load_image(path: str | Path) -> "np.ndarray":
    """Load an image file to an RGB array (handles multi-mode inputs)."""
    from PIL import Image

    with Image.open(str(path)) as im:
        return np.ascontiguousarray(np.array(im.convert("RGB")), dtype=np.uint8)


def ink_ratio(img: "np.ndarray") -> float:
    """Fraction of pixels darker than a mid threshold -- a cheap blank test.

    Uses a fixed threshold rather than Otsu on purpose: Otsu on a truly blank
    page amplifies sensor noise into "ink" and would report every blank scan as
    having content.
    """
    gray = img.mean(axis=2) if img.ndim == 3 else img
    return float((gray < 200).mean())


# ---------------------------------------------------------------------------
# PaddleOCR
# ---------------------------------------------------------------------------


def _get_paddle(lang: str, light: bool = True):
    """Lazily build and cache an in-process PaddleOCR instance for one language.

    The construction logic lives in :func:`src.paddle_worker._build` and is
    shared rather than duplicated. Those two used to be parallel copies kept in
    sync by a comment, and they drifted -- which is how a variant that loads the
    wrong recogniser for Arabic survived in one of them.

    This path is only used when ``OCRConfig.paddle_isolate_subprocess`` is off;
    the default route is the worker process.

    Raises ``RuntimeError`` listing everything tried when no variant yields a
    usable engine, so the failure is diagnosable rather than a silent fallback.
    """
    cache_key = f"{lang}:{'light' if light else 'server'}"
    if cache_key in _PADDLE_CACHE:
        return _PADDLE_CACHE[cache_key]

    from .paddle_worker import _build, recogniser_name

    engine = _build(lang, light)
    _PADDLE_CACHE[cache_key] = engine
    logger.info("PaddleOCR initialised in-process for %r (recogniser %s)",
                lang, recogniser_name(engine))
    return engine


def paddle_available() -> bool:
    try:
        import paddleocr  # noqa: F401

        return True
    except Exception:  # noqa: BLE001
        return False


def _parse_paddle_result(result: Any, page: int, scale: float, lang: str) -> list[OCRBox]:
    """Normalize PaddleOCR output across its several result shapes.

    2.x returns ``[[ [quad, (text, score)], ... ]]``. 3.x returns a list of
    dict-like objects with ``rec_texts`` / ``rec_scores`` / ``rec_polys``.
    Both are handled so a PaddleOCR upgrade does not silently produce zero boxes.
    """
    boxes: list[OCRBox] = []
    if not result:
        return boxes

    first = result[0] if isinstance(result, (list, tuple)) and result else None

    # --- 3.x dict-style ---
    if isinstance(first, dict) or hasattr(first, "get"):
        try:
            texts = first.get("rec_texts") or []
            scores = first.get("rec_scores") or []
            polys = first.get("rec_polys") or first.get("dt_polys") or []
            for t, s, q in zip(texts, scores, polys):
                if not str(t).strip():
                    continue
                boxes.append(
                    OCRBox(
                        text=str(t), conf=float(s),
                        bbox=BoundingBox.from_quad(q, page=page, scale=scale),
                        engine=SourceEngine.PADDLEOCR, lang_model=lang,
                    )
                )
            return boxes
        except Exception:  # noqa: BLE001
            pass

    # --- 2.x list-style ---
    page_lines = first if isinstance(first, (list, tuple)) else result
    for line in page_lines or []:
        try:
            quad, payload = line[0], line[1]
            text, score = (payload[0], payload[1]) if isinstance(payload, (list, tuple)) else (payload, 0.0)
            if not str(text).strip():
                continue
            boxes.append(
                OCRBox(
                    text=str(text), conf=float(score),
                    bbox=BoundingBox.from_quad(quad, page=page, scale=scale),
                    engine=SourceEngine.PADDLEOCR, lang_model=lang,
                )
            )
        except (IndexError, TypeError, ValueError):
            continue
    return boxes


class _PaddleWorker:
    """Client for a persistent :mod:`src.paddle_worker` subprocess.

    Owns one worker per language. Restarts it after a crash, and gives up on
    PaddleOCR entirely after ``max_restarts`` so a systematically-broken install
    degrades to Tesseract once rather than paying a model load per page forever.
    """

    max_restarts = 2

    def __init__(self, lang: str, light: bool) -> None:
        self.lang = lang
        self.light = light
        self.proc = None
        self.restarts = 0
        self.recogniser: str | None = None
        self.disabled_reason: str | None = None

    def _start(self) -> None:
        import subprocess

        from .config import PROJECT_ROOT

        self.proc = subprocess.Popen(
            [sys.executable, "-m", "src.paddle_worker", self.lang, str(self.light)],
            cwd=str(PROJECT_ROOT),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", bufsize=1,
        )
        payload = self._read_json("startup handshake")
        if not payload.get("ok"):
            raise RuntimeError(payload.get("error", "worker init failed"))
        self.recogniser = payload.get("recogniser")
        logger.info("PaddleOCR worker ready (lang=%s, recogniser=%s)",
                    self.lang, self.recogniser)

    def _read_json(self, what: str, max_skipped: int = 50) -> dict:
        """Read one JSON line, tolerating stray non-JSON output.

        The worker takes exclusive ownership of its stdout fd, so this should
        never be needed -- but a future PaddleOCR could find a new way to print
        on that descriptor, and silently reading garbage as "PaddleOCR failed"
        would hide a working engine behind a permanent Tesseract fallback.
        """
        for _ in range(max_skipped):
            line = self.proc.stdout.readline()
            if not line:
                code = self.proc.poll()
                self.proc = None
                raise RuntimeError(
                    f"PaddleOCR worker died during {what} (exit code {code})"
                )
            line = line.strip()
            if not line:
                continue
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                logger.debug("ignoring non-protocol worker output: %s", line[:200])
                continue
        raise RuntimeError(f"PaddleOCR worker produced no valid response during {what}")

    def _ensure(self) -> None:
        if self.disabled_reason:
            raise RuntimeError(self.disabled_reason)
        if self.proc is None or self.proc.poll() is not None:
            if self.restarts > self.max_restarts:
                self.disabled_reason = (
                    f"PaddleOCR worker crashed {self.restarts} times; disabled for this "
                    "run, falling back to Tesseract"
                )
                raise RuntimeError(self.disabled_reason)
            self.restarts += 1
            self._start()

    def infer(self, img: "np.ndarray") -> list:
        """Run one page. Raises on worker crash so the caller can fall back."""
        import tempfile

        self._ensure()
        with tempfile.NamedTemporaryFile(suffix=".npy", delete=False) as fh:
            tmp = fh.name
        try:
            np.save(tmp, img)
            self.proc.stdin.write(json.dumps({"npy": tmp}) + "\n")
            self.proc.stdin.flush()
            payload = self._read_json(
                "page inference (a crash here is the native access-violation "
                "failure mode, which is why PaddleOCR runs out-of-process)"
            )
            if not payload.get("ok"):
                raise RuntimeError(payload.get("error", "unknown worker error"))
            return payload["boxes"]
        except (BrokenPipeError, OSError) as exc:
            self.proc = None
            raise RuntimeError(f"PaddleOCR worker pipe broke: {exc}") from exc
        finally:
            try:
                Path(tmp).unlink(missing_ok=True)
            except OSError:
                pass

    def shutdown(self) -> None:
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.stdin.write(json.dumps({"shutdown": True}) + "\n")
                self.proc.stdin.flush()
                self.proc.wait(timeout=5)
            except Exception:  # noqa: BLE001
                self.proc.kill()
        self.proc = None


_PADDLE_WORKERS: dict[str, _PaddleWorker] = {}


def _get_worker(lang: str, light: bool) -> _PaddleWorker:
    key = f"{lang}:{light}"
    if key not in _PADDLE_WORKERS:
        _PADDLE_WORKERS[key] = _PaddleWorker(lang, light)
    return _PADDLE_WORKERS[key]


def shutdown_paddle_workers() -> None:
    """Stop all PaddleOCR worker processes. Safe to call more than once."""
    for worker in list(_PADDLE_WORKERS.values()):
        worker.shutdown()
    _PADDLE_WORKERS.clear()


atexit.register(shutdown_paddle_workers)


def _paddle_infer(engine, img: "np.ndarray"):
    """Call whichever inference entry point this PaddleOCR version exposes.

    2.x: ``ocr(img, cls=True)``. 3.x: ``predict(img)``, with ``ocr(img)`` kept
    as a deprecated alias that does not accept ``cls``.
    """
    errors: list[str] = []
    for call in (
        lambda: engine.ocr(img, cls=True),
        lambda: engine.predict(img),
        lambda: engine.ocr(img),
    ):
        try:
            return call()
        except (TypeError, AttributeError) as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
            continue
    raise RuntimeError("no usable PaddleOCR inference entry point: " + "; ".join(errors))


def _fit_for_paddle(img: "np.ndarray", max_side: int) -> tuple["np.ndarray", float]:
    """Downscale ``img`` to PaddleOCR's working range.

    Returns ``(image, shrink)`` where ``shrink`` is the factor the caller must
    multiply its points-per-pixel ``scale`` by, so boxes come back in the
    original coordinate space.

    Uses PIL rather than PaddleOCR's own internal resize on purpose: that
    internal path is one of the two ways this build dies (a native access
    violation), which is the failure we are avoiding.
    """
    longest = max(img.shape[0], img.shape[1])
    if not max_side or longest <= max_side:
        return img, 1.0

    from PIL import Image

    ratio = max_side / longest
    size = (max(1, int(img.shape[1] * ratio)), max(1, int(img.shape[0] * ratio)))
    resized = Image.fromarray(img).resize(size, Image.LANCZOS)
    logger.info("downscaled %dpx page to %dpx for PaddleOCR", longest, max_side)
    return np.ascontiguousarray(np.array(resized), dtype=np.uint8), 1.0 / ratio


def run_paddleocr(img: "np.ndarray", page: int, scale: float, cfg: OCRConfig) -> OCRPageResult:
    """Run PaddleOCR over one page image with every configured language model.

    PaddleOCR loads one recognition model per language, so for a mixed
    Arabic/English page we run both and merge. Where the two models produce
    overlapping boxes for the same region, the higher-confidence one wins --
    which in practice routes Arabic runs to the Arabic model and Latin runs to
    the English model without us having to segment the page by script first.
    """
    res = OCRPageResult(engine=SourceEngine.PADDLEOCR)
    t0 = time.perf_counter()
    all_boxes: list[OCRBox] = []
    detected = 0

    # PaddleOCR has a resolution ceiling this build cannot clear -- see
    # OCRConfig.paddle_max_side. Downscale for this engine only, and undo the
    # scaling on the way out so its boxes stay in the same coordinate space as
    # Tesseract's and the text layer's.
    img, shrink = _fit_for_paddle(img, cfg.paddle_max_side)
    scale = scale * shrink
    res.scale = scale

    for lang in cfg.paddle_langs:
        try:
            if cfg.paddle_isolate_subprocess:
                boxes = _get_worker(lang, cfg.paddle_light_models).infer(img)
                parsed = [
                    OCRBox(
                        text=text, conf=float(score),
                        bbox=BoundingBox.from_quad(quad, page=page, scale=scale),
                        engine=SourceEngine.PADDLEOCR, lang_model=lang,
                    )
                    for quad, text, score in boxes
                ]
            else:
                engine = _get_paddle(lang, light=cfg.paddle_light_models)
                raw = _paddle_infer(engine, img)
                parsed = _parse_paddle_result(raw, page=page, scale=scale, lang=lang)
            detected += len(parsed)
            all_boxes.extend(parsed)
        except Exception as exc:  # noqa: BLE001
            res.error = f"{type(exc).__name__}: {exc}"
            logger.warning("PaddleOCR[%s] failed on page %s: %s", lang, page, exc)

    res.detected_boxes = detected
    merged = _merge_overlapping(all_boxes)
    kept = [b for b in merged if b.conf >= cfg.drop_below_confidence]
    res.dropped_boxes = len(merged) - len(kept)
    res.boxes = _sort_reading_order(kept)
    # PaddleOCR's detector already emits one box per text region, which on a
    # table is one box per cell -- so its boxes are the atoms.
    res.atoms = list(kept)
    res.elapsed_ms = (time.perf_counter() - t0) * 1000
    return res


def _merge_overlapping(boxes: list[OCRBox], iou_threshold: float = 0.50) -> list[OCRBox]:
    """Deduplicate boxes produced by different language models for the same region."""
    if len(boxes) < 2:
        return boxes
    kept: list[OCRBox] = []
    for box in sorted(boxes, key=lambda b: -b.conf):
        if any(_box_iou(box.bbox, k.bbox) >= iou_threshold for k in kept):
            continue
        kept.append(box)
    return kept


def _box_iou(a: BoundingBox, b: BoundingBox) -> float:
    ix0, iy0 = max(a.x0, b.x0), max(a.y0, b.y0)
    ix1, iy1 = min(a.x1, b.x1), min(a.y1, b.y1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    inter = (ix1 - ix0) * (iy1 - iy0)
    union = a.width * a.height + b.width * b.height - inter
    return inter / union if union > 0 else 0.0


# ---------------------------------------------------------------------------
# Tesseract
# ---------------------------------------------------------------------------


def _configure_tesseract(cfg: OCRConfig) -> None:
    """Point pytesseract at the Tesseract binary and its language data.

    Search order for the binary: explicit config, PATH, then the standard
    Windows/Linux/macOS install locations.

    Language data is located via the ``TESSDATA_PREFIX`` environment variable
    rather than a ``--tessdata-dir`` argument. That is deliberate: pytesseract
    splits the config string on whitespace, so a data directory whose path
    contains spaces (the default on Windows, and this project lives under
    "Law firm") is torn in half and Tesseract fails to load *any* language --
    including English. The env var carries the path intact.

    Prefers the project-local ``tessdata/`` when it holds ``ara.traineddata``,
    since a stock Tesseract install ships English only and Arabic is the point.
    """
    import os
    import shutil

    import pytesseract

    from .config import PROJECT_ROOT

    binary = cfg.tesseract_cmd or shutil.which("tesseract")
    if not binary:
        for candidate in (
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            "/usr/bin/tesseract",
            "/usr/local/bin/tesseract",
            "/opt/homebrew/bin/tesseract",
        ):
            if Path(candidate).exists():
                binary = candidate
                break
    if binary:
        pytesseract.pytesseract.tesseract_cmd = binary

    local_tessdata = PROJECT_ROOT / "tessdata"
    if (local_tessdata / "ara.traineddata").exists():
        os.environ["TESSDATA_PREFIX"] = str(local_tessdata)


def tesseract_available() -> bool:
    try:
        import pytesseract

        _configure_tesseract(OCRConfig())
        pytesseract.get_tesseract_version()
        return True
    except Exception:  # noqa: BLE001
        return False


def run_tesseract(img: "np.ndarray", page: int, scale: float, cfg: OCRConfig) -> OCRPageResult:
    """Run Tesseract over one page image, collecting per-word confidences.

    ``--psm 1`` (auto page segmentation with OSD) is used because scanned
    Arabic legal pages are frequently rotated a few degrees, and OSD corrects
    that. Words with ``conf == -1`` are layout artifacts, not recognition
    failures, and are excluded from the confidence statistics.
    """
    import pytesseract
    from pytesseract import Output

    res = OCRPageResult(engine=SourceEngine.TESSERACT, scale=scale)
    t0 = time.perf_counter()
    _configure_tesseract(cfg)
    config_str = "--psm 1 --oem 1"

    try:
        data = pytesseract.image_to_data(
            img, lang=cfg.tesseract_lang, config=config_str, output_type=Output.DICT
        )
    except Exception as exc:  # noqa: BLE001
        res.error = f"{type(exc).__name__}: {exc}"
        res.elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.warning("Tesseract failed on page %s: %s", page, exc)
        return res

    # Group words into lines using Tesseract's own block/par/line indices --
    # more reliable than re-clustering by geometry.
    lines: dict[tuple, list[int]] = {}
    n = len(data.get("text", []))
    for i in range(n):
        if int(data["conf"][i]) < 0:
            continue
        if not str(data["text"][i]).strip():
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        lines.setdefault(key, []).append(i)

    res.detected_boxes = len(lines)
    boxes: list[OCRBox] = []
    for key, idxs in lines.items():
        idxs.sort(key=lambda i: data["word_num"][i])
        words = [str(data["text"][i]).strip() for i in idxs]
        confs = [int(data["conf"][i]) / 100.0 for i in idxs]
        for i, word, conf in zip(idxs, words, confs):
            if not word or conf < cfg.drop_below_confidence:
                continue
            res.atoms.append(
                OCRBox(
                    text=word, conf=conf,
                    bbox=BoundingBox(
                        x0=data["left"][i], y0=data["top"][i],
                        x1=data["left"][i] + data["width"][i],
                        y1=data["top"][i] + data["height"][i],
                        page=page, scale=scale,
                    ),
                    engine=SourceEngine.TESSERACT, lang_model=cfg.tesseract_lang,
                )
            )
        text = " ".join(w for w in words if w)
        if not text:
            continue
        x0 = min(data["left"][i] for i in idxs)
        y0 = min(data["top"][i] for i in idxs)
        x1 = max(data["left"][i] + data["width"][i] for i in idxs)
        y1 = max(data["top"][i] + data["height"][i] for i in idxs)
        boxes.append(
            OCRBox(
                text=text,
                conf=float(np.mean(confs)) if confs else 0.0,
                bbox=BoundingBox(x0=x0, y0=y0, x1=x1, y1=y1, page=page, scale=scale),
                engine=SourceEngine.TESSERACT,
                lang_model=cfg.tesseract_lang,
            )
        )

    kept = [b for b in boxes if b.conf >= cfg.drop_below_confidence]
    res.dropped_boxes = len(boxes) - len(kept)
    res.boxes = _sort_reading_order(kept)
    res.elapsed_ms = (time.perf_counter() - t0) * 1000
    return res


# ---------------------------------------------------------------------------
# Reading order + block assembly
# ---------------------------------------------------------------------------


def _group_into_lines(boxes: list[OCRBox]) -> list[list[OCRBox]]:
    """Group boxes into visual lines by vertical overlap.

    The tolerance is proportional to box height, so it adapts to font size
    rather than assuming a fixed line spacing. Lines come back top to bottom;
    the boxes within a line are in no particular horizontal order.
    """
    lines: list[list[OCRBox]] = []
    for box in sorted(boxes, key=lambda b: b.bbox.y0):
        placed = False
        for line in lines:
            ref = line[0].bbox
            tol = max(ref.height, box.bbox.height) * 0.5
            centre = (box.bbox.y0 + box.bbox.y1) / 2
            ref_centre = (ref.y0 + ref.y1) / 2
            if abs(centre - ref_centre) <= tol:
                line.append(box)
                placed = True
                break
        if not placed:
            lines.append([box])
    return lines


def _sort_reading_order(boxes: list[OCRBox]) -> list[OCRBox]:
    """Order boxes into lines, then put each line into logical reading order.

    OCR is the pipeline's *second* source of visual order. The engine returns
    recognized words with positions and no sequence: each word is internally
    correct (the recognizer read it as a word) but their order is whatever
    ``sorted by x`` gives, which is screen order, which for Arabic is backwards.

    A pure Latin line is sorted left to right and a pure Arabic line right to
    left, and for those two cases that is the whole job. **A mixed line is not
    one of those cases**, and sorting it entirely right-to-left -- which is what
    this function used to do -- fixes the Arabic and reverses any English inside
    it, so "(the Lessor)" comes back as "(Lessor the)". Egyptian legal practice
    puts English defined terms inside Arabic clauses constantly, so that is not
    an edge case.

    So a mixed line goes through :func:`~src.visual_order.reorder_tokens_visual_to_logical`,
    which applies the Unicode Bidi Algorithm's reordering at *token* granularity:
    reverse the line for an RTL base, then reverse each embedded LTR run back.
    Same transform :mod:`src.visual_order` applies to characters on the PDF path,
    one level up.

    :mod:`src.rtl_fix` still checks the result for the residual ambiguities no
    geometric rule can resolve -- and flags rather than guesses.
    """
    if not boxes:
        return []

    from .document_chunk_schema import Language
    from .visual_order import reorder_tokens_visual_to_logical

    lines = _group_into_lines(boxes)

    ordered: list[OCRBox] = []
    for line in lines:
        joined = " ".join(b.text for b in line)
        lang = detect_language(joined)
        # Visual order first: left to right, exactly as the eye sweeps the page.
        line.sort(key=lambda b: b.bbox.x0)
        if lang is Language.AR_EN:
            perm = reorder_tokens_visual_to_logical([b.text for b in line], base_dir="R")
            line = [line[i] for i in perm]
        elif lang is Language.AR:
            line.reverse()
        ordered.extend(line)
    return ordered


# ---------------------------------------------------------------------------
# Tables on the OCR path
# ---------------------------------------------------------------------------


def tables_from_atoms(
    atoms: list[OCRBox], page: int, scale: float, cfg: OCRConfig
) -> list[ExtractedTable]:
    """Reconstruct tables from OCR word/box geometry.

    Neither of the pipeline's two table extractors can see an OCR'd page.
    Docling runs over the source file on the text-layer route only, and
    PyMuPDF's ``find_tables`` reads ruling lines out of the content stream --
    which a raster has none of. So before this existed, every table on every
    scanned page was flattened into loose paragraph text with no ``is_table``
    chunk ever emitted.

    The reconstruction works on *atoms* (Tesseract words, PaddleOCR detection
    boxes) rather than the line-joined ``boxes``, because joining a row into one
    line is precisely what destroys the column structure.

    Method, in order:

    1. Group atoms into visual lines.
    2. Split each line into **cells** wherever the horizontal gap between
       neighbouring atoms exceeds ``table_cell_gap_factor`` x the median glyph
       height. Word spacing is a fraction of glyph height; column spacing is a
       multiple of it, so the two separate cleanly at any DPI.
    3. Take maximal runs of consecutive lines that split into at least
       ``table_min_cols`` cells.
    4. Cluster the cell left-edges of a run into columns, and keep the run only
       if enough columns recur across enough of its rows
       (``table_column_occupancy``). This is the test that rejects justified
       Arabic prose, whose stretched inter-word spaces also produce wide gaps
       but never in the same place on consecutive lines.

    Column *order* follows the same convention as :func:`_sort_reading_order`:
    right-to-left when the table's own text is Arabic-dominant.

    Low-confidence atoms are dropped first, which also removes a specific
    nuisance: Tesseract reads a table's horizontal ruling line as a row of
    two-character garbage (``a mR + ee CS SS I``), perfectly column-aligned and
    therefore indistinguishable from a real row on geometry alone. Every token
    of it scores under 0.30.
    """
    from .document_chunk_schema import Language

    if not cfg.detect_tables:
        return []
    atoms = [a for a in atoms if a.text.strip() and a.conf >= cfg.drop_below_confidence]
    if len(atoms) < cfg.table_min_rows * cfg.table_min_cols:
        return []

    heights = [a.bbox.height for a in atoms if a.bbox.height > 0]
    if not heights:
        return []
    gap = float(np.median(heights)) * cfg.table_cell_gap_factor

    # --- 1-2. lines -> cells ------------------------------------------------
    rows: list[list[list[OCRBox]]] = []
    for line in _group_into_lines(atoms):
        line.sort(key=lambda b: b.bbox.x0)
        cells: list[list[OCRBox]] = [[line[0]]]
        for prev, cur in zip(line, line[1:]):
            if cur.bbox.x0 - prev.bbox.x1 > gap:
                cells.append([cur])
            else:
                cells[-1].append(cur)
        rows.append(cells)

    # --- 3. runs of multi-cell lines ----------------------------------------
    tables: list[ExtractedTable] = []
    run: list[list[list[OCRBox]]] = []
    for cells in rows + [[]]:          # sentinel flushes the final run
        if len(cells) >= cfg.table_min_cols:
            run.append(cells)
            continue
        if len(run) >= cfg.table_min_rows:
            table = _run_to_table(run, page, scale, gap, cfg)
            if table is not None:
                table.order = len(tables)
                tables.append(table)
        run = []

    return tables


def _run_to_table(
    run: list[list[list[OCRBox]]], page: int, scale: float, gap: float, cfg: OCRConfig
) -> ExtractedTable | None:
    """Turn one run of multi-cell lines into a grid, or reject it as prose."""
    from .document_chunk_schema import Language

    # Cluster cell left-edges into columns: sort them and cut wherever
    # successive edges are more than one cell-gap apart.
    edges = sorted(c[0].bbox.x0 for line in run for c in line)
    clusters: list[list[float]] = [[edges[0]]]
    for edge in edges[1:]:
        if edge - clusters[-1][-1] > gap:
            clusters.append([edge])
        else:
            clusters[-1].append(edge)
    centres = [float(np.mean(c)) for c in clusters]
    if len(centres) < cfg.table_min_cols:
        return None

    # --- 4. occupancy: a real column recurs down the run --------------------
    grid: list[list[str]] = []
    occupancy = [0] * len(centres)
    for line in run:
        cells = [""] * len(centres)
        for cell in line:
            col = min(range(len(centres)), key=lambda i: abs(centres[i] - cell[0].bbox.x0))
            text = " ".join(a.text for a in cell).strip()
            cells[col] = f"{cells[col]} {text}".strip() if cells[col] else text
            occupancy[col] += 1
        grid.append(cells)

    kept = [i for i, n in enumerate(occupancy) if n >= len(run) * cfg.table_column_occupancy]
    if len(kept) < cfg.table_min_cols:
        return None

    # A table's cells nearly all belong to one of its columns. Justified prose
    # can still reach this point -- every line starts at the left margin, so
    # that one x-position has 100% occupancy, and one more accidental alignment
    # somewhere down the page is enough to make two "columns". What gives it
    # away is that most of the text does not sit in either of them.
    retained = sum(occupancy[i] for i in kept)
    if retained < sum(occupancy) * cfg.table_min_cell_retention:
        return None

    grid = [[row[i] for i in kept] for row in grid]

    joined = " ".join(c for row in grid for c in row)
    if detect_language(joined) in (Language.AR, Language.AR_EN):
        grid = [list(reversed(row)) for row in grid]

    return ExtractedTable(
        rows=grid,
        page=page,
        bbox=BoundingBox.union(
            [a.bbox for line in run for cell in line for a in cell]
        ),
        source_engine=run[0][0][0].engine,
    )


def boxes_to_blocks(
    boxes: list[OCRBox], page: int, scale: float, line_gap_factor: float = 1.8
) -> list[TextBlock]:
    """Group ordered OCR boxes into paragraph-level blocks.

    A new block starts when the vertical gap to the previous line exceeds
    ``line_gap_factor`` x the running median line height. Keeping OCR output at
    paragraph rather than line granularity matters because the legal marker
    detector in :mod:`src.structure_preservation` reads the *first line* of a
    block: line-granular blocks would make every line look like a potential
    heading.
    """
    if not boxes:
        return []

    blocks: list[TextBlock] = []
    current: list[OCRBox] = []
    prev_bottom: float | None = None
    heights = [b.bbox.height for b in boxes if b.bbox.height > 0]
    median_h = float(np.median(heights)) if heights else 10.0

    def flush(order: int) -> None:
        if not current:
            return
        text = clean_control_chars("\n".join(b.text for b in current)).strip()
        if not text:
            return
        bbox = BoundingBox.union([b.bbox for b in current])
        confs = [b.conf for b in current]
        blocks.append(
            TextBlock(
                text=text, page=page, bbox=bbox, block_type=BlockType.PARAGRAPH,
                source_engine=current[0].engine, order=order,
                confidence=float(np.mean(confs)) if confs else None,
                n_boxes=len(current),
            )
        )

    order = 0
    for box in boxes:
        if prev_bottom is not None and (box.bbox.y0 - prev_bottom) > median_h * line_gap_factor:
            flush(order)
            order += 1
            current = []
        current.append(box)
        prev_bottom = max(prev_bottom or 0.0, box.bbox.y1)
    flush(order)
    return blocks


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def _passes_gates(res: OCRPageResult, cfg: OCRConfig) -> tuple[bool, str]:
    """Apply the three acceptance gates. Returns ``(passed, reason)``."""
    if res.error:
        return False, f"engine error: {res.error}"
    if not res.boxes:
        return False, "engine returned no text boxes"
    if res.n_chars < cfg.min_chars_per_page:
        return False, f"only {res.n_chars} chars (< {cfg.min_chars_per_page})"
    mean = res.mean_conf or 0.0
    if mean < cfg.min_mean_confidence:
        return False, f"mean confidence {mean:.3f} (< {cfg.min_mean_confidence})"
    if res.recognized_ratio < cfg.min_recognized_ratio:
        return False, (
            f"only {res.recognized_ratio:.0%} of {res.detected_boxes} detected boxes "
            f"survived recognition (< {cfg.min_recognized_ratio:.0%})"
        )
    return True, "passed all gates"


def ocr_page_image(
    img: "np.ndarray", page_number: int, scale: float, cfg: OCRConfig
) -> tuple[ExtractedPage, dict]:
    """OCR one page image with the primary engine, falling back if it fails.

    Returns ``(page, log_entry)``. ``log_entry`` is the per-page engine record
    the spec asks for -- it always names both engines' outcomes when a fallback
    was attempted, so the two can be compared later without a re-run.
    """
    epage = ExtractedPage(page_number=page_number, source_engine=SourceEngine.UNKNOWN)
    log: dict[str, Any] = {"page": page_number, "engine": None}

    ink = ink_ratio(img)
    log["ink_ratio"] = round(ink, 5)
    if ink < cfg.blank_page_ink_ratio:
        epage.is_blank = True
        epage.notes.append("page is blank (below ink threshold); OCR skipped")
        log.update(engine="none", status="blank", reason=f"ink ratio {ink:.5f}")
        return epage, log

    # Preprocessing runs *after* the blank test on purpose: binarization drives
    # ink ratio to 0 or 1 and would make the threshold meaningless.
    if cfg.preprocess.enabled:
        from .preprocess import preprocess_for_ocr

        t_pre = time.perf_counter()
        img, pre_info = preprocess_for_ocr(img, cfg.preprocess)
        pre_info["ms"] = round((time.perf_counter() - t_pre) * 1000, 1)
        log["preprocess"] = pre_info

    runners = {
        "paddleocr": lambda: run_paddleocr(img, page_number, scale, cfg),
        "tesseract": lambda: run_tesseract(img, page_number, scale, cfg),
    }

    primary_name = cfg.primary_engine
    fallback_name = cfg.fallback_engine if cfg.fallback_engine != "none" else None

    if primary_name == "paddleocr" and not paddle_available():
        log["paddle_unavailable"] = True
        primary_name, fallback_name = "tesseract", None

    primary = runners[primary_name]()
    passed, reason = _passes_gates(primary, cfg)
    log["primary"] = _summarize(primary, passed, reason)

    chosen, fallback_used, fb_reason = primary, False, None

    if not passed and fallback_name:
        if fallback_name == "tesseract" and not tesseract_available():
            log["fallback"] = {"engine": "tesseract", "status": "unavailable"}
            epage.notes.append(
                f"{primary_name} failed ({reason}) and Tesseract is not installed; "
                "keeping the low-quality primary result"
            )
        else:
            fb = runners[fallback_name]()
            fb_passed, fb_reason_txt = _passes_gates(fb, cfg)
            log["fallback"] = _summarize(fb, fb_passed, fb_reason_txt)
            fallback_used = True
            fb_reason = reason

            if not primary.boxes:
                chosen = fb
            elif not fb.boxes:
                chosen = primary
            elif cfg.prefer_higher_confidence_on_fallback:
                # Approximate comparison -- see the module docstring caveat.
                p_score = (primary.mean_conf or 0.0) * min(primary.n_chars / max(cfg.min_chars_per_page, 1), 1.0)
                f_score = (fb.mean_conf or 0.0) * min(fb.n_chars / max(cfg.min_chars_per_page, 1), 1.0)
                chosen = fb if f_score > p_score else primary
                log["comparison"] = {
                    "primary_score": round(p_score, 4),
                    "fallback_score": round(f_score, 4),
                    "winner": chosen.engine.value,
                    "note": "confidence scales are not calibrated between engines",
                }
            else:
                chosen = fb

    epage.blocks = boxes_to_blocks(chosen.boxes, page_number, chosen.scale)
    epage.tables = tables_from_atoms(chosen.atoms, page_number, chosen.scale, cfg)
    if epage.tables:
        log["tables"] = [t.shape for t in epage.tables]
    epage.source_engine = chosen.engine
    epage.ocr = OCRConfidence(
        engine=chosen.engine,
        mean=round(chosen.mean_conf, 4) if chosen.mean_conf is not None else None,
        min=round(chosen.min_conf, 4) if chosen.min_conf is not None else None,
        n_boxes=len(chosen.boxes),
        low_confidence_boxes=chosen.dropped_boxes,
        fallback_used=fallback_used and chosen.engine is not _engine_of(primary_name),
        fallback_reason=fb_reason if fallback_used else None,
    )
    for b in epage.blocks:
        b.source_engine = chosen.engine

    log["engine"] = chosen.engine.value
    log["status"] = "ok" if epage.blocks else "empty"
    log["chars"] = chosen.n_chars
    log["mean_conf"] = round(chosen.mean_conf, 4) if chosen.mean_conf is not None else None
    log["fallback_used"] = epage.ocr.fallback_used
    if not epage.blocks:
        epage.notes.append("OCR produced no text on a non-blank page")
    return epage, log


def _engine_of(name: str) -> SourceEngine:
    return SourceEngine.PADDLEOCR if name == "paddleocr" else SourceEngine.TESSERACT


def _summarize(res: OCRPageResult, passed: bool, reason: str) -> dict:
    return {
        "engine": res.engine.value,
        "passed_gates": passed,
        "reason": reason,
        "chars": res.n_chars,
        "boxes_kept": len(res.boxes),
        "boxes_detected": res.detected_boxes,
        "boxes_dropped": res.dropped_boxes,
        "mean_conf": round(res.mean_conf, 4) if res.mean_conf is not None else None,
        "ms": round(res.elapsed_ms, 1),
        "error": res.error,
    }


def ocr_pdf_pages(
    path: str | Path, doc: ExtractedDocument, cfg: OCRConfig, pages: list[int] | None = None
) -> list[ExtractedPage]:
    """OCR the given 1-based ``pages`` of a PDF (all pages when ``None``)."""
    import fitz

    out: list[ExtractedPage] = []
    pdf = fitz.open(str(path))
    ocr_ms = 0.0
    try:
        wanted = set(pages) if pages else set(range(1, pdf.page_count + 1))
        for pno, page in enumerate(pdf, start=1):
            if pno not in wanted:
                continue
            t0 = time.perf_counter()
            img, scale = render_pdf_page(page, cfg.render_dpi, cfg.max_render_side)
            render_ms = (time.perf_counter() - t0) * 1000
            epage, log = ocr_page_image(img, pno, scale, cfg)
            epage.width, epage.height = float(page.rect.width), float(page.rect.height)
            page_ms = (time.perf_counter() - t0) * 1000
            ocr_ms += page_ms
            log["render_ms"] = round(render_ms, 1)
            log["page_ms"] = round(page_ms, 1)
            log["dpi"] = cfg.render_dpi
            doc.engine_log.append(log)
            out.append(epage)
    finally:
        pdf.close()
    # OCR dominates the runtime of any scanned document, so it must appear in
    # the stage breakdown or the slowest-stage column is meaningless.
    doc.timings_ms["ocr"] = doc.timings_ms.get("ocr", 0.0) + ocr_ms
    return out


def ocr_image_file(path: str | Path, doc: ExtractedDocument, cfg: OCRConfig) -> list[ExtractedPage]:
    """OCR a standalone image file. Images are a single page by definition."""
    t0 = time.perf_counter()
    img = load_image(path)
    epage, log = ocr_page_image(img, 1, 1.0, cfg)
    epage.height, epage.width = float(img.shape[0]), float(img.shape[1])
    log["dpi"] = "native"
    log["page_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    doc.engine_log.append(log)
    doc.timings_ms["ocr"] = doc.timings_ms.get("ocr", 0.0) + (time.perf_counter() - t0) * 1000
    return [epage]
