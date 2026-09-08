import pytest
from pydantic import ValidationError

from src.schemas.m2_contract import (
    EmbeddedQuery,
    IdentifierSet,
    ProcessedQuery,
    QueryFilters,
)


def make_query(
    **overrides,
) -> ProcessedQuery:
    data = {
        "query_id": "q_001",
        "text_original": (
            "What does Article 69 require?"
        ),
        "normalized_text": (
            "What does Article 69 require?"
        ),
        "language": "en",
    }

    data.update(
        overrides
    )

    return ProcessedQuery(
        **data
    )


def test_processed_query_has_stable_default_collections():
    first = make_query()

    second = make_query(
        query_id="q_002"
    )

    assert first.embedding == []
    assert first.query_variants == []
    assert first.identifiers == IdentifierSet()
    assert first.filters == QueryFilters()

    first.query_variants.append(
        "variant"
    )

    first.identifiers.article_numbers.append(
        "69"
    )

    assert second.query_variants == []

    assert (
        second.identifiers.article_numbers
        == []
    )


def test_identifier_set_includes_named_legal_terms():
    identifiers = IdentifierSet(
        article_numbers=[
            "69"
        ],
        case_numbers=[
            "123/2025"
        ],
        party_names=[
            "Acme Egypt LLC"
        ],
        named_legal_terms=[
            "force majeure"
        ],
    )

    dumped = identifiers.model_dump()

    assert (
        dumped["article_numbers"]
        == ["69"]
    )

    assert (
        dumped["case_numbers"]
        == ["123/2025"]
    )

    assert (
        dumped["party_names"]
        == ["Acme Egypt LLC"]
    )

    assert (
        dumped["named_legal_terms"]
        == ["force majeure"]
    )


def test_processed_query_canonicalizes_legacy_mixed_language():
    query = make_query(
        language="mixed"
    )

    assert query.language == "ar-en"


def test_query_filters_canonicalize_mixed_language():
    filters = QueryFilters(
        language="mixed"
    )

    assert filters.language == "ar-en"


def test_processed_query_rejects_unsupported_language():
    with pytest.raises(
        ValidationError
    ):
        make_query(
            language="fr"
        )


def test_processed_query_preserves_original_text_exactly():
    original = (
        "  What does Article 69 require?  "
    )

    query = make_query(
        text_original=original
    )

    assert (
        query.text_original
        == original
    )


def test_processed_query_rejects_whitespace_only_required_text():
    with pytest.raises(
        ValidationError
    ):
        make_query(
            text_original="   "
        )

    with pytest.raises(
        ValidationError
    ):
        make_query(
            normalized_text="   "
        )


def test_document_ids_are_trimmed_deduplicated_and_ordered():
    filters = QueryFilters(
        document_ids=[
            "doc_002",
            "doc_001",
            "doc_002",
        ]
    )

    assert filters.document_ids == [
        "doc_002",
        "doc_001",
    ]


def test_document_ids_reject_internal_whitespace():
    with pytest.raises(
        ValidationError
    ):
        QueryFilters(
            document_ids=[
                "doc 001"
            ]
        )


def test_contracts_forbid_unknown_fields():
    with pytest.raises(
        ValidationError
    ):
        make_query(
            unexpected_field=True
        )

    with pytest.raises(
        ValidationError
    ):
        IdentifierSet(
            unexpected_field=True
        )

    with pytest.raises(
        ValidationError
    ):
        QueryFilters(
            unexpected_field=True
        )


def test_embedded_query_requires_non_empty_embedding():
    processed = make_query()

    with pytest.raises(
        ValidationError
    ):
        EmbeddedQuery(
            processed_query=processed,
            embedding=[],
            model="BAAI/bge-m3",
            dimension=1024,
        )


def test_embedded_query_keeps_dimension_metadata_separate():
    processed = make_query()

    embedded = EmbeddedQuery(
        processed_query=processed,
        embedding=[
            0.1,
            0.2,
            0.3,
        ],
        model="fake-bge",
        dimension=3,
    )

    assert embedded.embedding == [
        0.1,
        0.2,
        0.3,
    ]

    assert embedded.dimension == 3
