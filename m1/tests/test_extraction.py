"""Tests for the text-layer path: PyMuPDF, Docling merge, DOCX and TXT."""

from __future__ import annotations

import pytest

from src.config import ExtractionConfig
from src.document_chunk_schema import BlockType, SourceEngine
from src.extract_pymupdf_docling import (
    _iou,
    _merge_docling_labels,
    _merge_pages,
    docling_available,
    extract_docx,
    extract_pdf_pymupdf,
    extract_plaintext,
    extract_text_pdf,
)
from src.structure_preservation import ExtractedDocument


def _doc(path="test", ftype="pdf") -> ExtractedDocument:
    return ExtractedDocument(document_id="doc_test", source_path=str(path), file_type=ftype)


class _FakeDoclingDoc:
    """Minimal stand-in for a DoclingDocument, for tests that only care whether
    Docling was *invoked*, not what it returned."""

    texts: list = []
    tables: list = []
    pages: dict = {}

    def iterate_items(self):
        return iter(())


class TestPyMuPDF:
    def test_extracts_pages_and_text(self, contract_pdf):
        pages, warnings = extract_pdf_pymupdf(contract_pdf, ExtractionConfig())
        assert len(pages) == 3
        assert all(p.blocks for p in pages)
        assert not warnings

    def test_page_numbers_are_1_based_and_ordered(self, contract_pdf):
        pages, _ = extract_pdf_pymupdf(contract_pdf, ExtractionConfig())
        assert [p.page_number for p in pages] == [1, 2, 3]

    def test_bounding_boxes_present_and_sane(self, contract_pdf):
        """Bounding boxes are a named spec requirement -- they must survive
        extraction with plausible geometry, not just exist."""
        pages, _ = extract_pdf_pymupdf(contract_pdf, ExtractionConfig())
        page = pages[0]
        boxed = [b for b in page.blocks if b.bbox is not None]
        assert boxed, "no block carried a bounding box"
        for b in boxed:
            assert b.bbox.width > 0 and b.bbox.height > 0
            assert 0 <= b.bbox.x0 <= page.width + 1
            assert 0 <= b.bbox.y0 <= page.height + 1
            assert b.bbox.page == page.page_number

    def test_font_metrics_captured(self, contract_pdf):
        """Font size drives typographic heading detection, so it must be read."""
        pages, _ = extract_pdf_pymupdf(contract_pdf, ExtractionConfig())
        sizes = [b.font_size for b in pages[0].blocks if b.font_size]
        assert sizes
        assert max(sizes) > min(sizes), "expected varied font sizes in a titled document"

    def test_reading_order_recorded(self, contract_pdf):
        pages, _ = extract_pdf_pymupdf(contract_pdf, ExtractionConfig())
        orders = [b.order for b in pages[0].blocks]
        assert orders == sorted(orders)
        assert len(set(orders)) == len(orders)

    def test_only_pages_limits_extraction(self, contract_pdf):
        """Hybrid PDFs need the text path restricted to text pages."""
        pages, _ = extract_pdf_pymupdf(contract_pdf, ExtractionConfig(), only_pages=[2])
        assert [p.page_number for p in pages] == [2]

    def test_source_engine_tagged(self, contract_pdf):
        pages, _ = extract_pdf_pymupdf(contract_pdf, ExtractionConfig())
        assert all(b.source_engine is SourceEngine.PYMUPDF for b in pages[0].blocks)

    def test_arabic_public_pdf_yields_text(self, public_arabic_pdf):
        pages, _ = extract_pdf_pymupdf(public_arabic_pdf, ExtractionConfig())
        text = "\n".join(p.text for p in pages[:5])
        assert any("؀" <= c <= "ۿ" for c in text)


class TestDoclingMerge:
    def test_iou_basics(self):
        from src.document_chunk_schema import BoundingBox

        a = BoundingBox(x0=0, y0=0, x1=10, y1=10)
        assert _iou(a, a) == pytest.approx(1.0)
        assert _iou(a, BoundingBox(x0=20, y0=20, x1=30, y1=30)) == 0.0
        assert 0 < _iou(a, BoundingBox(x0=5, y0=5, x1=15, y1=15)) < 1

    def test_labels_transferred_but_not_text(self, contract_pdf):
        """The merge takes Docling's *label* only. Docling reflows text in ways
        that can disturb Arabic, so PyMuPDF stays the source of truth for it."""
        from src.document_chunk_schema import BoundingBox

        pages, _ = extract_pdf_pymupdf(contract_pdf, ExtractionConfig())
        target = pages[0].blocks[0]
        original_text = target.text
        items = [{
            "page": 1,
            "bbox": BoundingBox(
                x0=target.bbox.x0, y0=target.bbox.y0,
                x1=target.bbox.x1, y1=target.bbox.y1, page=1,
            ),
            "label": "section_header",
            "level": 2,
            "text": "COMPLETELY DIFFERENT TEXT FROM DOCLING",
        }]
        matched = _merge_docling_labels(pages, items)
        assert matched == 1
        assert target.block_type is BlockType.HEADING
        assert target.struct.heading_level == 2
        assert target.text == original_text, "Docling text must never overwrite PyMuPDF's"
        assert target.source_engine is SourceEngine.PYMUPDF_DOCLING

    def test_non_overlapping_items_are_ignored(self, contract_pdf):
        from src.document_chunk_schema import BoundingBox

        pages, _ = extract_pdf_pymupdf(contract_pdf, ExtractionConfig())
        items = [{
            "page": 1,
            "bbox": BoundingBox(x0=9000, y0=9000, x1=9100, y1=9100, page=1),
            "label": "section_header", "level": 1, "text": "",
        }]
        assert _merge_docling_labels(pages, items) == 0

    def test_degrades_cleanly_when_docling_disabled(self, contract_pdf):
        cfg = ExtractionConfig(use_docling=False)
        doc = _doc(contract_pdf)
        extract_text_pdf(contract_pdf, doc, cfg)
        assert doc.pages
        assert not any(e.get("engine") == "docling" for e in doc.engine_log)

    def test_docling_failure_is_logged_not_raised(self, contract_pdf, monkeypatch):
        """A Docling failure must degrade the pipeline, never break it -- and it
        must be recorded, not swallowed."""
        import src.extract_pymupdf_docling as mod

        def boom(*a, **kw):
            raise RuntimeError("simulated Docling explosion")

        monkeypatch.setattr(mod, "_docling_convert", boom)
        monkeypatch.setattr(mod, "docling_available", lambda: True)

        doc = _doc(contract_pdf)
        extract_text_pdf(contract_pdf, doc, ExtractionConfig(use_docling=True))

        assert doc.pages, "PyMuPDF output must survive a Docling failure"
        assert any("Docling failed" in w for w in doc.warnings)
        assert any(e.get("status") == "failed" for e in doc.engine_log)

    def test_docling_timeout_is_enforced(self, contract_pdf, monkeypatch):
        """Docling has no cancellation, so the wall-clock deadline is the only
        thing bounding a batch. It must actually fire."""
        import time

        import src.extract_pymupdf_docling as mod

        monkeypatch.setattr(mod, "docling_available", lambda: True)
        monkeypatch.setattr(
            mod, "_get_converter",
            lambda: type("C", (), {"convert": lambda self, p: time.sleep(30)})(),
        )
        doc = _doc(contract_pdf)
        cfg = ExtractionConfig(use_docling=True, docling_timeout_s=1)
        start = time.perf_counter()
        extract_text_pdf(contract_pdf, doc, cfg)
        elapsed = time.perf_counter() - start

        assert elapsed < 15, "timeout did not abandon the Docling thread"
        assert doc.pages
        assert any("Docling failed" in w or "budget" in w for w in doc.warnings)

    def test_long_document_skips_docling(self, contract_pdf, monkeypatch):
        """Docling's preprocessing can raise std::bad_alloc in native code and
        **abort the interpreter** -- the thread timeout cannot save us, because
        there is no process left. Long documents must be excluded before
        Docling is entered at all."""
        import src.extract_pymupdf_docling as mod

        monkeypatch.setattr(mod, "docling_available", lambda: True)
        monkeypatch.setattr(
            mod, "_docling_convert",
            lambda *a, **k: pytest.fail("Docling must not run on an over-length document"),
        )
        doc = _doc(contract_pdf)
        cfg = ExtractionConfig(use_docling=True, docling_max_pages=1)
        extract_text_pdf(contract_pdf, doc, cfg)

        assert doc.pages, "PyMuPDF extraction must still happen"
        assert any("Docling skipped" in w for w in doc.warnings)
        assert any(e.get("status") == "skipped" for e in doc.engine_log)

    def test_oversized_pages_skip_docling(self, contract_pdf, monkeypatch):
        import src.extract_pymupdf_docling as mod

        monkeypatch.setattr(mod, "docling_available", lambda: True)
        monkeypatch.setattr(
            mod, "_docling_convert",
            lambda *a, **k: pytest.fail("Docling must not run on oversized pages"),
        )
        doc = _doc(contract_pdf)
        cfg = ExtractionConfig(use_docling=True, docling_max_page_pixels=1000)
        extract_text_pdf(contract_pdf, doc, cfg)
        assert any("MP" in w for w in doc.warnings)

    def test_guard_allows_normal_documents(self, contract_pdf, monkeypatch):
        """The guard must not exclude everything -- a 3-page A4 contract is
        exactly what Docling is for."""
        import src.extract_pymupdf_docling as mod

        called = []
        monkeypatch.setattr(mod, "docling_available", lambda: True)
        monkeypatch.setattr(mod, "_docling_convert",
                            lambda *a, **k: called.append(True) or _FakeDoclingDoc())
        doc = _doc(contract_pdf)
        extract_text_pdf(contract_pdf, doc, ExtractionConfig(use_docling=True))
        assert called, "Docling was skipped on a document it should handle"

    @pytest.mark.docling
    @pytest.mark.slow
    def test_real_docling_labels_something(self, contract_pdf, has_docling):
        if not has_docling:
            pytest.skip("Docling not installed")
        doc = _doc(contract_pdf)
        extract_text_pdf(contract_pdf, doc, ExtractionConfig(use_docling=True, docling_timeout_s=600))
        entries = [e for e in doc.engine_log if e.get("engine") == "docling"]
        assert entries, "Docling produced no engine-log entry"
        assert any(e.get("status") == "ok" for e in entries)


class TestDocx:
    def test_paragraphs_and_headings(self, contract_docx):
        doc = _doc(contract_docx, "docx")
        extract_docx(contract_docx, doc, ExtractionConfig(use_docling=False))
        assert doc.pages
        blocks = list(doc.all_blocks())
        assert blocks
        assert any(b.block_type is BlockType.HEADING for b in blocks)

    def test_tables_extracted(self, contract_docx):
        doc = _doc(contract_docx, "docx")
        extract_docx(contract_docx, doc, ExtractionConfig(use_docling=False))
        tables = list(doc.all_tables())
        assert tables
        assert tables[0].shape[1] == 5

    def test_pagination_warning_is_explicit(self, contract_docx):
        """DOCX page numbers are synthesized. Consumers must be told, or they
        will compare them to PDF page numbers."""
        doc = _doc(contract_docx, "docx")
        extract_docx(contract_docx, doc, ExtractionConfig(use_docling=False))
        assert any("pagination" in w for w in doc.warnings)

    def test_python_docx_fallback_used_when_docling_off(self, contract_docx):
        doc = _doc(contract_docx, "docx")
        extract_docx(contract_docx, doc, ExtractionConfig(use_docling=False))
        assert any(e.get("engine") == "python-docx" for e in doc.engine_log)


class TestPlaintext:
    def test_utf8_arabic(self, statute_txt):
        doc = _doc(statute_txt, "txt")
        extract_plaintext(statute_txt, doc)
        assert len(doc.pages) == 1
        assert "المادة" in doc.full_text

    def test_paragraphs_split_on_blank_lines(self, statute_txt):
        doc = _doc(statute_txt, "txt")
        extract_plaintext(statute_txt, doc)
        assert len(doc.pages[0].blocks) > 5

    def test_cp1256_legacy_encoding(self, tmp_path):
        """Older Egyptian office software still emits CP1256."""
        p = tmp_path / "legacy.txt"
        p.write_bytes("المادة الأولى من العقد".encode("cp1256"))
        doc = _doc(p, "txt")
        extract_plaintext(p, doc)
        assert "المادة" in doc.full_text
        assert any("cp1256" in w for w in doc.warnings)

    def test_encoding_recorded_in_engine_log(self, statute_txt):
        doc = _doc(statute_txt, "txt")
        extract_plaintext(statute_txt, doc)
        entry = next(e for e in doc.engine_log if e["engine"] == "plaintext")
        assert entry["encoding"].startswith("utf-8")


class TestPageMerging:
    def test_disjoint_pages_interleave_in_order(self, make_doc):
        """Hybrid PDFs produce disjoint page sets from two extractors; they must
        land in one page-ordered document."""
        doc = _doc()
        a = make_doc([(1, ["text page one"]), (3, ["text page three"])])
        b = make_doc([(2, ["ocr page two"])])
        _merge_pages(doc, a.pages)
        _merge_pages(doc, b.pages)
        assert [p.page_number for p in doc.pages] == [1, 2, 3]

    def test_same_page_from_both_paths_is_combined(self, make_doc):
        doc = _doc()
        _merge_pages(doc, make_doc([(1, ["from text layer"])]).pages)
        _merge_pages(doc, make_doc([(1, ["from ocr"])]).pages)
        assert len(doc.pages) == 1
        texts = [b.text for b in doc.pages[0].blocks]
        assert texts == ["from text layer", "from ocr"]
        orders = [b.order for b in doc.pages[0].blocks]
        assert len(set(orders)) == 2, "merged blocks must not collide on order"


class TestDoclingTablePageProvenance:
    """``_docling_tables`` must never produce a page-less or sub-1 table page.

    ``page`` is required and ``ge=1`` on the emitted chunk, so a table whose
    page is lost here becomes an invalid chunk downstream. Docling gives
    tables no ``prov`` at all for formats it reads without a page model
    (DOCX), which is a genuinely single-page source, not a lost number.
    """

    @staticmethod
    def _fake_doc(page_no, *, with_prov=True):
        class _Cell:
            def __init__(self, text): self.text = text

        class _Data:
            def __init__(self, grid): self.grid = grid

        class _Prov:
            def __init__(self, pno): self.page_no, self.bbox = pno, None

        class _Tbl:
            def __init__(self):
                self.data = _Data([[_Cell("a"), _Cell("b")], [_Cell("1"), _Cell("2")]])
                self.prov = [_Prov(page_no)] if with_prov else []

        class _Doc:
            def __init__(self): self.tables = [_Tbl()]

        return _Doc()

    def test_real_page_number_is_kept(self):
        from src.extract_pymupdf_docling import _docling_tables

        assert _docling_tables(self._fake_doc(3))[0].page == 3

    @pytest.mark.parametrize(
        "kwargs",
        [
            pytest.param({"page_no": None, "with_prov": False}, id="no-prov-docx"),
            pytest.param({"page_no": None}, id="page_no-None"),
            pytest.param({"page_no": 0}, id="page_no-zero"),
            pytest.param({"page_no": "not-an-int"}, id="page_no-garbage"),
        ],
    )
    def test_absent_or_invalid_page_falls_back_to_one(self, kwargs):
        from src.extract_pymupdf_docling import _docling_tables

        page = _docling_tables(self._fake_doc(**kwargs))[0].page
        assert page == 1, "must never be None or < 1 -- the chunk schema forbids it"
