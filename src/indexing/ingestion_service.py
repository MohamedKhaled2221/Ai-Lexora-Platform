from __future__ import annotations

import asyncio
from typing import BinaryIO, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

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


class DocumentIngestionService:
    """
    Complete Package 1 document-ingestion coordinator.

    Flow:
        uploaded file
            -> M1 document processing
            -> M2 embedding
            -> Qdrant indexing

    Search/RAG remains a separate M2 -> M3 -> M4 flow.
    """

    def __init__(
        self,
        *,
        m1_client: M1Client,
        indexing_service: DocumentIndexingService,
    ) -> None:
        self.m1_client = m1_client
        self.indexing_service = indexing_service

    async def ingest_document(
        self,
        *,
        file_name: str,
        file_object: BinaryIO,
        content_type: str | None = None,
        document_id: str | None = None,
    ) -> DocumentIngestionResult:
        m1_result = (
            await self.m1_client.ingest_document(
                file_name=file_name,
                file_object=file_object,
                content_type=content_type,
                document_id=document_id,
            )
        )

        try:
            indexing_result = await asyncio.to_thread(
                self.indexing_service.index_document,
                m1_result.chunks,
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

    async def aclose(self) -> None:
        await self.m1_client.aclose()
