from collections.abc import Sequence

from FlagEmbedding import BGEM3FlagModel

from src.config import settings
from src.schemas import (
    DocumentChunk,
    EmbeddedDocumentChunk,
    EmbeddedQuery,
    ProcessedQuery,
)


class EmbeddingService:
    """BGE-M3 embedding service owned by M2.

    Responsibilities:
        - Load BGE-M3.
        - Embed legal document chunks received from M1.
        - Embed legal user queries.
        - Keep model and dimension information explicit.

    Non-responsibilities:
        - Qdrant indexing.
        - Retrieval.
        - Reranking.
        - RAG generation.
    """

    def __init__(
        self,
        model_name: str = settings.embedding_model,
        use_fp16: bool = settings.use_fp16,
        batch_size: int = settings.batch_size,
        max_length: int = settings.max_length,
    ) -> None:
        """Load BGE-M3 and store inference configuration."""
        self.model_name = model_name
        self.batch_size = batch_size
        self.max_length = max_length

        self.model = BGEM3FlagModel(
            model_name,
            use_fp16=use_fp16,
        )

        self._dimension: int | None = None

    @property
    def dimension(self) -> int | None:
        """Return the detected embedding dimension, if available."""
        return self._dimension

    def _encode(self, texts: Sequence[str]) -> list[list[float]]:
        """Encode a non-empty sequence with BGE-M3."""
        if not texts:
            raise ValueError("texts must not be empty")

        if any(not text or not text.strip() for text in texts):
            raise ValueError("texts must not contain empty strings")

        result = self.model.encode(
            list(texts),
            batch_size=self.batch_size,
            max_length=self.max_length,
        )

        vectors = result["dense_vecs"]

        output = [vector.tolist() for vector in vectors]

        if output:
            self._dimension = len(output[0])

        return output

    def embed_text(self, text: str) -> list[float]:
        """Embed one legal text."""
        return self._encode([text])[0]

    def embed_documents(
        self,
        texts: Sequence[str],
    ) -> list[list[float]]:
        """Embed multiple legal texts using batching."""
        return self._encode(texts)

    def embed_query(
        self,
        query: str | ProcessedQuery,
    ) -> list[float]:
        """Embed a raw query or an already processed query."""
        text = (
            query.normalized_text
            if isinstance(query, ProcessedQuery)
            else query
        )

        return self.embed_text(text)

    def embed_processed_query(
        self,
        query: ProcessedQuery,
    ) -> EmbeddedQuery:
        """Produce the complete M2 query handoff object."""
        vector = self.embed_query(query)

        return EmbeddedQuery(
            processed_query=query,
            embedding=vector,
            model=self.model_name,
            dimension=len(vector),
        )

    def embed_document_chunk(
        self,
        document_id: str,
        chunk_id: str,
        text: str,
    ) -> EmbeddedDocumentChunk:
        """Embed one document chunk received from M1."""
        vector = self.embed_text(text)

        return EmbeddedDocumentChunk(
            document_id=document_id,
            chunk_id=chunk_id,
            text=text,
            embedding=vector,
            model=self.model_name,
            dimension=len(vector),
        )

    def embed_document_chunks(
        self,
        chunks: Sequence[DocumentChunk],
    ) -> list[EmbeddedDocumentChunk]:
        """Embed document chunks received from M1.

        M1 provides DocumentChunk objects.
        M2 embeds their text using BGE-M3 while preserving
        all source information required by downstream consumers.
        """
        if not chunks:
            raise ValueError("chunks must not be empty")

        texts = [chunk.text for chunk in chunks]

        vectors = self._encode(texts)

        results: list[EmbeddedDocumentChunk] = []

        for chunk, vector in zip(chunks, vectors):
            results.append(
                EmbeddedDocumentChunk(
                    document_id=chunk.document_id,
                    chunk_id=chunk.chunk_id,
                    text=chunk.text,
                    page=chunk.page,
                    section=chunk.section,
                    clause=chunk.clause,
                    language=chunk.language,
                    document_type=chunk.document_type,
                    metadata=chunk.metadata,
                    embedding=vector,
                    model=self.model_name,
                    dimension=len(vector),
                )
            )

        return results
