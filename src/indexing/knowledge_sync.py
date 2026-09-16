"""
Document ingestion -> M6 canonical record -> IndexUpdate -> Qdrant.

Connects the M1 output that M3's ingestion path already receives to M6's
knowledge base, so PostgreSQL holds the canonical record and Qdrant is
filled only through :class:`IndexSyncService`. This replaces the unconnected
``KnowledgeIngestionAdapter`` route for uploaded documents, and avoids its
defects: record ids are derived from ``document_id`` (not random), and access
comes from the authenticated caller's ``ChunkACL`` (not dropped).

One record per document. That is also what M6's repository assumes: it
upserts on a unique ``source_document_id``.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from typing import Optional

from src.indexing.index_sync import IndexSyncError, IndexSyncResult, IndexSyncService
from src.knowledge.repository import KnowledgeRepository
from src.schemas import DocumentChunk
from src.schemas.m6_knowledge import (
    AccessLevel,
    AccessMetadata,
    IndexUpdate,
    KnowledgeRecord,
    KnowledgeRecordType,
    SourcePassage,
)


RECORD_TYPE_BY_DOCUMENT_TYPE = {
    "law": KnowledgeRecordType.LAW,
    "court_ruling": KnowledgeRecordType.CASE,
}
"""M1 document types M6 can represent. Contracts, pleadings, memos and the
like have no ``KnowledgeRecordType``; those keep the direct indexing path."""

_ACCESS_LEVEL_BY_CONFIDENTIALITY = {
    "public": AccessLevel.PUBLIC,
    "internal": AccessLevel.INTERNAL,
    # M3's top rung. RESTRICTED maps back to "privileged" in IndexSyncService,
    # so the round trip is lossless.
    "privileged": AccessLevel.RESTRICTED,
}


class KnowledgeSyncService:
    def __init__(
        self,
        *,
        repository_factory: Callable[[], KnowledgeRepository],
        index_sync: IndexSyncService,
    ) -> None:
        # A factory, not a repository: ingestion runs in worker threads and a
        # SQLAlchemy session must not be shared between them.
        self.repository_factory = repository_factory
        self.index_sync = index_sync

    @staticmethod
    def supports(document_type: str | None) -> bool:
        return document_type in RECORD_TYPE_BY_DOCUMENT_TYPE

    @staticmethod
    def record_id_for(document_id: str) -> str:
        return f"doc:{document_id}"

    def sync_document(
        self,
        chunks: Sequence[DocumentChunk],
        *,
        title: Optional[str] = None,
    ) -> IndexSyncResult:
        record = self.build_record(chunks, title=title)
        repository = self.repository_factory()

        try:
            # Commits the canonical record first. If indexing then fails, M6
            # holds a version Qdrant does not; re-ingesting bumps the version
            # and the sync applies it, so the state is recoverable.
            saved = repository.upsert(record)
        finally:
            session = getattr(repository, "session", None)
            if session is not None:
                session.close()

        return self.index_sync.apply(
            IndexUpdate(
                record_id=saved.record_id,
                operation="upsert",
                version=saved.version,
            ),
            saved,
        )

    def build_record(
        self,
        chunks: Sequence[DocumentChunk],
        *,
        title: Optional[str] = None,
    ) -> KnowledgeRecord:
        if not chunks:
            raise IndexSyncError("Cannot sync a document with no chunks.")

        first = chunks[0]
        if {c.document_id for c in chunks} != {first.document_id}:
            raise IndexSyncError("All chunks must belong to one document.")

        if not self.supports(first.document_type):
            raise IndexSyncError(
                f"Document type {first.document_type!r} has no M6 record type."
            )

        acl = {(c.client_id, c.matter_id, c.confidentiality_level) for c in chunks}
        if len(acl) != 1 or None in next(iter(acl)):
            raise IndexSyncError(
                "Every chunk must carry the same, complete access-control stamp."
            )
        client_id, matter_id, confidentiality = next(iter(acl))

        now = datetime.now(timezone.utc)
        return KnowledgeRecord(
            record_id=self.record_id_for(first.document_id),
            record_type=RECORD_TYPE_BY_DOCUMENT_TYPE[first.document_type],
            canonical_name=(title or first.document_id).strip() or first.document_id,
            normalized_data={
                "source_document_id": first.document_id,
                "language": first.language,
                "jurisdiction": first.metadata.get("jurisdiction"),
                "ingestion_path": "m3_document_ingestion",
                "passage_metadata": [
                    {
                        "passage_id": c.chunk_id,
                        "section": c.section,
                        "clause": c.clause,
                    }
                    for c in chunks
                ],
            },
            source_passages=[
                SourcePassage(
                    source_id=c.document_id,
                    passage=c.text,
                    page=c.page,
                    chunk_id=c.chunk_id,
                )
                for c in chunks
            ],
            access=AccessMetadata(
                access_level=_ACCESS_LEVEL_BY_CONFIDENTIALITY[confidentiality],
                client_id=client_id,
                matter_id=matter_id,
            ),
            created_at=now,
            updated_at=now,
        )


def postgres_repository_factory() -> Callable[[], KnowledgeRepository]:
    """
    Build a factory over M6's PostgreSQL repository and verify the database.

    Imported lazily: ``src.knowledge.database`` creates its engine at import
    time, and nothing should require PostgreSQL unless knowledge sync is on.
    Fails at startup, not at the first upload, when the database is
    unreachable.
    """
    from src.knowledge.database import SessionLocal, create_tables
    from src.knowledge.postgres_repository import PostgresKnowledgeRepository

    create_tables()

    def factory() -> KnowledgeRepository:
        return PostgresKnowledgeRepository(SessionLocal())

    return factory
