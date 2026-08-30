"""Tests for RTL reading-order repair and ambiguity flagging.

The governing rule under test throughout: **ambiguous reading order is flagged,
never silently rewritten.** Several tests assert that text is *unchanged* --
those are the important ones.
"""

from __future__ import annotations

import pytest

from src.config import RTLConfig
from src.document_chunk_schema import SourceEngine
from src.rtl_fix import (
    analyze_direction,
    detect_mirrored_neutrals,
    document_is_mirrored,
    fix_block,
    has_presentation_forms,
    looks_visually_ordered,
    repair_visual_order,
    strip_presentation_forms,
    to_display_form,
    unmirror_brackets,
)
from src.structure_preservation import TextBlock

LOGICAL_AR = (
    "المادة (4) لا يجوز التعاقد إلا بعد الإعلان عن العملية بإحدى الطرق المبينة "
    "باللائحة التنفيذية لهذا القانون، وذلك فيما عدا حالات التعاقد المباشر."
)


def _block(text: str, page: int = 1) -> TextBlock:
    return TextBlock(text=text, page=page, source_engine=SourceEngine.PLAINTEXT)


class TestPresentationForms:
    def test_detects_presentation_forms(self):
        assert has_presentation_forms("ﻋﻘﺪ")
        assert not has_presentation_forms("عقد")

    def test_folds_to_base_letters(self):
        assert strip_presentation_forms("ﻋﻘﺪ") == "عقد"

    def test_leaves_clean_text_alone(self):
        assert strip_presentation_forms(LOGICAL_AR) == LOGICAL_AR


class TestVisualOrderRepair:
    def test_logical_text_is_not_flagged_as_visual(self):
        """The critical negative case: reversing correct text is worse than
        leaving damaged text alone."""
        is_visual, _ = looks_visually_ordered(LOGICAL_AR)
        assert is_visual is False

    def test_logical_text_is_not_modified(self):
        out, repaired, _ = repair_visual_order(LOGICAL_AR)
        assert out == LOGICAL_AR
        assert repaired is False

    def test_character_reversed_text_is_detected(self):
        reversed_text = LOGICAL_AR[::-1]
        is_visual, evidence = looks_visually_ordered(reversed_text)
        assert is_visual is True
        assert evidence

    def test_repair_recovers_logical_order(self):
        out, repaired, _ = repair_visual_order(LOGICAL_AR[::-1])
        assert repaired is True
        assert "المادة" in out

    def test_too_short_to_judge(self):
        is_visual, evidence = looks_visually_ordered("المادة")
        assert is_visual is False
        assert "too few" in evidence


class TestMirroredNeutrals:
    """The dominant real-world artifact: words correct, neutrals mirrored."""

    def test_detects_mirrored_brackets_and_leading_stop(self):
        # Realistic mirrored page: *every* bracket pair is mirrored, and
        # sentence-final stops lead their lines.
        text = ".المادة )1( بشأن الشركة )طرف أول( وذلك\n.الطرف الثاني يقر بما تقدم"
        detected, evidence = detect_mirrored_neutrals(text)
        assert detected is True
        assert len(evidence) >= 2

    def test_clean_arabic_not_flagged(self):
        detected, _ = detect_mirrored_neutrals(LOGICAL_AR)
        assert detected is False

    def test_reversed_year_is_evidence(self):
        text = ".تحرر هذا العقد في ٥١ يناير ٦٢٠٢ بين الطرفين\n.وذلك بمقر الشركة )طرف أول("
        _, evidence = detect_mirrored_neutrals(text)
        assert any("year" in e for e in evidence)

    def test_unmirror_brackets_is_structural_only(self):
        out, n = unmirror_brackets("الشركة )طرف أول( وكذلك ]ملحق 1[")
        assert n == 2
        assert "(طرف أول)" in out
        assert "[ملحق 1]" in out

    def test_unmirror_leaves_correct_brackets_alone(self):
        src = "المادة (1) والملحق [2]"
        out, n = unmirror_brackets(src)
        assert out == src
        assert n == 0

    def test_digits_are_never_reordered(self):
        """'٢١' is indistinguishable from '١٢' in extracted text. Guessing would
        silently corrupt article numbers and amounts, so digits must survive
        the mirrored-neutral repair untouched."""
        src = "الشركة )طرف أول( بتاريخ ٥١ يناير ٦٢٠٢"
        out, _ = unmirror_brackets(src)
        assert "٥١" in out and "٦٢٠٢" in out

    def test_mirrored_block_is_flagged_not_reversed(self):
        cfg = RTLConfig()
        # Realistic mirrored page: *every* bracket pair is mirrored, and
        # sentence-final stops lead their lines.
        text = ".المادة )1( بشأن الشركة )طرف أول( وذلك\n.الطرف الثاني يقر بما تقدم"
        block = fix_block(_block(text), cfg)
        kinds = {f.kind for f in block.rtl_flags}
        assert "neutral_order_mirrored" in kinds
        assert "المادة" in block.text, "words must not be reversed in this case"

    def test_document_level_verdict(self, make_doc):
        doc = make_doc([(1, [
            ".المادة (1) بشأن الشركة )طرف أول( وذلك التزم الطرف",
            ".تحرر في ٥١ يناير ٦٢٠٢ بمقر الشركة )طرف ثان(",
        ])])
        mirrored, evidence = document_is_mirrored(doc)
        assert mirrored is True
        assert evidence

    def test_document_verdict_propagates_to_short_blocks(self):
        """A short heading rarely carries enough evidence alone, yet that is
        where mirroring is most visible. The document verdict must cover it."""
        cfg = RTLConfig()
        heading = _block("( : التعريفات1) المادة")
        alone = fix_block(_block("( : التعريفات1) المادة"), cfg)
        assert "neutral_order_mirrored" not in {f.kind for f in alone.rtl_flags}

        with_doc_hint = fix_block(heading, cfg, doc_mirrored=True)
        assert "neutral_order_mirrored" in {f.kind for f in with_doc_hint.rtl_flags}


class TestAmbiguityFlagging:
    def test_mixed_arabic_english_is_flagged(self):
        cfg = RTLConfig()
        flags = analyze_direction(
            "البند (5) delay penalty cap محدد بنسبة عشرة بالمائة of the contract value",
            cfg,
        )
        assert "mixed_direction" in {f.kind for f in flags}

    def test_pure_arabic_is_not_flagged_as_mixed(self):
        cfg = RTLConfig()
        flags = analyze_direction(LOGICAL_AR, cfg)
        assert "mixed_direction" not in {f.kind for f in flags}

    def test_single_stray_latin_char_is_noise_not_a_switch(self):
        cfg = RTLConfig(mixed_direction_min_latin_chars=5)
        flags = analyze_direction("المادة الأولى بشأن التعاقد a وما بعدها", cfg)
        assert "mixed_direction" not in {f.kind for f in flags}

    def test_high_switch_count_flagged(self):
        cfg = RTLConfig(max_direction_switches_before_flag=2)
        flags = analyze_direction("عقد Agreement بند Clause طرف Party شركة Company", cfg)
        assert "high_switch_count" in {f.kind for f in flags}

    def test_numeral_between_scripts_flagged(self):
        cfg = RTLConfig()
        flags = analyze_direction("المادة 12 Article of the contract التزام", cfg)
        assert "numeral_direction_ambiguous" in {f.kind for f in flags}

    def test_flagging_never_alters_text(self):
        cfg = RTLConfig()
        src = "البند (5) delay penalty محدد بنسبة 10% of value"
        block = fix_block(_block(src), cfg)
        assert block.rtl_flags, "this text should raise flags"
        # Only presentation-form folding may touch it, and there are none here.
        assert "delay penalty" in block.text
        assert "البند" in block.text

    def test_flags_disabled_by_config(self):
        cfg = RTLConfig(flag_mixed_direction=False)
        flags = analyze_direction("المادة 12 Article of contract", cfg)
        assert flags == []

    def test_flags_carry_a_sample_for_review(self):
        """Flags exist to be reviewed by a human, so each must carry enough
        context to be actionable without re-opening the source."""
        cfg = RTLConfig()
        flags = analyze_direction("البند (5) delay penalty cap محدد بنسبة عشرة", cfg)
        assert all(f.detail for f in flags)
        assert any(f.sample for f in flags)


class TestDisplayForm:
    def test_display_form_produces_presentation_forms(self):
        out = to_display_form("المادة")
        assert has_presentation_forms(out)

    def test_display_form_not_in_text_by_default(self):
        cfg = RTLConfig()
        block = fix_block(_block(LOGICAL_AR), cfg)
        assert block.display_text is None
        assert not has_presentation_forms(block.text)

    def test_display_form_emitted_when_requested(self):
        cfg = RTLConfig(emit_display_form=True)
        block = fix_block(_block(LOGICAL_AR), cfg)
        assert block.display_text is not None
        assert block.text != block.display_text
        assert not has_presentation_forms(block.text), "primary text stays logical"

    def test_force_display_in_text_is_opt_in_only(self):
        cfg = RTLConfig(force_display_in_text=True)
        block = fix_block(_block(LOGICAL_AR), cfg)
        assert has_presentation_forms(block.text)


class TestBlockHandling:
    def test_raw_text_preserved(self):
        cfg = RTLConfig()
        block = fix_block(_block("ﻋﻘﺪ ﺗﻮﺭﻳﺪ"), cfg)
        assert block.raw_text == "ﻋﻘﺪ ﺗﻮﺭﻳﺪ"
        assert block.text != block.raw_text

    def test_disabled_config_is_a_no_op(self):
        cfg = RTLConfig(enabled=False)
        block = fix_block(_block("ﻋﻘﺪ"), cfg)
        assert block.text == "ﻋﻘﺪ"
        assert block.rtl_flags == []

    def test_empty_block_safe(self):
        cfg = RTLConfig()
        assert fix_block(_block("   "), cfg).text == "   "

    def test_english_only_block_untouched(self):
        cfg = RTLConfig()
        src = "Termination may occur upon fifteen (15) days written notice."
        block = fix_block(_block(src), cfg)
        assert block.text == src
