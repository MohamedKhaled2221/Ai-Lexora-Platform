"""Tests for the pre-OCR image preprocessing module.

These do not check that preprocessing *helps* -- that is an accuracy question,
answered by ``scripts/arabic_preprocess_sweep.py`` against ground truth, not by
assertions. What they check is that each transform does what it says, that the
output stays a drop-in replacement for the raster it replaces, and that the
disabled path is genuinely a no-op -- because that last one is the shipped
default and a regression in it would silently change every scanned page.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.config import OCRConfig, PreprocessConfig
from src.preprocess import (
    binarize,
    clahe,
    deskew,
    estimate_skew,
    preprocess_for_ocr,
    unsharp_mask,
)


def _text_page(height: int = 400, width: int = 600, angle: float = 0.0) -> np.ndarray:
    """A synthetic page: horizontal dark bars on white, optionally rotated."""
    import cv2

    page = np.full((height, width), 255, dtype=np.uint8)
    for y in range(40, height - 40, 30):
        page[y:y + 8, 60:width - 60] = 30
    if angle:
        matrix = cv2.getRotationMatrix2D((width / 2, height / 2), angle, 1.0)
        page = cv2.warpAffine(page, matrix, (width, height),
                              borderMode=cv2.BORDER_CONSTANT, borderValue=255)
    return page


def _rgb(gray: np.ndarray) -> np.ndarray:
    return np.repeat(gray[:, :, None], 3, axis=2)


class TestBinarize:
    def test_none_is_identity(self):
        gray = _text_page()
        assert binarize(gray, "none") is gray

    @pytest.mark.parametrize("method", ["otsu", "global", "adaptive"])
    def test_output_is_two_valued(self, method):
        out = binarize(_text_page(), method)
        assert set(np.unique(out)) <= {0, 255}
        assert out.dtype == np.uint8

    def test_global_threshold_sensitivity(self):
        """A higher cut point must classify at least as much as ink, never less."""
        gray = np.tile(np.arange(256, dtype=np.uint8), (20, 1))
        low = (binarize(gray, "global", threshold=100) == 0).sum()
        high = (binarize(gray, "global", threshold=200) == 0).sum()
        assert high > low

    def test_adaptive_accepts_even_block_size(self):
        """OpenCV requires an odd block; the caller should not have to know."""
        out = binarize(_text_page(), "adaptive", block_size=30)
        assert out.shape == (400, 600)

    def test_unknown_method_raises(self):
        with pytest.raises(ValueError, match="unknown binarization"):
            binarize(_text_page(), "sauvola")


class TestContrast:
    def test_unsharp_increases_edge_contrast(self):
        gray = _text_page()
        sharpened = unsharp_mask(gray, amount=1.0)
        assert sharpened.std() >= gray.std()
        assert sharpened.dtype == np.uint8

    def test_clahe_preserves_shape_and_type(self):
        out = clahe(_text_page())
        assert out.shape == (400, 600)
        assert out.dtype == np.uint8


class TestDeskew:
    @pytest.mark.parametrize("angle", [-2.0, -0.75, 1.5, 3.0])
    def test_estimates_introduced_skew(self, angle):
        """The estimator must recover an angle it did not introduce itself."""
        estimated = estimate_skew(_text_page(angle=angle))
        # The correction rotates by +estimated, so it should oppose the skew.
        assert estimated == pytest.approx(-angle, abs=0.5)

    def test_straight_page_is_left_alone(self):
        gray = _text_page()
        out, applied = deskew(gray)
        assert applied == 0.0
        assert out is gray, "a sub-threshold rotation must not resample the page"

    def test_skewed_page_is_rotated(self):
        out, applied = deskew(_text_page(angle=2.0))
        assert applied != 0.0
        assert abs(estimate_skew(out)) < 0.5

    def test_blank_page_does_not_crash(self):
        assert estimate_skew(np.full((200, 200), 255, dtype=np.uint8)) == 0.0


class TestPreprocessForOCR:
    def test_disabled_returns_the_same_array(self):
        """The shipped default must not touch a single pixel, or copy them."""
        img = _rgb(_text_page())
        out, info = preprocess_for_ocr(img, PreprocessConfig(enabled=False))
        assert out is img
        assert info == {"preprocessed": False}

    def test_output_is_three_channel_uint8(self):
        """Everything downstream -- ink_ratio, both engines, the blank gate --
        expects an RGB uint8 array, whatever the content."""
        img = _rgb(_text_page(angle=1.0))
        cfg = PreprocessConfig(enabled=True, binarization="otsu", deskew=True,
                               contrast="unsharp")
        out, info = preprocess_for_ocr(img, cfg)
        assert out.ndim == 3 and out.shape[2] == 3
        assert out.dtype == np.uint8
        assert out.shape[:2] == img.shape[:2]
        assert info["binarization"] == "otsu"
        assert info["contrast"] == "unsharp"
        assert "skew_deg" in info

    def test_accepts_grayscale_input(self):
        out, _ = preprocess_for_ocr(_text_page(), PreprocessConfig(enabled=True))
        assert out.ndim == 3

    def test_skew_angle_is_reported(self):
        cfg = PreprocessConfig(enabled=True, deskew=True)
        _, info = preprocess_for_ocr(_rgb(_text_page(angle=2.0)), cfg)
        assert abs(info["skew_deg"]) > 0.5


class TestConfigDefaults:
    def test_preprocessing_is_off_by_default(self):
        """Off is a measured result (reports/arabic_preprocess_sweep.md), not an
        oversight, so it is asserted rather than left implicit."""
        cfg = OCRConfig()
        assert cfg.preprocess.enabled is False
        assert cfg.preprocess.binarization == "none"
        assert cfg.preprocess.deskew is False
        assert cfg.preprocess.contrast == "none"
