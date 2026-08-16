import pytest
from src.vector_store.qdrant_manager import QdrantVectorStore
from src.pipeline import M3RetrievalPipeline
from src.utils.mock_data import (
    generate_mock_legal_chunks,
    prepare_qdrant_points,
    generate_mock_processed_query
)
from src.evaluation.metrics import RetrievalEvaluator


@pytest.fixture
def setup_vector_store():
    """
    Fixture initializing in-memory QdrantVectorStore seeded with mock legal chunks.
    """
    store = QdrantVectorStore(location=":memory:", collection_name="test_legal_docs")
    chunks = generate_mock_legal_chunks()
    points = prepare_qdrant_points(chunks)
    store.upsert_chunks(points)
    return store, chunks


def test_qdrant_ingestion_and_search(setup_vector_store):
    """
    Verify Qdrant point upsert and dense search capability.
    """
    store, _ = setup_vector_store
    mock_query = generate_mock_processed_query(query_id="q_test_1", seed=101)

    results = store.dense_search(query_vector=mock_query.embedding, top_k=5)
    assert len(results) > 0
    assert "text" in results[0]
    assert "document_id" in results[0]


def test_metadata_filtering(setup_vector_store):
    """
    Verify metadata filtering for document_type, jurisdiction, and language.
    """
    store, _ = setup_vector_store
    mock_query = generate_mock_processed_query(
        query_id="q_test_filter",
        doc_type="contract",
        jurisdiction="Egypt",
        lang="ar",
        seed=101
    )

    qfilter = store.build_qdrant_filter(
        document_type=mock_query.filters.document_type,
        jurisdiction=mock_query.filters.jurisdiction,
        language=mock_query.filters.language
    )

    results = store.dense_search(query_vector=mock_query.embedding, query_filter=qfilter, top_k=10)
    assert len(results) > 0
    for res in results:
        assert res["document_type"] == "contract"
        assert res["jurisdiction"] == "Egypt"
        assert res["language"] == "ar"


def test_m3_full_pipeline_end_to_end(setup_vector_store):
    """
    End-to-End test of M3 Pipeline: ProcessedQuery -> Hybrid Search -> Reranking -> RetrievedEvidence.
    """
    store, _ = setup_vector_store
    pipeline = M3RetrievalPipeline(
        vector_store=store,
        candidate_top_k=10,
        final_top_k=3,
        reranker_model_name="",
        use_mock_fallback=True
    )

    query = generate_mock_processed_query(
        query_id="q_001",
        query_text="ما هي شروط الفسخ؟",
        doc_type="contract",
        jurisdiction="Egypt",
        lang="ar",
        seed=101
    )

    evidence, latency_ms = pipeline.run(query)

    # 1. Validate Schema output for M4
    assert evidence.query_id == "q_001"
    assert len(evidence.retrieved_evidence) <= 3
    assert len(evidence.retrieved_evidence) > 0

    # 2. Check top chunk details
    top_item = evidence.retrieved_evidence[0]
    assert top_item.document_id != ""
    assert top_item.chunk_id != ""
    assert top_item.text != ""
    assert top_item.score > 0.0
    assert latency_ms > 0.0

    # 3. Evaluate Retrieval metrics
    retrieved_chunk_ids = [item.chunk_id for item in evidence.retrieved_evidence]
    ground_truth = {"chunk_017", "chunk_005"}  # Expected relevant chunks for "شروط الفسخ"
    eval_results = RetrievalEvaluator.evaluate_query(
        retrieved_chunk_ids=retrieved_chunk_ids,
        ground_truth_chunk_ids=ground_truth,
        latency_ms=latency_ms
    )

    assert "Recall@5" in eval_results
    assert "MRR" in eval_results
    assert "nDCG@5" in eval_results
    assert eval_results["latency_ms"] < 2000.0  # Latency under 2s target
