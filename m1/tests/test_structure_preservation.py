"""Tests for the structural IR: markers, headings, boilerplate, inference."""

from __future__ import annotations

import pytest

from src.document_chunk_schema import BlockType, BoundingBox, DocumentType, Language, SourceEngine
from src.structure_preservation import (
    ExtractedDocument,
    ExtractedPage,
    StructLevel,
    TextBlock,
    annotate_structure,
    detect_language,
    detect_marker,
    infer_document_type,
    infer_jurisdiction,
    looks_like_heading,
    mark_running_headers,
    to_western_digits,
)


class TestMarkerDetection:
    @pytest.mark.parametrize(
        "line,kind,number",
        [
            ("المادة (12) : الإنهاء", "article", "12"),
            ("المادة ١٢", "article", "12"),
            ("مادة 5", "article", "5"),
            ("الباب الأول", "book", "1"),
            ("الفصل الثاني في الالتزامات", "chapter", "2"),
            ("البند (3)", "clause", "3"),
            ("أولاً: التعريفات", "clause", "1"),
            ("(أ) يلتزم الطرف الأول", "subclause", "أ"),
            ("Article 12. Termination", "article", "12"),
            ("Article (42):", "article", "42"),
            ("Section 4 Governing Law", "section", "4"),
            ("Section (3)", "section", "3"),
            ("12.3 The Supplier shall", "clause", "12.3"),
            ("7. Confidentiality", "clause", "7"),
            ("(a) the Buyer shall", "subclause", "a"),
            ("SCHEDULE 2", "annex", "2"),
        ],
    )
    def test_markers(self, line, kind, number):
        marker = detect_marker(line)
        assert marker is not None, f"no marker detected in {line!r}"
        assert marker.kind == kind
        assert marker.number == number

    def test_bis_numbering_preserved(self):
        """'مكرر' is an Egyptian legislative convention -- article 7 مكرر is a
        different article from article 7, and a naive parser conflates them."""
        marker = detect_marker("المادة (7) مكرر")
        assert marker.number and "مكرر" in marker.number

    def test_unnumbered_headings(self):
        for line in ("Termination", "التعريفات", "Governing Law", "القوة القاهرة"):
            assert detect_marker(line) is not None, line

    def test_prose_is_not_a_marker(self):
        assert detect_marker(
            "This is an ordinary sentence of body text that runs on for a while."
        ) is None

    def test_cross_reference_is_not_a_boundary(self):
        """'ونصت المادة 12' mid-sentence is a citation. Treating it as a
        boundary would split a clause at every internal reference."""
        assert detect_marker("ونصت المادة 12 من القانون المدني على أن الالتزام") is None

    def test_overlong_line_is_not_a_heading(self):
        assert detect_marker("Termination " * 40) is None

    def test_label_excludes_the_title(self):
        """The label is the citable identifier; the title is separate. A label
        with a whole sentence glued to it is useless for grouping and citing."""
        marker = detect_marker("Article 12. Termination and Consequences")
        assert marker.label == "Article 12"
        assert marker.title == "Termination and Consequences"


class TestLanguageDetection:
    def test_pure_arabic(self):
        assert detect_language("هذا نص عربي بالكامل وطويل بما يكفي للاختبار") is Language.AR

    def test_pure_english(self):
        assert detect_language("This is entirely English text for the test") is Language.EN

    def test_bilingual_is_ar_en(self):
        assert detect_language(
            "المادة 12 Termination يجب على الطرف الأول the First Party notify"
        ) is Language.AR_EN

    def test_single_english_term_stays_arabic(self):
        """One defined term inside an Arabic clause should not flip the whole
        chunk to 'ar-en' -- that would misroute a great deal of ordinary text."""
        assert detect_language(
            "يلتزم الطرف الثاني بتوريد المهمات والمواد الموضحة بالملحق المرفق "
            "طبقا للمواصفات الفنية المعتمدة وذلك على مسئوليته الكاملة SLA"
        ) is Language.AR

    def test_too_short_is_unknown(self):
        assert detect_language("ab") is Language.UNKNOWN

    def test_digits_do_not_decide_language(self):
        assert detect_language("المادة 12 والمادة 13 والمادة 14 من القانون") is Language.AR


class TestDigits:
    def test_arabic_indic_folded(self):
        assert to_western_digits("١٢٣٤٥٦٧٨٩٠") == "1234567890"

    def test_extended_arabic_indic_folded(self):
        assert to_western_digits("۱۲۳") == "123"


class TestDocumentInference:
    def test_contract(self):
        dtype, conf = infer_document_type(
            "عقد اتفاقية بين الطرف الأول والطرف الثاني أبرم هذا العقد بنود العقد"
        )
        assert dtype is DocumentType.CONTRACT and conf > 0

    def test_court_ruling(self):
        dtype, _ = infer_document_type(
            "محكمة النقض الدائرة المدنية حكم المحكمة حيثيات الحكم منطوق الحكم"
        )
        assert dtype is DocumentType.COURT_RULING

    def test_statute(self):
        dtype, _ = infer_document_type(
            "الجريدة الرسمية قانون رقم 17 لسنة 2026 قرر مجلس النواب القانون الآتي"
        )
        assert dtype is DocumentType.LAW

    def test_constitution_is_a_law(self):
        dtype, _ = infer_document_type("دستور جمهورية مصر العربية الصادر عام 2014")
        assert dtype is DocumentType.LAW

    def test_broken_intra_word_spacing_still_matches(self):
        """Arabic PDFs routinely extract as 'دس تور' when the producer placed
        glyphs individually. Matching only the spaced text misses those files
        entirely -- a national constitution was classifying as `unknown`."""
        dtype, _ = infer_document_type("دس تور مصر الصادر عام 2014 الجمهورية العربية")
        assert dtype is DocumentType.LAW

    def test_unknown_when_no_cues(self):
        dtype, conf = infer_document_type("قائمة المشتريات: خبز، لبن، جبن")
        assert dtype is DocumentType.UNKNOWN and conf == 0.0

    def test_jurisdiction_from_cues(self):
        assert infer_jurisdiction("محكمة شمال القاهرة الابتدائية") == "Egypt"
        assert infer_jurisdiction("The parties in Tanta, Gharbia") == "Egypt"

    def test_jurisdiction_default_when_absent(self):
        assert infer_jurisdiction("no location cues here at all", default="Egypt") == "Egypt"
        assert infer_jurisdiction("no location cues here at all") is None


class TestRunningHeaders:
    """Running boilerplate must be excluded before headings are inferred.

    A page header is short, prominent and unterminated, so the typographic
    heuristic promotes it to a section -- and then every chunk on every page
    inherits a meaningless section label.
    """

    @staticmethod
    def _doc(n_pages: int, header: str = "constituteproject.org",
             with_page_numbers: bool = False) -> ExtractedDocument:
        doc = ExtractedDocument(document_id="d", source_path="m", file_type="pdf")
        for pno in range(1, n_pages + 1):
            page = ExtractedPage(page_number=pno, width=595.0, height=842.0,
                                 source_engine=SourceEngine.PYMUPDF)
            head = f"{header} Page {pno} of {n_pages}" if with_page_numbers else header
            page.blocks.append(TextBlock(
                text=head, page=pno, order=0,
                bbox=BoundingBox(x0=50, y0=20, x1=300, y1=40, page=pno),
            ))
            page.blocks.append(TextBlock(
                text=f"المادة ({pno})", page=pno, order=1,
                bbox=BoundingBox(x0=50, y0=200, x1=300, y1=220, page=pno),
            ))
            page.blocks.append(TextBlock(
                text=f"نص المادة رقم {pno} وهو نص طويل بما يكفي لاعتباره جسد المادة.",
                page=pno, order=2,
                bbox=BoundingBox(x0=50, y0=230, x1=500, y1=300, page=pno),
            ))
            doc.pages.append(page)
        return doc

    def test_repeated_top_margin_block_is_marked(self):
        doc = self._doc(8)
        marked = mark_running_headers(doc)
        assert marked == 8
        headers = [b for b in doc.all_blocks() if b.block_type is BlockType.HEADER_FOOTER]
        assert all("constituteproject" in b.text for b in headers)

    def test_page_numbers_do_not_defeat_the_repeat_test(self):
        """'Page 3 of 40' differs on every page; digits must be wildcarded."""
        doc = self._doc(8, with_page_numbers=True)
        assert mark_running_headers(doc) == 8

    def test_body_text_is_never_marked(self):
        doc = self._doc(8)
        mark_running_headers(doc)
        bodies = [b for b in doc.all_blocks() if "نص المادة" in b.text]
        assert bodies
        assert all(b.block_type is not BlockType.HEADER_FOOTER for b in bodies)

    def test_short_documents_are_left_alone(self):
        """Two pages is not enough evidence that something is boilerplate."""
        assert mark_running_headers(self._doc(2)) == 0

    def test_repeated_text_outside_the_margin_is_not_boilerplate(self):
        """A clause that recurs mid-page is not a header."""
        doc = self._doc(8)
        for page in doc.pages:
            page.blocks[0].bbox = BoundingBox(
                x0=50, y0=400, x1=300, y1=420, page=page.page_number
            )
        assert mark_running_headers(doc) == 0

    def test_no_bboxes_is_a_safe_noop(self):
        doc = self._doc(8)
        for block in doc.all_blocks():
            block.bbox = None
        assert mark_running_headers(doc) == 0

    def test_header_does_not_become_a_section(self):
        doc = annotate_structure(self._doc(8))
        sections = {b.struct.section for b in doc.all_blocks() if b.struct.section}
        assert not any("constituteproject" in (s or "") for s in sections)

    def test_articles_still_detected_around_the_header(self):
        doc = annotate_structure(self._doc(8))
        articles = {b.struct.article for b in doc.all_blocks() if b.struct.article}
        assert "المادة 1" in articles and "المادة 8" in articles


class TestHeadingHeuristic:
    def test_bold_short_line_is_a_heading(self):
        assert looks_like_heading("Termination", is_bold=True)

    def test_larger_font_is_a_heading(self):
        assert looks_like_heading("Termination", font_size=16, body_font_size=11)

    def test_sentence_terminated_line_is_not(self):
        assert not looks_like_heading("This ends with a full stop.", is_bold=True)

    def test_bracketed_note_is_not_a_heading(self):
        """'[SYNTHETIC TEST DOCUMENT]' and '[DRAFT]' watermarks are editorial
        notes; promoting them to sections poisons every following chunk."""
        assert not looks_like_heading("[FABRICATED TEST DATA]", is_bold=True)
        assert not looks_like_heading("(draft for discussion)", is_bold=True)

    def test_long_line_is_not_a_heading(self):
        assert not looks_like_heading("word " * 40, is_bold=True)


class TestAnnotation:
    def test_heading_stack_maintained(self, make_doc):
        doc = annotate_structure(make_doc([(1, [
            "الباب الأول", "الفصل الأول", "المادة (1)", "نص المادة الأولى هنا.",
            "المادة (2)", "نص المادة الثانية هنا.",
        ])]))
        blocks = list(doc.all_blocks())
        last = blocks[-1]
        assert last.struct.book == "الباب 1"
        assert last.struct.chapter == "الفصل 1"
        assert last.struct.article == "المادة 2"
        assert last.struct.clause_id == "art_2"

    def test_deeper_marker_closes_same_level(self, make_doc):
        doc = annotate_structure(make_doc([(1, [
            "المادة (1)", "نص أول.", "المادة (2)", "نص ثان.",
        ])]))
        blocks = list(doc.all_blocks())
        assert blocks[1].struct.article == "المادة 1"
        assert blocks[3].struct.article == "المادة 2"

    def test_heading_path_is_ordered_outermost_first(self, make_doc):
        doc = annotate_structure(make_doc([(1, [
            "الباب الأول", "الفصل الأول", "المادة (1)", "نص المادة.",
        ])]))
        path = list(doc.all_blocks())[-1].struct.heading_path
        assert "الباب" in path[0]
        assert "المادة" in path[-1]
