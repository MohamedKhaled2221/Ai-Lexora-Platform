"""Tests for visual-order detection and repair (README known limitation #9).

The governing rule: **a false positive here is worse than doing nothing.**
Reversing correct text destroys it silently, where leaving a reversed document
alone at least leaves it flagged. So the negative tests in this module --
:class:`TestGenuineErrorsAreNotReordered` and
:class:`TestLogicalTextIsNeverReordered` -- are the load-bearing ones, and a
change that makes a positive test pass at their expense is a regression.
"""

from __future__ import annotations

import pytest

pytest.importorskip("bidi", reason="python-bidi is required for reading-order repair")

from src.config import PipelineConfig, RTLConfig
from src.document_chunk_schema import SourceEngine
from src.rtl_fix import apply_rtl_fix, document_visual_order
from src.structure_preservation import TextBlock, detect_marker
from src.visual_order import (
    REVERSAL_HELPS,
    choose_reading,
    marker_recovery,
    order_score,
    reorder_tokens_visual_to_logical,
    reverse_line_words,
    detect_and_repair,
    visual_line_from_chars,
    visual_to_logical,
)


def _shape(text: str) -> str:
    """Render text the way an Arabic DTP producer would store it: reshaped into
    presentation forms and laid out in visual order. This is the damage under
    test, produced by the same call the corpus generator uses."""
    import arabic_reshaper
    from bidi.algorithm import get_display

    return "\n".join(
        get_display(arabic_reshaper.reshape(line)) for line in text.splitlines()
    )


# A real Egyptian statutory article, logical order.
LOGICAL_AR = """المادة 4 - التعاقد المباشر
لا يجوز التعاقد إلا بعد الإعلان عن العملية بإحدى الطرق المبينة باللائحة التنفيذية.
المادة 5 - لجنة البت
تشكل لجنة البت بقرار من السلطة المختصة وتتولى فحص العروض المقدمة.
المادة 6 - التظلمات
لكل ذي شأن أن يتظلم من القرار خلال خمسة عشر يوما من تاريخ إخطاره."""

# Bilingual, Arabic and English interleaved inside single sentences -- the shape
# of stress_inline_bilingual.pdf.
LOGICAL_BILINGUAL = """1. بمراجعة البند الثالث (Clause 3) من العقد تبين أن التزام المؤجر (the Lessor) قائم.
2. نوصي بإضافة عبارة (within thirty days) إلى نهاية البند، مع مقابل عربي صريح.
3. البند الحادي عشر (Clause 11) يحيل إلى قانون رقم 95 لسنة 1995 بشأن التأجير.
4. من حيث اختصاص المحكمة (jurisdiction)، ينص العقد على التحكيم أمام مركز القاهرة.
5. الخلاصة (Conclusion): العقد قابل للتوقيع بعد إجراء التعديلات المشار إليها."""


class TestOrderScore:
    def test_logical_arabic_scores_positive(self):
        assert order_score(LOGICAL_AR).score > 0.5

    def test_visual_arabic_scores_negative(self):
        assert order_score(_shape(LOGICAL_AR)).score < 0

    def test_score_is_backed_by_evidence(self):
        s = order_score(LOGICAL_AR)
        assert s.observations >= 4
        assert s.evidence, "a score with no stated evidence is not auditable"

    def test_english_only_text_offers_no_arabic_evidence(self):
        s = order_score("Termination may occur upon fifteen (15) days written notice.")
        assert s.score >= 0


class TestPureArabicVisualOrder:
    """Positive case 1: a wholly Arabic document stored in visual order."""

    def test_detected_and_repaired(self):
        v = detect_and_repair(_shape(LOGICAL_AR))
        assert v.repaired is True
        assert v.gain >= REVERSAL_HELPS

    def test_repair_recovers_the_original_text(self):
        v = detect_and_repair(_shape(LOGICAL_AR))
        assert "المادة 4 - التعاقد المباشر" in v.text
        assert "لا يجوز التعاقد" in v.text

    def test_repair_recovers_the_clause_markers(self):
        visual = _shape(LOGICAL_AR)
        assert marker_recovery(visual) == 0, "markers are unreachable before repair"
        assert marker_recovery(detect_and_repair(visual).text) == 3

    def test_lam_alef_ligature_survives_the_reversal(self):
        """The ligature ﻻ is one glyph and therefore one position in a visual
        string. Decomposing it before reordering splits it the wrong way round
        and turns الإيجار into اإليجار -- a whole-corpus corruption that no
        marker test would catch."""
        out = detect_and_repair(_shape("عقد الإيجار التمويلي المبرم بين الطرفين\n"
                                     "لا يجوز إلا بعد الإخطار الكتابي بذلك\n"
                                     "الخلاصة أن العقد قابل للتوقيع الآن")).text
        assert "الإيجار" in out
        assert "اإليجار" not in out


class TestBilingualInlineVisualOrder:
    """Positive case 2: the hard one. Arabic and English inside one sentence.

    The repair must put the Arabic back **without** reversing the English runs
    between it, and without moving them relative to the Arabic.
    """

    def test_detected_and_repaired(self):
        assert detect_and_repair(_shape(LOGICAL_BILINGUAL)).repaired is True

    def test_english_runs_keep_their_internal_word_order(self):
        out = detect_and_repair(_shape(LOGICAL_BILINGUAL)).text
        assert "the Lessor" in out
        assert "Lessor the" not in out
        assert "within thirty days" in out

    def test_arabic_is_restored(self):
        out = detect_and_repair(_shape(LOGICAL_BILINGUAL)).text
        assert "بمراجعة البند الثالث" in out

    def test_brackets_are_not_left_mirrored(self):
        out = detect_and_repair(_shape(LOGICAL_BILINGUAL)).text
        assert "(Clause 3)" in out
        assert ")Clause 3(" not in out

    def test_clause_numbers_return_to_the_head_of_their_line(self):
        visual = _shape(LOGICAL_BILINGUAL)
        assert marker_recovery(visual) == 0
        assert marker_recovery(detect_and_repair(visual).text) == 5

    def test_digits_are_not_reordered(self):
        """Out of scope by design: '٢١' and '١٢' are indistinguishable in
        extracted text, so a guess would corrupt article numbers and amounts."""
        out = detect_and_repair(_shape(LOGICAL_BILINGUAL)).text
        assert "1995" in out
        assert "95" in out


class TestLogicalTextIsNeverReordered:
    """Negative case 1: correct text must survive untouched."""

    def test_logical_arabic_is_left_alone(self):
        v = detect_and_repair(LOGICAL_AR)
        assert v.repaired is False
        assert v.text == LOGICAL_AR

    def test_logical_bilingual_is_left_alone(self):
        v = detect_and_repair(LOGICAL_BILINGUAL)
        assert v.repaired is False
        assert v.text == LOGICAL_BILINGUAL

    def test_english_only_is_left_alone(self):
        src = "Article 5 - Termination\nEither party may terminate on notice."
        assert detect_and_repair(src).text == src

    def test_a_reading_that_loses_markers_is_rejected(self):
        """The criterion that vetoes the corpus's one real false positive.

        ``wipo_eg081ar_1.pdf`` is a published statute whose reference the audit
        classifies as *logical*, but whose sentence punctuation is mirrored --
        so reordering it **improves** the order score (+0.73 -> +0.94) while
        taking its recovered structural markers from 3 to 0. Score alone would
        have reversed a correct document.
        """
        verdict = choose_reading(LOGICAL_AR, reverse_line_words(LOGICAL_AR))
        assert verdict.repaired is False
        assert "structural marker" in verdict.reason
        assert verdict.markers_after < verdict.markers_before

    def test_rejection_states_its_reason(self):
        """A document that should have been repaired and was not must be
        discoverable, not invisible."""
        v = detect_and_repair(LOGICAL_AR)
        assert v.reason
        assert v.as_dict()["markers_before"] == 3


class TestGenuineErrorsAreNotReordered:
    """Negative case 2, and the one this whole design exists to get right.

    Text that is *damaged* rather than *reversed* is bad in both directions, so
    the reversal test's margin is not met and nothing is touched. Reordering it
    would convert a recoverable OCR problem into an unrecoverable one.
    """

    def test_mangled_ocr_output_is_left_alone(self):
        # Realistic Tesseract damage on Arabic: dropped dots, split words,
        # substituted letters. The word order is correct throughout.
        garbled = (
            "الماده 4 - التعاقد المباشـر\n"
            "لا بحوز التعاقد الا نعد الاعلان عں العمليه ياحدى الطرق المبينه\n"
            "باللائحه التنفيديه لهدا الفانون وذلك فيما عدا حالات التعاقد"
        )
        v = detect_and_repair(garbled)
        assert v.repaired is False
        assert v.text == garbled

    def test_glyph_fragmented_text_is_left_alone(self):
        """One public fixture stores words fragmented into single glyphs. That
        is a reference defect, not a reading-order one, and reversing it makes
        it worse."""
        fragmented = "دس تور نا ه ذا\nإ ن ش اء تم PDF ملف\nة جاب يالد الرح يم"
        assert detect_and_repair(fragmented).repaired is False

    def test_mojibake_is_left_alone(self):
        assert detect_and_repair("��� المادة ��").repaired is False

    def test_too_short_to_judge(self):
        v = detect_and_repair("المادة الأولى")
        assert v.repaired is False


class TestTokenReordering:
    """The OCR path: words are internally correct, their sequence is visual."""

    def test_pure_arabic_line_is_reversed(self):
        toks = ["الدورية", "بالصيانة", "المؤجر", "التزام"]
        perm = reorder_tokens_visual_to_logical(toks)
        assert [toks[i] for i in perm] == ["التزام", "المؤجر", "بالصيانة", "الدورية"]

    def test_embedded_english_keeps_its_word_order(self):
        # Visual (left-to-right on the page) for: "التزام المؤجر the Lessor قائم"
        toks = ["قائم", "the", "Lessor", "المؤجر", "التزام"]
        out = [toks[i] for i in reorder_tokens_visual_to_logical(toks)]
        assert out == ["التزام", "المؤجر", "the", "Lessor", "قائم"]
        assert " ".join(out).count("the Lessor") == 1

    def test_ltr_base_is_a_no_op_on_english(self):
        toks = ["The", "Consultant", "shall", "perform"]
        perm = reorder_tokens_visual_to_logical(toks, base_dir="L")
        assert [toks[i] for i in perm] == toks

    def test_single_token_is_safe(self):
        assert reorder_tokens_visual_to_logical(["المادة"]) == [0]
        assert reorder_tokens_visual_to_logical([]) == []


class TestGeometricReconstruction:
    def test_chars_are_ordered_by_x(self):
        chars = [
            {"c": "b", "bbox": (10, 0, 20, 10)},
            {"c": "a", "bbox": (0, 0, 10, 10)},
            {"c": "c", "bbox": (20, 0, 30, 10)},
        ]
        assert visual_line_from_chars(chars) == "abc"

    def test_empty_is_safe(self):
        assert visual_line_from_chars([]) == ""


class TestPipelineIntegration:
    def test_inline_bilingual_fixture_recovers_its_clause_markers(self, synthetic_dir):
        """The regression fixture for this repair. Before: 1 chunk, 0 clause
        markers, whole document demoted to paragraph chunking. After: the five
        numbered memorandum paragraphs are recovered as structural units."""
        from src.pipeline import process_document

        pdf = synthetic_dir / "stress_inline_bilingual.pdf"
        if not pdf.exists():
            pytest.skip("stress fixture not generated")

        cfg = PipelineConfig()
        cfg.extraction.use_docling = False
        result = process_document(pdf, cfg)

        clause_ids = {
            (c.metadata.get("structure") or {}).get("clause_id")
            for c in result.chunks
        } - {None}
        assert len(clause_ids) == 5, f"expected 5 numbered paragraphs, got {clause_ids}"
        assert all(
            c.metadata.get("chunk_strategy") != "paragraph" for c in result.chunks
        ), "document must no longer be demoted to paragraph chunking"

    def test_repair_is_flagged_not_silent(self, synthetic_dir):
        from src.pipeline import process_document

        pdf = synthetic_dir / "stress_inline_bilingual.pdf"
        if not pdf.exists():
            pytest.skip("stress fixture not generated")

        cfg = PipelineConfig()
        cfg.extraction.use_docling = False
        result = process_document(pdf, cfg)

        assert any(f.kind == "visual_order_repaired" for f in result.rtl_flags)
        assert any("VISUAL" in w for w in result.warnings)
        assert any(
            c.metadata.get("reading_order_repaired") for c in result.chunks
        ), "reordered chunks must say so in their metadata"
        assert any(
            e.get("engine") == "reading_order" for e in result.engine_log
        ), "the verdict and its numbers must be in the engine log"

    def test_english_only_document_is_not_touched(self, synthetic_dir):
        from src.pipeline import process_document

        pdf = synthetic_dir / "stress_exhibits_footnotes.pdf"
        if not pdf.exists():
            pytest.skip("stress fixture not generated")

        cfg = PipelineConfig()
        cfg.extraction.use_docling = False
        result = process_document(pdf, cfg)
        assert not any(
            c.metadata.get("reading_order_repaired") for c in result.chunks
        )

    def test_document_verdict_is_all_or_nothing(self, make_doc):
        """Visual layout is a property of the producing software, so the verdict
        is taken once per document. Half a document reordered and half not is
        worse than either."""
        doc = make_doc([(1, _shape(LOGICAL_AR).splitlines())])
        verdict = document_visual_order(doc, RTLConfig())
        assert verdict is not None
        assert verdict.repaired is True

    def test_disabled_config_skips_the_test_entirely(self, make_doc):
        doc = make_doc([(1, _shape(LOGICAL_AR).splitlines())])
        assert document_visual_order(doc, RTLConfig(repair_visual_order=False)) is None


class TestSharedWithAudit:
    def test_audit_script_uses_the_pipeline_threshold(self):
        """The offline audit and the live repair must not drift apart on what
        counts as "reversing helps"."""
        import scripts.audit_ground_truth as audit

        assert audit.REVERSAL_HELPS == REVERSAL_HELPS
        assert audit.reverse_line_words is reverse_line_words

    def test_reverse_line_words(self):
        assert reverse_line_words("a b c\nd e") == "c b a\ne d"
