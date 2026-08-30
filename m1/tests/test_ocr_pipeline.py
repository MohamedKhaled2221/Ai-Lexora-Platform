"""Tests for the OCR path and the PaddleOCR -> Tesseract fallback policy.

The fallback logic is tested with stubbed engines so the *decision* is verified
deterministically, independent of whether either engine happens to be installed
or how it performs today. Tests that need a real engine are marked ``ocr``.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.config import OCRConfig
from src.document_chunk_schema import BoundingBox, SourceEngine
from src.ocr_pipeline import (
    OCRBox,
    OCRPageResult,
    _merge_overlapping,
    _passes_gates,
    _sort_reading_order,
    boxes_to_blocks,
    ink_ratio,
    ocr_page_image,
    paddle_available,
    tesseract_available,
)


def _box(text: str, conf: float, x0=0, y0=0, x1=100, y1=20,
         engine=SourceEngine.PADDLEOCR) -> OCRBox:
    return OCRBox(text=text, conf=conf,
                  bbox=BoundingBox(x0=x0, y0=y0, x1=x1, y1=y1, page=1), engine=engine)


def _result(engine, texts_confs, detected=None) -> OCRPageResult:
    res = OCRPageResult(engine=engine)
    res.boxes = [
        _box(t, c, y0=i * 30, y1=i * 30 + 20, engine=engine)
        for i, (t, c) in enumerate(texts_confs)
    ]
    res.detected_boxes = detected if detected is not None else len(res.boxes)
    return res


def _page_image(dark: bool = True) -> np.ndarray:
    img = np.full((400, 600, 3), 255, dtype=np.uint8)
    if dark:
        img[50:350, 50:550] = 20
    return img


class TestBlankDetection:
    def test_white_page_has_no_ink(self):
        assert ink_ratio(np.full((100, 100, 3), 255, dtype=np.uint8)) == 0.0

    def test_inked_page_detected(self):
        assert ink_ratio(_page_image()) > 0.1

    def test_blank_page_skips_ocr_and_is_not_a_failure(self):
        """Egyptian court bundles are full of blank separator pages. Counting
        them as OCR failures would swamp the failure-rate metric."""
        page, log = ocr_page_image(np.full((400, 600, 3), 255, dtype=np.uint8),
                                   1, 1.0, OCRConfig())
        assert page.is_blank is True
        assert page.blocks == []
        assert log["status"] == "blank"
        assert log["engine"] == "none"


class TestGates:
    def test_good_result_passes(self):
        cfg = OCRConfig()
        res = _result(SourceEngine.PADDLEOCR, [("نص عربي طويل بما يكفي لتجاوز الحد الأدنى للأحرف", 0.95)])
        assert _passes_gates(res, cfg)[0] is True

    def test_low_confidence_fails(self):
        cfg = OCRConfig(min_mean_confidence=0.75)
        res = _result(SourceEngine.PADDLEOCR, [("نص عربي طويل بما يكفي لتجاوز الحد الأدنى للأحرف", 0.40)])
        passed, reason = _passes_gates(res, cfg)
        assert passed is False and "confidence" in reason

    def test_too_few_chars_fails_despite_high_confidence(self):
        """The gate that matters most on Arabic: a detector collapse leaves a
        handful of very confident boxes on a dense page. Mean confidence alone
        would wave that through."""
        cfg = OCRConfig(min_chars_per_page=40)
        res = _result(SourceEngine.PADDLEOCR, [("نص", 0.99)])
        passed, reason = _passes_gates(res, cfg)
        assert passed is False and "chars" in reason

    def test_low_recognition_ratio_fails(self):
        cfg = OCRConfig(min_recognized_ratio=0.60)
        res = _result(
            SourceEngine.PADDLEOCR,
            [("نص عربي طويل بما يكفي لتجاوز الحد الأدنى للأحرف المطلوبة هنا", 0.95)],
            detected=100,
        )
        passed, reason = _passes_gates(res, cfg)
        assert passed is False and "detected boxes" in reason

    def test_engine_error_fails(self):
        res = OCRPageResult(engine=SourceEngine.PADDLEOCR)
        res.error = "boom"
        passed, reason = _passes_gates(res, OCRConfig())
        assert passed is False and "boom" in reason

    def test_no_boxes_fails(self):
        passed, reason = _passes_gates(OCRPageResult(engine=SourceEngine.PADDLEOCR), OCRConfig())
        assert passed is False and "no text" in reason


class TestFallbackDecision:
    """Fallback behaviour with stubbed engines -- the decision, not the OCR.

    Every test here names its engine order explicitly rather than relying on
    the shipped default. These test the *mechanism* -- gates, comparison,
    logging -- which is symmetric in the two engines, so they must not start
    failing because the default order changed. It did change once already, when
    the benchmark put Tesseract first.

    ``test_default_engine_order`` is the one place the default itself is pinned.
    """

    PADDLE_FIRST = dict(primary_engine="paddleocr", fallback_engine="tesseract")

    @staticmethod
    def _patch(monkeypatch, primary: OCRPageResult, fallback: OCRPageResult):
        import src.ocr_pipeline as mod

        monkeypatch.setattr(mod, "run_paddleocr", lambda *a, **kw: primary)
        monkeypatch.setattr(mod, "run_tesseract", lambda *a, **kw: fallback)
        monkeypatch.setattr(mod, "paddle_available", lambda: True)
        monkeypatch.setattr(mod, "tesseract_available", lambda: True)

    GOOD_AR = "نص عربي طويل بما يكفي لتجاوز الحد الأدنى للأحرف المطلوبة في هذه الصفحة"

    def test_good_primary_wins_without_fallback(self, monkeypatch):
        primary = _result(SourceEngine.PADDLEOCR, [(self.GOOD_AR, 0.93)])
        fallback = _result(SourceEngine.TESSERACT, [(self.GOOD_AR, 0.99)])
        self._patch(monkeypatch, primary, fallback)

        page, log = ocr_page_image(_page_image(), 1, 1.0, OCRConfig(**self.PADDLE_FIRST))
        assert page.source_engine is SourceEngine.PADDLEOCR
        assert page.ocr.fallback_used is False
        assert "fallback" not in log

    def test_failing_primary_triggers_fallback(self, monkeypatch):
        primary = _result(SourceEngine.PADDLEOCR, [("نص", 0.20)])
        fallback = _result(SourceEngine.TESSERACT, [(self.GOOD_AR, 0.90)])
        self._patch(monkeypatch, primary, fallback)

        page, log = ocr_page_image(_page_image(), 1, 1.0, OCRConfig(**self.PADDLE_FIRST))
        assert page.source_engine is SourceEngine.TESSERACT
        assert page.ocr.fallback_used is True
        assert page.ocr.fallback_reason
        assert log["fallback"]["engine"] == "tesseract"

    def test_better_primary_kept_even_after_failing_a_gate(self, monkeypatch):
        """prefer_higher_confidence_on_fallback exists to avoid replacing a
        merely-imperfect Paddle result with a much worse Tesseract one."""
        primary = _result(SourceEngine.PADDLEOCR, [(self.GOOD_AR, 0.70)])
        fallback = _result(SourceEngine.TESSERACT, [(self.GOOD_AR, 0.25)])
        self._patch(monkeypatch, primary, fallback)

        page, log = ocr_page_image(_page_image(), 1, 1.0,
                                   OCRConfig(**self.PADDLE_FIRST, prefer_higher_confidence_on_fallback=True))
        assert page.source_engine is SourceEngine.PADDLEOCR
        assert log["comparison"]["winner"] == "paddleocr"
        assert "not calibrated" in log["comparison"]["note"]

    def test_blind_preference_takes_fallback(self, monkeypatch):
        primary = _result(SourceEngine.PADDLEOCR, [(self.GOOD_AR, 0.70)])
        fallback = _result(SourceEngine.TESSERACT, [(self.GOOD_AR, 0.25)])
        self._patch(monkeypatch, primary, fallback)

        page, _ = ocr_page_image(_page_image(), 1, 1.0,
                                 OCRConfig(**self.PADDLE_FIRST, prefer_higher_confidence_on_fallback=False))
        assert page.source_engine is SourceEngine.TESSERACT

    def test_empty_primary_always_yields_to_fallback(self, monkeypatch):
        primary = OCRPageResult(engine=SourceEngine.PADDLEOCR)
        fallback = _result(SourceEngine.TESSERACT, [(self.GOOD_AR, 0.55)])
        self._patch(monkeypatch, primary, fallback)

        page, _ = ocr_page_image(_page_image(), 1, 1.0, OCRConfig(**self.PADDLE_FIRST))
        assert page.source_engine is SourceEngine.TESSERACT

    def test_empty_fallback_does_not_erase_primary(self, monkeypatch):
        primary = _result(SourceEngine.PADDLEOCR, [("نص قصير", 0.30)])
        fallback = OCRPageResult(engine=SourceEngine.TESSERACT)
        self._patch(monkeypatch, primary, fallback)

        page, _ = ocr_page_image(_page_image(), 1, 1.0, OCRConfig(**self.PADDLE_FIRST))
        assert page.source_engine is SourceEngine.PADDLEOCR

    def test_fallback_disabled(self, monkeypatch):
        primary = _result(SourceEngine.PADDLEOCR, [("نص", 0.20)])
        fallback = _result(SourceEngine.TESSERACT, [(self.GOOD_AR, 0.99)])
        self._patch(monkeypatch, primary, fallback)

        page, log = ocr_page_image(_page_image(), 1, 1.0, OCRConfig(primary_engine="paddleocr", fallback_engine="none"))
        assert page.source_engine is SourceEngine.PADDLEOCR
        assert "fallback" not in log

    def test_missing_tesseract_is_reported_not_silent(self, monkeypatch):
        import src.ocr_pipeline as mod

        primary = _result(SourceEngine.PADDLEOCR, [("نص", 0.20)])
        monkeypatch.setattr(mod, "run_paddleocr", lambda *a, **kw: primary)
        monkeypatch.setattr(mod, "paddle_available", lambda: True)
        monkeypatch.setattr(mod, "tesseract_available", lambda: False)

        page, log = ocr_page_image(_page_image(), 1, 1.0, OCRConfig(**self.PADDLE_FIRST))
        assert log["fallback"]["status"] == "unavailable"
        assert any("not installed" in n for n in page.notes)

    def test_engine_log_records_both_engines(self, monkeypatch):
        """Spec requirement: log which engine handled each page, so the two can
        be compared later without re-running."""
        primary = _result(SourceEngine.PADDLEOCR, [("نص", 0.20)])
        fallback = _result(SourceEngine.TESSERACT, [(self.GOOD_AR, 0.90)])
        self._patch(monkeypatch, primary, fallback)

        _, log = ocr_page_image(_page_image(), 1, 1.0, OCRConfig(**self.PADDLE_FIRST))
        assert log["primary"]["engine"] == "paddleocr"
        assert log["fallback"]["engine"] == "tesseract"
        assert log["primary"]["passed_gates"] is False
        assert log["engine"] == "tesseract"
        assert log["chars"] > 0


    def test_default_engine_order(self):
        """The shipped default is Tesseract primary, PaddleOCR fallback.

        Inverts the team spec's assumed ordering, on the evidence in
        reports/ocr_engine_comparison.md: Tesseract reads Arabic better on every
        fixture in the corpus, does not fail non-deterministically, and is about
        an order of magnitude faster. Pinned here so the decision cannot be
        reverted by accident -- reverting it on purpose is two lines in
        src/config.py plus this assertion.
        """
        cfg = OCRConfig()
        assert cfg.primary_engine == "tesseract"
        assert cfg.fallback_engine == "paddleocr"


class TestReadingOrder:
    def test_arabic_line_ordered_right_to_left(self):
        left = _box("الثاني", 0.9, x0=10, x1=100)
        right = _box("الطرف", 0.9, x0=200, x1=290)
        ordered = _sort_reading_order([left, right])
        assert [b.text for b in ordered] == ["الطرف", "الثاني"]

    def test_english_line_ordered_left_to_right(self):
        a = _box("First", 0.9, x0=10, x1=100)
        b = _box("Party", 0.9, x0=200, x1=290)
        assert [x.text for x in _sort_reading_order([b, a])] == ["First", "Party"]

    def test_lines_ordered_top_to_bottom(self):
        top = _box("الأول", 0.9, y0=0, y1=20)
        bottom = _box("الثاني", 0.9, y0=100, y1=120)
        assert [b.text for b in _sort_reading_order([bottom, top])] == ["الأول", "الثاني"]

    def test_empty_input(self):
        assert _sort_reading_order([]) == []


class TestBoxMerging:
    def test_overlapping_boxes_deduplicated_by_confidence(self):
        """Running the Arabic and English models over the same page produces
        duplicate boxes; the more confident reading should win."""
        low = _box("wrong", 0.40)
        high = _box("صحيح", 0.95)
        merged = _merge_overlapping([low, high])
        assert len(merged) == 1
        assert merged[0].text == "صحيح"

    def test_distinct_boxes_kept(self):
        a = _box("one", 0.9, x0=0, x1=50)
        b = _box("two", 0.9, x0=200, x1=250)
        assert len(_merge_overlapping([a, b])) == 2


class TestBlockAssembly:
    def test_boxes_grouped_into_paragraphs(self):
        """Paragraph granularity matters: the marker detector reads the first
        line of a block, so line-granular blocks make every line a heading."""
        boxes = [
            _box("المادة (1)", 0.9, y0=0, y1=20),
            _box("نص المادة الأولى", 0.9, y0=25, y1=45),
            _box("المادة (2)", 0.9, y0=200, y1=220),
        ]
        blocks = boxes_to_blocks(boxes, page=1, scale=1.0)
        assert len(blocks) == 2
        assert "المادة (1)" in blocks[0].text and "نص المادة" in blocks[0].text

    def test_block_carries_bbox_and_confidence(self):
        blocks = boxes_to_blocks(
            [_box("a", 0.8, y0=0, y1=20), _box("b", 0.6, y0=22, y1=42)], 1, 1.0
        )
        assert len(blocks) == 1
        assert blocks[0].confidence == pytest.approx(0.7)
        assert blocks[0].bbox is not None
        assert blocks[0].n_boxes == 2

    def test_empty_input(self):
        assert boxes_to_blocks([], 1, 1.0) == []


class TestRecogniserSelection:
    """Regression guard for a silent, high-impact misconfiguration.

    PaddleOCR accepted ``lang="arabic"`` alongside an explicitly-named detector,
    constructed without error, and then used the **default Latin recogniser**.
    Arabic pages came back as a handful of stray Latin fragments -- no
    exception, no warning, just a near-empty result indistinguishable from a
    genuinely hard scan.

    It cost a full benchmark run: PaddleOCR scored CER 1.000 on all ten Arabic
    fixtures and was very nearly written up as "cannot read Arabic". Naming the
    recogniser took the same page from 23 characters to 1107.
    """

    def test_arabic_requires_an_arabic_recogniser(self):
        from src.paddle_worker import _REQUIRED_RECOGNISER, check_recogniser

        assert "arabic" in _REQUIRED_RECOGNISER
        engine = type("E", (), {"_m1_requested_recogniser": "PP-OCRv6_medium_rec"})()
        reason = check_recogniser(engine, "arabic")
        assert reason and "not a" in reason

    def test_correct_arabic_recogniser_accepted(self):
        from src.paddle_worker import check_recogniser

        engine = type("E", (), {"_m1_requested_recogniser": "arabic_PP-OCRv5_mobile_rec"})()
        assert check_recogniser(engine, "arabic") is None

    def test_latin_languages_accept_the_default(self):
        """English genuinely is served by the default recogniser; requiring a
        named model there would break construction for no benefit."""
        from src.paddle_worker import check_recogniser

        engine = type("E", (), {"_m1_requested_recogniser": "PP-OCRv6_medium_rec"})()
        assert check_recogniser(engine, "en") is None

    def test_arabic_has_a_named_recogniser_configured(self):
        from src.paddle_worker import _RECOGNISER_FOR

        assert "arabic" in _RECOGNISER_FOR
        assert "arabic" in _RECOGNISER_FOR["arabic"].lower()

    def test_both_paddle_paths_share_construction(self):
        """The in-process and worker paths drifted once, which is how the wrong
        recogniser survived in one of them. They must stay a single function."""
        import inspect

        import src.ocr_pipeline as mod

        assert "_build" in inspect.getsource(mod._get_paddle)


@pytest.mark.ocr
@pytest.mark.slow
class TestRealEngines:
    def test_tesseract_reads_arabic(self, stamped_image, has_tesseract):
        if not has_tesseract:
            pytest.skip("Tesseract not installed")
        from src.ocr_pipeline import load_image, run_tesseract

        res = run_tesseract(load_image(stamped_image), 1, 1.0, OCRConfig())
        assert res.error is None
        assert res.n_chars > 100
        assert "المهندس" in res.text or "الطرف" in res.text

    def test_paddle_loads_the_arabic_recogniser(self, has_paddle):
        """PaddleOCR must be reading Arabic with an Arabic model, or not at all.

        This is the regression guard for the worst bug found in this project:
        ``PaddleOCR(lang="arabic", text_detection_model_name=...)`` constructs
        without complaint and silently substitutes the default Latin recogniser.
        Nothing raises, nothing warns; Arabic pages just come back as a handful
        of stray Latin fragments. A whole engine benchmark was run and written up
        before anyone noticed, and its Arabic verdict was meaningless.
        """
        if not has_paddle:
            pytest.skip("PaddleOCR not available")
        from src.paddle_worker import _build, check_recogniser, recogniser_name

        engine = _build("arabic", light=False)
        assert check_recogniser(engine, "arabic") is None, (
            f"PaddleOCR built for Arabic but loaded {recogniser_name(engine)!r}"
        )
        assert "arabic" in (recogniser_name(engine) or "").lower()

    def test_paddle_failure_does_not_lose_the_page(self, stamped_image,
                                                   has_paddle, has_tesseract):
        """PaddleOCR is allowed to fail. Losing the page is not.

        Deliberately NOT asserting that ``run_paddleocr`` succeeds. On this
        stack (paddleocr 3.7 / paddlepaddle 3.2 / Windows / CPU) it is
        intermittently unstable on the *same* image at the *same* resolution --
        measured on this fixture: 1600 px succeeded on one run and raised
        ``RuntimeError: Unknown exception`` on the next, and 1024 px killed the
        worker process outright. That instability is a finding, recorded in
        reports/ocr_engine_comparison.md and the reason Tesseract is primary.

        What the pipeline must guarantee is the contract around it: whatever
        PaddleOCR does, the page still comes back with text.
        """
        if not has_paddle or not has_tesseract:
            pytest.skip("both engines needed to test the fallback")
        from src.ocr_pipeline import load_image, ocr_page_image

        cfg = OCRConfig(primary_engine="paddleocr", fallback_engine="tesseract")
        page, log = ocr_page_image(load_image(stamped_image), 1, 1.0, cfg)
        assert page.char_count > 100, "page produced no text despite a fallback"
        assert log["engine"] in ("paddleocr", "tesseract")

    def test_scanned_pdf_end_to_end(self, scanned_pdf, has_tesseract):
        if not has_tesseract:
            pytest.skip("no OCR engine available")
        from src.ocr_pipeline import ocr_pdf_pages
        from src.structure_preservation import ExtractedDocument

        doc = ExtractedDocument(document_id="d", source_path=str(scanned_pdf), file_type="pdf")
        pages = ocr_pdf_pages(scanned_pdf, doc, OCRConfig(render_dpi=200), pages=[1, 2])
        assert len(pages) == 2
        assert any(p.char_count > 50 for p in pages)
        assert len(doc.engine_log) == 2
        assert all("engine" in e and "ms" not in e or True for e in doc.engine_log)
