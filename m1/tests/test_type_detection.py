"""Tests for input type detection and scanned/text-PDF routing."""

from __future__ import annotations

import pytest

from src.config import PUBLIC_CORPUS_DIR
from src.type_detection import (
    ExtractionRoute,
    FileType,
    classify_pdf,
    detect,
    detect_file_type,
    text_layer_quality,
)


class TestFileType:
    def test_pdf_by_magic(self, contract_pdf):
        ftype, how = detect_file_type(contract_pdf)
        assert ftype is FileType.PDF
        assert how == "magic"

    def test_docx_by_magic(self, contract_docx):
        ftype, how = detect_file_type(contract_docx)
        assert ftype is FileType.DOCX
        assert how in ("magic+zip", "zip-listing")

    def test_png_by_magic(self, stamped_image):
        ftype, how = detect_file_type(stamped_image)
        assert ftype is FileType.IMAGE
        assert how == "magic"

    def test_txt_by_extension(self, statute_txt):
        ftype, _ = detect_file_type(statute_txt)
        assert ftype is FileType.TXT

    def test_magic_beats_wrong_extension(self, tmp_path, contract_pdf):
        """A PDF named .txt must still be detected as a PDF.

        This is the case that matters in practice: scanned material arrives from
        clients with whatever extension the sender's scanner produced.
        """
        wrong = tmp_path / "actually_a_pdf.txt"
        wrong.write_bytes(contract_pdf.read_bytes())
        ftype, how = detect_file_type(wrong)
        assert ftype is FileType.PDF
        assert how == "magic"

    def test_extensionless_arabic_text_is_sniffed(self, tmp_path):
        p = tmp_path / "noextension"
        p.write_text("المادة (1) يعمل بأحكام هذا القانون." * 20, encoding="utf-8")
        ftype, how = detect_file_type(p)
        assert ftype is FileType.TXT
        assert how == "content-sniff"

    def test_legacy_doc_detected_and_rejected_loudly(self, tmp_path):
        """Binary .doc is unsupported -- it must be *named*, not silently misrouted."""
        p = tmp_path / "old.doc"
        p.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 512)
        result = detect(p)
        assert result.file_type is FileType.DOC
        assert result.route is ExtractionRoute.UNSUPPORTED
        assert any("not supported" in n for n in result.notes)

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            detect_file_type(tmp_path / "nope.pdf")

    def test_unknown_binary(self, tmp_path):
        p = tmp_path / "blob.bin"
        p.write_bytes(bytes(range(256)) * 40)
        ftype, _ = detect_file_type(p)
        assert ftype is FileType.UNKNOWN


class TestPDFClassification:
    def test_text_pdf_is_text(self, contract_pdf, config):
        report = classify_pdf(contract_pdf, config.extraction)
        assert report.kind == "text"
        assert report.route is ExtractionRoute.TEXT_LAYER
        assert report.scanned_pages == []
        assert report.total_chars > 500

    def test_scanned_pdf_is_scanned(self, scanned_pdf, config):
        """Image-only PDF: every page must route to OCR."""
        report = classify_pdf(scanned_pdf, config.extraction)
        assert report.kind == "scanned"
        assert report.route is ExtractionRoute.OCR
        assert len(report.scanned_pages) == report.n_pages
        assert report.total_chars < 50, "an image-only PDF should have no text layer"

    def test_per_page_verdicts_carry_evidence(self, scanned_pdf, config):
        report = classify_pdf(scanned_pdf, config.extraction)
        for v in report.pages:
            assert v.reason, "every page verdict must record why it was made"
            assert v.image_area_ratio > 0.5, "rasterized page should be image-covered"

    def test_public_arabic_pdf_has_text_layer(self, public_arabic_pdf, config):
        report = classify_pdf(public_arabic_pdf, config.extraction)
        assert report.kind == "text"
        assert report.total_chars > 5000

    def test_threshold_controls_routing(self, contract_pdf, config):
        """Raising the char threshold must push text pages to OCR.

        Guards the knob itself: if this stops working, hybrid documents silently
        stop being OCR'd.
        """
        cfg = config.extraction.model_copy()
        cfg.text_layer_min_chars_per_page = 10 ** 9
        report = classify_pdf(contract_pdf, cfg)
        assert report.kind == "scanned"
        assert len(report.scanned_pages) == report.n_pages


class TestTextLayerQuality:
    """A text layer that decodes to nonsense is worse than no text layer.

    A PDF whose embedded font has a broken or custom encoding extracts happily
    but yields mojibake; routing it to the text path produces confident garbage.
    One public corpus document (`wipo_eg087ar_1.pdf`) is exactly this case.
    """

    def test_real_arabic_scores_high(self):
        text = ("المادة (4) لا يجوز التعاقد إلا بعد الإعلان عن العملية بإحدى الطرق "
                "المبينة باللائحة التنفيذية لهذا القانون، وذلك فيما عدا حالات التعاقد.")
        ratio, _ = text_layer_quality(text)
        assert ratio > 0.75

    def test_real_english_scores_high(self):
        text = ("Termination may occur at the option of the First Party without "
                "recourse to the courts upon fifteen days written notice of breach.")
        ratio, _ = text_layer_quality(text)
        assert ratio > 0.75

    def test_mojibake_scores_low(self):
        """Characteristic broken-CMap output: diverse punctuation, few words."""
        text = (r"----------------- \ '\'\A ;.;..J Yo (.J wj\i ~JbJl.1 -;_,;.u.1 "
                r",1}1 j ..:..t::~I .;jli Jl.l.oi ;.;..J Yo (.J wj\i ~JbJl.1 -;_,") * 3
        ratio, note = text_layer_quality(text)
        assert ratio < 0.50
        assert "mojibake" in note

    def test_dot_leaders_do_not_trigger_a_false_positive(self):
        """A table of contents is mostly dots and page numbers. It is a
        legitimate page and must not be pushed to OCR."""
        toc = "\n".join(
            f"الفصل {i} " + ". " * 40 + f" {i * 3}" for i in range(1, 25)
        )
        ratio, _ = text_layer_quality(toc)
        assert ratio > 0.65

    def test_underscore_leaders_also_handled(self):
        form = "\n".join("الاسم " + "_ " * 30 + " التاريخ" for _ in range(20))
        ratio, _ = text_layer_quality(form)
        assert ratio > 0.65

    def test_short_text_is_not_judged(self):
        ratio, note = text_layer_quality("hi")
        assert ratio == 1.0 and "too little" in note

    def test_garbled_pdf_routed_to_ocr(self, config):
        """End-to-end on the real corpus document with the broken font."""
        path = PUBLIC_CORPUS_DIR / "wipo_eg087ar_1.pdf"
        if not path.exists():
            pytest.skip("public corpus not downloaded")
        report = classify_pdf(path, config.extraction)
        assert report.kind == "scanned"
        assert report.route is ExtractionRoute.OCR
        assert all(p.text_quality < 0.5 for p in report.pages)
        assert any("garbled" in n for n in report.notes)

    def test_good_arabic_pdf_keeps_its_text_layer(self, config, public_arabic_pdf):
        """The guard against over-eager rejection: a genuine Arabic PDF, table
        of contents and all, must stay on the fast text path."""
        report = classify_pdf(public_arabic_pdf, config.extraction)
        assert report.kind == "text"
        assert report.scanned_pages == []

    def test_threshold_is_configurable(self, config, public_arabic_pdf):
        cfg = config.extraction.model_copy()
        cfg.min_text_layer_quality = 0.999
        report = classify_pdf(public_arabic_pdf, cfg)
        assert report.route is ExtractionRoute.OCR


class TestRouting:
    def test_image_routes_straight_to_ocr(self, stamped_image):
        result = detect(stamped_image)
        assert result.file_type is FileType.IMAGE
        assert result.route is ExtractionRoute.OCR
        assert result.pdf_kind == "n/a"

    def test_docx_routes_to_docx_path(self, contract_docx):
        assert detect(contract_docx).route is ExtractionRoute.DOCX

    def test_txt_routes_to_plaintext(self, statute_txt):
        assert detect(statute_txt).route is ExtractionRoute.PLAINTEXT

    def test_hybrid_pdf_splits_pages(self, tmp_path, contract_pdf, scanned_pdf, config):
        """A PDF with both text and image-only pages must report route=HYBRID
        and list each kind of page separately."""
        import fitz

        out = fitz.open()
        with fitz.open(contract_pdf) as a:
            out.insert_pdf(a, from_page=0, to_page=0)
        with fitz.open(scanned_pdf) as b:
            out.insert_pdf(b, from_page=0, to_page=1)
        merged = tmp_path / "hybrid.pdf"
        out.save(str(merged))
        out.close()

        report = classify_pdf(merged, config.extraction)
        assert report.route is ExtractionRoute.HYBRID
        assert report.text_pages == [1]
        assert report.scanned_pages == [2, 3]
        assert report.kind == "hybrid"
