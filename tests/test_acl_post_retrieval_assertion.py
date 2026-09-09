"""
Stage 6 coverage: the L3 post-retrieval assertion.

This layer exists to catch a failure of the layer below it. Its tests
therefore have to simulate a broken vector store -- if the filter works, the
assertion never fires, and a test that only exercises the happy path proves
nothing about it.
"""

import pytest

from src.pipeline import M3RetrievalPipeline
from src.schemas import ProcessedQuery, QueryFilters
from src.schemas.access_control import (
    SHARED_CLIENT_ID,
    AccessScopeRequired,
    AccessScopeViolation,
)
from tests.access_helpers import (
    OTHER_CLIENT_ID,
    TEST_CLIENT_ID,
    access_scope,
    scoped_filters,
)


class _LeakyVectorStore:
    """
    A vector store whose filter does not work.

    Stands in for the bug the assertion is defending against: a malformed
    condition, an unindexed field, a Qdrant version quirk -- anything that
    lets a filtered search return content it should not have.
    """

    vector_size = 3

    def __init__(self, payloads):
        self._payloads = payloads

    def build_qdrant_filter(self, **kwargs):
        return object()

    def dense_search(self, **kwargs):
        return list(self._payloads)

    def get_all_chunks(self, **kwargs):
        return list(self._payloads)


def _chunk(**overrides):
    values = {
        "point_id": 1,
        "document_id": "doc_001",
        "chunk_id": "chunk_001",
        "text": "termination for material breach",
        "page": 1,
        "section": "Termination",
        "language": "en",
        "client_id": TEST_CLIENT_ID,
        "matter_id": "_none",
        "confidentiality_level": "internal",
    }
    values.update(overrides)

    return values


def _pipeline(payloads):
    return M3RetrievalPipeline(
        vector_store=_LeakyVectorStore(payloads),
        reranker_model_name="",
        use_mock_fallback=True,
    )


def _query(filters=None):
    return ProcessedQuery(
        query_id="q_leak_001",
        text_original="termination",
        normalized_text="termination",
        language="en",
        embedding=[1.0, 0.0, 0.0],
        filters=filters if filters is not None else scoped_filters(),
    )


# ---------------------------------------------------------------------------
# Projection: the ACL has to survive as far as the check
# ---------------------------------------------------------------------------


def test_acl_keys_are_projected_out_of_the_vector_store():
    from qdrant_client.http.models import PointStruct

    from src.vector_store.qdrant_manager import QdrantVectorStore
    from tests.access_helpers import acl_payload

    store = QdrantVectorStore(
        location=":memory:",
        collection_name="acl_projection_test",
        vector_size=3,
    )
    store.upsert_chunks([
        PointStruct(
            id=1,
            vector=[1.0, 0.0, 0.0],
            payload={
                "document_id": "doc_001",
                "chunk_id": "chunk_001",
                "text": "termination",
                **acl_payload(matter_id="matter_7"),
            },
        )
    ])

    query_filter = store.build_qdrant_filter(access=access_scope())

    for result in (
        store.dense_search(
            query_vector=[1.0, 0.0, 0.0],
            query_filter=query_filter,
        )
        + store.get_all_chunks(query_filter=query_filter)
    ):
        assert result["client_id"] == TEST_CLIENT_ID
        assert result["matter_id"] == "matter_7"
        assert result["confidentiality_level"] == "internal"


def test_missing_acl_keys_project_as_none_not_as_permitted():
    from qdrant_client.http.models import PointStruct

    from src.vector_store.qdrant_manager import QdrantVectorStore

    store = QdrantVectorStore(
        location=":memory:",
        collection_name="acl_projection_missing",
        vector_size=3,
    )
    store.upsert_chunks([
        PointStruct(
            id=1,
            vector=[1.0, 0.0, 0.0],
            payload={
                "document_id": "doc_legacy",
                "chunk_id": "chunk_001",
                "text": "a v1 point with no ACL",
            },
        )
    ])

    results = store.get_all_chunks(
        query_filter=store.build_qdrant_filter(access=access_scope())
    )

    # Filtered out entirely, as a v1 point should be.
    assert results == []


# ---------------------------------------------------------------------------
# The assertion fires when the filter fails
# ---------------------------------------------------------------------------


def test_another_tenants_content_raises_rather_than_being_returned():
    pipeline = _pipeline([_chunk(client_id=OTHER_CLIENT_ID)])

    with pytest.raises(AccessScopeViolation):
        pipeline.run(_query())


def test_content_above_the_ceiling_raises():
    pipeline = _pipeline([_chunk(confidentiality_level="privileged")])

    with pytest.raises(AccessScopeViolation):
        pipeline.run(
            _query(
                scoped_filters(
                    access=access_scope(max_confidentiality="internal")
                )
            )
        )


def test_out_of_scope_matter_raises():
    pipeline = _pipeline([_chunk(matter_id="matter_other")])

    with pytest.raises(AccessScopeViolation):
        pipeline.run(
            _query(
                scoped_filters(
                    access=access_scope(matter_ids=["matter_mine"])
                )
            )
        )


def test_unstamped_content_raises_rather_than_being_treated_as_public():
    pipeline = _pipeline([
        _chunk(
            client_id=None,
            matter_id=None,
            confidentiality_level=None,
        )
    ])

    with pytest.raises(AccessScopeViolation):
        pipeline.run(_query())


def test_one_bad_candidate_fails_the_whole_result():
    """
    Not a filter-and-continue. A violation means the enforcement layer is
    broken, and serving the remaining candidates would hide that.
    """

    pipeline = _pipeline([
        _chunk(chunk_id="chunk_ok"),
        _chunk(chunk_id="chunk_leaked", client_id=OTHER_CLIENT_ID),
    ])

    with pytest.raises(AccessScopeViolation):
        pipeline.run(_query())


def test_violation_is_not_silently_dropped():
    """
    The failure mode this test guards against is the tempting one: quietly
    removing the offending item and returning the rest, which turns a
    security bug into an invisible one.
    """

    pipeline = _pipeline([_chunk(client_id=OTHER_CLIENT_ID)])

    try:
        evidence, _ = pipeline.run(_query())
    except AccessScopeViolation:
        return

    raise AssertionError(
        "Out-of-scope evidence was filtered out instead of raising: "
        f"{len(evidence.retrieved_evidence)} items returned"
    )


# ---------------------------------------------------------------------------
# The assertion stays quiet when everything is in scope
# ---------------------------------------------------------------------------


def test_in_scope_content_passes_through():
    pipeline = _pipeline([_chunk()])

    evidence, _ = pipeline.run(_query())

    assert len(evidence.retrieved_evidence) == 1
    assert evidence.retrieved_evidence[0].document_id == "doc_001"


def test_shared_corpus_content_passes_through():
    pipeline = _pipeline([
        _chunk(
            client_id=SHARED_CLIENT_ID,
            confidentiality_level="public",
        )
    ])

    evidence, _ = pipeline.run(_query())

    assert len(evidence.retrieved_evidence) == 1


def test_empty_results_are_fine():
    pipeline = _pipeline([])

    evidence, _ = pipeline.run(_query())

    assert evidence.retrieved_evidence == []


# ---------------------------------------------------------------------------
# The scope itself cannot go missing at this point
# ---------------------------------------------------------------------------


def test_candidates_with_no_scope_to_check_against_are_refused():
    """
    HybridSearcher refuses first, so this is unreachable today. It is pinned
    anyway: a future caller assembling candidates by another route must not
    be able to skip the check simply by omitting a scope.
    """

    pipeline = _pipeline([_chunk()])

    with pytest.raises(AccessScopeRequired):
        pipeline._assert_within_scope(
            access=None,
            candidates=[_chunk()],
            query_id="q_001",
        )


def test_hybrid_search_refuses_before_the_assertion_is_reached():
    pipeline = _pipeline([_chunk()])

    with pytest.raises(AccessScopeRequired):
        pipeline.run(_query(QueryFilters()))
