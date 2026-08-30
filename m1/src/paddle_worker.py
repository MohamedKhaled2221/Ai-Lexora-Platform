"""PaddleOCR worker process.

WHY THIS EXISTS
===============

PaddleOCR on this stack (paddleocr 3.7 / paddlepaddle 3.2 / Windows / CPU)
does not always fail cleanly. On some inputs it raises a catchable
``RuntimeError("Unknown exception")``; on others the native layer dies with an
**access violation that terminates the interpreter**. No ``try``/``except`` can
catch the second kind -- the process is simply gone, taking the batch with it.

That is incompatible with the spec's requirement that Tesseract act as a
fallback "if PaddleOCR fails outright". A fallback that only handles Python
exceptions is not a fallback; it just narrows the window in which the pipeline
dies.

So PaddleOCR runs here, in a separate process, behind a line-oriented protocol.
If it crashes, the parent sees the pipe close, records the crash in the engine
log, and falls back to Tesseract for that page -- exactly as designed.

The worker is *persistent*: model weights take ~20-40s to load, so a
process-per-page would be unusable. One worker per language is started on first
use and reused for the rest of the run.

PROTOCOL
--------
Parent -> worker: one JSON object per line::

    {"npy": "<path to .npy RGB uint8 array>"}

Worker -> parent: one JSON object per line::

    {"ok": true,  "boxes": [[[[x,y],...], "text", 0.97], ...]}
    {"ok": false, "error": "..."}

The image goes via a temp ``.npy`` file rather than the pipe because pages are
tens of megabytes and Windows pipe buffering makes that fragile.

Run directly for debugging::

    python -m src.paddle_worker arabic
"""

from __future__ import annotations

import json
import sys


# A language whose recogniser has a dedicated model family must actually get
# that family. PaddleOCR does **not** guarantee this: asking for lang="arabic"
# with an explicitly-named detector constructs happily and silently substitutes
# the default Chinese/Latin recogniser, which reads an Arabic page as a handful
# of stray Latin fragments. That failure is invisible -- no exception, no
# warning, just a near-empty result that looks like a hard document.
#
# It is not hypothetical: it is what this project shipped. The first
# PaddleOCR-vs-Tesseract benchmark scored PaddleOCR at CER 1.000 on all ten
# Arabic fixtures, which was PP-OCRv6_medium_rec being asked to read Arabic.
#
# Values are substrings required in ``text_recognition_model_name``. Languages
# absent from this map accept whatever PaddleOCR chooses, because the default
# recogniser genuinely is the right model for Latin script.
_REQUIRED_RECOGNISER = {"arabic": "arabic", "ar": "arabic"}

# The recogniser to ask for by name, per language. Naming it is not optional:
# on this build ``PaddleOCR(lang="arabic", ...)`` raises "No models are
# available for lang='arabic'" for every variant *except* the one that also
# names a detector -- and that one constructs successfully while quietly using
# the default Latin recogniser. Asking for the model explicitly is the only way
# to actually get it.
#
# Measured on bench_wipo_eg088ar_1_clean.pdf, page 1, 1600 px:
#     default recogniser : 23 chars of Latin-looking noise
#     named recogniser   : 1074 chars of correct Arabic
_RECOGNISER_FOR = {
    "arabic": "arabic_PP-OCRv5_mobile_rec",
    "ar": "arabic_PP-OCRv5_mobile_rec",
}


def recogniser_name(engine) -> str | None:
    """The recognition model PaddleOCR actually loaded, if it will say.

    PaddleOCR 3.x exposes no reliable accessor for this, so :func:`_build`
    records what it asked for on the instance. That is weaker evidence than
    reading the loaded model back, but it is the difference between knowing and
    guessing which model is in use.
    """
    requested = getattr(engine, "_m1_requested_recogniser", None)
    if requested:
        return str(requested)
    params = getattr(engine, "_params", None)
    if isinstance(params, dict):
        name = params.get("text_recognition_model_name")
        if name:
            return str(name)
    return getattr(engine, "text_recognition_model_name", None)


def check_recogniser(engine, lang: str) -> str | None:
    """Return a rejection reason if ``engine`` is not really reading ``lang``."""
    required = _REQUIRED_RECOGNISER.get(lang.lower())
    if not required:
        return None
    name = recogniser_name(engine)
    if name is None:
        # Unverifiable means rejected, for a language we know has its own model.
        # An unverified instance is exactly the failure this check exists to
        # stop, and a verifiable variant is always tried first. If every variant
        # is rejected, :func:`_build` raises with the full list of attempts and
        # the pipeline falls back to Tesseract -- loud and diagnosable, rather
        # than a run that silently reads nothing.
        return f"could not confirm which recogniser was loaded for {lang!r}"
    if required not in name.lower():
        return f"loaded recogniser {name!r}, which is not a {lang!r} model"
    return None


def _build(lang: str, light: bool):
    """Construct a PaddleOCR instance, trying the API shapes across versions.

    Kept in sync with :func:`src.ocr_pipeline._get_paddle` -- see that function
    for why several variants are attempted.

    A variant that constructs but loads the wrong recogniser is **rejected and
    probing continues** (see :data:`_REQUIRED_RECOGNISER`). Without that check
    the very first Arabic-capable-looking variant wins and reads nothing.
    """
    from paddleocr import PaddleOCR

    base = {
        "use_textline_orientation": True,
        "use_doc_orientation_classify": False,
        "use_doc_unwarping": False,
    }
    # Order matters and must match src.ocr_pipeline._get_paddle: the detector
    # PaddleOCR picks by default (PP-OCRv6_medium_det on this build) reads
    # noticeably more text than an explicitly-named PP-OCRv5 detector, so the
    # unqualified variant is tried first. Naming a detector here dropped the
    # stamped-page fixture from 645 chars to 101.
    variants = [
        {"use_angle_cls": True, "show_log": False},          # 2.x
        {"use_angle_cls": True},                             # 2.x, no show_log
        *([dict(base, text_detection_model_name="PP-OCRv5_mobile_det")] if light else []),
        base,                                                # 3.x, default detector
        {"use_textline_orientation": True},                  # 3.x, all defaults
        dict(base, text_detection_model_name="PP-OCRv5_server_det"),
        {},                                                  # bare
    ]
    named = _RECOGNISER_FOR.get(lang.lower())
    if named:
        # Ask for the language's recogniser by name, ahead of anything that
        # lets PaddleOCR choose. Every variant below that merely passes
        # ``lang=`` either raises or silently substitutes.
        variants = [dict(v, text_recognition_model_name=named) for v in variants
                    if "show_log" not in v] + variants

    errors = []
    for alias in ([lang, "ar"] if lang == "arabic" else [lang]):
        for kw in variants:
            try:
                engine = PaddleOCR(lang=alias, **kw)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{alias} {sorted(kw)}: {type(exc).__name__}: {exc}")
                continue
            engine._m1_requested_recogniser = kw.get("text_recognition_model_name")
            wrong = check_recogniser(engine, alias)
            if wrong:
                errors.append(f"{alias} {sorted(kw)}: {wrong}")
                continue
            return engine
    raise RuntimeError("could not construct PaddleOCR: " + " | ".join(errors[:8]))


def _infer(engine, img):
    """Call whichever inference entry point this PaddleOCR version exposes."""
    for call in (
        lambda: engine.ocr(img, cls=True),
        lambda: engine.predict(img),
        lambda: engine.ocr(img),
    ):
        try:
            return call()
        except (TypeError, AttributeError):
            continue
    raise RuntimeError("no usable PaddleOCR inference entry point")


def _normalize(result) -> list:
    """Flatten PaddleOCR's several output shapes to ``[[quad, text, score], ...]``."""
    out: list = []
    if not result:
        return out
    first = result[0] if isinstance(result, (list, tuple)) and result else None

    # 3.x: dict-like OCRResult
    if isinstance(first, dict) or hasattr(first, "get"):
        try:
            texts = list(first.get("rec_texts") or [])
            scores = list(first.get("rec_scores") or [])
            polys = list(first.get("rec_polys") or first.get("dt_polys") or [])
            for t, s, q in zip(texts, scores, polys):
                if str(t).strip():
                    out.append([[[float(p[0]), float(p[1])] for p in q], str(t), float(s)])
            return out
        except Exception:  # noqa: BLE001
            pass

    # 2.x: [[ [quad, (text, score)], ... ]]
    lines = first if isinstance(first, (list, tuple)) else result
    for line in lines or []:
        try:
            quad, payload = line[0], line[1]
            text, score = (
                (payload[0], payload[1]) if isinstance(payload, (list, tuple)) else (payload, 0.0)
            )
            if str(text).strip():
                out.append([[[float(p[0]), float(p[1])] for p in quad], str(text), float(score)])
        except (IndexError, TypeError, ValueError):
            continue
    return out


def _claim_stdout():
    """Take exclusive ownership of stdout for the protocol.

    Reassigning ``sys.stdout`` is not enough. PaddlePaddle's C++ layer and its
    oneDNN backend write to **file descriptor 1 directly**, bypassing Python
    entirely, and a single line of "Creating model: ..." on that fd corrupts
    the JSON stream and makes every page look like a PaddleOCR failure.

    So we duplicate fd 1 to a private descriptor for our own use, then point
    the real fd 1 at stderr. Native writes then land harmlessly in stderr
    (which the parent discards) while the protocol has a channel nobody else
    can reach.
    """
    import os

    private = os.dup(1)
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    return os.fdopen(private, "w", encoding="utf-8", buffering=1)


def main() -> int:
    lang = sys.argv[1] if len(sys.argv) > 1 else "arabic"
    light = (sys.argv[2].lower() == "true") if len(sys.argv) > 2 else False

    real_stdout = _claim_stdout()

    try:
        import numpy as np

        engine = _build(lang, light)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": f"init failed: {exc}"}), file=real_stdout, flush=True)
        return 1

    print(json.dumps({"ok": True, "ready": True,
                      "recogniser": recogniser_name(engine)}),
          file=real_stdout, flush=True)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            print(json.dumps({"ok": False, "error": f"bad request: {exc}"}),
                  file=real_stdout, flush=True)
            continue
        if request.get("shutdown"):
            return 0
        try:
            img = np.load(request["npy"])
            boxes = _normalize(_infer(engine, img))
            print(json.dumps({"ok": True, "boxes": boxes}), file=real_stdout, flush=True)
        except Exception as exc:  # noqa: BLE001
            print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}),
                  file=real_stdout, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
