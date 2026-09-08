import pytest

from src.identifier_preserver import (
    IdentifierPreserver,
)


@pytest.fixture
def preserver():
    return IdentifierPreserver()


# =========================================================
# Article numbers
# =========================================================


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "What does Article 69 require?",
            ["69"],
        ),
        (
            "What does Art. 157 require?",
            ["157"],
        ),
        (
            "ما حكم المادة 69؟",
            ["69"],
        ),
        (
            "ما حكم المادة ٦٩؟",
            ["٦٩"],
        ),
        (
            "راجع المادة رقم ١٥٧.",
            ["١٥٧"],
        ),
    ],
)
def test_extract_article_numbers(
    preserver,
    text,
    expected,
):
    assert (
        preserver.extract_articles(text)
        == expected
    )


def test_multiple_articles_preserve_order(
    preserver,
):
    text = (
        "Article 69 and Article 157 "
        "apply to this matter."
    )

    assert (
        preserver.extract_articles(text)
        == ["69", "157"]
    )


def test_duplicate_articles_are_removed(
    preserver,
):
    text = (
        "Article 69 refers back "
        "to Article 69."
    )

    assert (
        preserver.extract_articles(text)
        == ["69"]
    )

def test_english_role_matching_is_case_insensitive_only_for_role(
    preserver,
):
    assert preserver.extract_party_names(
        "plaintiff John Smith filed the claim."
    ) == ["John Smith"]


def test_generic_arabic_party_word_does_not_create_fake_name(
    preserver,
):
    assert preserver.extract_party_names(
        "تم الاتفاق مع الطرف الآخر."
    ) == []


@pytest.mark.parametrize(
    "text",
    [
        "وفقا للمادة ٦٩",
        "طبقا للمادة ٦٩",
        "راجع بالمادة ٦٩",
    ],
)
def test_arabic_article_with_attached_prefix(
    preserver,
    text,
):
    assert (
        preserver.extract_articles(text)
        == ["٦٩"]
    )
# =========================================================
# Case numbers
# =========================================================


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "Case 123/2025 concerns the dispute.",
            ["123/2025"],
        ),
        (
            "Case No. 123/2025 concerns the dispute.",
            ["123/2025"],
        ),
        (
            "القضية رقم ١٢٣/٢٠٢٥ تخص النزاع.",
            ["١٢٣/٢٠٢٥"],
        ),
        (
            "دعوى 45-2024 منظورة أمام المحكمة.",
            ["45-2024"],
        ),
    ],
)
def test_extract_case_numbers(
    preserver,
    text,
    expected,
):
    assert (
        preserver.extract_cases(text)
        == expected
    )


# =========================================================
# Dates
# =========================================================


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "The agreement was signed on 09/09/2026.",
            ["09/09/2026"],
        ),
        (
            "The agreement was signed on 2026-09-09.",
            ["2026-09-09"],
        ),
        (
            "The agreement was signed on 9 September 2026.",
            ["9 September 2026"],
        ),
        (
            "The agreement was signed on September 9, 2026.",
            ["September 9, 2026"],
        ),
        (
            "تم توقيع العقد في ٩ سبتمبر ٢٠٢٦.",
            ["٩ سبتمبر ٢٠٢٦"],
        ),
    ],
)
def test_extract_dates(
    preserver,
    text,
    expected,
):
    assert (
        preserver.extract_dates(text)
        == expected
    )


def test_dates_preserve_original_order(
    preserver,
):
    text = (
        "Signed on 01/01/2026 "
        "and expires on 31/12/2026."
    )

    assert (
        preserver.extract_dates(text)
        == [
            "01/01/2026",
            "31/12/2026",
        ]
    )


# =========================================================
# Monetary values
# =========================================================


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "The claim is for EGP 250,000.",
            ["EGP 250,000"],
        ),
        (
            "The claim is for 250,000 EGP.",
            ["250,000 EGP"],
        ),
        (
            "The claim is for $1,500.50.",
            ["$1,500.50"],
        ),
        (
            "قيمة المطالبة ٢٥٠٬٠٠٠ جنيه مصري.",
            ["٢٥٠٬٠٠٠ جنيه مصري"],
        ),
        (
            "The amount is AED 10000.",
            ["AED 10000"],
        ),
    ],
)
def test_extract_monetary_values(
    preserver,
    text,
    expected,
):
    assert (
        preserver.extract_money(text)
        == expected
    )


# =========================================================
# Party names
# =========================================================


def test_extract_english_company_name(
    preserver,
):
    text = (
        "The dispute concerns Acme Egypt LLC."
    )

    assert (
        preserver.extract_party_names(text)
        == ["Acme Egypt LLC"]
    )


def test_extract_multiple_english_companies(
    preserver,
):
    text = (
        "Acme Egypt LLC sued "
        "Beta Holdings Ltd."
    )

    assert (
        preserver.extract_party_names(text)
        == [
            "Acme Egypt LLC",
            "Beta Holdings Ltd.",
        ]
    )


def test_extract_english_person_with_legal_role(
    preserver,
):
    text = (
        "Plaintiff John Smith filed the claim."
    )

    assert (
        preserver.extract_party_names(text)
        == ["John Smith"]
    )


def test_extract_arabic_company_name(
    preserver,
):
    text = (
        "تعاقدت شركة النيل للمقاولات "
        "مع الطرف الآخر."
    )

    assert (
        preserver.extract_party_names(text)
        == ["شركة النيل للمقاولات"]
    )


def test_arabic_company_name_stops_at_connector(
    preserver,
):
    text = (
        "شركة النيل للمقاولات "
        "في القضية رقم ١٢٣/٢٠٢٥"
    )

    assert (
        preserver.extract_party_names(text)
        == ["شركة النيل للمقاولات"]
    )


def test_extract_arabic_person_with_role(
    preserver,
):
    text = (
        "المدعي أحمد محمد علي "
        "في القضية رقم ١٢٣/٢٠٢٥"
    )

    assert (
        preserver.extract_party_names(text)
        == ["أحمد محمد علي"]
    )


# =========================================================
# Named legal terms
# =========================================================


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "Does the force majeure clause apply?",
            ["force majeure"],
        ),
        (
            "What is the governing law?",
            ["governing law"],
        ),
        (
            "Does the limitation of liability apply?",
            ["limitation of liability"],
        ),
        (
            "هل تنطبق القوة القاهرة؟",
            ["القوة القاهرة"],
        ),
        (
            "ما أثر فسخ العقد؟",
            ["فسخ العقد"],
        ),
        (
            "هل يوجد شرط بشأن التحكيم؟",
            ["التحكيم"],
        ),
    ],
)
def test_extract_named_legal_terms(
    preserver,
    text,
    expected,
):
    assert (
        preserver.extract_legal_terms(text)
        == expected
    )


# =========================================================
# Complete extraction
# =========================================================


def test_complete_english_legal_query(
    preserver,
):
    text = (
        "What happened in Case 123/2025 "
        "under Article 157 for "
        "Acme Egypt LLC concerning "
        "EGP 250,000 and force majeure?"
    )

    result = preserver.extract(
        text
    )

    assert (
        result.article_numbers
        == ["157"]
    )

    assert (
        result.case_numbers
        == ["123/2025"]
    )

    assert (
        result.monetary_values
        == ["EGP 250,000"]
    )

    assert (
        result.party_names
        == ["Acme Egypt LLC"]
    )

    assert (
        result.named_legal_terms
        == ["force majeure"]
    )


def test_complete_arabic_legal_query(
    preserver,
):
    text = (
        "ما موقف شركة النيل للمقاولات "
        "في القضية رقم ١٢٣/٢٠٢٥ "
        "وفقا للمادة ٦٩ بشأن القوة القاهرة "
        "ومبلغ ٢٥٠٬٠٠٠ جنيه مصري؟"
    )

    result = preserver.extract(
        text
    )

    assert (
        result.article_numbers
        == ["٦٩"]
    )

    assert (
        result.case_numbers
        == ["١٢٣/٢٠٢٥"]
    )

    assert (
        result.monetary_values
        == ["٢٥٠٬٠٠٠ جنيه مصري"]
    )

    assert (
        result.party_names
        == ["شركة النيل للمقاولات"]
    )

    assert (
        result.named_legal_terms
        == ["القوة القاهرة"]
    )


def test_empty_text_returns_empty_identifier_set(
    preserver,
):
    result = preserver.extract("")

    assert result.article_numbers == []
    assert result.case_numbers == []
    assert result.dates == []
    assert result.monetary_values == []
    assert result.party_names == []
    assert result.named_legal_terms == []
