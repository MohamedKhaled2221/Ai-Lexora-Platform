import pytest

from src.query_processor import (
    QueryProcessor,
)


@pytest.fixture
def processor() -> QueryProcessor:
    return QueryProcessor()


# =========================================================
# Language detection
# =========================================================


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "What are the termination conditions?",
            "en",
        ),
        (
            "What does Article 69 require?",
            "en",
        ),
        (
            "ما هي شروط إنهاء العقد؟",
            "ar",
        ),
        (
            "ما حكم المادة 69؟",
            "ar",
        ),
        (
            "إيه شروط فسخ العقد؟",
            "ar",
        ),
        (
            "العقد ده ينتهي إمتى؟",
            "ar",
        ),
        (
            "إيه termination conditions في العقد؟",
            "ar-en",
        ),
        (
            "هل Article 69 ينطبق على العقد؟",
            "ar-en",
        ),
        (
            "NDA ده ينتهي إمتى؟",
            "ar-en",
        ),
        (
            "12345",
            "unknown",
        ),
        (
            "!!! ???",
            "unknown",
        ),
    ],
)
def test_detect_language(
    processor,
    text,
    expected,
):
    assert (
        processor.detect_language(text)
        == expected
    )

def test_arabic_with_arabic_digits_is_still_arabic(
    processor,
):
    text = "ما حكم المادة ٦٩؟"

    assert (
        processor.detect_language(text)
        == "ar"
    )


def test_arabic_digits_alone_do_not_define_language(
    processor,
):
    assert (
        processor.detect_language("٦٩")
        == "unknown"
    )
def test_english_with_arabic_digits_is_still_english(
    processor,
):
    text = (
        "What does Article ٦٩ require?"
    )

    assert (
        processor.detect_language(text)
        == "en"
    )


def test_arabic_with_latin_identifier_is_mixed(
    processor,
):
    text = (
        "ما موقف NDA في هذه الحالة؟"
    )

    assert (
        processor.detect_language(text)
        == "ar-en"
    )


# =========================================================
# Normalization
# =========================================================


def test_normalize_collapses_whitespace(
    processor,
):
    assert processor.normalize(
        "  termination   of   contract  "
    ) == "termination of contract"


def test_normalize_removes_tatweel(
    processor,
):
    assert processor.normalize(
        "العقــــد"
    ) == "العقد"


def test_normalize_removes_arabic_diacritics(
    processor,
):
    assert processor.normalize(
        "العَقْد"
    ) == "العقد"


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            "إنهاء العقد",
            "انهاء العقد",
        ),
        (
            "أحكام العقد",
            "احكام العقد",
        ),
        (
            "آثار الإنهاء",
            "اثار الانهاء",
        ),
    ],
)
def test_normalize_arabic_alef_variants(
    processor,
    source,
    expected,
):
    assert (
        processor.normalize(source)
        == expected
    )


def test_normalize_does_not_change_teh_marbuta(
    processor,
):
    assert processor.normalize(
        "المحكمة"
    ) == "المحكمة"


def test_normalize_does_not_change_arabic_yeh_or_alef_maqsura(
    processor,
):
    text = "علي على"

    assert (
        processor.normalize(text)
        == text
    )


def test_normalization_preserves_case_number(
    processor,
):
    text = (
        "Case 123/2025 concerns termination."
    )

    normalized = processor.normalize(
        text
    )

    assert "123/2025" in normalized


def test_normalization_preserves_article_number(
    processor,
):
    text = (
        "What does Article 69 require?"
    )

    normalized = processor.normalize(
        text
    )

    assert "69" in normalized


def test_normalization_preserves_money(
    processor,
):
    text = (
        "The claim is for EGP 250,000."
    )

    normalized = processor.normalize(
        text
    )

    assert "EGP 250,000" in normalized


def test_normalization_preserves_latin_case(
    processor,
):
    text = "NDA ABC Legal LLC"

    assert (
        processor.normalize(text)
        == text
    )


# =========================================================
# Full processing
# =========================================================


def test_process_preserves_original_query_exactly(
    processor,
):
    raw = (
        "  إيه termination conditions "
        "في العقد؟  "
    )

    result = processor.process(
        raw
    )

    assert (
        result.text_original
        == raw
    )

    assert result.language == "ar-en"

    assert result.normalized_text == (
        "ايه termination conditions "
        "في العقد؟"
    )


def test_process_english_query(
    processor,
):
    result = processor.process(
        "What are the termination conditions?"
    )

    assert result.language == "en"

    assert (
        result.query_variants[0]
        == result.normalized_text
    )

    assert len(
        result.query_variants
    ) == 2

    assert (
        "إنهاء العقد"
        in result.query_variants[1]
    )


def test_process_formal_arabic_query(
    processor,
):
    result = processor.process(
        "ما هي شروط إنهاء العقد؟"
    )

    assert result.language == "ar"

    assert result.normalized_text == (
        "ما هي شروط انهاء العقد؟"
    )

def test_process_arabic_legal_term_adds_english_variant(
    processor,
):
    result = processor.process(
        "هل تنطبق القوة القاهرة؟"
    )

    assert result.language == "ar"

    assert len(
        result.query_variants
    ) == 2

    assert (
        "force majeure"
        in result.query_variants[1]
    )


def test_process_variants_preserve_exact_case_number(
    processor,
):
    result = processor.process(
        "Does force majeure apply "
        "in Case 123/2025?"
    )

    assert (
        result.identifiers.case_numbers
        == ["123/2025"]
    )

    assert all(
        "123/2025" in variant
        for variant
        in result.query_variants
    )


def test_process_mixed_query_with_both_terms_does_not_expand(
    processor,
):
    result = processor.process(
        "هل force majeure تعني "
        "القوة القاهرة؟"
    )

    assert result.language == "ar-en"

    assert (
        result.query_variants
        == [result.normalized_text]
    )
def test_process_egyptian_arabic_query(
    processor,
):
    result = processor.process(
        "إيه شروط فسخ العقد؟"
    )

    # Egyptian Arabic written in Arabic script
    # intentionally uses the canonical Arabic label.
    assert result.language == "ar"

    assert result.normalized_text == (
        "ايه شروط فسخ العقد؟"
    )


def test_process_mixed_query(
    processor,
):
    result = processor.process(
        "هل Article 69 ينطبق على العقد؟"
    )

    assert result.language == "ar-en"

    assert (
        result.identifiers.article_numbers
        == ["69"]
    )


def test_process_generates_query_id(
    processor,
):
    result = processor.process(
        "What does the contract require?"
    )

    assert result.query_id.startswith(
        "q_"
    )

    assert (
        len(result.query_id)
        == 10
    )


def test_process_rejects_empty_query(
    processor,
):
    with pytest.raises(
        ValueError,
        match="query must not be empty",
    ):
        processor.process("")


def test_process_rejects_whitespace_only_query(
    processor,
):
    with pytest.raises(
        ValueError,
        match="query must not be empty",
    ):
        processor.process(
            "   "
        )
def test_process_populates_complete_identifier_set(
    processor,
):
    query = (
        "What happened in Case 123/2025 "
        "under Article 157 for "
        "Acme Egypt LLC concerning "
        "EGP 250,000 and force majeure?"
    )

    result = processor.process(
        query
    )

    identifiers = result.identifiers

    assert (
        identifiers.article_numbers
        == ["157"]
    )

    assert (
        identifiers.case_numbers
        == ["123/2025"]
    )

    assert (
        identifiers.monetary_values
        == ["EGP 250,000"]
    )

    assert (
        identifiers.party_names
        == ["Acme Egypt LLC"]
    )

    assert (
        identifiers.named_legal_terms
        == ["force majeure"]
    )


def test_identifier_extraction_uses_original_query(
    processor,
):
    query = (
        "ما حكم المادة ٦٩ "
        "بشأن القوة القاهرة؟"
    )

    result = processor.process(
        query
    )

    # Exact identifiers come from the original query,
    # not from normalized text.
    assert (
        result.identifiers.article_numbers
        == ["٦٩"]
    )

    assert (
        result.identifiers.named_legal_terms
        == ["القوة القاهرة"]
    )