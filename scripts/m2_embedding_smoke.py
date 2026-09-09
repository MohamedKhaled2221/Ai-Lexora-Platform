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
from dataclasses import asdict
import json
import math

from src.embedding_service import (
    EmbeddingService,
)
from src.query_pipeline import (
    M2QueryPipeline,
)


def vector_norm(
    vector,
):
    return math.sqrt(
        sum(
            value * value
            for value in vector
        )
    )


def main():
    print(
        "Loading configured BGE-M3 model..."
    )

    embedding_service = (
        EmbeddingService()
    )

    pipeline = M2QueryPipeline(
        embedding_service=(
            embedding_service
        )
    )

    print()
    print("Runtime metadata:")

    print(
        json.dumps(
            embedding_service
            .runtime_metadata,
            indent=2,
            ensure_ascii=False,
        )
    )

    queries = [
        (
            "What are the termination "
            "conditions under Article 69?"
        ),
        (
            "هل تنطبق القوة القاهرة "
            "في المادة ٦٩؟"
        ),
        (
            "Does arbitration apply "
            "في Case 123/2025?"
        ),
    ]

    for query in queries:
        print()
        print("=" * 80)
        print(
            f"Query: {query}"
        )

        result = pipeline.process(
            query
        )

        print(
            "Language:",
            result
            .processed_query
            .language,
        )

        print(
            "Model:",
            result.model,
        )

        print(
            "Dimension:",
            result.dimension,
        )

        print(
            "L2 norm:",
            round(
                vector_norm(
                    result.embedding
                ),
                6,
            ),
        )

        metrics = (
            embedding_service
            .last_metrics
        )

        if metrics is not None:
            print(
                "Metrics:",
                json.dumps(
                    asdict(
                        metrics
                    ),
                    indent=2,
                    ensure_ascii=False,
                ),
            )

    print()
    print("=" * 80)
    print(
        "Testing document-passage batch..."
    )

    document_vectors = (
        embedding_service
        .embed_documents(
            [
                (
                    "Either party may terminate "
                    "the agreement by written notice."
                ),
                (
                    "يجوز لأي طرف إنهاء العقد "
                    "بموجب إخطار كتابي."
                ),
            ]
        )
    )

    assert len(
        document_vectors
    ) == 2

    assert all(
        len(vector)
        == embedding_service
        .expected_dimension
        for vector
        in document_vectors
    )

    print(
        "Document batch dimension:",
        len(
            document_vectors[0]
        ),
    )

    print(
        "Final metrics:",
        json.dumps(
            asdict(
                embedding_service
                .last_metrics
            ),
            indent=2,
            ensure_ascii=False,
        ),
    )

    print()
    print(
        "M2 BGE-M3 smoke test PASSED."
    )


if __name__ == "__main__":
    main()
