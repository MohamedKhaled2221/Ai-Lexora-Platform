"""
Stage 5 coverage: neither read path can reach Qdrant unfiltered.

Both paths matter. Dense search is the obvious one; get_all_chunks is the one
that quietly scrolls the whole collection to build the BM25 corpus, so an
unfiltered scroll there would leak every tenant's text into the keyword index
even while dense search stayed correctly scoped.
"""

import inspect

import pytest
from qdrant_client.http.models import PointStruct

from src.retrieval.hybrid_search import HybridSearcher
from src.schemas import ProcessedQuery
from src.schemas.access_control import AccessScopeRequired
from src.vector_store.qdrant_manager import QdrantVectorStore
from tests.access_helpers import (
    OTHER_CLIENT_ID,
    access_scope,
    acl_payload,
    scoped_filters,
    shared_corpus_payload,
)


READ_METHODS = ("dense_search", "get_all_chunks")


def _store(name="acl_read_path_test"):
    return QdrantVectorStore(
        location=":memory:",
        collection_name=name,
        vector_size=3,
    )


def _populated_store():
    store = _store("acl_read_path_data")

    store.upsert_chunks([
        PointStruct(
            id=1,
            vector=[1.0, 0.0, 0.0],
            payload={
                "document_id": "doc_mine",
                "chunk_id": "chunk_001",
                "text": "termination for material breach",
                **acl_payload(confidentiality_level="internal"),
            },
        ),
        PointStruct(
            id=2,
            vector=[0.99, 0.01, 0.0],
            payload={
                "document_id": "doc_theirs",
                "chunk_id": "chunk_001",
                "text": "termination for material breach",
                **acl_payload(client_id=OTHER_CLIENT_ID),
            },
        ),
        PointStruct(
            id=3,
            vector=[0.98, 0.02, 0.0],
            payload={
                "document_id": "doc_privileged",
                "chunk_id": "chunk_002",
                "text": "termination for material breach",
                **acl_payload(confidentiality_level="privileged"),
            },
        ),
        PointStruct(
            id=4,
            vector=[0.97, 0.03, 0.0],
            payload={
                "document_id": "doc_statute",
                "chunk_id": "chunk_001",
                "text": "termination for material breach",
                **shared_corpus_payload(),
            },
        ),
    ])

    return store


# ---------------------------------------------------------------------------
# The signatures themselves
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method_name", READ_METHODS)
def test_query_filter_has_no_default(method_name):
    """
    The structural guarantee. If a default ever comes back, a future read
    path can silently omit the filter again.
    """

    parameter = inspect.signature(
        getattr(QdrantVectorStore, method_name)
    ).parameters["query_filter"]

    assert parameter.default is inspect.Parameter.empty
    assert "Optional" not in str(parameter.annotation)


@pytest.mark.parametrize("method_name", READ_METHODS)
def test_calling_without_a_filter_is_a_type_error(method_name):
    store = _store()
    method = getattr(store, method_name)

    with pytest.raises(TypeError):
        if method_name == "dense_search":
            method(query_vector=[1.0, 0.0, 0.0])
        else:
            method()


@pytest.mark.parametrize("method_name", READ_METHODS)
def test_explicit_none_filter_is_refused(method_name):
    """
    The signature stops the forgetful caller; this stops the one that built
    a filter conditionally and passed the None through.
    """

    store = _store()
    method = getattr(store, method_name)

    with pytest.raises(AccessScopeRequired):
        if method_name == "dense_search":
            method(query_vector=[1.0, 0.0, 0.0], query_filter=None)
        else:
            method(query_filter=None)


# ---------------------------------------------------------------------------
# What each path actually returns under a scope
# ---------------------------------------------------------------------------


def test_dense_search_returns_only_in_scope_documents():
    store = _populated_store()

    results = store.dense_search(
        query_vector=[1.0, 0.0, 0.0],
        query_filter=store.build_qdrant_filter(
            access=access_scope(max_confidentiality="internal")
        ),
    )

    returned = {item["document_id"] for item in results}

    assert returned == {"doc_mine", "doc_statute"}


def test_bm25_corpus_is_scoped_too():
    """The scroll path must not see another tenant's text."""

    store = _populated_store()

    chunks = store.get_all_chunks(
        query_filter=store.build_qdrant_filter(
            access=access_scope(max_confidentiality="internal")
        )
    )

    returned = {item["document_id"] for item in chunks}

    assert returned == {"doc_mine", "doc_statute"}
    assert "doc_theirs" not in returned


def test_raising_the_ceiling_reveals_privileged_content():
    store = _populated_store()

    chunks = store.get_all_chunks(
        query_filter=store.build_qdrant_filter(
            access=access_scope(max_confidentiality="privileged")
        )
    )

    assert "doc_privileged" in {
        item["document_id"] for item in chunks
    }


def test_excluding_shared_corpus_removes_statutes():
    store = _populated_store()

    chunks = store.get_all_chunks(
        query_filter=store.build_qdrant_filter(
            access=access_scope(include_shared_corpus=False)
        )
    )

    assert "doc_statute" not in {
        item["document_id"] for item in chunks
    }


def test_hybrid_search_end_to_end_excludes_other_tenants():
    store = _populated_store()
    searcher = HybridSearcher(vector_store=store)

    query = ProcessedQuery(
        query_id="q_001",
        text_original="termination for material breach",
        normalized_text="termination for material breach",
        language="en",
        embedding=[1.0, 0.0, 0.0],
        filters=scoped_filters(
            access=access_scope(max_confidentiality="internal")
        ),
    )

    results = searcher.search(query)

    assert results
    assert all(
        item["document_id"] in {"doc_mine", "doc_statute"}
        for item in results
    )
    # The ACL keys are not projected into result dicts yet; that arrives with
    # the post-retrieval assertion, and is covered there.
