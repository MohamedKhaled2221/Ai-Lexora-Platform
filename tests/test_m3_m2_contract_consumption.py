from __future__ import annotations

from qdrant_client.http.models import (
    PointStruct,
)

from src.query_processor import (
    QueryProcessor,
)
from src.retrieval.hybrid_search import (
    build_retrieval_text,
)
from src.retrieval.identifiers import (
    identifier_payload,
    normalize_identifier_set,
)
from src.schemas.m2_contract import (
    ProcessedQuery,
)
from src.vector_store.qdrant_manager import (
    QdrantVectorStore,
)
from tests.access_helpers import (
    access_scope,
    scoped_filters,
    shared_corpus_payload,
)


def _processed_query():
    return QueryProcessor().process(
        "What happened in Case 123/2025 "
        "under Article 157 for "
        "Acme Egypt LLC concerning "
        "force majeure?"
    )


def test_m3_consumes_complete_m2_identifier_contract():

    processed = _processed_query()

    normalized = normalize_identifier_set(
        processed.identifiers
    )

    assert normalized[
        "article_numbers"
    ] == ["157"]

    assert normalized[
        "case_numbers"
    ] == ["123/2025"]

    assert normalized[
        "party_names"
    ] == [
        "acme egypt llc"
    ]

    assert normalized[
        "named_legal_terms"
    ] == [
        "force majeure"
    ]


def test_index_payload_stores_party_name():

    payload = identifier_payload(
        document_id="doc-1",
        text=(
            "Acme Egypt LLC relies "
            "on force majeure."
        ),
    )

    assert payload[
        "party_name"
    ] == [
        "acme egypt llc"
    ]


def test_party_name_exact_lookup_is_acl_scoped():

    store = QdrantVectorStore(
        location=":memory:",
        collection_name=(
            "m3_party_name_test"
        ),
        vector_size=3,
    )

    payload = {
        "document_id": "doc-1",
        "chunk_id": "chunk-1",
        "text": (
            "Acme Egypt LLC relies "
            "on force majeure."
        ),
        **shared_corpus_payload(),
        **identifier_payload(
            document_id="doc-1",
            text=(
                "Acme Egypt LLC relies "
                "on force majeure."
            ),
        ),
    }

    store.upsert_chunks(
        [
            PointStruct(
                id=1,
                vector=[
                    1.0,
                    0.0,
                    0.0,
                ],
                payload=payload,
            )
        ]
    )

    query_filter = (
        store.build_qdrant_filter(
            access=access_scope()
        )
    )

    results = store.identifier_search(
        query_filter=query_filter,
        party_names=[
            "acme egypt llc"
        ],
    )

    assert [
        result["document_id"]
        for result in results
    ] == [
        "doc-1"
    ]


def test_retrieval_text_consumes_m2_variants_and_terms():

    processed = _processed_query()

    processed = processed.model_copy(
        update={
            "query_variants": [
                processed.normalized_text,
                (
                    processed.normalized_text
                    + " القوة القاهرة"
                ),
            ]
        }
    )

    retrieval_text = (
        build_retrieval_text(
            processed
        )
    )

    assert (
        "acme egypt llc"
        in retrieval_text.casefold()
    )

    assert (
        "force majeure"
        in retrieval_text.casefold()
    )

    assert (
        "القوة القاهرة"
        in retrieval_text
    )


def test_retrieval_text_deduplicates_equivalent_variants():

    query = ProcessedQuery(
        query_id="q1",
        text_original=(
            "force majeure"
        ),
        normalized_text=(
            "force majeure"
        ),
        query_variants=[
            "force majeure",
            "Force Majeure",
        ],
        filters=scoped_filters(),
    )

    assert (
        build_retrieval_text(
            query
        )
        == "force majeure"
    )
