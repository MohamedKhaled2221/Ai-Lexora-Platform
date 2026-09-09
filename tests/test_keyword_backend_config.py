"""
Step 5 coverage: the backend switch is configuration, and runs are labelled.

The point of this step is that an A/B comparison needs neither a code edit nor
a trusted memory of which side was measured.
"""

import pytest
from qdrant_client.http import models as qmodels

from src.api.runtime import RAGRuntimeSettings
from src.pipeline import M3RetrievalPipeline
from src.utils.mock_data import (
    DEMO_CLIENT_ID,
    generate_mock_legal_chunks,
    generate_mock_processed_query,
    generate_mock_sparse_weights,
    prepare_qdrant_points,
)
from src.vector_store.qdrant_manager import (
    DENSE_VECTOR_NAME,
    SPARSE_VECTOR_NAME,
    QdrantVectorStore,
)


def _settings(**overrides):
    values = {
        "qdrant_location": ":memory:",
        "reranker_use_mock_fallback": True,
        "strict_offline": True,
        "reranker_local_files_only": True,
    }
    values.update(overrides)

    return RAGRuntimeSettings(_env_file=None, **values)


def _pipeline(**kwargs):
    store = QdrantVectorStore(
        location=":memory:",
        collection_name=kwargs.pop("collection", "kb_config_test"),
        vector_size=1024,
    )

    return M3RetrievalPipeline(
        vector_store=store,
        reranker_model_name="",
        use_mock_fallback=True,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def test_default_backend_is_sparse():
    assert _settings().keyword_backend == "sparse"


def test_backend_is_settable_from_the_environment(monkeypatch):
    """
    The whole point of step 5: an A/B run is an environment variable, not a
    code change.
    """

    monkeypatch.setenv("RAG_KEYWORD_BACKEND", "bm25")

    assert _settings().keyword_backend == "bm25"


def test_an_unknown_backend_is_rejected_at_startup(monkeypatch):
    """A typo must fail loudly, not silently select a default."""

    monkeypatch.setenv("RAG_KEYWORD_BACKEND", "bm52")

    with pytest.raises(Exception):
        _settings()


def test_pipeline_passes_the_backend_to_the_searcher():
    pipeline = _pipeline(keyword_backend="bm25")

    assert pipeline.keyword_backend == "bm25"
    assert pipeline.hybrid_searcher.keyword_backend == "bm25"


def test_pipeline_defaults_to_sparse():
    pipeline = _pipeline()

    assert pipeline.hybrid_searcher.keyword_backend == "sparse"


# ---------------------------------------------------------------------------
# Benchmark labelling
# ---------------------------------------------------------------------------


class _StubPipeline:
    def __init__(self, keyword_backend):
        self.keyword_backend = keyword_backend

    def run(self, query):
        raise AssertionError("not called")


def _runner(keyword_backend):
    from src.evaluation import RAGBenchmarkRunner

    return RAGBenchmarkRunner(
        query_pipeline=object(),
        retrieval_pipeline=_StubPipeline(keyword_backend),
        orchestration_service=object(),
    )


def test_runner_reports_the_backend_it_actually_measured():
    assert _runner("sparse").keyword_backend == "sparse"
    assert _runner("bm25").keyword_backend == "bm25"


def test_backend_is_read_from_the_pipeline_not_configured_separately():
    """
    A benchmark that could be told one backend while measuring another would
    produce confidently mislabelled A/B numbers -- worse than no label.
    """

    from src.evaluation import RAGBenchmarkRunner

    parameters = (
        RAGBenchmarkRunner.__init__.__code__.co_varnames
    )

    assert "keyword_backend" not in parameters


def test_unknown_backend_is_reported_rather_than_guessed():
    class _NoBackend:
        def run(self, query):
            raise AssertionError("not called")

    from src.evaluation import RAGBenchmarkRunner

    runner = RAGBenchmarkRunner(
        query_pipeline=object(),
        retrieval_pipeline=_NoBackend(),
        orchestration_service=object(),
    )

    assert runner.keyword_backend == "unknown"


def test_benchmark_sample_carries_the_backend_column():
    from dataclasses import fields

    from src.evaluation.benchmark import BenchmarkSample

    names = [field.name for field in fields(BenchmarkSample)]

    assert "keyword_backend" in names


def test_benchmark_csv_includes_the_backend_column(tmp_path):
    """
    Recorded per row: a CSV outlives whatever command produced it, and an A/B
    is only comparable if each row says which side it came from.
    """

    from dataclasses import fields

    from src.evaluation.benchmark import BenchmarkSample, write_benchmark_csv

    values = {}
    for field in fields(BenchmarkSample):
        if field.name == "keyword_backend":
            values[field.name] = "sparse"
        elif field.type == "str":
            values[field.name] = "x"
        elif field.type == "int":
            values[field.name] = 0
        elif field.type == "bool":
            values[field.name] = False
        else:
            values[field.name] = None

    path = tmp_path / "bench.csv"
    write_benchmark_csv(path=path, samples=[BenchmarkSample(**values)])

    header = path.read_text(encoding="utf-8").splitlines()[0]

    assert "keyword_backend" in header


# ---------------------------------------------------------------------------
# Mock sparse weights
# ---------------------------------------------------------------------------


def test_mock_weights_are_stable_for_the_same_text():
    """A term must map to the same id every time, or nothing ever matches."""

    assert generate_mock_sparse_weights(
        "termination clause"
    ) == generate_mock_sparse_weights("termination clause")


def test_query_and_document_share_ids_for_shared_words():
    """
    The property that makes the demo's sparse path meaningful rather than
    merely non-empty.
    """

    document = generate_mock_sparse_weights(
        "either party may terminate the agreement for breach"
    )
    query = generate_mock_sparse_weights("terminate agreement")

    assert set(document) & set(query)


def test_mock_weights_are_qdrant_shaped():
    weights = generate_mock_sparse_weights("termination clause")

    assert weights
    for token_id, weight in weights.items():
        assert int(token_id) >= 0
        assert 0.0 < float(weight) <= 1.0


def test_empty_text_produces_no_weights():
    assert generate_mock_sparse_weights("   ") == {}


def test_mock_points_carry_both_vectors():
    points = prepare_qdrant_points(
        generate_mock_legal_chunks(),
        vector_size=1024,
    )

    assert points
    for point in points:
        assert set(point.vector) == {
            DENSE_VECTOR_NAME,
            SPARSE_VECTOR_NAME,
        }
        assert point.vector[SPARSE_VECTOR_NAME].indices


def test_mock_query_carries_sparse_weights():
    query = generate_mock_processed_query()

    assert query.sparse_embedding


# ---------------------------------------------------------------------------
# Both backends run end to end on the demo corpus
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("backend", ["sparse", "bm25"])
def test_demo_corpus_retrieves_under_both_backends(backend):
    store = QdrantVectorStore(
        location=":memory:",
        collection_name=f"kb_demo_{backend}",
        vector_size=1024,
    )
    store.upsert_chunks(
        prepare_qdrant_points(
            generate_mock_legal_chunks(),
            vector_size=1024,
        )
    )

    pipeline = M3RetrievalPipeline(
        vector_store=store,
        candidate_top_k=10,
        final_top_k=3,
        reranker_model_name="",
        use_mock_fallback=True,
        keyword_backend=backend,
    )

    evidence, _ = pipeline.run(generate_mock_processed_query())

    assert evidence.retrieved_evidence


def test_sparse_backend_actually_contributes_candidates():
    """
    Guards against the demo passing merely because dense carried it: the
    sparse retriever must return something on its own.
    """

    store = QdrantVectorStore(
        location=":memory:",
        collection_name="kb_sparse_contrib",
        vector_size=1024,
    )
    store.upsert_chunks(
        prepare_qdrant_points(
            generate_mock_legal_chunks(),
            vector_size=1024,
        )
    )

    query = generate_mock_processed_query()

    from src.vector_store.qdrant_manager import to_sparse_vector

    results = store.sparse_search(
        query_sparse=to_sparse_vector(query.sparse_embedding),
        query_filter=store.build_qdrant_filter(
            access=query.filters.access
        ),
    )

    assert results
    assert all(
        item["client_id"] in {DEMO_CLIENT_ID, "_shared"}
        for item in results
    )
