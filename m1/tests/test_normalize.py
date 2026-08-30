"""Tests for Arabic normalization and its per-step toggles."""

from __future__ import annotations

import pytest

from src.config import NormalizationConfig
from src.normalize import (
    normalize_text,
    step_collapse_whitespace,
    step_normalize_alef,
    step_normalize_alef_maksura,
    step_normalize_digits,
    step_normalize_hamza,
    step_normalize_ligatures,
    step_normalize_punctuation,
    step_normalize_teh_marbuta,
    step_strip_diacritics,
    step_strip_presentation_forms,
    step_strip_tatweel,
)


class TestIndividualSteps:
    def test_strip_tatweel(self):
        assert step_strip_tatweel("الـمـادة") == "المادة"

    def test_strip_diacritics(self):
        assert step_strip_diacritics("الْمَادَّةُ") == "المادة"

    def test_normalize_alef_all_variants(self):
        assert step_normalize_alef("أإآا") == "اااا"

    def test_normalize_alef_maksura_only_word_final(self):
        """Interior ى is an OCR error, not an orthographic variant.

        Folding it would hide the error rather than fix it, so the rule is
        restricted to word-final position.
        """
        assert step_normalize_alef_maksura("علي") == "علي"
        assert step_normalize_alef_maksura("على") == "علي"
        assert step_normalize_alef_maksura("مىم") == "مىم", "interior ى must survive"

    def test_normalize_teh_marbuta(self):
        assert step_normalize_teh_marbuta("مادة") == "ماده"

    def test_normalize_hamza_carriers(self):
        out = step_normalize_hamza("مسؤولية")
        assert "ؤ" not in out

    def test_ligature_decomposition(self):
        assert step_normalize_ligatures("ﻻ") == "لا"

    def test_presentation_forms_folded_to_base_letters(self):
        """OCR and old DTP emit contextual glyphs; they must fold to base letters
        or nothing downstream will ever match them."""
        pres = "ﻋﻘﺪ"  # ain-initial, qaf-medial, dal-final = عقد
        assert step_strip_presentation_forms(pres) == "عقد"

    @pytest.mark.parametrize(
        "src,mode,expected",
        [
            ("المادة ١٢", "to_western", "المادة 12"),
            ("Article 12", "to_arabic", "Article ١٢"),
            ("المادة ١٢", "none", "المادة ١٢"),
        ],
    )
    def test_digit_modes(self, src, mode, expected):
        assert step_normalize_digits(src, mode) == expected

    def test_punctuation_arabic_context(self):
        out = step_normalize_punctuation("الشركة, والطرف; هل?", arabic_context=True)
        assert "،" in out and "؛" in out and "؟" in out

    def test_punctuation_english_context_untouched(self):
        """An English clause in a bilingual contract must keep English commas."""
        src = "The Buyer, the Seller; who?"
        assert step_normalize_punctuation(src, arabic_context=False) == src

    def test_dot_leaders_collapsed(self):
        out = step_normalize_punctuation("الاسم ................ التاريخ")
        assert "...." in out and "........" not in out

    def test_collapse_whitespace_preserves_paragraphs(self):
        out = step_collapse_whitespace("a   b\n\n\n\nc  \n  d")
        assert out == "a b\n\nc\nd"

    def test_collapse_whitespace_removes_zero_width(self):
        assert step_collapse_whitespace("ا​ب") == "اب"

    def test_collapse_whitespace_nbsp(self):
        assert step_collapse_whitespace("a b") == "a b"


class TestToggles:
    """Every step must be independently switchable -- that is the whole point
    of the design, so it is tested directly rather than implied."""

    def test_default_config_leaves_hamza_and_teh_alone(self):
        cfg = NormalizationConfig()
        out, applied = normalize_text("مسؤولية الشركة", cfg)
        assert "ؤ" in out, "normalize_hamza must be OFF by default"
        assert "ة" in out, "normalize_teh_marbuta must be OFF by default"
        assert "normalize_hamza" not in applied

    def test_enabling_hamza_changes_output(self):
        cfg = NormalizationConfig(normalize_hamza=True)
        out, applied = normalize_text("مسؤولية", cfg)
        assert "ؤ" not in out
        assert "normalize_hamza" in applied

    def test_disabling_a_step_is_honoured(self):
        cfg = NormalizationConfig(normalize_alef=False)
        out, applied = normalize_text("الإنهاء", cfg)
        assert "إ" in out
        assert "normalize_alef" not in applied

    def test_master_switch_off_is_identity(self):
        cfg = NormalizationConfig(enabled=False)
        src = "الـمـادة ١٢ : الإنهاء"
        out, applied = normalize_text(src, cfg)
        assert out == src
        assert applied == []

    def test_applied_lists_only_steps_that_changed_something(self):
        """``normalization_applied`` describes what happened to *this* text,
        not what was merely enabled -- otherwise it is useless for debugging."""
        cfg = NormalizationConfig()
        out, applied = normalize_text("Article 12", cfg)
        assert "normalize_alef" not in applied
        assert "strip_tatweel" not in applied

    def test_every_toggle_is_reachable(self):
        """Guards against a step being added to the config but never wired into
        the driver -- a silent no-op that would look like the step working."""
        from src.normalize import _STEPS

        cfg_fields = set(NormalizationConfig.model_fields)
        wired = {attr for attr, _, _ in _STEPS}
        unwired = cfg_fields - wired - {
            "enabled", "normalize_digits", "collapse_whitespace",
        }
        assert not unwired, f"config toggles never applied by normalize_text: {unwired}"


class TestEndToEnd:
    def test_full_pipeline_on_damaged_arabic(self):
        cfg = NormalizationConfig()
        out, applied = normalize_text("الـمـ__ادة ١٢ : الإنــهاء", cfg)
        assert "12" in out
        assert "ـ" not in out
        assert "إ" not in out
        assert set(applied) >= {"strip_tatweel", "normalize_alef"}

    def test_normalization_is_idempotent(self):
        """Re-running must be a no-op. If not, chunk text depends on how many
        times the pipeline happened to run over it."""
        cfg = NormalizationConfig()
        once, _ = normalize_text("الـمـادة ١٢ : الإنهاء والتـعويض", cfg)
        twice, applied = normalize_text(once, cfg)
        assert once == twice
        assert applied == []

    def test_empty_and_whitespace_safe(self):
        cfg = NormalizationConfig()
        assert normalize_text("", cfg) == ("", [])
        assert normalize_text("   \n  ", cfg)[0] == ""

    def test_latin_text_survives(self):
        cfg = NormalizationConfig()
        src = "Termination may occur upon 15 days notice."
        out, _ = normalize_text(src, cfg)
        assert out == src

    def test_article_number_matchable_after_normalization(self):
        """The point of digit folding: an article written with Arabic-Indic
        digits and one written with Western digits must become the same string,
        so retrieval can match a citation to its article."""
        cfg = NormalizationConfig()
        a, _ = normalize_text("المادة ١٢", cfg)
        b, _ = normalize_text("المادة 12", cfg)
        assert a == b
