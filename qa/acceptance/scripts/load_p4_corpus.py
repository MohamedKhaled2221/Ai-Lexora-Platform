import json
from pathlib import Path

from qdrant_client import QdrantClient

from src.embedding_service import EmbeddingService
from src.indexing.index_sync import IndexSyncService
from src.indexing.knowledge_sync import KnowledgeSyncService
from src.indexing.service import DocumentIndexingService
from src.knowledge.governance import KnowledgeGovernanceService
from src.knowledge.repository import InMemoryKnowledgeRepository
from src.schemas.m1_contract import DocumentChunk
from src.schemas.m6_knowledge import IndexUpdate
from src.vector_store.qdrant_manager import QdrantVectorStore


COLLECTION = "legal_documents_acceptance_test"
QDRANT_URL = "http://127.0.0.1:6333"

CORPUS = Path(
    "qa/acceptance/data/p4_synthetic_corpus.jsonl"
)

LEGACY_DOCUMENT_ID = "qa-no-lifecycle"


def build_chunk(row: dict) -> DocumentChunk:
    return DocumentChunk(
        document_id=row["document_id"],
        chunk_id=row["chunk_id"],
        text=row["text"],
        page=1,
        language=row["language"],
        document_type="law",
        metadata={
            "jurisdiction": "EG",
            "qa_test_id": row["test_id"],
            "title": row["title"],
        },
        client_id=row["client_id"],
        matter_id=row["matter_id"],
        confidentiality_level=row[
            "confidentiality_level"
        ],
    )


def recreate_acceptance_collection() -> QdrantVectorStore:
    """
    This deletes ONLY the isolated QA collection.

    Production collection legal_documents is never touched.
    """
    client = QdrantClient(url=QDRANT_URL)

    existing = {
        collection.name
        for collection in client.get_collections().collections
    }

    if COLLECTION in existing:
        print(
            f"Deleting isolated QA collection: {COLLECTION}"
        )
        client.delete_collection(COLLECTION)

    store = QdrantVectorStore(
        location=QDRANT_URL,
        collection_name=COLLECTION,
        vector_size=1024,
    )

    if not store.sparse_enabled:
        raise RuntimeError(
            "QA collection was created without text_sparse."
        )

    return store


def apply_lifecycle(
    row: dict,
    record,
    governance: KnowledgeGovernanceService,
):
    status = row.get("validity_status")

    if status == "current":
        return governance.approve_current(
            record,
            reviewer="qa-acceptance",
            outcome="approved for acceptance testing",
        )

    if status == "review_required":
        return governance.mark_for_review(
            record,
            reason="QA lifecycle test",
        )

    if status == "superseded":
        return governance.mark_superseded(
            record,
            superseded_by_record_id=(
                KnowledgeSyncService.record_id_for(
                    "qa-current-notice"
                )
            ),
        )

    raise ValueError(
        f"Unsupported lifecycle status for "
        f"{row['document_id']}: {status!r}"
    )


def main() -> None:
    rows = [
        json.loads(line)
        for line in CORPUS.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]

    print("===== P4 ACCEPTANCE CORPUS LOAD =====")
    print("Records:", len(rows))
    print("Collection:", COLLECTION)

    if len(rows) != 15:
        raise RuntimeError(
            f"Expected 15 QA records, got {len(rows)}."
        )

    vector_store = recreate_acceptance_collection()

    print("Sparse enabled:", vector_store.sparse_enabled)

    print("\nLoading real local BGE-M3...")
    embedding_service = EmbeddingService(
        return_sparse=True,
        expected_dimension=1024,
    )

    index_sync = IndexSyncService(
        embedding_service=embedding_service,
        vector_store=vector_store,
    )

    repository = InMemoryKnowledgeRepository()

    knowledge_sync = KnowledgeSyncService(
        repository_factory=lambda: repository,
        index_sync=index_sync,
    )

    governance = KnowledgeGovernanceService()

    # Used ONLY for the deliberately unversioned legacy
    # control point.
    direct_indexer = DocumentIndexingService(
        embedding_service=embedding_service,
        vector_store=vector_store,
    )

    canonical_count = 0
    legacy_count = 0

    for row in rows:
        chunk = build_chunk(row)

        # -------------------------------------------------
        # Special negative-control record.
        #
        # This intentionally bypasses M6 so it has no
        # validity_status. P4 must exclude it.
        # -------------------------------------------------
        if row["document_id"] == LEGACY_DOCUMENT_ID:
            result = direct_indexer.index_document(
                [chunk]
            )

            legacy_count += result.chunks_indexed

            print(
                "LEGACY ",
                row["document_id"],
                "validity=<missing>",
            )
            continue

        # -------------------------------------------------
        # Canonical Package 4 path:
        # M1/M3 DocumentChunk -> M6 KnowledgeRecord
        # -> lifecycle governance -> repository
        # -> IndexUpdate -> M3 IndexSync -> Qdrant
        # -------------------------------------------------
        record = knowledge_sync.build_record(
            [chunk],
            title=row["title"],
        )

        record = apply_lifecycle(
            row,
            record,
            governance,
        )

        persisted = repository.upsert(record)

        update = IndexUpdate(
            record_id=persisted.record_id,
            operation="upsert",
            version=persisted.version,
            embedding_text=row["text"],
        )

        result = index_sync.apply(
            update,
            persisted,
        )

        canonical_count += result.points_written

        print(
            "CANONICAL",
            row["document_id"],
            f"validity={persisted.validity_status.value}",
            f"outcome={result.outcome}",
            f"points={result.points_written}",
        )

    info = vector_store.client.get_collection(
        COLLECTION
    )

    print("\n===== LOAD SUMMARY =====")
    print("Canonical points:", canonical_count)
    print("Legacy points:", legacy_count)
    print("Qdrant points:", info.points_count)
    print("Sparse enabled:", vector_store.sparse_enabled)

    if canonical_count != 14:
        raise RuntimeError(
            f"Expected 14 canonical points, "
            f"got {canonical_count}."
        )

    if legacy_count != 1:
        raise RuntimeError(
            f"Expected 1 legacy point, got {legacy_count}."
        )

    if info.points_count != 15:
        raise RuntimeError(
            f"Expected 15 Qdrant points, "
            f"got {info.points_count}."
        )

    print("PASS: acceptance corpus loaded")


if __name__ == "__main__":
    main()