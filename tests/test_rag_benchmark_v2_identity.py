"""
End-to-end benchmark: v2 case schema, (document_id, chunk_id) identity, and
the server-side access scope a live run needs.
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from src.evaluation import BenchmarkCase, RAGBenchmarkRunner, load_benchmark_cases
from src.schemas import QueryFilters
from src.schemas.access_control import AccessScope
from tests.access_helpers import scoped_filters
from tests.test_rag_benchmark import FakeM2Pipeline, FakeM4Service, FakeRetrievalPipeline

REPO = Path(__file__).resolve().parents[1]


def _runner(**kwargs):
    return RAGBenchmarkRunner(
        query_pipeline=FakeM2Pipeline(),
        retrieval_pipeline=FakeRetrievalPipeline(),
        orchestration_service=FakeM4Service(),
        expected_embedding_dimension=3,
        **kwargs,
    )


def _v2_case(ground_truth):
    return BenchmarkCase.model_validate({
        "case_id": "v2_case",
        "category": "semantic",
        "language": "en",
        "query": "question text",
        "filters": {"jurisdiction": "Egypt"},
        "ground_truth": ground_truth,
        "confidence": "self_verified",
        "notes": "n",
        "multi_chunk": False,
    }).model_copy(update={"filters": scoped_filters(jurisdiction="Egypt")})


def test_pair_ground_truth_hits_only_the_right_document():
    # The fake retriever returns doc_001/chunk_017 at rank 1.
    sample = _runner().run_case(
        case=_v2_case([{"document_id": "doc_001", "chunk_id": "chunk_017"}]),
        repetition=1, sequence_index=1,
    )
    assert sample.status == "success"
    assert sample.mrr == 1.0
    assert sample.citation_precision == 1.0


def test_same_chunk_id_in_another_document_is_not_a_hit():
    """The ambiguity v1 had: bare 'chunk_017' matched every document's chunk_017."""
    sample = _runner().run_case(
        case=_v2_case([{"document_id": "doc_999", "chunk_id": "chunk_017"}]),
        repetition=1, sequence_index=1,
    )
    assert sample.status == "success"
    assert sample.mrr == 0.0
    assert sample.recall_at_5 == 0.0
    assert sample.citation_precision == 0.0


def test_legacy_chunk_id_only_cases_still_score():
    case = BenchmarkCase(
        case_id="v1", category="c", language="en", question="q",
        filters=scoped_filters(jurisdiction="Egypt"),
        ground_truth_chunk_ids=["chunk_017"],
    )
    assert _runner().run_case(case=case, repetition=1, sequence_index=1).mrr == 1.0


def test_empty_v2_ground_truth_marks_a_no_answer_case():
    assert _v2_case([]).expect_supported is False


def test_both_ground_truth_schemas_at_once_is_rejected():
    with pytest.raises(ValidationError):
        BenchmarkCase(
            case_id="x", category="c", language="en", question="q",
            ground_truth_chunk_ids=["chunk_1"],
            ground_truth=[{"document_id": "d", "chunk_id": "chunk_1"}],
        )


@pytest.mark.parametrize("name", ["benchmark_cases.json", "benchmark_cases_v2.json"])
def test_both_repository_case_files_load(name):
    cases = load_benchmark_cases(REPO / "evaluation" / name)
    assert cases


def test_v2_file_uses_pair_identity_for_every_answerable_case():
    cases = load_benchmark_cases(REPO / "evaluation" / "benchmark_cases_v2.json")
    answerable = [c for c in cases if c.expect_supported]
    assert answerable and all(c.matches_on_pair for c in answerable)
    assert all(not c.ground_truth for c in cases if not c.expect_supported)


def test_server_side_scope_is_applied_and_overrides_case_access():
    scope = AccessScope(client_id="firm_eval", max_confidentiality="public")
    seen = {}

    class RecordingRetrieval(FakeRetrievalPipeline):
        def run(self, query):
            seen["access"] = query.filters.access
            return super().run(query)

    runner = RAGBenchmarkRunner(
        query_pipeline=FakeM2Pipeline(),
        retrieval_pipeline=RecordingRetrieval(),
        orchestration_service=FakeM4Service(),
        expected_embedding_dimension=3,
        access_scope=scope,
    )
    case = _v2_case([{"document_id": "doc_001", "chunk_id": "chunk_017"}])
    assert case.filters.access is not None and case.filters.access != scope

    runner.run_case(case=case, repetition=1, sequence_index=1)

    assert seen["access"] == scope


def test_without_a_scope_a_case_with_no_access_fails_loudly_not_silently():
    case = _v2_case([{"document_id": "doc_001", "chunk_id": "chunk_017"}]).model_copy(
        update={"filters": QueryFilters(jurisdiction="Egypt")}
    )

    class ScopeCheckingRetrieval(FakeRetrievalPipeline):
        def run(self, query):
            if query.filters.access is None:
                from src.schemas.access_control import AccessScopeRequired
                raise AccessScopeRequired("no scope")
            return super().run(query)

    runner = RAGBenchmarkRunner(
        query_pipeline=FakeM2Pipeline(),
        retrieval_pipeline=ScopeCheckingRetrieval(),
        orchestration_service=FakeM4Service(),
        expected_embedding_dimension=3,
    )
    sample = runner.run_case(case=case, repetition=1, sequence_index=1)
    assert sample.status == "error" and sample.error_type == "AccessScopeRequired"
