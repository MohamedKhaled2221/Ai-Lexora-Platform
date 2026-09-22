"""
M3 consumer for M6 ``IndexUpdate`` events.

Keeps Qdrant in step with M6's canonical PostgreSQL records: when a
knowledge record is created, changed, or removed, M6 emits an ``IndexUpdate``
and this service applies it. Qdrant stays a derived index -- nothing here
decides what a record *is*; it only mirrors the record M6 hands over.

Guarantees
----------
* **Idempotent and order-safe.** Every point carries ``record_version``. An
  update whose version is not newer than what is indexed is skipped, so a
  replayed or out-of-order event cannot roll a record back.
* **Deterministic point ids**, derived from ``record_id`` + passage id. The
  same record re-synced overwrites the same points.
* **Replace, not append.** An upsert writes the new passages first and then
  deletes points the new version no longer has, so a passage removed in M6
  disappears from retrieval and a failed write never leaves the record empty.
* **Fail closed on access.** A record whose access metadata cannot be
  expressed as M3's (client_id, matter_id, confidentiality_level) triple is
  refused, never indexed as readable.

Status: no producer exists yet -- M6 does not emit ``IndexUpdate`` today.
This is the M3 half, ready for M6 to call.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional
from uuid import NAMESPACE_URL, uuid5

from qdrant_client.http.models import PointStruct

from src.embedding_service import EmbeddingService
from src.indexing.service import (
    DocumentIndexingError,
    DocumentIndexingService,
)
from src.schemas import DocumentChunk
from src.schemas.access_control import NO_MATTER_ID, SHARED_CLIENT_ID
from src.schemas.m6_knowledge import (
    AccessLevel,
    IndexUpdate,
    KnowledgeRecord,
    KnowledgeRecordType,
)
from src.vector_store.qdrant_manager import QdrantVectorStore


SUPPORTED_OPERATIONS = ("upsert", "delete")

_CONFIDENTIALITY_BY_ACCESS_LEVEL = {
    AccessLevel.PUBLIC: "public",
    AccessLevel.INTERNAL: "internal",
    # M3's ladder tops out at "privileged". Both of M6's upper rungs map to it:
    # collapsing two restrictions into the stricter one is safe, and the
    # reverse (dropping restricted to internal) would not be.
    AccessLevel.CONFIDENTIAL: "privileged",
    AccessLevel.RESTRICTED: "privileged",
}

_DOCUMENT_TYPE_BY_RECORD_TYPE = {
    KnowledgeRecordType.LAW: "law",
    KnowledgeRecordType.ARTICLE: "law",
    KnowledgeRecordType.CASE: "court_ruling",
}


class IndexSyncError(RuntimeError):
    """An IndexUpdate could not be applied safely. Nothing was written."""


@dataclass(frozen=True)
class IndexSyncResult:
    record_id: str
    operation: str
    outcome: Literal["applied", "skipped_stale"]
    points_written: int = 0
    points_deleted: int = 0
    indexed_version: Optional[int] = None
    embedding_model: Optional[str] = None
    embedding_dimension: Optional[int] = None


class IndexSyncService:
    def __init__(
        self,
        embedding_service: EmbeddingService,
        vector_store: QdrantVectorStore,
    ) -> None:
        self.vector_store = vector_store
        # Reused for embedding validation and payload construction, so a
        # synced record gets exactly the payload (identifiers, jurisdiction,
        # ACL keys) a document-pipeline chunk would.
        self._indexer = DocumentIndexingService(
            embedding_service=embedding_service,
            vector_store=vector_store,
        )
        self.embedding_service = embedding_service

    def apply(
        self,
        update: IndexUpdate,
        record: Optional[KnowledgeRecord] = None,
    ) -> IndexSyncResult:
        operation = update.operation.strip().lower()

        if operation not in SUPPORTED_OPERATIONS:
            raise IndexSyncError(
                f"Unsupported IndexUpdate operation {update.operation!r}; "
                f"expected one of {SUPPORTED_OPERATIONS}."
            )

        indexed_version = self.vector_store.get_record_version(
            update.record_id
        )

        if operation == "delete":
            return self._delete(update, indexed_version)

        return self._upsert(update, record, indexed_version)

    # ------------------------------------------------------------------ delete

    def _delete(
        self,
        update: IndexUpdate,
        indexed_version: Optional[int],
    ) -> IndexSyncResult:
        if indexed_version is not None and indexed_version > update.version:
            # A newer version was indexed after this delete was emitted.
            return IndexSyncResult(
                record_id=update.record_id,
                operation="delete",
                outcome="skipped_stale",
                indexed_version=indexed_version,
            )

        existing = self.vector_store.list_record_point_ids(update.record_id)
        self.vector_store.delete_record_points(update.record_id)

        return IndexSyncResult(
            record_id=update.record_id,
            operation="delete",
            outcome="applied",
            points_deleted=len(existing),
            indexed_version=indexed_version,
        )

    # ------------------------------------------------------------------ upsert

    def _upsert(
        self,
        update: IndexUpdate,
        record: Optional[KnowledgeRecord],
        indexed_version: Optional[int],
    ) -> IndexSyncResult:
        if record is None:
            # IndexUpdate alone carries no access metadata, so indexing from it
            # would have to guess who may read the result.
            raise IndexSyncError(
                "An upsert needs the KnowledgeRecord: IndexUpdate carries no "
                "access or validity metadata."
            )

        if record.record_id != update.record_id:
            raise IndexSyncError(
                "KnowledgeRecord.record_id does not match IndexUpdate.record_id."
            )

        if record.version != update.version:
            raise IndexSyncError(
                f"KnowledgeRecord version {record.version} does not match "
                f"IndexUpdate version {update.version}."
            )

        if indexed_version is not None and indexed_version >= update.version:
            return IndexSyncResult(
                record_id=update.record_id,
                operation="upsert",
                outcome="skipped_stale",
                indexed_version=indexed_version,
            )

        chunks = self._chunks_for(record, update)

        try:
            # Same validation the document pipeline applies, including the
            # refusal to index an unstamped chunk.
            self._indexer._validate_source_chunks(chunks)
            embedded = self.embedding_service.embed_document_chunks(chunks)
            self._indexer._validate_embedded_chunks(
                source_chunks=chunks,
                embedded_chunks=embedded,
            )
        except DocumentIndexingError as exc:
            raise IndexSyncError(str(exc)) from exc

        lifecycle = self._lifecycle_payload(record)
        points = []
        for chunk in embedded:
            base = self._indexer._to_qdrant_point(chunk)
            points.append(
                PointStruct(
                    id=self.point_id(record.record_id, chunk.chunk_id),
                    vector=base.vector,
                    payload={**base.payload, **lifecycle},
                )
            )

        previous_ids = set(
            self.vector_store.list_record_point_ids(record.record_id)
        )
        new_ids = {str(point.id) for point in points}

        self.vector_store.upsert_chunks(points)

        obsolete = sorted(previous_ids - new_ids)
        if obsolete:
            self.vector_store.delete_point_ids(obsolete)

        return IndexSyncResult(
            record_id=record.record_id,
            operation="upsert",
            outcome="applied",
            points_written=len(points),
            points_deleted=len(obsolete),
            indexed_version=indexed_version,
            embedding_model=embedded[0].model,
            embedding_dimension=embedded[0].dimension,
        )

    @staticmethod
    def point_id(record_id: str, chunk_id: str) -> str:
        # Separate key space from DocumentIndexingService._point_id
        # ("ai-lexora:{document_id}:{chunk_id}"), so a record can never
        # overwrite a document-pipeline point or vice versa.
        return str(uuid5(NAMESPACE_URL, f"ai-lexora:record:{record_id}:{chunk_id}"))

    def _chunks_for(
        self,
        record: KnowledgeRecord,
        update: IndexUpdate,
    ) -> list[DocumentChunk]:
        acl = self.chunk_acl(record)
        data = record.normalized_data or {}
        document_id = str(data.get("source_document_id") or record.record_id)
        language = data.get("language")
        if language not in ("ar", "en", "ar-en"):
            language = "unknown"
        metadata = {
            "record_type": record.record_type.value,
            "title": record.canonical_name,
        }
        if data.get("jurisdiction"):
            metadata["jurisdiction"] = data["jurisdiction"]

        common = dict(
            document_id=document_id,
            language=language,
            document_type=_DOCUMENT_TYPE_BY_RECORD_TYPE.get(
                record.record_type, "unknown"
            ),
            metadata=metadata,
            **acl,
        )

        # SourcePassage has no section/clause fields. M6 ingestion keeps them
        # in normalized_data["passage_metadata"], keyed by passage_id; they
        # matter here because identifier extraction reads the article heading.
        structure = {
            str(item.get("passage_id")): item
            for item in data.get("passage_metadata") or []
            if isinstance(item, dict) and item.get("passage_id")
        }

        chunks: list[DocumentChunk] = []
        for index, passage in enumerate(record.source_passages, start=1):
            if passage.page is None:
                # DocumentChunk requires a page and M4 cites it. Inventing one
                # would put a false page number into a legal citation.
                raise IndexSyncError(
                    f"Record {record.record_id} passage {index} has no page; "
                    "refusing to index it with a fabricated citation page."
                )
            chunk_id = passage.chunk_id or f"passage_{index:03d}"
            extra = structure.get(chunk_id, {})
            chunks.append(
                DocumentChunk(
                    chunk_id=chunk_id,
                    text=passage.passage,
                    page=passage.page,
                    section=extra.get("section"),
                    clause=extra.get("clause"),
                    **common,
                )
            )

        if not chunks:
            raise IndexSyncError(
                f"Record {record.record_id} has no source passages to index."
            )

        return chunks

    @staticmethod
    def chunk_acl(record: KnowledgeRecord) -> dict:
        """
        Translate M6 AccessMetadata into M3's ACL triple, or refuse.
        """
        access = record.access

        if access.allowed_roles:
            # M3 filters by tenant, matter and confidentiality only. Indexing a
            # role-restricted record would silently drop that restriction.
            raise IndexSyncError(
                f"Record {record.record_id} is restricted to roles "
                f"{access.allowed_roles}; M3 cannot enforce role restrictions "
                "at retrieval, so it is not indexed."
            )

        confidentiality = _CONFIDENTIALITY_BY_ACCESS_LEVEL[access.access_level]

        client_id = access.client_id
        if not client_id:
            if access.access_level != AccessLevel.PUBLIC:
                raise IndexSyncError(
                    f"Record {record.record_id} is {access.access_level.value} "
                    "but has no client_id, so there is no tenant to scope it "
                    "to. Only public records may join the shared corpus."
                )
            client_id = SHARED_CLIENT_ID

        return {
            "client_id": client_id,
            "matter_id": access.matter_id or NO_MATTER_ID,
            "confidentiality_level": confidentiality,
        }

    @staticmethod
    def _lifecycle_payload(record: KnowledgeRecord) -> dict:
        return {
            "record_id": record.record_id,
            "record_version": record.version,
            "record_type": record.record_type.value,
            "validity_status": record.validity_status.value,
            "effective_from": (
                record.effective_from.isoformat() if record.effective_from else None
            ),
            "effective_to": (
                record.effective_to.isoformat() if record.effective_to else None
            ),
            "supersedes_record_id": record.supersedes_record_id,
            "superseded_by_record_id": record.superseded_by_record_id,
        }
