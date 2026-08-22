import csv
import os
import subprocess
import time
from dataclasses import (
    asdict,
    dataclass,
)
from datetime import (
    datetime,
    timezone,
)
from pathlib import Path
from typing import Protocol

import psutil
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from src.evaluation.metrics import (
    RetrievalEvaluator,
)
from src.schemas.m2_contract import (
    EmbeddedQuery,
    QueryFilters,
)
from src.schemas.m4_contract import (
    AIResponse,
    RetrievedEvidence,
)


class BenchmarkCase(BaseModel):
    """
    One reproducible RAG evaluation case.
    """

    model_config = ConfigDict(
        extra="forbid"
    )

    case_id: str
    category: str
    language: str

    question: str

    filters: QueryFilters = Field(
        default_factory=QueryFilters
    )

    ground_truth_chunk_ids: list[str] = (
        Field(
            default_factory=list
        )
    )

    expect_supported: bool = True


@dataclass(frozen=True)
class BenchmarkSample:
    """
    Privacy-conscious quantitative result.

    Raw question text, evidence text, prompts, and
    generated answers are intentionally not stored.
    """

    timestamp_utc: str

    case_id: str
    category: str

    declared_language: str
    detected_language: str

    repetition: int

    status: str
    error_type: str | None

    m2_ms: float | None
    retrieval_ms: float | None
    generation_ms: float | None
    end_to_end_ms: float | None

    retrieved_chunk_count: int
    citation_count: int
    confidence: float | None

    recall_at_5: float | None
    recall_at_10: float | None
    mrr: float | None
    ndcg_at_5: float | None

    citation_precision: float | None
    citation_recall: float | None

    expect_supported: bool
    abstained: bool | None
    unsupported_pass: bool | None

    answer_chars: int | None

    retrieved_chunk_ids: str
    cited_chunk_ids: str

    process_rss_mb: float | None
    system_ram_used_mb: float | None
    system_ram_available_mb: float | None
    gpu_memory_used_mib: float | None

    def to_row(
        self,
    ) -> dict[str, object]:
        return asdict(self)


class M2PipelineProtocol(Protocol):
    def process(
        self,
        raw_query: str,
    ) -> EmbeddedQuery:
        ...


class RetrievalPipelineProtocol(Protocol):
    def run(
        self,
        query,
    ) -> tuple[
        RetrievedEvidence,
        float,
    ]:
        ...


class M4ServiceProtocol(Protocol):
    def answer_search(
        self,
        processed_query,
        retrieved_evidence,
    ) -> AIResponse:
        ...


class RAGBenchmarkRunner:
    """
    Measure the real M2 -> M3 -> M4 components while
    keeping benchmark data separate from production
    observability logs.
    """

    def __init__(
        self,
        *,
        query_pipeline: M2PipelineProtocol,
        retrieval_pipeline: RetrievalPipelineProtocol,
        orchestration_service: M4ServiceProtocol,
        expected_embedding_dimension: int = 1024,
    ) -> None:
        self.query_pipeline = (
            query_pipeline
        )

        self.retrieval_pipeline = (
            retrieval_pipeline
        )

        self.orchestration_service = (
            orchestration_service
        )

        self.expected_embedding_dimension = (
            expected_embedding_dimension
        )

    def run_case(
        self,
        *,
        case: BenchmarkCase,
        repetition: int,
    ) -> BenchmarkSample:
        overall_start = (
            time.perf_counter()
        )

        m2_ms = None
        retrieval_ms = None
        generation_ms = None

        detected_language = "unknown"

        try:
            m2_start = (
                time.perf_counter()
            )

            embedded_query = (
                self.query_pipeline
                .process(
                    case.question
                )
            )

            m2_ms = self._elapsed_ms(
                m2_start
            )

            detected_language = (
                embedded_query
                .processed_query
                .language
            )

            self._validate_embedding(
                embedded_query
            )

            processed_query = (
                embedded_query
                .processed_query
                .model_copy(
                    update={
                        "embedding": list(
                            embedded_query
                            .embedding
                        ),
                        "filters": (
                            case.filters
                            .model_copy(
                                deep=True
                            )
                        ),
                    },
                    deep=True,
                )
            )

            (
                retrieved_evidence,
                retrieval_ms,
            ) = (
                self.retrieval_pipeline
                .run(
                    processed_query
                )
            )

            generation_start = (
                time.perf_counter()
            )

            response = (
                self.orchestration_service
                .answer_search(
                    processed_query,
                    retrieved_evidence,
                )
            )

            generation_ms = (
                self._elapsed_ms(
                    generation_start
                )
            )

            end_to_end_ms = (
                self._elapsed_ms(
                    overall_start
                )
            )

            retrieved_chunk_ids = [
                item.chunk_id
                for item
                in retrieved_evidence
                .retrieved_evidence
            ]

            cited_chunk_ids = [
                citation.chunk_id
                for citation
                in response.citations
            ]

            retrieval_metrics = (
                self._retrieval_metrics(
                    retrieved_chunk_ids=(
                        retrieved_chunk_ids
                    ),
                    ground_truth_chunk_ids=(
                        case
                        .ground_truth_chunk_ids
                    ),
                    latency_ms=(
                        retrieval_ms
                    ),
                )
            )

            (
                citation_precision,
                citation_recall,
            ) = self._citation_metrics(
                cited_chunk_ids=(
                    cited_chunk_ids
                ),
                ground_truth_chunk_ids=(
                    case
                    .ground_truth_chunk_ids
                ),
            )

            abstained = (
                len(response.citations)
                == 0
            )

            unsupported_pass = (
                abstained
                if not case.expect_supported
                else None
            )

            resources = (
                self._resource_snapshot()
            )

            return BenchmarkSample(
                timestamp_utc=(
                    self._timestamp()
                ),
                case_id=case.case_id,
                category=case.category,
                declared_language=(
                    case.language
                ),
                detected_language=(
                    detected_language
                ),
                repetition=repetition,
                status="success",
                error_type=None,
                m2_ms=round(
                    m2_ms,
                    2,
                ),
                retrieval_ms=round(
                    retrieval_ms,
                    2,
                ),
                generation_ms=round(
                    generation_ms,
                    2,
                ),
                end_to_end_ms=round(
                    end_to_end_ms,
                    2,
                ),
                retrieved_chunk_count=len(
                    retrieved_chunk_ids
                ),
                citation_count=len(
                    cited_chunk_ids
                ),
                confidence=(
                    response.confidence
                ),
                recall_at_5=(
                    retrieval_metrics.get(
                        "Recall@5"
                    )
                ),
                recall_at_10=(
                    retrieval_metrics.get(
                        "Recall@10"
                    )
                ),
                mrr=(
                    retrieval_metrics.get(
                        "MRR"
                    )
                ),
                ndcg_at_5=(
                    retrieval_metrics.get(
                        "nDCG@5"
                    )
                ),
                citation_precision=(
                    citation_precision
                ),
                citation_recall=(
                    citation_recall
                ),
                expect_supported=(
                    case.expect_supported
                ),
                abstained=abstained,
                unsupported_pass=(
                    unsupported_pass
                ),
                answer_chars=len(
                    response.answer
                ),
                retrieved_chunk_ids=(
                    "|".join(
                        retrieved_chunk_ids
                    )
                ),
                cited_chunk_ids=(
                    "|".join(
                        cited_chunk_ids
                    )
                ),
                process_rss_mb=(
                    resources[
                        "process_rss_mb"
                    ]
                ),
                system_ram_used_mb=(
                    resources[
                        "system_ram_used_mb"
                    ]
                ),
                system_ram_available_mb=(
                    resources[
                        "system_ram_available_mb"
                    ]
                ),
                gpu_memory_used_mib=(
                    resources[
                        "gpu_memory_used_mib"
                    ]
                ),
            )

        except Exception as exc:
            resources = (
                self._resource_snapshot()
            )

            return BenchmarkSample(
                timestamp_utc=(
                    self._timestamp()
                ),
                case_id=case.case_id,
                category=case.category,
                declared_language=(
                    case.language
                ),
                detected_language=(
                    detected_language
                ),
                repetition=repetition,
                status="error",
                error_type=(
                    type(exc).__name__
                ),
                m2_ms=m2_ms,
                retrieval_ms=(
                    retrieval_ms
                ),
                generation_ms=(
                    generation_ms
                ),
                end_to_end_ms=round(
                    self._elapsed_ms(
                        overall_start
                    ),
                    2,
                ),
                retrieved_chunk_count=0,
                citation_count=0,
                confidence=None,
                recall_at_5=None,
                recall_at_10=None,
                mrr=None,
                ndcg_at_5=None,
                citation_precision=None,
                citation_recall=None,
                expect_supported=(
                    case.expect_supported
                ),
                abstained=None,
                unsupported_pass=None,
                answer_chars=None,
                retrieved_chunk_ids="",
                cited_chunk_ids="",
                process_rss_mb=(
                    resources[
                        "process_rss_mb"
                    ]
                ),
                system_ram_used_mb=(
                    resources[
                        "system_ram_used_mb"
                    ]
                ),
                system_ram_available_mb=(
                    resources[
                        "system_ram_available_mb"
                    ]
                ),
                gpu_memory_used_mib=(
                    resources[
                        "gpu_memory_used_mib"
                    ]
                ),
            )

    def _validate_embedding(
        self,
        embedded_query: EmbeddedQuery,
    ) -> None:
        actual_dimension = len(
            embedded_query.embedding
        )

        if (
            actual_dimension
            != self.expected_embedding_dimension
        ):
            raise ValueError(
                "Unexpected embedding dimension."
            )

        if (
            embedded_query.dimension
            != actual_dimension
        ):
            raise ValueError(
                "Embedding dimension metadata "
                "does not match vector length."
            )

    @staticmethod
    def _retrieval_metrics(
        *,
        retrieved_chunk_ids: list[str],
        ground_truth_chunk_ids: list[str],
        latency_ms: float,
    ) -> dict[str, float]:
        if not ground_truth_chunk_ids:
            return {}

        return (
            RetrievalEvaluator
            .evaluate_query(
                retrieved_chunk_ids=(
                    retrieved_chunk_ids
                ),
                ground_truth_chunk_ids=set(
                    ground_truth_chunk_ids
                ),
                latency_ms=latency_ms,
            )
        )

    @staticmethod
    def _citation_metrics(
        *,
        cited_chunk_ids: list[str],
        ground_truth_chunk_ids: list[str],
    ) -> tuple[
        float | None,
        float | None,
    ]:
        if not ground_truth_chunk_ids:
            return (
                None,
                None,
            )

        ground_truth = set(
            ground_truth_chunk_ids
        )

        cited = set(
            cited_chunk_ids
        )

        hits = len(
            cited.intersection(
                ground_truth
            )
        )

        precision = (
            hits / len(cited)
            if cited
            else 0.0
        )

        recall = (
            hits / len(ground_truth)
        )

        return (
            precision,
            recall,
        )

    @staticmethod
    def _elapsed_ms(
        start: float,
    ) -> float:
        return (
            time.perf_counter()
            - start
        ) * 1000.0

    @staticmethod
    def _timestamp() -> str:
        return (
            datetime.now(
                timezone.utc
            )
            .isoformat(
                timespec="seconds"
            )
        )

    @staticmethod
    def _resource_snapshot(
    ) -> dict[
        str,
        float | None,
    ]:
        process = psutil.Process(
            os.getpid()
        )

        rss_mb = (
            process
            .memory_info()
            .rss
            / (1024 * 1024)
        )

        virtual_memory = (
            psutil.virtual_memory()
        )

        used_mb = (
            virtual_memory.used
            / (1024 * 1024)
        )

        available_mb = (
            virtual_memory.available
            / (1024 * 1024)
        )

        return {
            "process_rss_mb": round(
                rss_mb,
                2,
            ),
            "system_ram_used_mb": round(
                used_mb,
                2,
            ),
            "system_ram_available_mb": round(
                available_mb,
                2,
            ),
            "gpu_memory_used_mib": (
                RAGBenchmarkRunner
                ._gpu_memory_used_mib()
            ),
        }

    @staticmethod
    def _gpu_memory_used_mib(
    ) -> float | None:
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    (
                        "--query-gpu="
                        "memory.used"
                    ),
                    (
                        "--format="
                        "csv,noheader,nounits"
                    ),
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=5,
            )

            first_line = (
                result.stdout
                .strip()
                .splitlines()[0]
            )

            return float(
                first_line.strip()
            )

        except (
            FileNotFoundError,
            subprocess.SubprocessError,
            ValueError,
            IndexError,
        ):
            return None


def load_benchmark_cases(
    path: Path,
) -> list[BenchmarkCase]:
    import json

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        payload = json.load(
            file
        )

    return [
        BenchmarkCase.model_validate(
            item
        )
        for item
        in payload["cases"]
    ]


def write_benchmark_csv(
    *,
    path: Path,
    samples: list[BenchmarkSample],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not samples:
        raise ValueError(
            "samples must not be empty"
        )

    fieldnames = list(
        samples[0]
        .to_row()
        .keys()
    )

    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
        )

        writer.writeheader()

        for sample in samples:
            writer.writerow(
                sample.to_row()
            )
