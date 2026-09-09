from collections.abc import Sequence
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field
from qdrant_client.http.models import PointStruct

from src.embedding_service import EmbeddingService
from src.retrieval.identifiers import identifier_payload
from src.schemas import DocumentChunk, EmbeddedDocumentChunk
from src.vector_store.qdrant_manager import (
    DENSE_VECTOR_NAME,
    PAYLOAD_SCHEMA_VERSION,
    SPARSE_VECTOR_NAME,
    QdrantVectorStore,
    to_sparse_vector,
)


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
        - authenticating the caller.

    It does, however, refuse to index a chunk with no access-control stamp.
    Establishing *who* the caller is remains someone else's job; ensuring
    nothing reaches the vector store without an owner is this layer's, because
    this is the last point where it can still be checked.
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

        self._validate_access_control(chunks)

    @staticmethod
    def _validate_access_control(
        chunks: Sequence[DocumentChunk],
    ) -> None:
        """
        Refuse any chunk that was not stamped at the ingest boundary.

        An unstamped chunk is not readable -- a null client_id matches no
        allowed-client set -- so this is not the difference between private
        and public. It is the difference between a document that works and
        one that silently indexes and can never be retrieved by anyone. That
        is worth failing loudly at write time rather than discovering as a
        support ticket months later.
        """

        for chunk in chunks:
            missing = [
                name
                for name in (
                    "client_id",
                    "matter_id",
                    "confidentiality_level",
                )
                if not getattr(chunk, name, None)
            ]

            if missing:
                raise DocumentIndexingError(
                    "Refusing to index a chunk with no access-control "
                    f"stamp (missing: {', '.join(missing)}). The ACL is "
                    "applied at the ingest boundary from the authenticated "
                    "caller; a chunk arriving here without one means that "
                    "boundary was bypassed."
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
            # Access control, flat and top-level so each condition is a
            # single indexed keyword match. These are guaranteed non-null
            # by _validate_access_control, which runs before embedding.
            "client_id": chunk.client_id,
            "matter_id": chunk.matter_id,
            "confidentiality_level": (
                chunk.confidentiality_level
            ),
            "schema_version": PAYLOAD_SCHEMA_VERSION,
        }

        # Sparse lives in the point's *vector*, not its payload, so it cannot
        # collide with the access-control keys above -- they occupy different
        # halves of the point. Worth stating explicitly because both were
        # added to this same method within a few weeks of each other.

        # M3 currently expects jurisdiction as a
        # top-level Qdrant payload value for filtering.
        jurisdiction = chunk.metadata.get(
            "jurisdiction"
        )

        if jurisdiction is not None:
            payload["jurisdiction"] = str(
                jurisdiction
            )

        # Normalized legal identifiers, flat and top-level so each one is a
        # single indexed KEYWORD match. Written here rather than derived at
        # query time because an exact lookup has to hit an index -- deriving
        # them per query would mean scanning payload text, which is the thing
        # the identifier index exists to avoid.
        #
        # Keys are omitted entirely when the chunk carries no identifier,
        # which in this corpus is most chunks. An absent key matches nothing,
        # which is the correct reading: "no article number here", never
        # "matches any article".
        payload.update(
            identifier_payload(
                document_id=chunk.document_id,
                text=chunk.text,
                section=chunk.section,
                clause=chunk.clause,
            )
        )

        return PointStruct(
            id=self._point_id(
                document_id=chunk.document_id,
                chunk_id=chunk.chunk_id,
            ),
            vector=self._build_vector(chunk),
            payload=payload,
        )

    def _build_vector(
        self,
        chunk: EmbeddedDocumentChunk,
    ) -> Any:
        """
        Build the point's vector: dense always, sparse when both sides have it.

        Returns the bare dense list unless there is a sparse vector to attach,
        in which case it returns the named-vector mapping Qdrant needs. The
        dense vector keeps Qdrant's default (unnamed) slot either way, so a
        point written before sparse existed and one written after are both
        addressed identically by dense search.

        Two conditions have to hold before a sparse vector is written, and
        they fail for different reasons:

        * ``chunk.sparse_embedding`` is empty -- M2 was run with sparse
          disabled, or the model returned no lexical weights for this text.
        * the collection has no sparse vector configured -- it predates
          sparse support, and Qdrant rejects the upsert outright rather than
          ignoring the extra vector, which would fail the whole document.

        In both cases the chunk is indexed dense-only. It stays fully
        searchable by dense retrieval and is simply invisible to sparse
        retrieval, which is the same graceful degradation Qdrant applies to a
        mixed corpus where only some points carry sparse vectors.
        """

        sparse_vector = to_sparse_vector(
            chunk.sparse_embedding
        )

        if sparse_vector is None:
            return chunk.embedding

        if not getattr(
            self.vector_store,
            "sparse_enabled",
            False,
        ):
            return chunk.embedding

        return {
            DENSE_VECTOR_NAME: chunk.embedding,
            SPARSE_VECTOR_NAME: sparse_vector,
        }
