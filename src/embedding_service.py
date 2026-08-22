from collections.abc import Sequence

from FlagEmbedding import BGEM3FlagModel

from src.config import settings
from src.schemas import DocumentChunk, EmbeddedDocumentChunk, EmbeddedQuery, ProcessedQuery


class EmbeddingService:
    """BGE-M3 embedding service owned by M2.

    Responsibilities:
        - Load BGE-M3.
        - Embed legal document chunks.
        - Embed processed user queries.
        - Keep model/dimension information explicit.

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
        """Load BGE-M3 and store inference configuration.

        Input:
            model_name: Hugging Face model identifier.
            use_fp16: Use half precision when supported.
            batch_size: Batch size for document embedding.
            max_length: Maximum encoded token length.

        Output:
            None.

        Side effects:
            Loads the model into RAM/VRAM.

        Edge cases:
            Model download failures and insufficient memory are propagated.
        """
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
        """Encode a non-empty sequence with BGE-M3.

        Input:
            texts: Text strings.

        Output:
            Dense vectors as Python float lists.

        Side effects:
            Uses the loaded BGE-M3 model.

        Edge cases:
            Empty strings are rejected because they are invalid embedding
            inputs for this service.
        """
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
        """Embed one legal text.

        Input:
            text: Arabic, English, or mixed legal text.

        Output:
            One dense embedding vector.

        Side effects:
            Model inference.

        Edge cases:
            Empty text raises ValueError.
        """
        return self._encode([text])[0]

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed multiple legal chunks using batching.

        Input:
            Sequence of document chunk texts.

        Output:
            One vector per input text, preserving order.

        Side effects:
            Model inference.

        Important constraint:
            The caller must keep the original chunk IDs separately.
        """
        return self._encode(texts)

    def embed_query(self, query: str | ProcessedQuery) -> list[float]:
        """Embed a raw query or an already processed query.

        Input:
            query: Raw string or ProcessedQuery.

        Output:
            Dense query embedding.

        Side effects:
            Model inference.

        Edge cases:
            Empty raw strings are rejected.
        """
        text = query.normalized_text if isinstance(query, ProcessedQuery) else query
        return self.embed_text(text)

    def embed_processed_query(self, query: ProcessedQuery) -> EmbeddedQuery:
        """Produce the complete M2 query handoff object.

        Input:
            ProcessedQuery from QueryProcessor.

        Output:
            EmbeddedQuery containing processed query + embedding + model info.

        Side effects:
            Model inference.
        """
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
        """Produce an embedding result for one M1 document chunk.

        Input:
            document_id: Source document ID.
            chunk_id: Stable chunk ID.
            text: Chunk text.

        Output:
            EmbeddedDocumentChunk.

        Side effects:
            Model inference.

        Constraint:
            Page/section metadata remain owned by M1 and/or the storage layer.
        """
        vector = self.embed_text(text)

        return EmbeddedDocumentChunk(
            document_id=document_id,
            chunk_id=chunk_id,
            embedding=vector,
            model=self.model_name,
            dimension=len(vector),
        )

    def embed_document_chunks(
        self,
        chunks: Sequence[DocumentChunk],
    ) -> list[EmbeddedDocumentChunk]:
        """Embed multiple document chunks efficiently in batches.

        Input:
            chunks: Sequence of DocumentChunk instances.

        Output:
            list of EmbeddedDocumentChunk instances.
        """
        if not chunks:
            return []
            
        texts = [chunk.text for chunk in chunks]
        vectors = self.embed_documents(texts)
        
        return [
            EmbeddedDocumentChunk(
                document_id=chunk.document_id,
                chunk_id=chunk.chunk_id,
                embedding=vec,
                model=self.model_name,
                dimension=len(vec),
            )
            for chunk, vec in zip(chunks, vectors)
        ]
