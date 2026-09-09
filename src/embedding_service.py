import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from FlagEmbedding import BGEM3FlagModel

from src.config import settings
from src.schemas import (
    DocumentChunk,
    EmbeddedDocumentChunk,
    EmbeddedQuery,
    ProcessedQuery,
)


logger = logging.getLogger(__name__)


SparseWeights = dict[str, float]
"""BGE-M3 lexical weights: token id (as a string) -> learned term weight."""


def normalize_lexical_weights(
    raw_weights: Mapping,
) -> SparseWeights:
    """
    Turn one BGE-M3 ``lexical_weights`` entry into a plain JSON-safe dict.

    FlagEmbedding returns a ``defaultdict`` keyed by token id -- sometimes as
    a string, sometimes as a numpy integer -- with numpy float weights. None
    of that survives a Pydantic round-trip or a JSON boundary intact, so it
    is normalized once, here, rather than at each consumer.

    Zero and negative weights are dropped. BGE-M3 emits a weight for every
    token it saw, and a zero-weight term contributes nothing to a sparse dot
    product while still costing index space in every stored vector.
    """

    normalized: SparseWeights = {}

    for token_id, weight in dict(raw_weights).items():
        value = float(weight)

        if value <= 0.0:
            continue

        normalized[str(int(token_id))] = value

    return normalized


@dataclass(frozen=True)
class EncodedTexts:
    """One BGE-M3 forward pass: dense always, sparse when requested."""

    dense: list[list[float]]
    sparse: list[SparseWeights] | None = None

    def sparse_at(self, index: int) -> SparseWeights | None:
        if self.sparse is None:
            return None

        return self.sparse[index]


class EmbeddingService:
    """BGE-M3 embedding service owned by M2.

    Responsibilities:
        - Load BGE-M3.
        - Embed legal document chunks received from M1.
        - Embed legal user queries.
        - Produce both the dense vector and the lexical (sparse) weights.
        - Keep model and dimension information explicit.

    Non-responsibilities:
        - Qdrant indexing.
        - Retrieval.
        - Reranking.
        - RAG generation.

    On sparse
    ---------
    BGE-M3 computes dense and lexical representations in the same forward
    pass. This service previously asked for the dense output only, so the
    lexical weights were computed and thrown away on every call while
    keyword search was served by a separate Python BM25 index built from a
    full-collection scroll. Requesting ``return_sparse`` recovers work that
    was already being done.
    """

    def __init__(
        self,
        model_name: str = settings.embedding_model,
        use_fp16: bool = settings.use_fp16,
        batch_size: int = settings.batch_size,
        max_length: int = settings.max_length,
        return_sparse: bool = settings.return_sparse,
        warn_on_truncation: bool = settings.warn_on_truncation,
    ) -> None:
        """Load BGE-M3 and store inference configuration."""
        self.model_name = model_name
        self.batch_size = batch_size
        self.max_length = max_length

        self.return_sparse = return_sparse
        self.warn_on_truncation = warn_on_truncation

        self.model = BGEM3FlagModel(
            model_name,
            use_fp16=use_fp16,
        )

        self._dimension: int | None = None

    @property
    def dimension(self) -> int | None:
        """Return the detected embedding dimension, if available."""
        return self._dimension

    def _encode_full(self, texts: Sequence[str]) -> EncodedTexts:
        """
        Encode a non-empty sequence with BGE-M3, dense plus optional sparse.

        ``return_dense`` is passed explicitly rather than relying on the
        default: this call now names what it wants, and a future FlagEmbedding
        whose defaults shift cannot quietly stop returning the dense vectors
        that everything downstream depends on.
        """
        if not texts:
            raise ValueError("texts must not be empty")

        if any(not text or not text.strip() for text in texts):
            raise ValueError("texts must not contain empty strings")

        self._warn_if_truncated(texts)

        result = self.model.encode(
            list(texts),
            batch_size=self.batch_size,
            max_length=self.max_length,
            return_dense=True,
            return_sparse=self.return_sparse,
        )

        vectors = result["dense_vecs"]

        dense = [vector.tolist() for vector in vectors]

        if dense:
            self._dimension = len(dense[0])

        sparse: list[SparseWeights] | None = None

        if self.return_sparse:
            raw_sparse = result.get("lexical_weights")

            if raw_sparse is None:
                # Asked for sparse and did not get it. Degrade to dense-only
                # rather than failing the request: retrieval still works
                # without sparse, and a hard failure here would take down
                # ingestion and search over a secondary signal.
                logger.warning(
                    "BGE-M3 returned no lexical_weights despite "
                    "return_sparse=True; continuing dense-only."
                )

            else:
                sparse = [
                    normalize_lexical_weights(entry)
                    for entry in raw_sparse
                ]

                if len(sparse) != len(dense):
                    raise ValueError(
                        "BGE-M3 returned "
                        f"{len(sparse)} sparse vectors for {len(dense)} "
                        "texts; refusing to pair them by position."
                    )

        return EncodedTexts(dense=dense, sparse=sparse)

    def _warn_if_truncated(self, texts: Sequence[str]) -> None:
        """Report any text the encoder is about to cut short.

        ``max_length`` truncation is silent: the model returns a perfectly
        normal-looking vector built from only the first ``max_length`` tokens.
        Since M1 now sizes chunks against this same tokenizer, reaching this
        point means something upstream is out of step -- an older M1, a
        mismatched tokenizer, or text assembled after chunking -- and the
        symptom otherwise is only that retrieval quietly stops finding the
        ends of long passages.
        """
        if not self.warn_on_truncation:
            return

        tokenizer = getattr(self.model, "tokenizer", None)

        if tokenizer is None:
            return

        for text in texts:
            try:
                n_tokens = len(
                    tokenizer.encode(text, add_special_tokens=True)
                )

            except Exception:  # noqa: BLE001 -- diagnostics must never fail ingest
                return

            if n_tokens > self.max_length:
                logger.warning(
                    "text of %d tokens exceeds the %d-token encoder window "
                    "and will be truncated: %d tokens (%.0f%%) will not be "
                    "embedded, dense or sparse, though the full text remains "
                    "searchable by keyword. Chunking should have prevented "
                    "this.",
                    n_tokens,
                    self.max_length,
                    n_tokens - self.max_length,
                    100.0 * (n_tokens - self.max_length) / n_tokens,
                )

    def _encode(self, texts: Sequence[str]) -> list[list[float]]:
        """Dense-only view of :meth:`_encode_full`, kept for callers that
        genuinely only need vectors."""
        return self._encode_full(texts).dense

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
        """
        Produce the complete M2 query handoff object.

        The sparse weights are written onto the returned ProcessedQuery as
        well as the envelope. ProcessedQuery.sparse_embedding has been
        declared since the original M2 contract but was never populated, so
        M3 had no sparse query vector to search with even though the model
        had computed one.
        """
        text = (
            query.normalized_text
            if query.normalized_text
            else query.text_original
        )

        encoded = self._encode_full([text])

        vector = encoded.dense[0]
        sparse = encoded.sparse_at(0)

        return EmbeddedQuery(
            processed_query=query.model_copy(
                update={"sparse_embedding": sparse},
            ),
            embedding=vector,
            model=self.model_name,
            dimension=len(vector),
            sparse_embedding=sparse,
        )

    def embed_document_chunk(
        self,
        document_id: str,
        chunk_id: str,
        text: str,
    ) -> EmbeddedDocumentChunk:
        """Embed one document chunk received from M1."""
        encoded = self._encode_full([text])

        vector = encoded.dense[0]

        return EmbeddedDocumentChunk(
            document_id=document_id,
            chunk_id=chunk_id,
            text=text,
            embedding=vector,
            sparse_embedding=encoded.sparse_at(0),
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

        encoded = self._encode_full(texts)

        vectors = encoded.dense

        results: list[EmbeddedDocumentChunk] = []

        for index, (chunk, vector) in enumerate(
            zip(chunks, vectors)
        ):
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
                    client_id=chunk.client_id,
                    matter_id=chunk.matter_id,
                    confidentiality_level=(
                        chunk.confidentiality_level
                    ),
                    embedding=vector,
                    sparse_embedding=(
                        encoded.sparse_at(index)
                    ),
                    model=self.model_name,
                    dimension=len(vector),
                )
            )

        return results
