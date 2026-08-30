"""Tests for OCR-tolerant structure-marker matching (README known limitation #4).

Three things are under test and they are not equally important:

1. **The silent failure is gone.** A document that loses its clause structure
   now says so (``structure_detection_failed``), and a marker that had to be
   repaired says that too. :class:`TestFailuresAreVisible` is the point of the
   change; the rest is how much it manages to rescue on the way.
2. **False positives stay at zero.** A fuzzy matcher that invents clause
   boundaries is worse than the exact one that misses them, because an invented
   boundary splits a clause in half and nothing flags it as wrong.
   :class:`TestNoFalsePositives` is the constraint everything else is tuned
   against.
3. **Recall on realistic damage**, and an honest statement of the ceiling --
   :class:`TestTwoErrorsAreNotHandled` asserts the documented gap rather than
   leaving it implied.
"""

from __future__ import annotations

import pytest

from src.config import PipelineConfig
from src.fuzzy_markers import (
    CONFUSABLE_WORDS,
    MAX_MARKER_DISTANCE,
    MIN_FUZZY_LENGTH,
    edit_distance,
    join_split_digits,
    match_marker_word,
    normalize_for_match,
    repair_marker_line,
)
from src.structure_preservation import _detect_exact, detect_marker

TITLE = "التعريفات"


def strict(line: str):
    return detect_marker(line, allow_fuzzy=False)


class TestNormalization:
    def test_tatweel_and_diacritics_are_free(self):
        """These cost none of the distance-1 budget, which is why the budget
        stretches as far as it does."""
        assert normalize_for_match("المـادة") == normalize_for_match("المادة")
        assert normalize_for_match("المَادة") == normalize_for_match("المادة")

    def test_teh_marbuta_and_alef_variants_fold(self):
        assert normalize_for_match("الماده") == normalize_for_match("المادة")
        assert normalize_for_match("إلمادة") == normalize_for_match("المادة")

    def test_internal_spaces_are_removed(self):
        assert normalize_for_match("الما دة") == normalize_for_match("المادة")


class TestEditDistance:
    def test_identical(self):
        assert edit_distance("مادة", "مادة") == 0

    def test_one_substitution(self):
        assert edit_distance("ماذة", "مادة") == 1

    def test_abandons_past_the_ceiling(self):
        assert edit_distance("مادة", "شهادة", ceiling=1) == 2
        assert edit_distance("abcdefgh", "z", ceiling=2) == 3


class TestMarkerWordMatching:
    @pytest.mark.parametrize("word", ["المادة", "مادة", "الماده", "المـادة", "المَادة"])
    def test_canonical_and_free_variants(self, word):
        kind, _, distance = match_marker_word(word)
        assert kind == "article"
        assert distance == 0

    @pytest.mark.parametrize("word,kind", [
        ("الماذة", "article"),   # dot added to dal
        ("المارة", "article"),   # dal read as reh
        ("لمادة", "article"),    # alef of the article dropped
    ])
    def test_one_edit_is_recovered(self, word, kind):
        hit = match_marker_word(word)
        assert hit is not None and hit[0] == kind
        assert hit[2] <= MAX_MARKER_DISTANCE

    @pytest.mark.parametrize("word", ["البند", "الفصل", "الباب", "القسم", "الفقرة"])
    def test_other_structural_words(self, word):
        assert match_marker_word(word) is not None

    def test_short_words_are_exact_only(self):
        """At three letters one edit reaches a third of the language, so
        tolerance there buys nothing and costs a great deal."""
        assert len("بند") < MIN_FUZZY_LENGTH
        assert match_marker_word("بند") is not None
        assert match_marker_word("بنر") is None
        assert match_marker_word("يند") is None

    def test_first_letter_must_survive(self):
        """The guard that separates مادة from عادة, سادة and قادة."""
        assert match_marker_word("الهادة") is None
        assert match_marker_word("العادة") is None


class TestNoFalsePositives:
    """The constraint the threshold is set by."""

    # Ordinary Arabic that is one or two edits from a marker word, or that
    # simply precedes a number the way markers do.
    NON_MARKERS = [
        "عادة", "العادة", "سادة", "السادة", "قادة", "القادة",
        "مدة", "المدة", "زيادة", "الزيادة", "إفادة", "الإفادة",
        "شهادة", "الشهادة", "إعادة", "الإعادة", "فائدة", "الفائدة",
        "نسبة", "النسبة", "قيمة", "القيمة", "غرامة", "الغرامة",
        "مرحلة", "المرحلة", "جلسة", "الجلسة", "لجنة", "اللجنة",
        "سنة", "السنة", "وحدة", "الوحدة", "قاعدة", "القاعدة",
        "دفعة", "الدفعة", "حصة", "الحصة", "بنود", "البنود",
        "فصول", "الفصول", "أبواب", "الأبواب", "منطقة", "المنطقة",
        "علاوة", "العلاوة", "قسط", "الأقساط", "ودائع", "الودائع",
    ]

    TAILS = [" 5", " 12", " (3)", " ٥", " الأول"]

    def test_ordinary_words_before_a_number_are_not_markers(self):
        """Every distractor against every numbering shape a marker can take.

        Looped rather than parametrized: this is one claim -- "the tolerant
        matcher fires on no ordinary Arabic word" -- and 250 test ids would
        report it as 250, drowning the rest of the module.
        """
        tested, fps = 0, []
        for word in self.NON_MARKERS:
            for tail in self.TAILS:
                line = f"{word}{tail} من هذا العقد المبرم بين الطرفين"
                if strict(line) is not None:
                    continue      # the strict matcher already claims this line
                tested += 1
                if detect_marker(line) is not None:
                    fps.append(line)
        assert tested > 200, "the distractor set stopped covering anything"
        assert not fps, (
            f"{len(fps)}/{tested} ordinary words were mistaken for structural "
            f"markers: {fps[:5]}. A false positive invents a clause boundary "
            f"the document does not have, and nothing downstream flags it."
        )

    def test_the_deny_list_is_actually_consulted(self):
        """المدة ("the period") is one deletion from المادة and Egyptian
        contracts write "المدة 5 سنوات". It must never be article 5."""
        assert "مده" in CONFUSABLE_WORDS
        assert detect_marker("المدة 5 سنوات من تاريخ التوقيع") is None

    def test_prose_is_not_a_marker(self):
        for line in [
            "يلتزم الطرف الأول بتسليم الأعمال خلال 30 يوما من تاريخ التوقيع.",
            "بلغت قيمة العقد 2,450,000 جنيه مصري لا غير.",
            "وذلك وفقا لأحكام القانون رقم 95 لسنة 1995 المشار إليه.",
        ]:
            assert detect_marker(line) is None

    def test_corpus_arabic_has_no_false_positives(self, synthetic_dir):
        """Measured, not asserted: every non-marker line of every Arabic
        ground-truth file in the corpus, through the tolerant matcher."""
        lines, fps = 0, []
        for gt in sorted(synthetic_dir.glob("*.groundtruth.txt")):
            for raw in gt.read_text(encoding="utf-8", errors="replace").splitlines():
                s = raw.strip()
                if len(s) < 8 or _detect_exact(s) is not None:
                    continue
                lines += 1
                m = detect_marker(s)
                if m is not None and m.fuzzy:
                    fps.append((s, m.label))
        if lines < 100:
            pytest.skip("corpus ground truth not generated")
        rate = len(fps) / lines
        assert rate <= 0.001, (
            f"{len(fps)}/{lines} false positives ({rate:.3%}) on non-marker "
            f"Arabic: {fps[:5]}"
        )


class TestCorruptedMarkersAreRecovered:
    @pytest.mark.parametrize("written,label", [
        ("المادة", "exact"),
        ("الماده", "teh marbuta read as heh"),
        ("الماذة", "dot added to dal"),
        ("المارة", "dal read as reh"),
        ("المـادة", "tatweel inserted"),
        ("المَادة", "spurious diacritic"),
        ("الما دة", "word split by a broken join"),
        ("لمادة", "alef of the article dropped"),
        ("الماذه", "two OCR errors, but only one after folding"),
    ])
    def test_article_marker_is_recovered(self, written, label):
        marker = detect_marker(f"{written} 12 - {TITLE}")
        assert marker is not None, f"missed: {label}"
        assert marker.kind == "article"
        assert marker.number == "12"

    def test_clause_and_chapter_words_too(self):
        assert detect_marker("الفـصل 3 - أحكام عامة").kind == "chapter"
        assert detect_marker("البـند 4 - الالتزامات").kind == "clause"

    def test_arabic_indic_digits_survive(self):
        marker = detect_marker(f"الماذة ١٢ - {TITLE}")
        assert marker is not None and marker.number == "12"


class TestSplitDigits:
    """OCR splitting "12" into "1 2" -- the *other* half of limitation #4."""

    @pytest.mark.parametrize("line,expected", [
        ("المادة 1 2 - التعريفات", "12"),
        ("المادة (1 2) التعريفات", "12"),
        ("المادة ١ ٢ - التعريفات", "12"),
        ("المادة 1,2 - التعريفات", "12"),
        ("الماذة 1 2 - التعريفات", "12"),
    ])
    def test_split_number_is_rejoined(self, line, expected):
        marker = detect_marker(line)
        assert marker is not None
        assert marker.number == expected

    def test_the_strict_matcher_silently_truncated_these(self):
        """Not a miss -- a *wrong answer*. "المادة 1 2" matched strictly and
        returned article 1, folding article 12's text into article 1's chunk."""
        assert strict("المادة 1 2 - التعريفات").number == "1"
        assert detect_marker("المادة 1 2 - التعريفات").number == "12"

    def test_repair_stops_at_the_marker_number(self):
        """The scope constraint. An amount later in the same line must survive
        untouched -- applied loosely this rule rewrites every date, price and
        citation in the document."""
        line = "المادة 12 المبلغ 1 500 جنيه"
        marker = detect_marker(line)
        assert marker.number == "12"
        out, changed = join_split_digits(line, len("المادة"))
        assert out == line and changed is False

    def test_meaningful_separators_are_not_collapsed(self):
        """"12/2019" and "5.2.1" are structured numbers, not split ones."""
        assert join_split_digits("المادة 12/2019", len("المادة"))[1] is False
        assert detect_marker("5.2.1 The scope includes legal review.").number == "5.2.1"

    def test_digit_order_is_never_changed(self):
        """Out of scope by explicit decision: '٢١' and '١٢' are
        indistinguishable in extracted text."""
        marker = detect_marker("المادة ٢ ١ - التعريفات")
        assert marker.number == "21", "digits must be joined in the order found"


class TestTwoErrorsAreNotHandled:
    """The documented ceiling, asserted rather than implied.

    Distance 2 is not reachable at these word lengths without the matcher
    firing on ordinary vocabulary -- see the module docstring. Saying so in a
    test means a later change that quietly loosens the threshold has to delete
    an assertion rather than slip through.
    """

    @pytest.mark.parametrize("written", [
        "الهاده",   # first letter destroyed
        "الملاه",   # two substitutions, neither folded away
        "الم ا دة",  # split into three fragments
        "الءاذة",   # two substitutions
    ])
    def test_two_or_more_errors_are_missed(self, written):
        assert detect_marker(f"{written} 12 - {TITLE}") is None


class TestFailuresAreVisible:
    """The actual point of the change."""

    def test_a_fuzzy_match_says_it_was_fuzzy(self):
        marker = detect_marker(f"الماذة 12 - {TITLE}")
        assert marker.fuzzy is True
        assert marker.match_confidence < 1.0
        assert "edit distance 1" in marker.match_evidence
        assert marker.raw.startswith("الماذة"), "raw keeps what was on the page"

    def test_a_clean_match_is_not_labelled_fuzzy(self):
        marker = detect_marker(f"المادة 12 - {TITLE}")
        assert marker.fuzzy is False
        assert marker.match_confidence == 1.0
        assert marker.match_evidence is None

    def test_repair_returns_a_line_the_strict_patterns_accept(self):
        """One definition of what a marker is: the tolerant layer rewrites, the
        strict patterns still do the parsing."""
        hit = repair_marker_line(f"الماذة 1 2 - {TITLE}")
        assert hit is not None
        assert hit.digits_joined is True
        assert _detect_exact(hit.repaired_line).number == "12"

    def test_fuzzy_markers_reach_the_chunk_metadata(self, tmp_txt):
        from src.pipeline import process_document

        text = "\n\n".join(
            f"الماذة {n} - بند رقم {n}\nيلتزم الطرف الأول بأداء الالتزامات "
            f"المنصوص عليها في هذه المادة على الوجه المبين بالعقد وملاحقه."
            for n in range(1, 6)
        )
        cfg = PipelineConfig()
        cfg.ocr.enabled = False
        cfg.extraction.use_docling = False
        result = process_document(tmp_txt(text), cfg)

        assert any(
            (c.metadata.get("structure") or {}).get("marker_fuzzy")
            for c in result.chunks
        ), "a fuzzy marker must be visible on the chunk, not just in the log"
        assert any("OCR-tolerant matching" in w for w in result.warnings)

    def test_structure_detection_failure_is_announced(self, tmp_txt):
        """The silent demotion this whole limitation is about."""
        from src.pipeline import process_document

        text = "\n\n".join(
            "هذا نص عادي لا يحمل أي علامة هيكلية على الإطلاق، وهو مكتوب "
            "لغرض اختبار سلوك النظام عندما لا يعثر على أي بنية قانونية "
            f"يمكن الاعتماد عليها في التقطيع رقم {n}."
            for n in range(1, 8)
        )
        cfg = PipelineConfig()
        cfg.ocr.enabled = False
        cfg.extraction.use_docling = False
        result = process_document(tmp_txt(text), cfg)

        assert all(
            c.metadata.get("chunk_strategy") == "paragraph" for c in result.chunks
        )
        assert any("structure_detection_failed" in w for w in result.warnings), (
            "falling back to paragraph chunking must leave a trace; that is the "
            "failure mode this limitation is about"
        )
        assert any(
            e.get("status") == "structure_detection_failed" for e in result.engine_log
        )

    def test_a_structured_document_raises_no_failure_flag(self, statute_txt):
        from src.pipeline import process_document

        cfg = PipelineConfig()
        cfg.ocr.enabled = False
        cfg.extraction.use_docling = False
        result = process_document(statute_txt, cfg)
        assert not any("structure_detection_failed" in w for w in result.warnings)


class TestChunkingEquivalence:
    """The real success criterion: not "the regex matched" but "the document
    chunks the same way it would have if OCR had not damaged it"."""

    CLEAN = "\n\n".join(
        f"المادة {n} - الالتزامات\nيلتزم الطرف الأول بأداء الخدمات المنصوص "
        f"عليها في هذه المادة وفقا للأصول المهنية المتعارف عليها في هذا "
        f"المجال، وذلك خلال المدة المحددة بالعقد وملاحقه المرفقة به."
        for n in range(1, 7)
    )

    @staticmethod
    def _clause_ids(path, cfg):
        from src.pipeline import process_document

        result = process_document(path, cfg)
        return {
            (c.metadata.get("structure") or {}).get("clause_id")
            for c in result.chunks
        } - {None}

    @pytest.mark.parametrize("corrupt", [
        lambda t: t.replace("المادة", "الماذة"),
        lambda t: t.replace("المادة", "المارة"),
        lambda t: t.replace("المادة", "الما دة"),
        lambda t: t.replace("المادة", "لمادة"),
    ])
    def test_corrupted_document_chunks_like_the_clean_one(self, corrupt, tmp_txt):
        cfg = PipelineConfig()
        cfg.ocr.enabled = False
        cfg.extraction.use_docling = False

        clean = self._clause_ids(tmp_txt(self.CLEAN, "clean.txt"), cfg)
        damaged = self._clause_ids(tmp_txt(corrupt(self.CLEAN), "damaged.txt"), cfg)

        assert clean, "the clean fixture must itself produce clause ids"
        assert damaged == clean, (
            "chunking must land on the same clause boundaries; matching the "
            "regex is not the goal, equivalent chunks are"
        )
