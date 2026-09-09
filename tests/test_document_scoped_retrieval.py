from qdrant_client.http.models import (
    PointStruct,
)

from src.retrieval.hybrid_search import (
    HybridSearcher,
)
from src.schemas import (
    ProcessedQuery,
    QueryFilters,
)
from src.vector_store.qdrant_manager import (
    QdrantVectorStore,
)
from tests.access_helpers import (
    acl_payload,
    scoped_filters,
)


def make_store():
    store = QdrantVectorStore(
        location=":memory:",
        collection_name=(
            "document_scope_test"
        ),
        vector_size=3,
    )

    store.upsert_chunks(
        [
            PointStruct(
                id=1,
                vector=[
                    1.0,
                    0.0,
                    0.0,
                ],
                payload={
                    "document_id": "doc_a",
                    "chunk_id": "chunk_001",
                    "text": (
                        "The agreement may be "
                        "terminated for material "
                        "breach."
                    ),
                    "page": 1,
                    "section": "Termination",
                    "language": "en",
                    "document_type": (
                        "contract"
                    ),
                    **acl_payload(),
                },
            ),
            PointStruct(
                id=2,
                vector=[
                    0.8,
                    0.2,
                    0.0,
                ],
                payload={
                    "document_id": "doc_b",
                    "chunk_id": "chunk_001",
                    "text": (
                        "Payment is due within "
                        "thirty days."
                    ),
                    "page": 2,
                    "section": "Payment",
                    "language": "en",
                    "document_type": (
                        "contract"
                    ),
                    **acl_payload(),
                },
            ),
            PointStruct(
                id=3,
                vector=[
                    0.9,
                    0.1,
                    0.0,
                ],
                payload={
                    "document_id": "doc_c",
                    "chunk_id": "chunk_001",
                    "text": (
                        "This excluded document "
                        "must never be retrieved."
                    ),
                    "page": 3,
                    "section": "Excluded",
                    "language": "en",
                    "document_type": (
                        "contract"
                    ),
                    **acl_payload(),
                },
            ),
        ]
    )

    return store


def make_query(
    document_ids,
):
    return ProcessedQuery(
        query_id="q_scope_001",
        text_original=(
            "What are the termination terms?"
        ),
        normalized_text=(
            "what are the termination terms"
        ),
        language="en",
        embedding=[
            1.0,
            0.0,
            0.0,
        ],
        filters=scoped_filters(
            document_ids=document_ids,
        ),
    )


def test_query_filters_normalize_document_ids():
    filters = QueryFilters(
        document_ids=[
            " doc_a ",
            "doc_b",
            "doc_a",
        ]
    )

    assert filters.document_ids == [
        "doc_a",
        "doc_b",
    ]


def test_hybrid_search_is_scoped_to_one_document():
    store = make_store()

    searcher = HybridSearcher(
        vector_store=store
    )

    results = searcher.search(
        query=make_query(
            ["doc_a"]
        ),
        candidate_top_k=10,
    )

    assert results

    assert {
        item["document_id"]
        for item in results
    } == {
        "doc_a"
    }


def test_multiple_documents_with_same_chunk_id_do_not_collide():
    store = make_store()

    searcher = HybridSearcher(
        vector_store=store
    )

    results = searcher.search(
        query=make_query(
            [
                "doc_a",
                "doc_b",
            ]
        ),
        candidate_top_k=10,
    )

    identities = {
        (
            item["document_id"],
            item["chunk_id"],
        )
        for item in results
    }

    assert (
        "doc_a",
        "chunk_001",
    ) in identities

    assert (
        "doc_b",
        "chunk_001",
    ) in identities

    assert all(
        item["document_id"]
        in {
            "doc_a",
            "doc_b",
        }
        for item in results
    )

    assert not any(
        item["document_id"]
        == "doc_c"
        for item in results
    )
