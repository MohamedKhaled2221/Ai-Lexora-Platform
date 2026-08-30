"""Image preprocessing for the OCR path.

Written for, and validated by, ``scripts/arabic_preprocess_sweep.py``. Every
knob here exists because that sweep measures it; nothing is enabled by default
that the sweep did not show to be worth its cost.

WHY THIS IS A SEPARATE MODULE
=============================

Until this existed, the pipeline handed Tesseract exactly what MuPDF rendered:
an RGB raster at ``render_dpi``, unprocessed. That is a defensible default --
Tesseract does its own Otsu binarization internally -- but it left four
questions unmeasured, and Arabic is where they matter most, because the dots
that separate ب ت ث are a few pixels across and are the first thing any lossy
step destroys.

ORDER OF OPERATIONS
===================

``gray -> contrast -> deskew -> binarize``, and the order is not arbitrary:

* **Contrast before deskew** so the sharpening kernel sees the original pixel
  grid rather than one that has already been through a rotation's bilinear
  interpolation.
* **Deskew before binarize** because rotating a binary image resamples 0/255
  into a gray ramp along every glyph edge, which then has to be re-thresholded
  by Tesseract anyway -- so the binarization would be measuring the rotation's
  interpolation as much as the threshold.

Everything returns a 3-channel uint8 array even when the content is binary, so
this is a drop-in transform anywhere in the OCR path: ``ink_ratio``, both
engines and the blank-page gate all keep working unchanged.
"""

from __future__ import annotations

import logging
from typing import Literal

import numpy as np

logger = logging.getLogger(__name__)

Binarization = Literal["none", "otsu", "global", "adaptive"]


def _as_gray(img: "np.ndarray") -> "np.ndarray":
    if img.ndim == 2:
        return img
    import cv2

    return cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)


def _as_rgb(gray: "np.ndarray") -> "np.ndarray":
    import cv2

    return np.ascontiguousarray(cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB), dtype=np.uint8)


# ---------------------------------------------------------------------------
# Contrast / sharpening
# ---------------------------------------------------------------------------


def unsharp_mask(gray: "np.ndarray", amount: float = 0.8, radius: float = 1.2) -> "np.ndarray":
    """Light unsharp mask: ``gray + amount * (gray - blur(gray))``.

    Deliberately light. A strong mask thickens Arabic strokes until adjacent
    dots merge into one blob, which is the specific failure this whole exercise
    is trying to avoid -- so the default amount is well below what a
    document-scanning preset would use.
    """
    import cv2

    blurred = cv2.GaussianBlur(gray, (0, 0), radius)
    return cv2.addWeighted(gray, 1.0 + amount, blurred, -amount, 0)


def clahe(gray: "np.ndarray", clip: float = 2.0, tile: int = 8) -> "np.ndarray":
    """Contrast-limited adaptive histogram equalization.

    Helps pages with uneven illumination (photocopy hot-spots, scanner gutter
    shadow). Costs a little noise amplification in flat areas, which is why it
    is separate from :func:`unsharp_mask` rather than bundled with it.
    """
    import cv2

    return cv2.createCLAHE(clipLimit=clip, tileGridSize=(tile, tile)).apply(gray)


# ---------------------------------------------------------------------------
# Deskew
# ---------------------------------------------------------------------------


def estimate_skew(gray: "np.ndarray", limit: float = 6.0, step: float = 0.25,
                  work_height: int = 900) -> float:
    """Estimate page skew in degrees by projection-profile variance.

    Rotates a downscaled copy through ``±limit`` degrees and keeps the angle
    whose horizontal ink projection has the highest variance -- text lines are
    maximally "peaky" when they are horizontal.

    Chosen over the usual ``minAreaRect`` trick on purpose: that fits one box to
    all the ink, so a page with a marginal annotation column or a stamp reports
    the angle of the *bounding box*, not of the text lines. On the two-column
    Arabic fixtures here it disagreed with the projection method by several
    degrees, always in the wrong direction.

    Works on a downscaled copy because skew is a page-scale property; measuring
    it at full resolution costs ~30x more for the same answer.
    """
    import cv2

    if gray.shape[0] > work_height:
        ratio = work_height / gray.shape[0]
        small = cv2.resize(gray, (max(1, int(gray.shape[1] * ratio)), work_height),
                           interpolation=cv2.INTER_AREA)
    else:
        small = gray

    ink = (cv2.threshold(small, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1] > 0)
    ink = ink.astype(np.float32)
    if ink.sum() < 50:                      # effectively blank; nothing to align
        return 0.0

    h, w = ink.shape
    centre = (w / 2, h / 2)
    best_angle, best_score = 0.0, -1.0
    angle = -limit
    while angle <= limit + 1e-9:
        matrix = cv2.getRotationMatrix2D(centre, angle, 1.0)
        rotated = cv2.warpAffine(ink, matrix, (w, h), flags=cv2.INTER_LINEAR,
                                 borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        profile = rotated.sum(axis=1)
        score = float(np.var(profile))
        if score > best_score:
            best_score, best_angle = score, angle
        angle += step
    return best_angle


def deskew(gray: "np.ndarray", limit: float = 6.0, min_angle: float = 0.15
           ) -> tuple["np.ndarray", float]:
    """Straighten ``gray``. Returns ``(image, angle_applied)``.

    Rotations below ``min_angle`` are skipped rather than applied: the
    resampling costs a little sharpness, and below ~0.15 degrees there is no
    skew left to correct, so the trade is all cost and no benefit.

    The border is filled with the page's own median value rather than white, so
    a grey scan does not acquire four bright corners that the binarizer then has
    to reason about.
    """
    import cv2

    angle = estimate_skew(gray, limit=limit)
    if abs(angle) < min_angle:
        return gray, 0.0
    h, w = gray.shape
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    border = float(np.median(gray))
    rotated = cv2.warpAffine(gray, matrix, (w, h), flags=cv2.INTER_CUBIC,
                             borderMode=cv2.BORDER_CONSTANT, borderValue=border)
    return rotated, angle


# ---------------------------------------------------------------------------
# Binarization
# ---------------------------------------------------------------------------


def binarize(gray: "np.ndarray", method: Binarization = "none",
             threshold: int = 180, block_size: int = 31, c: int = 10) -> "np.ndarray":
    """Binarize ``gray`` by the named method.

    ``none`` is a real option, not a placeholder: Tesseract runs its own Otsu
    internally, so handing it grayscale is handing it the binarization it would
    have chosen anyway -- with the full grayscale still available to its own
    adaptive path. Any method here has to beat that, not merely beat nothing.

    ``block_size`` is forced odd, as OpenCV requires.
    """
    import cv2

    if method == "none":
        return gray
    if method == "otsu":
        return cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    if method == "global":
        return cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY)[1]
    if method == "adaptive":
        block = block_size if block_size % 2 == 1 else block_size + 1
        return cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block, c
        )
    raise ValueError(f"unknown binarization method: {method!r}")


# ---------------------------------------------------------------------------
# The one entry point the pipeline calls
# ---------------------------------------------------------------------------


def preprocess_for_ocr(img: "np.ndarray", cfg) -> tuple["np.ndarray", dict]:
    """Apply the configured preprocessing chain to one page raster.

    ``cfg`` is a :class:`~src.config.PreprocessConfig`. Returns
    ``(image, info)``; ``info`` records what was actually done (notably the skew
    angle found) so it can go in the engine log rather than being invisible.

    Returns the input untouched when ``cfg.enabled`` is False, including the
    array identity -- so the disabled path costs nothing at all, not even a
    colour conversion.
    """
    if not getattr(cfg, "enabled", False):
        return img, {"preprocessed": False}

    info: dict = {"preprocessed": True}
    gray = _as_gray(img)

    if cfg.contrast == "unsharp":
        gray = unsharp_mask(gray, amount=cfg.unsharp_amount, radius=cfg.unsharp_radius)
    elif cfg.contrast == "clahe":
        gray = clahe(gray)
    elif cfg.contrast == "clahe+unsharp":
        gray = unsharp_mask(clahe(gray), amount=cfg.unsharp_amount,
                            radius=cfg.unsharp_radius)
    info["contrast"] = cfg.contrast

    if cfg.deskew:
        gray, angle = deskew(gray, limit=cfg.deskew_limit_deg)
        info["skew_deg"] = round(angle, 3)

    gray = binarize(gray, cfg.binarization, threshold=cfg.global_threshold,
                    block_size=cfg.adaptive_block_size, c=cfg.adaptive_c)
    info["binarization"] = cfg.binarization

    return _as_rgb(gray), info
