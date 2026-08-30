"""PaddleOCR-VL adapter -- evaluation only, not wired into the pipeline.

PaddleOCR-VL is **not** a variant of the classical PaddleOCR pipeline this repo
already ships and rejected (see ``reports/ocr_engine_comparison.md``). It is a
vision-language model -- a NaViT-style visual encoder feeding an ERNIE-4.5-0.3B
decoder, ~0.9B parameters total -- that reads a cropped layout block and
*generates* its text, rather than detecting text boxes and classifying glyph
sequences. It shares the ``paddleocr`` package name and nothing else: different
weights, different inference code, different failure modes. It is evaluated
here from scratch.

WHAT THIS MODULE IS
===================

A thin adapter with the **same signature as** :func:`src.ocr_pipeline.run_tesseract`
and :func:`src.ocr_pipeline.run_paddleocr`::

    run_paddleocr_vl(img, page, scale, cfg) -> OCRPageResult

so ``scripts/paddleocr_vl_benchmark.py`` can swap it into the existing harness
without the harness knowing. **Nothing imports it from the pipeline**, no
default changes, and ``SourceEngine`` is untouched -- results are tagged
``SourceEngine.PADDLEOCR`` with ``lang_model="paddleocr-vl-1.6"`` so the
existing schema still validates. Adopting it for production would mean adding
the enum member and a config branch; that is deliberately not done here.

WHERE THE SHAPE DIFFERS FROM THE OTHER ENGINES, AND WHY IT MATTERS
==================================================================

* **No per-atom confidence.** A generative decoder emits tokens, not box
  scores. Every :class:`OCRBox` therefore carries ``conf=1.0``, which means
  ``OCRConfig.drop_below_confidence`` and the pipeline's ``min_conf`` gate are
  **inert** for this engine -- it cannot report low confidence, so it cannot
  trigger a fallback that way. This is a real operational difference, not a
  detail of the adapter, and is reported as such.
* **Blocks, not words.** The layout detector emits one box per block
  (paragraph, table, heading); the VLM fills each with text. There are no
  word-level boxes, so ``atoms`` are blocks. The geometric table reconstructor
  in ``ocr_pipeline.tables_from_atoms`` reads word geometry and would find
  nothing here -- but it does not need to: the model emits tables directly as
  HTML, which :func:`page_tables` returns instead.
* **Local only.** ``vl_rec_backend="native"`` runs the weights in-process
  through PaddlePaddle. The other supported backends (``vllm-server``,
  ``sglang-server``, ``fastdeploy-server``, ``mlx-vlm-server``,
  ``llama-cpp-server``) all speak HTTP to a model server and are never selected
  here. There is no hosted-endpoint code path in this module: ``vl_rec_api_key``
  and ``vl_rec_server_url`` are left unset.
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .config import OCRConfig
from .document_chunk_schema import BoundingBox, SourceEngine
from .ocr_pipeline import OCRBox, OCRPageResult, _sort_reading_order

logger = logging.getLogger(__name__)

MODEL_TAG = "paddleocr-vl-1.6"

# The pipeline version, not the package version. v1.6 is the current default in
# paddleocr 3.7.0 and selects the PaddleOCR-VL-1.6-0.9B checkpoint; v1 and v1.5
# select the earlier ones. Pinned rather than defaulted so a package upgrade
# cannot silently change which model the numbers in the report describe.
PIPELINE_VERSION = "v1.6"

# Layout labels that are not page text. The pipeline's own markdown export drops
# these too; keeping the list here means the benchmark scores the same content
# whether it reads blocks or markdown.
NON_TEXT_LABELS = {
    "number", "header", "footer", "header_image", "footer_image",
    "aside_text", "seal", "image", "figure", "chart",
}

_PIPELINE: Any = None
_PIPELINE_KEY: tuple | None = None


@dataclass
class VLTable:
    """One table the model emitted, as HTML plus a parsed grid."""

    html: str
    rows: int
    cols: int
    cells: list[list[str]] = field(default_factory=list)
    bbox: tuple[float, float, float, float] | None = None


def available() -> bool:
    """True if the package exposes the VL pipeline. Says nothing about weights."""
    try:
        from paddleocr import PaddleOCRVL  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return True


def get_pipeline(device: str = "cpu", **kwargs):
    """Build (once) and return the local PaddleOCR-VL pipeline.

    Cached because construction loads ~1.9 GB of weights and costs tens of
    seconds -- doing it per page would make the timing figures meaningless.

    ``device`` is passed through to PaddleX: ``"cpu"``, or ``"gpu:0"`` on a
    paddlepaddle-gpu build. The backend is always ``native`` (in-process); no
    server URL and no API key is ever supplied, so there is no code path here
    that can reach a hosted endpoint.
    """
    global _PIPELINE, _PIPELINE_KEY
    key = (device, tuple(sorted(kwargs.items())))
    if _PIPELINE is not None and _PIPELINE_KEY == key:
        return _PIPELINE

    # Once the weights are cached, PaddleX still probes its four model hosters
    # for connectivity before doing anything. That probe is the only outbound
    # request in the whole path, it is not needed to load a cached model, and on
    # a firm network it would be the thing that looks like an API call. Off by
    # default here; the cached-directory branch is hit before any hoster is
    # consulted, so nothing about the run depends on it.
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

    from paddleocr import PaddleOCRVL

    _PIPELINE = PaddleOCRVL(
        pipeline_version=PIPELINE_VERSION,
        vl_rec_backend="native",
        device=device,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        **kwargs,
    )
    _PIPELINE_KEY = key
    return _PIPELINE


def reset_pipeline() -> None:
    """Drop the cached pipeline. Used by the benchmark between configurations."""
    global _PIPELINE, _PIPELINE_KEY
    _PIPELINE = None
    _PIPELINE_KEY = None


# ---------------------------------------------------------------------------
# Result parsing
# ---------------------------------------------------------------------------


def _as_dict(result: Any) -> dict:
    """PaddleX results are Mapping-like; normalize to a plain dict."""
    if isinstance(result, dict):
        return result
    for attr in ("json", "_json"):
        value = getattr(result, attr, None)
        if isinstance(value, dict):
            return value.get("res", value)
    try:
        return dict(result)
    except Exception:  # noqa: BLE001
        return {}


def _blocks(payload: dict) -> list[Any]:
    """The per-block parsing result, whatever key this version files it under.

    Blocks arrive as ``PaddleOCRVLBlock`` objects (plain attributes, and *not*
    Mapping-like -- ``dict(block)`` silently yields ``{}``), so they are handed
    on as-is and read through :func:`_field`.
    """
    for key in ("parsing_res_list", "layout_parsing_result", "parsing_result"):
        value = payload.get(key)
        if isinstance(value, list) and value:
            return list(value)
    return []


def _field(block: Any, *names: str) -> Any:
    """Read the first present field, whether the block is an object or a dict."""
    for name in names:
        if isinstance(block, dict):
            if name in block:
                return block[name]
        else:
            value = getattr(block, name, None)
            if value is not None:
                return value
    return None


def _block_text(block: Any) -> str:
    value = _field(block, "content", "block_content", "text", "block_text")
    return value if isinstance(value, str) else ""


def _block_label(block: Any) -> str:
    value = _field(block, "label", "block_label", "block_type")
    return value.lower() if isinstance(value, str) else ""


def _block_bbox(block: Any) -> tuple[float, float, float, float] | None:
    for key in ("bbox", "block_bbox", "block_box"):
        value = _field(block, key)
        if value is None:
            continue
        arr = np.asarray(value, dtype=float).reshape(-1)
        if arr.size == 4:
            return float(arr[0]), float(arr[1]), float(arr[2]), float(arr[3])
        if arr.size == 8:
            xs, ys = arr[0::2], arr[1::2]
            return float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max())
    return None


_TAG = re.compile(r"<[^>]+>")
_CELL = re.compile(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", re.S | re.I)
_ROW = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.S | re.I)
_TABLE = re.compile(r"<table\b.*?</table>", re.S | re.I)


def _strip_html(html: str) -> str:
    """Table HTML -> readable text, one row per line.

    The CER metric scores plain text against a plain-text reference, so a table
    that arrives as markup has to be flattened the same way the reference reads
    it: cells separated by spaces, rows by newlines.
    """
    rows = _ROW.findall(html)
    if not rows:
        return _TAG.sub(" ", html)
    out = []
    for row in rows:
        cells = [_TAG.sub("", c).strip() for c in _CELL.findall(row)]
        out.append(" ".join(c for c in cells if c))
    return "\n".join(r for r in out if r.strip())


def parse_table_html(html: str) -> VLTable:
    """Parse one ``<table>`` into a grid. Shape only -- no cell-content scoring."""
    cells: list[list[str]] = []
    for row in _ROW.findall(html):
        cells.append([_TAG.sub("", c).strip() for c in _CELL.findall(row)])
    rows = len(cells)
    cols = max((len(r) for r in cells), default=0)
    return VLTable(html=html, rows=rows, cols=cols, cells=cells)


def page_tables(res: OCRPageResult) -> list[VLTable]:
    """Tables the model emitted on this page, from the adapter's own record."""
    return list(getattr(res, "vl_tables", []) or [])


def _markdown_text(result: Any, payload: dict) -> str:
    """The pipeline's own markdown export.

    ``markdown`` is a computed property on the result object, not a key in its
    data dict, so the object is asked first and the dict only as a fallback.
    """
    for source in (getattr(result, "markdown", None), payload.get("markdown")):
        if isinstance(source, dict):
            for key in ("markdown_texts", "text", "markdown"):
                value = source.get(key)
                if isinstance(value, str) and value.strip():
                    return value
        elif isinstance(source, str) and source.strip():
            return source
    return ""


def _tables_from_result(payload: dict) -> list[str]:
    """Table HTML the pipeline reports separately from the block content."""
    out: list[str] = []
    for entry in payload.get("table_res_list") or []:
        html = _field(entry, "pred_html", "html", "table_html")
        if isinstance(html, dict):
            html = html.get("pred") or html.get("html")
        if isinstance(html, str) and "<table" in html.lower():
            out.append(html)
    return out


# ---------------------------------------------------------------------------
# The engine entry point
# ---------------------------------------------------------------------------


def run_paddleocr_vl(img: "np.ndarray", page: int, scale: float, cfg: OCRConfig,
                     *, device: str = "cpu", pipeline=None,
                     keep_non_text: bool = False) -> OCRPageResult:
    """Run PaddleOCR-VL over one page image.

    Same contract as :func:`src.ocr_pipeline.run_tesseract`: an RGB page array
    in, an :class:`OCRPageResult` out, exceptions captured into ``res.error``
    rather than raised, so one bad page cannot end a benchmark run.

    Two fields are attached beyond the shared contract, both read only by the
    benchmark: ``vl_tables`` (the tables the model emitted, as HTML plus a
    parsed grid) and ``vl_markdown`` (the pipeline's own markdown export, kept
    so the report can show what a downstream consumer would receive).
    """
    res = OCRPageResult(engine=SourceEngine.PADDLEOCR, scale=scale)
    res.vl_tables = []          # type: ignore[attr-defined]
    res.vl_markdown = ""        # type: ignore[attr-defined]
    t0 = time.perf_counter()

    try:
        pipe = pipeline if pipeline is not None else get_pipeline(device=device)
        # PaddleX expects BGR, the same convention cv2.imread uses; the
        # pipeline's rasters are RGB. Getting this backwards costs accuracy
        # silently rather than loudly, so it is done here once.
        bgr = np.ascontiguousarray(img[:, :, ::-1])
        outputs = list(pipe.predict(bgr))
    except Exception as exc:  # noqa: BLE001
        res.error = f"{type(exc).__name__}: {exc}"
        res.elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.warning("PaddleOCR-VL failed on page %s: %s", page, exc)
        return res

    if not outputs:
        res.error = "PaddleOCR-VL returned no result for the page"
        res.elapsed_ms = (time.perf_counter() - t0) * 1000
        return res

    payload = _as_dict(outputs[0])
    res.vl_markdown = _markdown_text(outputs[0], payload)   # type: ignore[attr-defined]
    for html in _tables_from_result(payload):
        res.vl_tables.append(parse_table_html(html))        # type: ignore[attr-defined]

    boxes: list[OCRBox] = []
    blocks = _blocks(payload)
    res.detected_boxes = len(blocks)

    for block in blocks:
        label = _block_label(block)
        raw = _block_text(block)
        if not raw.strip():
            continue

        bbox = _block_bbox(block)
        if "<table" in raw.lower():
            # A table can be reported twice -- once in ``table_res_list`` and
            # once as this block's content. Counting it twice would inflate the
            # table score, so the block copy only lands if it is new.
            seen = {t.html for t in res.vl_tables}   # type: ignore[attr-defined]
            for html in _TABLE.findall(raw):
                if html in seen:
                    continue
                table = parse_table_html(html)
                table.bbox = bbox
                res.vl_tables.append(table)     # type: ignore[attr-defined]
            text = _strip_html(raw)
        else:
            text = raw

        if not keep_non_text and label in NON_TEXT_LABELS and "<table" not in raw.lower():
            res.dropped_boxes += 1
            continue

        text = text.strip()
        if not text:
            continue

        x0, y0, x1, y1 = bbox if bbox else (0.0, 0.0, 0.0, 0.0)
        boxes.append(
            OCRBox(
                # A generative decoder reports no per-box score, so conf is a
                # constant. Recorded here rather than faked from token
                # probabilities: an invented confidence would silently disable
                # the pipeline's low-confidence fallback gate.
                text=text, conf=1.0,
                bbox=BoundingBox(x0=x0, y0=y0, x1=x1, y1=y1, page=page, scale=scale),
                engine=SourceEngine.PADDLEOCR, lang_model=MODEL_TAG,
            )
        )

    # The layout detector already emits blocks in reading order, including RTL
    # column order. Re-sorting geometrically would discard that and re-derive it
    # worse, so the model's order is kept -- except when boxes have no geometry
    # at all, where sorting is a no-op anyway.
    res.boxes = boxes if any(b.bbox.x1 for b in boxes) else _sort_reading_order(boxes)
    res.atoms = list(res.boxes)
    res.elapsed_ms = (time.perf_counter() - t0) * 1000
    return res
