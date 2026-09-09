import pytest

from src.query_variant_builder import (
    QueryVariantBuilder,
)
from src.schemas.m2_contract import (
    IdentifierSet,
)


@pytest.fixture
def builder():
    return QueryVariantBuilder()


def test_english_query_adds_controlled_arabic_equivalent(
    builder,
):
    identifiers = IdentifierSet(
        named_legal_terms=[
            "termination"
        ]
    )

    variants = builder.build(
        normalized_text=(
            "What are the termination conditions?"
        ),
        language="en",
        identifiers=identifiers,
    )

    assert variants[0] == (
        "What are the termination conditions?"
    )

    assert len(variants) == 2

    assert "إنهاء العقد" in variants[1]


def test_arabic_query_adds_controlled_english_equivalent(
    builder,
):
    identifiers = IdentifierSet(
        named_legal_terms=[
            "القوة القاهرة"
        ]
    )

    variants = builder.build(
        normalized_text=(
            "هل تنطبق القوة القاهرة؟"
        ),
        language="ar",
        identifiers=identifiers,
    )

    assert len(variants) == 2

    assert (
        "force majeure"
        in variants[1]
    )


def test_mixed_query_does_not_duplicate_existing_equivalents(
    builder,
):
    identifiers = IdentifierSet(
        named_legal_terms=[
            "force majeure",
            "القوة القاهرة",
        ]
    )

    variants = builder.build(
        normalized_text=(
            "هل force majeure تعني "
            "القوة القاهرة؟"
        ),
        language="ar-en",
        identifiers=identifiers,
    )

    assert variants == [
        (
            "هل force majeure تعني "
            "القوة القاهرة؟"
        )
    ]


def test_query_without_known_legal_terms_has_single_variant(
    builder,
):
    variants = builder.build(
        normalized_text=(
            "What happened yesterday?"
        ),
        language="en",
        identifiers=IdentifierSet(),
    )

    assert variants == [
        "What happened yesterday?"
    ]


def test_unknown_language_does_not_trigger_translation(
    builder,
):
    identifiers = IdentifierSet(
        named_legal_terms=[
            "force majeure"
        ]
    )

    variants = builder.build(
        normalized_text="12345",
        language="unknown",
        identifiers=identifiers,
    )

    # Exact identifier may be restored,
    # but no cross-language translation is generated.
    assert not any(
        "القوة القاهرة" in variant
        for variant in variants
    )


def test_article_number_is_preserved_in_every_variant(
    builder,
):
    identifiers = IdentifierSet(
        article_numbers=[
            "69"
        ],
        named_legal_terms=[
            "termination"
        ],
    )

    variants = builder.build(
        normalized_text=(
            "termination under Article 69"
        ),
        language="en",
        identifiers=identifiers,
    )

    assert all(
        "69" in variant
        for variant in variants
    )


def test_case_number_is_preserved_in_every_variant(
    builder,
):
    identifiers = IdentifierSet(
        case_numbers=[
            "123/2025"
        ],
        named_legal_terms=[
            "force majeure"
        ],
    )

    variants = builder.build(
        normalized_text=(
            "force majeure in Case 123/2025"
        ),
        language="en",
        identifiers=identifiers,
    )

    assert all(
        "123/2025" in variant
        for variant in variants
    )


def test_money_is_preserved_in_every_variant(
    builder,
):
    identifiers = IdentifierSet(
        monetary_values=[
            "EGP 250,000"
        ],
        named_legal_terms=[
            "liquidated damages"
        ],
    )

    variants = builder.build(
        normalized_text=(
            "liquidated damages of "
            "EGP 250,000"
        ),
        language="en",
        identifiers=identifiers,
    )

    assert all(
        "EGP 250,000" in variant
        for variant in variants
    )


def test_exact_arabic_party_name_is_restored_after_normalization(
    builder,
):
    identifiers = IdentifierSet(
        party_names=[
            "شركة الأمل"
        ]
    )

    variants = builder.build(
        normalized_text=(
            "ما موقف شركة الامل؟"
        ),
        language="ar",
        identifiers=identifiers,
    )

    assert (
        "شركة الأمل"
        in variants[0]
    )


def test_exact_arabic_legal_term_is_preserved(
    builder,
):
    identifiers = IdentifierSet(
        named_legal_terms=[
            "إنهاء العقد"
        ]
    )

    variants = builder.build(
        normalized_text=(
            "ما شروط انهاء العقد؟"
        ),
        language="ar",
        identifiers=identifiers,
    )

    assert (
        "إنهاء العقد"
        in variants[0]
    )

    assert (
        "termination"
        in variants[1]
    )


def test_multiple_legal_terms_use_one_combined_expansion(
    builder,
):
    identifiers = IdentifierSet(
        named_legal_terms=[
            "force majeure",
            "arbitration",
        ]
    )

    variants = builder.build(
        normalized_text=(
            "force majeure and arbitration"
        ),
        language="en",
        identifiers=identifiers,
    )

    assert len(variants) == 2

    assert (
        "القوة القاهرة"
        in variants[1]
    )

    assert (
        "التحكيم"
        in variants[1]
    )


def test_duplicate_legal_terms_do_not_duplicate_expansion(
    builder,
):
    identifiers = IdentifierSet(
        named_legal_terms=[
            "force majeure",
            "force majeure",
        ]
    )

    variants = builder.build(
        normalized_text=(
            "force majeure"
        ),
        language="en",
        identifiers=identifiers,
    )

    assert (
        variants[1].count(
            "القوة القاهرة"
        )
        == 1
    )
