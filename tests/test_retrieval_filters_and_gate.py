"""
Retrieval-side switches that are OFF by default:

* validity_status filter (M6 lifecycle), with explicit handling of points
  indexed before any status existed;
* the minimum dense-score abstention gate;

plus the jurisdiction filter as a real discriminator, and the structured
retrieval log.
"""

import logging

import pytest
from qdrant_client.http.models import PointStruct

from src.pipeline import M3RetrievalPipeline
from src.retrieval.hybrid_search import MEASURED_MIN_DENSE_SCORE, HybridSearcher
from src.schemas import ProcessedQuery
from src.vector_store.qdrant_manager import QdrantVectorStore
from tests.access_helpers import access_scope, scoped_filters, shared_corpus_payload


def _point(pid, vector, document_id, **extra):
    return PointStruct(
        id=pid,
        vector=vector,
        payload={
            "document_id": document_id,
            "chunk_id": "chunk_001",
            "text": f"text of {document_id}",
            **shared_corpus_payload(),
            **extra,
        },
    )


@pytest.fixture
def store():
    s = QdrantVectorStore(location=":memory:", collection_name="filters_gate", vector_size=3)
    s.upsert_chunks([
        _point(1, [1.0, 0.0, 0.0], "doc_eg_current", jurisdiction="Egypt",
               validity_status="current"),
        _point(2, [0.99, 0.1, 0.0], "doc_eg_superseded", jurisdiction="Egypt",
               validity_status="superseded"),
        _point(3, [0.98, 0.2, 0.0], "doc_ksa", jurisdiction="KSA",
               validity_status="current"),
        _point(4, [0.97, 0.3, 0.0], "doc_legacy_no_status", jurisdiction="Egypt"),
    ])
    return s


def _docs(store, **filter_kwargs):
    hits = store.dense_search(
        [1.0, 0.0, 0.0],
        store.build_qdrant_filter(access=access_scope(), **filter_kwargs),
        top_k=10,
    )
    return {h["document_id"] for h in hits}


# ------------------------------------------------------------- jurisdiction


def test_jurisdiction_filter_actually_excludes_other_jurisdictions(store):
    assert _docs(store, jurisdiction="KSA") == {"doc_ksa"}
    assert "doc_ksa" not in _docs(store, jurisdiction="Egypt")
    assert _docs(store, jurisdiction="UAE") == set()


# ----------------------------------------------------------- validity status


def test_no_status_filter_is_the_default_and_returns_everything(store):
    assert len(_docs(store)) == 4


def test_status_filter_fails_closed_on_unversioned_points(store):
    assert _docs(store, validity_statuses=["current"]) == {"doc_eg_current", "doc_ksa"}


def test_status_filter_can_explicitly_include_unversioned_points(store):
    assert _docs(store, validity_statuses=["current"], include_unversioned_points=True) == {
        "doc_eg_current", "doc_ksa", "doc_legacy_no_status"
    }


def test_status_filter_never_widens_the_access_scope(store):
    store.upsert_chunks([
        PointStruct(id=5, vector=[1.0, 0.0, 0.0], payload={
            "document_id": "doc_other_tenant", "chunk_id": "chunk_001", "text": "x",
            "client_id": "someone_else", "matter_id": "_none",
            "confidentiality_level": "public", "validity_status": "current",
        })
    ])
    assert "doc_other_tenant" not in _docs(
        store, validity_statuses=["current"], include_unversioned_points=True
    )


def test_empty_status_allow_list_is_rejected(store):
    with pytest.raises(ValueError):
        store.build_qdrant_filter(access=access_scope(), validity_statuses=[])


# ------------------------------------------------------- dense-score gate


def _query(vector):
    return ProcessedQuery(
        query_id="q1",
        text_original="question",
        normalized_text="question",
        embedding=vector,
        filters=scoped_filters(),
    )


def test_gate_is_off_by_default(store):
    assert HybridSearcher(store).min_dense_score is None
    assert HybridSearcher(store).search(_query([0.0, 0.0, 1.0]))


def test_gate_abstains_when_top_dense_score_is_below_threshold(store):
    searcher = HybridSearcher(store, min_dense_score=0.5)
    # Orthogonal to every stored vector: cosine 0.
    assert searcher.search(_query([0.0, 0.0, 1.0])) == []


def test_gate_passes_a_well_matched_query(store):
    searcher = HybridSearcher(store, min_dense_score=0.5)
    assert searcher.search(_query([1.0, 0.0, 0.0]))


def test_gate_rejects_out_of_range_threshold(store):
    with pytest.raises(ValueError):
        HybridSearcher(store, min_dense_score=1.5)


def test_measured_threshold_blocks_no_measured_answerable_case():
    # Lowest top-1 dense score among the 50 answerable benchmark cases was
    # 0.521; the documented value must stay below it (no false abstentions).
    assert MEASURED_MIN_DENSE_SCORE < 0.521


# ------------------------------------------------------------ retrieval log


def test_pipeline_logs_config_and_selected_evidence_without_text(store, caplog):
    pipeline = M3RetrievalPipeline(
        vector_store=store,
        reranker_model_name="",
        use_mock_fallback=True,
        min_dense_score=0.2,
        allowed_validity_statuses=["current"],
    )

    with caplog.at_level(logging.INFO, logger="src.pipeline"):
        evidence, _ = pipeline.run(_query([1.0, 0.0, 0.0]))

    record = next(r for r in caplog.records if r.getMessage() == "m3_retrieval_completed")
    assert record.query_id == "q1"
    assert record.retrieval_config["min_dense_score"] == 0.2
    assert record.retrieval_config["allowed_validity_statuses"] == ["current"]
    assert record.retrieval_config["dense_weight"] == 0.9
    logged_ids = {(e["document_id"], e["chunk_id"]) for e in record.evidence}
    assert logged_ids == {(e.document_id, e.chunk_id) for e in evidence.retrieved_evidence}
    assert all("text" not in e and "client_id" not in e for e in record.evidence)
