"""
Stage 4 coverage: build_qdrant_filter cannot produce an unfiltered result.

The property under test is structural, not behavioural: it is not "the filter
usually contains ACL conditions", it is "there is no argument combination that
yields a filter without them, and no way to get None back".
"""

import inspect

import pytest
from qdrant_client.http.models import Filter

from src.retrieval.hybrid_search import HybridSearcher
from src.schemas import ProcessedQuery
from src.schemas.access_control import (
    NO_MATTER_ID,
    SHARED_CLIENT_ID,
    AccessScope,
    AccessScopeRequired,
)
from src.vector_store.qdrant_manager import QdrantVectorStore
from tests.access_helpers import (
    TEST_CLIENT_ID,
    access_scope,
    scoped_filters,
)


def _store():
    return QdrantVectorStore(
        location=":memory:",
        collection_name="acl_filter_test",
        vector_size=3,
    )


def _conditions_by_key(qdrant_filter):
    return {
        condition.key: condition
        for condition in qdrant_filter.must
        if hasattr(condition, "key")
    }


# ---------------------------------------------------------------------------
# There is no unfiltered path
# ---------------------------------------------------------------------------


def test_filter_is_never_none_even_with_no_relevance_filters():
    """
    The old behaviour returned None here, which every read path accepted as
    "search everything".
    """

    result = _store().build_qdrant_filter(access=access_scope())

    assert isinstance(result, Filter)
    assert result.must


def test_access_is_a_required_positional_parameter():
    signature = inspect.signature(
        QdrantVectorStore.build_qdrant_filter
    )
    parameters = list(signature.parameters)

    assert parameters[1] == "access"
    assert (
        signature.parameters["access"].default
        is inspect.Parameter.empty
    )


def test_return_annotation_is_not_optional():
    signature = inspect.signature(
        QdrantVectorStore.build_qdrant_filter
    )

    assert "Optional" not in str(signature.return_annotation)


def test_none_access_is_refused():
    with pytest.raises(AccessScopeRequired):
        _store().build_qdrant_filter(access=None)


def test_unvalidated_access_shape_is_refused():
    """A dict must not be coerced into an authorization decision."""

    with pytest.raises(AccessScopeRequired):
        _store().build_qdrant_filter(
            access={
                "client_id": TEST_CLIENT_ID,
                "max_confidentiality": "privileged",
            }
        )


# ---------------------------------------------------------------------------
# What the access conditions actually say
# ---------------------------------------------------------------------------


def test_client_and_confidentiality_conditions_are_always_present():
    result = _store().build_qdrant_filter(access=access_scope())
    conditions = _conditions_by_key(result)

    assert set(conditions) >= {"client_id", "confidentiality_level"}

    assert conditions["client_id"].match.any == [
        TEST_CLIENT_ID,
        SHARED_CLIENT_ID,
    ]


def test_confidentiality_condition_expands_the_ladder():
    result = _store().build_qdrant_filter(
        access=access_scope(max_confidentiality="internal")
    )

    conditions = _conditions_by_key(result)

    assert conditions["confidentiality_level"].match.any == [
        "public",
        "internal",
    ]


def test_matter_condition_is_absent_when_unrestricted():
    result = _store().build_qdrant_filter(access=access_scope())

    assert "matter_id" not in _conditions_by_key(result)


def test_matter_condition_keeps_client_level_documents_visible():
    result = _store().build_qdrant_filter(
        access=access_scope(matter_ids=["matter_7"])
    )

    conditions = _conditions_by_key(result)

    assert conditions["matter_id"].match.any == [
        "matter_7",
        NO_MATTER_ID,
    ]


def test_excluding_shared_corpus_narrows_the_client_condition():
    result = _store().build_qdrant_filter(
        access=access_scope(include_shared_corpus=False)
    )

    conditions = _conditions_by_key(result)

    assert conditions["client_id"].match.any == [TEST_CLIENT_ID]


# ---------------------------------------------------------------------------
# Relevance filters can only narrow
# ---------------------------------------------------------------------------


def test_relevance_filters_are_added_alongside_access_conditions():
    result = _store().build_qdrant_filter(
        access=access_scope(),
        document_ids=["doc_a"],
        document_type="contract",
        jurisdiction="Egypt",
        language="en",
    )

    conditions = _conditions_by_key(result)

    assert set(conditions) == {
        "client_id",
        "confidentiality_level",
        "document_id",
        "document_type",
        "jurisdiction",
        "language",
    }


def test_extra_filters_cannot_carry_acl_fields():
    for field in (
        "client_id",
        "matter_id",
        "confidentiality_level",
    ):
        with pytest.raises(AccessScopeRequired):
            _store().build_qdrant_filter(
                access=access_scope(),
                extra_filters={field: "anything"},
            )


def test_ordinary_extra_filters_still_work():
    result = _store().build_qdrant_filter(
        access=access_scope(),
        extra_filters={"court": "cassation"},
    )

    assert "court" in _conditions_by_key(result)


# ---------------------------------------------------------------------------
# HybridSearcher refuses to search unscoped
# ---------------------------------------------------------------------------


def _query(filters):
    return ProcessedQuery(
        query_id="q_001",
        text_original="termination",
        normalized_text="termination",
        language="en",
        embedding=[1.0, 0.0, 0.0],
        filters=filters,
    )


def test_hybrid_search_refuses_a_query_with_no_access_scope():
    from src.schemas import QueryFilters

    searcher = HybridSearcher(vector_store=_store())

    with pytest.raises(AccessScopeRequired):
        searcher.search(_query(QueryFilters()))


def test_hybrid_search_accepts_a_scoped_query():
    searcher = HybridSearcher(vector_store=_store())

    assert searcher.search(_query(scoped_filters())) == []


def test_missing_scope_is_refused_before_the_embedding_check_passes():
    """
    An unscoped query must not reach the vector store even once, regardless
    of what else is wrong with it.
    """

    searcher = HybridSearcher(vector_store=_store())

    query = _query(scoped_filters())
    query = query.model_copy(update={"embedding": []})

    with pytest.raises(ValueError):
        searcher.search(query)


def test_access_scope_on_query_filters_defaults_to_none():
    """
    Optional in the schema, mandatory at retrieval. If this ever defaults to
    a real scope, every unscoped caller silently starts working again.
    """

    from src.schemas import QueryFilters

    assert QueryFilters().access is None
