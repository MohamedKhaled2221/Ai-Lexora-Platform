import argparse
from datetime import (
    datetime,
    timezone,
)
from pathlib import Path

from dotenv import load_dotenv

from src.evaluation import (
    RAGBenchmarkRunner,
    load_benchmark_cases,
    write_benchmark_csv,
)


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Run the local AI-Lexora "
            "M2 -> M3 -> M4 benchmark."
        )
    )

    parser.add_argument(
        "--cases",
        type=Path,
        default=Path(
            "evaluation/"
            "benchmark_cases.json"
        ),
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(
            "evaluation/results"
        ),
    )

    parser.add_argument(
        "--repetitions",
        type=int,
        default=3,
    )

    parser.add_argument(
        "--warmup",
        type=int,
        default=1,
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.repetitions < 1:
        raise ValueError(
            "repetitions must be >= 1"
        )

    if args.warmup < 0:
        raise ValueError(
            "warmup must be >= 0"
        )

    load_dotenv(
        ".env",
        override=False,
    )

    # Import after .env has populated the real
    # process environment for strict-offline
    # validation.
    from src.api.runtime import (
        RAGRuntimeSettings,
        build_rag_service,
    )
    from src.query_pipeline import (
        M2QueryPipeline,
    )

    cases = load_benchmark_cases(
        args.cases
    )

    if not cases:
        raise RuntimeError(
            "No benchmark cases found."
        )

    print(
        f"Loaded {len(cases)} "
        "benchmark cases."
    )

    runtime_settings = (
        RAGRuntimeSettings()
    )

    print(
        "Initializing M3/M4 runtime..."
    )

    rag_service = (
        build_rag_service(
            runtime_settings
        )
    )

    print(
        "Initializing M2/BGE-M3 runtime..."
    )

    query_pipeline = (
        M2QueryPipeline()
    )

    runner = RAGBenchmarkRunner(
        query_pipeline=(
            query_pipeline
        ),
        retrieval_pipeline=(
            rag_service
            .retrieval_pipeline
        ),
        orchestration_service=(
            rag_service
            .orchestration_service
        ),
        expected_embedding_dimension=(
            runtime_settings
            .qdrant_vector_size
        ),
    )

    if args.warmup > 0:
        print(
            f"Running {args.warmup} "
            "warm-up request(s)..."
        )

        warmup_case = cases[0]

        for index in range(
            1,
            args.warmup + 1,
        ):
            sample = runner.run_case(
                case=warmup_case,
                repetition=-index,
            )

            if (
                sample.status
                != "success"
            ):
                raise RuntimeError(
                    "Warm-up request failed "
                    f"with {sample.error_type}."
                )

    samples = []

    for repetition in range(
        1,
        args.repetitions + 1,
    ):
        print(
            "\n"
            f"Repetition "
            f"{repetition}/"
            f"{args.repetitions}"
        )

        for case in cases:
            sample = runner.run_case(
                case=case,
                repetition=repetition,
            )

            samples.append(
                sample
            )

            print(
                f"{case.case_id}: "
                f"status={sample.status}, "
                f"M2={sample.m2_ms}ms, "
                f"M3={sample.retrieval_ms}ms, "
                f"M4={sample.generation_ms}ms, "
                f"E2E={sample.end_to_end_ms}ms, "
                f"citations="
                f"{sample.citation_count}"
            )

    timestamp = (
        datetime.now(
            timezone.utc
        )
        .strftime(
            "%Y%m%d-%H%M%S"
        )
    )

    output_path = (
        args.output_dir
        / (
            "rag-benchmark-"
            f"{timestamp}.csv"
        )
    )

    write_benchmark_csv(
        path=output_path,
        samples=samples,
    )

    successes = sum(
        sample.status
        == "success"
        for sample
        in samples
    )

    print()
    print(
        "Benchmark complete."
    )

    print(
        f"Successful samples: "
        f"{successes}/"
        f"{len(samples)}"
    )

    print(
        f"Results: {output_path}"
    )


if __name__ == "__main__":
    main()
