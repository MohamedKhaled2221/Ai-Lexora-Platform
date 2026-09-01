from collections.abc import Sequence
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field
from qdrant_client.http.models import PointStruct

from src.embedding_service import EmbeddingService
from src.schemas import DocumentChunk, EmbeddedDocumentChunk
from src.vector_store.qdrant_manager import QdrantVectorStore


class DocumentIndexingError(RuntimeError):
    """
    Raised when a document cannot safely be converted into
    Qdrant points.
    """


class DocumentIndexingResult(BaseModel):
    """
    Result returned after one document has been embedded
    and successfully written to Qdrant.
    """

    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(
        ...,
        min_length=1,
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


class DocumentIndexingService:
    """
    Application service connecting M1 document chunks,
    M2 embeddings, and the M3-owned Qdrant vector store.

    Responsibilities:
        - validate one-document indexing batches;
        - request embeddings from M2;
        - preserve trusted M1 metadata;
        - convert embedded chunks into Qdrant points;
        - validate embedding dimensions;
        - upsert the points through QdrantVectorStore.

    Non-responsibilities:
        - document extraction/OCR;
        - query processing;
        - retrieval/reranking;
        - LLM generation;
        - authentication/authorization.
    """

    def __init__(
        self,
        embedding_service: EmbeddingService,
        vector_store: QdrantVectorStore,
    ) -> None:
        self.embedding_service = embedding_service
        self.vector_store = vector_store

    def index_document(
        self,
        chunks: Sequence[DocumentChunk],
    ) -> DocumentIndexingResult:
        """
        Embed and index all chunks belonging to one document.
        """

        self._validate_source_chunks(chunks)

        document_id = chunks[0].document_id

        embedded_chunks = (
            self.embedding_service.embed_document_chunks(
                chunks
            )
        )

        self._validate_embedded_chunks(
            source_chunks=chunks,
            embedded_chunks=embedded_chunks,
        )

        points = [
            self._to_qdrant_point(chunk)
            for chunk in embedded_chunks
        ]

        self.vector_store.upsert_chunks(points)

        first = embedded_chunks[0]

        return DocumentIndexingResult(
            document_id=document_id,
            chunks_indexed=len(points),
            embedding_model=first.model,
            embedding_dimension=first.dimension,
        )

    def _validate_source_chunks(
        self,
        chunks: Sequence[DocumentChunk],
    ) -> None:
        if not chunks:
            raise DocumentIndexingError(
                "Cannot index an empty document chunk batch."
            )

        document_ids = {
            chunk.document_id
            for chunk in chunks
        }

        if len(document_ids) != 1:
            raise DocumentIndexingError(
                "A single indexing operation must contain "
                "chunks from exactly one document."
            )

        chunk_ids = [
            chunk.chunk_id
            for chunk in chunks
        ]

        if len(chunk_ids) != len(set(chunk_ids)):
            raise DocumentIndexingError(
                "Duplicate chunk_id values are not allowed "
                "within one document."
            )

    def _validate_embedded_chunks(
        self,
        source_chunks: Sequence[DocumentChunk],
        embedded_chunks: Sequence[
            EmbeddedDocumentChunk
        ],
    ) -> None:
        if len(embedded_chunks) != len(source_chunks):
            raise DocumentIndexingError(
                "M2 returned a different number of embedded "
                "chunks than it received."
            )

        expected_dimension = self.vector_store.vector_size

        for source, embedded in zip(
            source_chunks,
            embedded_chunks,
        ):
            if (
                embedded.document_id
                != source.document_id
            ):
                raise DocumentIndexingError(
                    "M2 changed document_id while embedding."
                )

            if embedded.chunk_id != source.chunk_id:
                raise DocumentIndexingError(
                    "M2 changed chunk_id while embedding."
                )

            if (
                embedded.dimension
                != len(embedded.embedding)
            ):
                raise DocumentIndexingError(
                    "Embedded chunk dimension does not match "
                    "the actual vector length."
                )

            if embedded.dimension != expected_dimension:
                raise DocumentIndexingError(
                    "Embedding dimension does not match the "
                    "configured Qdrant collection dimension."
                )

    @staticmethod
    def _point_id(
        document_id: str,
        chunk_id: str,
    ) -> str:
        """
        Produce a deterministic Qdrant-compatible UUID.

        Re-indexing the same document/chunk pair therefore
        updates the same Qdrant point rather than creating
        a duplicate.
        """

        stable_key = (
            f"ai-lexora:{document_id}:{chunk_id}"
        )

        return str(
            uuid5(
                NAMESPACE_URL,
                stable_key,
            )
        )

    def _to_qdrant_point(
        self,
        chunk: EmbeddedDocumentChunk,
    ) -> PointStruct:
        payload = {
            "document_id": chunk.document_id,
            "chunk_id": chunk.chunk_id,
            "text": chunk.text,
            "page": chunk.page,
            "section": chunk.section,
            "clause": chunk.clause,
            "language": chunk.language,
            "document_type": chunk.document_type,
            "metadata": chunk.metadata,
        }

        # M3 currently expects jurisdiction as a
        # top-level Qdrant payload value for filtering.
        jurisdiction = chunk.metadata.get(
            "jurisdiction"
        )

        if jurisdiction is not None:
            payload["jurisdiction"] = str(
                jurisdiction
            )

        return PointStruct(
            id=self._point_id(
                document_id=chunk.document_id,
                chunk_id=chunk.chunk_id,
            ),
            vector=chunk.embedding,
            payload=payload,
        )
