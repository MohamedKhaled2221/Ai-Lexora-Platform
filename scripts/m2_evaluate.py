from pathlib import Path
import sys


PROJECT_ROOT = Path(
    __file__
).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(PROJECT_ROOT),
    )


import json
import math
from statistics import (
    mean,
    median,
)

from src.embedding_service import (
    EmbeddingService,
)
from src.evaluation.m2_evaluation import (
    M2EvaluationRunner,
    load_m2_evaluation_suite,
)
from src.query_processor import (
    QueryProcessor,
)


CASES_PATH = (
    PROJECT_ROOT
    / "evaluation"
    / "m2_cases.json"
)


CROSS_LANGUAGE_PAIRS = (
    (
        "termination",
        "إنهاء العقد",
    ),
    (
        "force majeure",
        "القوة القاهرة",
    ),
    (
        "arbitration",
        "التحكيم",
    ),
    (
        "confidentiality",
        "السرية",
    ),
)


def l2_norm(
    vector: list[float],
) -> float:
    return math.sqrt(
        sum(
            value * value
            for value in vector
        )
    )


def cosine_similarity(
    left: list[float],
    right: list[float],
) -> float:
    left_norm = l2_norm(
        left
    )

    right_norm = l2_norm(
        right
    )

    if (
        left_norm == 0.0
        or right_norm == 0.0
    ):
        raise ValueError(
            "cannot compare zero vectors"
        )

    return sum(
        a * b
        for a, b
        in zip(
            left,
            right,
        )
    ) / (
        left_norm
        * right_norm
    )


def main() -> None:
    suite = load_m2_evaluation_suite(
        CASES_PATH
    )

    processor = QueryProcessor()

    deterministic_runner = (
        M2EvaluationRunner(
            query_processor=processor
        )
    )

    deterministic_results = (
        deterministic_runner.run(
            suite
        )
    )

    failed = [
        result.case_id
        for result
        in deterministic_results
        if not result.passed
    ]

    if failed:
        raise SystemExit(
            "Deterministic M2 evaluation "
            f"failed: {failed}"
        )

    print(
        "Deterministic M2 cases:",
        f"{len(deterministic_results)}"
        f"/{len(deterministic_results)} passed",
    )

    print()
    print(
        "Loading local BGE-M3..."
    )

    embeddings = EmbeddingService()

    # Warm up CUDA/model execution before collecting
    # case-level latency.
    embeddings.embed_text(
        "M2 evaluation warmup"
    )

    latencies = []
    dimensions = []
    norms = []
    cuda_peaks = []

    print()
    print("Embedding evaluation:")

    for case in suite.cases:
        processed = processor.process(
            case.query
        )

        embedded = (
            embeddings
            .embed_processed_query(
                processed
            )
        )

        metrics = (
            embeddings.last_metrics
        )

        norm = l2_norm(
            embedded.embedding
        )

        dimensions.append(
            embedded.dimension
        )

        norms.append(
            norm
        )

        if metrics is not None:
            latencies.append(
                metrics.latency_ms
            )

            if (
                metrics
                .cuda_peak_allocated_mib
                is not None
            ):
                cuda_peaks.append(
                    metrics
                    .cuda_peak_allocated_mib
                )

        print(
            f"  {case.case_id}: "
            f"lang={processed.language}, "
            f"dim={embedded.dimension}, "
            f"norm={norm:.6f}, "
            f"latency_ms="
            f"{metrics.latency_ms:.2f}"
            if metrics is not None
            else (
                f"  {case.case_id}: "
                f"lang={processed.language}, "
                f"dim={embedded.dimension}, "
                f"norm={norm:.6f}"
            )
        )

    dimension_pass = all(
        dimension
        == embeddings.expected_dimension
        for dimension
        in dimensions
    )

    normalization_pass = all(
        abs(
            norm - 1.0
        ) <= 1e-5
        for norm in norms
    )

    print()
    print(
        "Cross-language embedding diagnostics:"
    )

    similarities = {}

    for (
        english,
        arabic,
    ) in CROSS_LANGUAGE_PAIRS:
        vectors = (
            embeddings.embed_documents(
                [
                    english,
                    arabic,
                ]
            )
        )

        similarity = cosine_similarity(
            vectors[0],
            vectors[1],
        )

        key = (
            f"{english} <-> {arabic}"
        )

        similarities[key] = (
            similarity
        )

        print(
            f"  {key}: "
            f"{similarity:.4f}"
        )

    summary = {
        "deterministic_cases": (
            len(
                deterministic_results
            )
        ),
        "deterministic_passed": (
            len(
                deterministic_results
            )
        ),
        "embedding_dimension_expected": (
            embeddings
            .expected_dimension
        ),
        "embedding_dimension_pass": (
            dimension_pass
        ),
        "normalization_pass": (
            normalization_pass
        ),
        "device": embeddings.device,
        "use_fp16": (
            embeddings.use_fp16
        ),
        "latency_ms": {
            "mean": (
                mean(latencies)
                if latencies
                else None
            ),
            "median": (
                median(latencies)
                if latencies
                else None
            ),
            "min": (
                min(latencies)
                if latencies
                else None
            ),
            "max": (
                max(latencies)
                if latencies
                else None
            ),
        },
        "max_cuda_peak_allocated_mib": (
            max(cuda_peaks)
            if cuda_peaks
            else None
        ),
        "cross_language_similarity": (
            similarities
        ),
    }

    print()
    print("Summary:")

    print(
        json.dumps(
            summary,
            indent=2,
            ensure_ascii=False,
        )
    )

    if not dimension_pass:
        raise SystemExit(
            "M2 embedding dimension "
            "evaluation failed."
        )

    if not normalization_pass:
        raise SystemExit(
            "M2 embedding normalization "
            "evaluation failed."
        )

    print()
    print(
        "M2 evaluation PASSED."
    )


if __name__ == "__main__":
    main()
