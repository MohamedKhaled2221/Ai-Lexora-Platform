"""
Stage 8 coverage: the last places a scope could have gone missing.

The service layer sits between the API (which always sets a scope) and
retrieval (which always demands one). It used to paper over the gap with a
bare QueryFilters(), which meant a direct caller -- a benchmark, a script, a
future internal service -- reached retrieval unscoped and failed several
layers deeper, after the embedding work had already been done.
"""

import pytest

from src.schemas import QueryFilters
from src.schemas.access_control import AccessScopeRequired
from tests.access_helpers import scoped_filters


class _StubQueryPipeline:
    """Fails loudly if reached: the guard must fire before embedding."""

    def process(self, question):
        raise AssertionError(
            "Embedding work started before the access scope was checked"
        )


class _StubRAGService:
    def answer_with_metrics(self, processed_query):
        raise AssertionError("Retrieval reached without a scope")

    async def aanswer_with_metrics(self, processed_query):
        raise AssertionError("Retrieval reached without a scope")


def _service():
    from src.orchestration.raw_rag_service import M2M3M4RAGService

    return M2M3M4RAGService(
        query_pipeline=_StubQueryPipeline(),
        rag_service=_StubRAGService(),
        expected_embedding_dimension=1024,
    )


def test_omitted_filters_are_refused():
    with pytest.raises(AccessScopeRequired):
        _service().answer(question="What are the termination terms?")


def test_filters_without_a_scope_are_refused():
    with pytest.raises(AccessScopeRequired):
        _service().answer(
            question="What are the termination terms?",
            filters=QueryFilters(document_type="contract"),
        )


def test_the_refusal_happens_before_any_embedding_work():
    """
    _StubQueryPipeline raises AssertionError if it is reached. Getting
    AccessScopeRequired instead proves the guard runs first.
    """

    with pytest.raises(AccessScopeRequired):
        _service().answer(question="anything")


@pytest.mark.asyncio
async def test_async_path_is_guarded_too():
    with pytest.raises(AccessScopeRequired):
        await _service().aanswer(question="anything")


def test_a_scoped_call_gets_past_the_guard():
    """
    Reaching the stub pipeline means the guard passed.

    The stub raises to announce it was reached, and the service translates
    any pipeline exception into M2QueryRuntimeError -- so that error, rather
    than AccessScopeRequired, is the success condition here.
    """

    from src.orchestration.raw_rag_service import M2QueryRuntimeError

    with pytest.raises(M2QueryRuntimeError):
        _service().answer(
            question="anything",
            filters=scoped_filters(),
        )


# ---------------------------------------------------------------------------
# Demo/mock data keeps working
# ---------------------------------------------------------------------------


def test_mock_query_carries_a_scope():
    """
    run_demo.py is the first thing anyone runs. Unscoped mock data would make
    it fail at retrieval, or -- worse if the ACL were absent from the points
    rather than the query -- silently return nothing.
    """

    from src.utils.mock_data import generate_mock_processed_query

    query = generate_mock_processed_query()

    assert query.filters.access is not None


def test_mock_points_are_stamped():
    from src.utils.mock_data import (
        DEMO_CLIENT_ID,
        generate_mock_legal_chunks,
        prepare_qdrant_points,
    )

    points = prepare_qdrant_points(
        generate_mock_legal_chunks(),
        vector_size=8,
    )

    assert points
    for point in points:
        assert point.payload["client_id"] == DEMO_CLIENT_ID
        assert point.payload["confidentiality_level"]
        assert point.payload["matter_id"]


def test_mock_data_is_retrievable_under_its_own_scope():
    """End-to-end: the demo corpus is visible to the demo query."""

    from src.utils.mock_data import (
        generate_mock_legal_chunks,
        generate_mock_processed_query,
        prepare_qdrant_points,
    )
    from src.vector_store.qdrant_manager import QdrantVectorStore

    store = QdrantVectorStore(
        location=":memory:",
        collection_name="mock_scope_test",
        vector_size=1024,
    )
    store.upsert_chunks(
        prepare_qdrant_points(
            generate_mock_legal_chunks(),
            vector_size=1024,
        )
    )

    query = generate_mock_processed_query()

    results = store.get_all_chunks(
        query_filter=store.build_qdrant_filter(
            access=query.filters.access
        )
    )

    assert results
