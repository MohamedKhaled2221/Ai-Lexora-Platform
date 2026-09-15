from __future__ import annotations

import asyncio
from typing import BinaryIO, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from src.schemas import DocumentChunk
from src.schemas.access_control import ChunkACL

from .index_sync import IndexSyncError
from .knowledge_sync import KnowledgeSyncService
from .m1_client import M1Client
from .service import (
    DocumentIndexingError,
    DocumentIndexingService,
)


class DocumentIndexingRuntimeError(RuntimeError):
    """
    Raised when the local embedding or Qdrant runtime
    fails during document indexing.
    """


class DocumentIngestionResult(BaseModel):
    """
    Public Package 1 result for one successfully
    processed and indexed document.
    """

    model_config = ConfigDict(
        extra="forbid"
    )

    document_id: str = Field(
        ...,
        min_length=1,
    )

    source_file: str = Field(
        ...,
        min_length=1,
    )

    file_type: str = Field(
        ...,
        min_length=1,
    )

    document_type: str = Field(
        ...,
        min_length=1,
    )

    language: str = Field(
        ...,
        min_length=1,
    )

    pages: int = Field(
        ...,
        ge=0,
    )

    chunks_indexed: int = Field(
        ...,
        ge=1,
    )

    embedding_model: str = Field(
        ...,
        min_length=1,
    )

    embedding_dimension: int = Field(
        ...,
        ge=1,
    )

    status: Literal["indexed"] = "indexed"

    knowledge_record_id: str | None = None
    """Set when the document was stored as an M6 knowledge record and
    indexed through index sync; None when it was indexed directly."""


class DocumentIngestionService:
    """
    Complete Package 1 document-ingestion coordinator.

    Flow:
        uploaded file
            -> M1 document processing
            -> M2 embedding
            -> Qdrant indexing

    When ``knowledge_sync`` is configured, documents M6 can represent (laws,
    court rulings) take a different last step: M6 canonical record in
    PostgreSQL -> IndexUpdate -> index sync -> Qdrant. They are never also
    indexed directly, so no document is indexed twice.

    Search/RAG remains a separate M2 -> M3 -> M4 flow.
    """

    def __init__(
        self,
        *,
        m1_client: M1Client,
        indexing_service: DocumentIndexingService,
        knowledge_sync: KnowledgeSyncService | None = None,
    ) -> None:
        self.m1_client = m1_client
        self.indexing_service = indexing_service
        self.knowledge_sync = knowledge_sync

    @staticmethod
    def _stamp(
        chunks: list[DocumentChunk],
        acl: ChunkACL,
    ) -> list[DocumentChunk]:
        """
        Apply the caller's ACL to every chunk, overwriting what M1 sent.

        The overwrite is the point. M1 sees only the file, and the uploader
        can put anything in it, so neither is an authority on who may read
        the result. Whatever arrives in these fields is discarded in favour
        of the authenticated caller's own scope.
        """

        return [
            chunk.model_copy(
                update={
                    "client_id": acl.client_id,
                    "matter_id": acl.matter_id,
                    "confidentiality_level": (
                        acl.confidentiality_level
                    ),
                }
            )
            for chunk in chunks
        ]

    async def ingest_document(
        self,
        *,
        file_name: str,
        file_object: BinaryIO,
        acl: ChunkACL,
        content_type: str | None = None,
        document_id: str | None = None,
    ) -> DocumentIngestionResult:
        """
        Process and index one document under the caller's access control.

        ``acl`` is keyword-only and has no default, so a caller cannot ingest
        without deciding who owns the result.
        """

        if not isinstance(acl, ChunkACL):
            raise DocumentIndexingError(
                "ingest_document requires a ChunkACL built from the "
                "authenticated caller. Refusing to index a document with no "
                "verified owner."
            )

        m1_result = (
            await self.m1_client.ingest_document(
                file_name=file_name,
                file_object=file_object,
                content_type=content_type,
                document_id=document_id,
            )
        )

        stamped_chunks = self._stamp(
            m1_result.chunks,
            acl,
        )

        if (
            self.knowledge_sync is not None
            and stamped_chunks
            and self.knowledge_sync.supports(
                stamped_chunks[0].document_type
            )
        ):
            return await self._ingest_via_knowledge_sync(
                m1_result,
                stamped_chunks,
            )

        try:
            indexing_result = await asyncio.to_thread(
                self.indexing_service.index_document,
                stamped_chunks,
            )

        except DocumentIndexingError:
            raise

        except Exception as exc:
            raise DocumentIndexingRuntimeError(
                "The local document-indexing runtime "
                "failed."
            ) from exc

        if (
            indexing_result.document_id
            != m1_result.document_id
        ):
            raise DocumentIndexingError(
                "Document identity changed between "
                "processing and indexing."
            )

        return DocumentIngestionResult(
            document_id=m1_result.document_id,
            source_file=m1_result.source_file,
            file_type=m1_result.file_type,
            document_type=(
                m1_result.document_type
            ),
            language=m1_result.language,
            pages=m1_result.n_pages,
            chunks_indexed=(
                indexing_result.chunks_indexed
            ),
            embedding_model=(
                indexing_result.embedding_model
            ),
            embedding_dimension=(
                indexing_result.embedding_dimension
            ),
        )

    async def _ingest_via_knowledge_sync(
        self,
        m1_result,
        stamped_chunks: list[DocumentChunk],
    ) -> DocumentIngestionResult:
        try:
            sync_result = await asyncio.to_thread(
                self.knowledge_sync.sync_document,
                stamped_chunks,
                title=m1_result.source_file,
            )

        except IndexSyncError as exc:
            raise DocumentIndexingError(str(exc)) from exc

        except Exception as exc:
            raise DocumentIndexingRuntimeError(
                "The knowledge-base sync runtime failed."
            ) from exc

        if sync_result.outcome != "applied" or not sync_result.points_written:
            # A fresh upsert always bumps the version, so a skip here means
            # something other than this request already moved the record on.
            raise DocumentIndexingError(
                "Knowledge-base sync did not index this document "
                f"(outcome={sync_result.outcome})."
            )

        return DocumentIngestionResult(
            document_id=m1_result.document_id,
            source_file=m1_result.source_file,
            file_type=m1_result.file_type,
            document_type=m1_result.document_type,
            language=m1_result.language,
            pages=m1_result.n_pages,
            chunks_indexed=sync_result.points_written,
            embedding_model=sync_result.embedding_model,
            embedding_dimension=sync_result.embedding_dimension,
            knowledge_record_id=sync_result.record_id,
        )

    async def aclose(self) -> None:
        await self.m1_client.aclose()
