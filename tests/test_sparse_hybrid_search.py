"""
Step 4 coverage: native sparse retrieval, and its access enforcement.

The first section is the one that matters. sparse_search is a *new read
path*, and the ACL work established that a read path which can reach Qdrant
without a filter is the whole failure mode. These tests assert the sparse path
carries the identical obligations to dense_search -- structurally (signature),
behaviourally (refuses None), and end to end (another tenant's document never
comes back).
"""

import inspect

import pytest
from qdrant_client.http import models as qmodels

from src.retrieval.hybrid_search import (
    DEFAULT_DENSE_WEIGHT,
    DEFAULT_KEYWORD_WEIGHT,
    HybridSearcher,
)
from src.schemas import ProcessedQuery
from src.schemas.access_control import AccessScopeRequired
from src.vector_store.qdrant_manager import (
    DENSE_VECTOR_NAME,
    SPARSE_VECTOR_NAME,
    QdrantVectorStore,
    to_sparse_vector,
)
from tests.access_helpers import (
    OTHER_CLIENT_ID,
    TEST_CLIENT_ID,
    access_scope,
    scoped_filters,
)


READ_PATHS = ("dense_search", "sparse_search", "get_all_chunks")


def _store(name="sparse_hybrid_test"):
    return QdrantVectorStore(
        location=":memory:",
        collection_name=name,
        vector_size=4,
    )


def _point(point_id, document_id, client_id, sparse_indices, dense):
    return qmodels.PointStruct(
        id=point_id,
        vector={
            DENSE_VECTOR_NAME: dense,
            SPARSE_VECTOR_NAME: qmodels.SparseVector(
                indices=sparse_indices,
                values=[1.0] * len(sparse_indices),
            ),
        },
        payload={
            "document_id": document_id,
            "chunk_id": "chunk_001",
            "text": "termination for material breach",
            "page": 1,
            "section": "Termination",
            "language": "en",
            "client_id": client_id,
            "matter_id": "_none",
            "confidentiality_level": "internal",
        },
    )


def _populated(name="sparse_hybrid_data"):
    store = _store(name)
    store.upsert_chunks([
        _point(1, "doc_mine", TEST_CLIENT_ID, [1045, 7890], [1.0, 0.0, 0.0, 0.0]),
        _point(2, "doc_theirs", OTHER_CLIENT_ID, [1045, 7890], [0.99, 0.01, 0.0, 0.0]),
        _point(3, "doc_shared", "_shared", [1045], [0.98, 0.02, 0.0, 0.0]),
    ])
    return store


def _query(sparse=True, **filter_overrides):
    return ProcessedQuery(
        query_id="q_sparse_001",
        text_original="termination for material breach",
        normalized_text="termination for material breach",
        language="en",
        embedding=[1.0, 0.0, 0.0, 0.0],
        sparse_embedding=({"1045": 0.9} if sparse else None),
        filters=scoped_filters(**filter_overrides),
    )


# ===========================================================================
# ACCESS ENFORCEMENT -- the new read path carries the same obligations
# ===========================================================================


def test_sparse_search_requires_a_filter_like_every_other_read_path():
    parameter = inspect.signature(
        QdrantVectorStore.sparse_search
    ).parameters["query_filter"]

    assert parameter.default is inspect.Parameter.empty
    assert "Optional" not in str(parameter.annotation)


@pytest.mark.parametrize("method_name", READ_PATHS)
def test_every_read_path_still_demands_a_filter(method_name):
    """
    Parametrized over all three deliberately: this test should fail the day
    someone adds a fourth read path without one.
    """

    parameter = inspect.signature(
        getattr(QdrantVectorStore, method_name)
    ).parameters["query_filter"]

    assert parameter.default is inspect.Parameter.empty


def test_sparse_search_without_a_filter_is_a_type_error():
    store = _store()

    with pytest.raises(TypeError):
        store.sparse_search(
            query_sparse=qmodels.SparseVector(indices=[1], values=[1.0])
        )


def test_sparse_search_refuses_an_explicit_none_filter():
    store = _store()

    with pytest.raises(AccessScopeRequired):
        store.sparse_search(
            query_sparse=qmodels.SparseVector(indices=[1], values=[1.0]),
            query_filter=None,
        )


def test_sparse_search_excludes_another_tenant():
    """The end-to-end property, against real Qdrant."""

    store = _populated()

    results = store.sparse_search(
        query_sparse=qmodels.SparseVector(indices=[1045], values=[1.0]),
        query_filter=store.build_qdrant_filter(access=access_scope()),
    )

    returned = {item["document_id"] for item in results}

    assert returned == {"doc_mine", "doc_shared"}
    assert "doc_theirs" not in returned


def test_sparse_search_respects_the_confidentiality_ceiling():
    store = _store("sparse_ceiling")
    store.upsert_chunks([
        qmodels.PointStruct(
            id=1,
            vector={
                DENSE_VECTOR_NAME: [1.0, 0.0, 0.0, 0.0],
                SPARSE_VECTOR_NAME: qmodels.SparseVector(
                    indices=[1045], values=[1.0]
                ),
            },
            payload={
                "document_id": "doc_privileged",
                "chunk_id": "c1",
                "text": "t",
                "client_id": TEST_CLIENT_ID,
                "matter_id": "_none",
                "confidentiality_level": "privileged",
            },
        )
    ])

    query_sparse = qmodels.SparseVector(indices=[1045], values=[1.0])

    assert store.sparse_search(
        query_sparse=query_sparse,
        query_filter=store.build_qdrant_filter(
            access=access_scope(max_confidentiality="internal")
        ),
    ) == []

    assert store.sparse_search(
        query_sparse=query_sparse,
        query_filter=store.build_qdrant_filter(
            access=access_scope(max_confidentiality="privileged")
        ),
    )


def test_sparse_projects_the_acl_keys_for_the_post_retrieval_check():
    """
    The L3 assertion reads client_id/confidentiality_level off each candidate.
    A read path that omitted them would fail every query -- or, if the
    assertion were ever relaxed, would not.
    """

    store = _populated("sparse_projection")

    results = store.sparse_search(
        query_sparse=qmodels.SparseVector(indices=[1045], values=[1.0]),
        query_filter=store.build_qdrant_filter(access=access_scope()),
    )

    assert results
    for item in results:
        assert item["client_id"]
        assert item["confidentiality_level"]
        assert item["matter_id"]


def test_hybrid_search_refuses_an_unscoped_query_before_either_retriever():
    from src.schemas import QueryFilters

    searcher = HybridSearcher(vector_store=_populated("sparse_unscoped"))

    query = _query()
    query = query.model_copy(update={"filters": QueryFilters()})

    with pytest.raises(AccessScopeRequired):
        searcher.search(query)


def test_both_halves_share_one_filter_object():
    """
    Access conditions are assembled once per query. Rebuilding them for the
    keyword half would create a second place they could drift.
    """

    store = _populated("sparse_one_filter")
    seen = []

    original_build = store.build_qdrant_filter

    def recording_build(**kwargs):
        built = original_build(**kwargs)
        seen.append(built)
        return built

    store.build_qdrant_filter = recording_build

    dense_filters = []
    sparse_filters = []

    original_dense = store.dense_search
    original_sparse = store.sparse_search
    store.dense_search = lambda **kw: (
        dense_filters.append(kw["query_filter"]) or original_dense(**kw)
    )
    store.sparse_search = lambda **kw: (
        sparse_filters.append(kw["query_filter"]) or original_sparse(**kw)
    )

    HybridSearcher(vector_store=store).search(_query())

    assert len(seen) == 1
    assert dense_filters[0] is seen[0]
    assert sparse_filters[0] is seen[0]


def test_end_to_end_hybrid_returns_only_in_scope_documents():
    store = _populated("sparse_e2e")
    searcher = HybridSearcher(vector_store=store)

    results = searcher.search(_query())

    assert results
    assert all(
        item["document_id"] in {"doc_mine", "doc_shared"}
        for item in results
    )


# ===========================================================================
# RETRIEVAL BEHAVIOUR
# ===========================================================================


def test_sparse_is_the_default_keyword_backend():
    assert HybridSearcher(vector_store=_store()).keyword_backend == "sparse"


def test_sparse_backend_does_not_scroll_the_collection():
    """
    The point of the change: keyword retrieval no longer materializes the
    corpus in Python.
    """

    store = _populated("sparse_no_scroll")
    scrolls = []

    original = store.get_all_chunks
    store.get_all_chunks = lambda **kw: (
        scrolls.append(kw) or original(**kw)
    )

    HybridSearcher(vector_store=store).search(_query())

    assert scrolls == []


def test_bm25_backend_still_works_for_ab_comparison():
    store = _populated("sparse_bm25_ab")

    results = HybridSearcher(
        vector_store=store,
        keyword_backend="bm25",
    ).search(_query())

    assert results
    assert all(
        item["document_id"] in {"doc_mine", "doc_shared"}
        for item in results
    )


def test_bm25_backend_is_equally_access_scoped():
    """Switching backends is a relevance decision, never a security one."""

    store = _populated("sparse_bm25_acl")

    results = HybridSearcher(
        vector_store=store,
        keyword_backend="bm25",
    ).search(_query())

    assert all(
        item["document_id"] != "doc_theirs" for item in results
    )


def test_missing_query_sparse_vector_degrades_to_dense_only(caplog):
    import logging

    store = _populated("sparse_missing_query")
    searcher = HybridSearcher(vector_store=store)

    with caplog.at_level(
        logging.WARNING, logger="src.retrieval.hybrid_search"
    ):
        results = searcher.search(_query(sparse=False))

    assert results  # dense still works
    assert any(
        "dense-only" in record.message for record in caplog.records
    )


def test_sparse_search_on_a_collection_without_sparse_returns_nothing():
    """
    Relevance degradation, not an access failure: dense stays correct and
    scoped.
    """

    from qdrant_client import QdrantClient

    from src.vector_store import qdrant_manager

    client = QdrantClient(location=":memory:")
    client.create_collection(
        collection_name="legacy_sparse",
        vectors_config=qmodels.VectorParams(
            size=4, distance=qmodels.Distance.COSINE
        ),
    )

    original = qdrant_manager.QdrantClient
    qdrant_manager.QdrantClient = lambda **kwargs: client
    try:
        store = QdrantVectorStore(
            location=":memory:",
            collection_name="legacy_sparse",
            vector_size=4,
        )
    finally:
        qdrant_manager.QdrantClient = original

    assert store.sparse_enabled is False
    assert store.sparse_search(
        query_sparse=qmodels.SparseVector(indices=[1045], values=[1.0]),
        query_filter=store.build_qdrant_filter(access=access_scope()),
    ) == []


def test_empty_sparse_query_returns_no_keyword_candidates():
    store = _populated("sparse_empty_query")

    assert store.sparse_search(
        query_sparse=to_sparse_vector({}),
        query_filter=store.build_qdrant_filter(access=access_scope()),
    ) == []


# ===========================================================================
# FUSION
# ===========================================================================


def test_rrf_weights_are_carried_over_unchanged_pending_retuning():
    assert DEFAULT_DENSE_WEIGHT == 0.9
    assert DEFAULT_KEYWORD_WEIGHT == 0.1


def test_fusion_combines_both_rankings():
    searcher = HybridSearcher(vector_store=_store("sparse_fusion"))

    dense = [
        {"document_id": "d1", "chunk_id": "c1", "text": "a"},
        {"document_id": "d2", "chunk_id": "c1", "text": "b"},
    ]
    keyword = [
        {"document_id": "d3", "chunk_id": "c1", "text": "c"},
        {"document_id": "d1", "chunk_id": "c1", "text": "a"},
    ]

    fused = searcher._reciprocal_rank_fusion(
        dense_results=dense,
        keyword_results=keyword,
        top_k=10,
    )

    ids = [item["document_id"] for item in fused]

    assert set(ids) == {"d1", "d2", "d3"}
    # d1 appears in both rankings, so it must outrank the singletons.
    assert ids[0] == "d1"


def test_fusion_keeps_documents_distinct_by_document_and_chunk():
    """Chunk ids are only unique within a document."""

    searcher = HybridSearcher(vector_store=_store("sparse_fusion_keys"))

    fused = searcher._reciprocal_rank_fusion(
        dense_results=[{"document_id": "d1", "chunk_id": "c1", "text": "a"}],
        keyword_results=[{"document_id": "d2", "chunk_id": "c1", "text": "b"}],
        top_k=10,
    )

    assert len(fused) == 2
