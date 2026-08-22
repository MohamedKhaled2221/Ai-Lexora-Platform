from pathlib import Path

from src.evaluation import (
    BenchmarkCase,
    RAGBenchmarkRunner,
    write_benchmark_csv,
)
from src.schemas import (
    AIResponse,
    Citation,
    EmbeddedQuery,
    EvidenceItem,
    ProcessedQuery,
    QueryFilters,
    RetrievedEvidence,
)


class FakeM2Pipeline:
    def process(
        self,
        raw_query: str,
    ) -> EmbeddedQuery:
        query = ProcessedQuery(
            query_id="q_benchmark",
            text_original=raw_query,
            normalized_text=(
                raw_query.lower()
            ),
            language="en",
            embedding=[],
            filters=QueryFilters(),
        )

        return EmbeddedQuery(
            processed_query=query,
            embedding=[
                0.1,
                0.2,
                0.3,
            ],
            model="fake-bge",
            dimension=3,
        )


class FakeRetrievalPipeline:
    def run(
        self,
        query,
    ):
        assert (
            query.filters
            .jurisdiction
            == "Egypt"
        )

        return (
            RetrievedEvidence(
                query_id=(
                    query.query_id
                ),
                retrieved_evidence=[
                    EvidenceItem(
                        document_id=(
                            "doc_001"
                        ),
                        chunk_id=(
                            "chunk_017"
                        ),
                        text=(
                            "Ground truth."
                        ),
                        page=12,
                        section=(
                            "Termination"
                        ),
                        language="en",
                        score=0.99,
                    ),
                    EvidenceItem(
                        document_id=(
                            "doc_002"
                        ),
                        chunk_id=(
                            "chunk_other"
                        ),
                        text=(
                            "Other evidence."
                        ),
                        page=2,
                        section="Other",
                        language="en",
                        score=0.5,
                    ),
                ],
            ),
            12.5,
        )


class FakeM4Service:
    def answer_search(
        self,
        processed_query,
        retrieved_evidence,
    ):
        return AIResponse(
            query_id=(
                processed_query.query_id
            ),
            answer=(
                "Grounded answer."
            ),
            citations=[
                Citation(
                    evidence_id="E1",
                    document_id="doc_001",
                    chunk_id="chunk_017",
                    page=12,
                    section="Termination",
                )
            ],
            confidence=0.9,
        )


def make_case():
    return BenchmarkCase(
        case_id="case_001",
        category="supported",
        language="en",
        question=(
            "CONFIDENTIAL TEST QUESTION"
        ),
        filters=QueryFilters(
            document_type="contract",
            jurisdiction="Egypt",
        ),
        ground_truth_chunk_ids=[
            "chunk_017"
        ],
        expect_supported=True,
    )


def test_runner_collects_retrieval_and_citation_metrics():
    runner = RAGBenchmarkRunner(
        query_pipeline=(
            FakeM2Pipeline()
        ),
        retrieval_pipeline=(
            FakeRetrievalPipeline()
        ),
        orchestration_service=(
            FakeM4Service()
        ),
        expected_embedding_dimension=3,
    )

    sample = runner.run_case(
        case=make_case(),
        repetition=1,
        sequence_index=1,
    )

    assert sample.status == "success"

    assert (
        sample.detected_language
        == "en"
    )

    assert (
        sample.retrieved_chunk_count
        == 2
    )

    assert (
        sample.citation_count
        == 1
    )

    assert (
        sample.recall_at_5
        == 1.0
    )

    assert sample.mrr == 1.0

    assert (
        sample.ndcg_at_5
        == 1.0
    )

    assert (
        sample.citation_precision
        == 1.0
    )

    assert (
        sample.citation_recall
        == 1.0
    )


def test_runner_preserves_case_filters():
    runner = RAGBenchmarkRunner(
        query_pipeline=(
            FakeM2Pipeline()
        ),
        retrieval_pipeline=(
            FakeRetrievalPipeline()
        ),
        orchestration_service=(
            FakeM4Service()
        ),
        expected_embedding_dimension=3,
    )

    sample = runner.run_case(
        case=make_case(),
        repetition=1,
        sequence_index=1,
    )

    assert sample.status == "success"


def test_csv_does_not_store_question_or_answer(
    tmp_path: Path,
):
    runner = RAGBenchmarkRunner(
        query_pipeline=(
            FakeM2Pipeline()
        ),
        retrieval_pipeline=(
            FakeRetrievalPipeline()
        ),
        orchestration_service=(
            FakeM4Service()
        ),
        expected_embedding_dimension=3,
    )

    sample = runner.run_case(
        case=make_case(),
        repetition=1,
        sequence_index=1,
    )

    path = (
        tmp_path
        / "benchmark.csv"
    )

    write_benchmark_csv(
        path=path,
        samples=[
            sample
        ],
    )

    text = path.read_text(
        encoding="utf-8"
    )

    assert (
        "CONFIDENTIAL TEST QUESTION"
        not in text
    )

    assert (
        "Grounded answer."
        not in text
    )


def test_unsupported_case_has_no_retrieval_ground_truth_metrics():
    case = make_case().model_copy(
        update={
            "ground_truth_chunk_ids": [],
            "expect_supported": False,
        }
    )

    runner = RAGBenchmarkRunner(
        query_pipeline=(
            FakeM2Pipeline()
        ),
        retrieval_pipeline=(
            FakeRetrievalPipeline()
        ),
        orchestration_service=(
            FakeM4Service()
        ),
        expected_embedding_dimension=3,
    )

    sample = runner.run_case(
        case=case,
        repetition=1,
        sequence_index=1,
    )

    assert sample.recall_at_5 is None
    assert sample.mrr is None
    assert sample.ndcg_at_5 is None

    # Fake M4 cited something, so it did not abstain.
    assert sample.abstained is False

    assert (
        sample.unsupported_pass
        is False
    )
    
def test_sequence_index_is_recorded():
    runner = RAGBenchmarkRunner(
        query_pipeline=(
            FakeM2Pipeline()
        ),
        retrieval_pipeline=(
            FakeRetrievalPipeline()
        ),
        orchestration_service=(
            FakeM4Service()
        ),
        expected_embedding_dimension=3,
    )

    sample = runner.run_case(
        case=make_case(),
        repetition=2,
        sequence_index=7,
    )

    assert sample.repetition == 2
    assert sample.sequence_index == 7
    
def test_optional_float_handles_unsupported_gpu_values():
    assert (
        RAGBenchmarkRunner
        ._optional_float("N/A")
        is None
    )

    assert (
        RAGBenchmarkRunner
        ._optional_float("[N/A]")
        is None
    )

    assert (
        RAGBenchmarkRunner
        ._optional_float("65")
        == 65.0
    )

    assert (
        RAGBenchmarkRunner
        ._optional_float("42.75")
        == 42.75
    )
