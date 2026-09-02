from src.indexing import (
    DocumentIndexingError,
    DocumentIndexingService,
)
from src.schemas import (
    DocumentChunk,
    EmbeddedDocumentChunk,
)
from src.vector_store.qdrant_manager import (
    QdrantVectorStore,
)


class FakeEmbeddingService:
    def __init__(
        self,
        dimension: int = 3,
    ) -> None:
        self.model_name = "fake-bge-m3"
        self.dimension = dimension

    def embed_document_chunks(
        self,
        chunks,
    ):
        results = []

        for index, chunk in enumerate(
            chunks,
            start=1,
        ):
            vector = [
                float(index)
                for _ in range(
                    self.dimension
                )
            ]

            results.append(
                EmbeddedDocumentChunk(
                    document_id=chunk.document_id,
                    chunk_id=chunk.chunk_id,
                    text=chunk.text,
                    page=chunk.page,
                    section=chunk.section,
                    clause=chunk.clause,
                    language=chunk.language,
                    document_type=(
                        chunk.document_type
                    ),
                    metadata=chunk.metadata,
                    embedding=vector,
                    model=self.model_name,
                    dimension=self.dimension,
                )
            )

        return results


def make_chunks():
    return [
        DocumentChunk(
            document_id="doc_001",
            chunk_id="chunk_001",
            text=(
                "Either party may terminate "
                "the agreement."
            ),
            page=12,
            section="Termination",
            clause="Clause 7",
            language="en",
            document_type="contract",
            metadata={
                "jurisdiction": "Egypt",
                "source_filename": (
                    "contract.pdf"
                ),
            },
        ),
        DocumentChunk(
            document_id="doc_001",
            chunk_id="chunk_002",
            text=(
                "Payment shall be made "
                "within thirty days."
            ),
            page=13,
            section="Payment",
            clause="Clause 8",
            language="en",
            document_type="contract",
            metadata={
                "jurisdiction": "Egypt",
                "source_filename": (
                    "contract.pdf"
                ),
            },
        ),
    ]


def make_service(
    embedding_dimension: int = 3,
):
    vector_store = QdrantVectorStore(
        location=":memory:",
        collection_name=(
            "document_indexing_test"
        ),
        vector_size=3,
    )

    service = DocumentIndexingService(
        embedding_service=FakeEmbeddingService(
            dimension=embedding_dimension,
        ),
        vector_store=vector_store,
    )

    return service, vector_store


def test_indexes_document_chunks_into_qdrant():
    service, vector_store = make_service()

    result = service.index_document(
        make_chunks()
    )

    assert result.document_id == "doc_001"
    assert result.chunks_indexed == 2
    assert (
        result.embedding_model
        == "fake-bge-m3"
    )
    assert result.embedding_dimension == 3

    stored = vector_store.get_all_chunks()

    assert len(stored) == 2

    stored_by_chunk = {
        item["chunk_id"]: item
        for item in stored
    }

    first = stored_by_chunk["chunk_001"]

    assert first["document_id"] == "doc_001"
    assert first["text"].startswith(
        "Either party"
    )
    assert first["page"] == 12
    assert first["section"] == "Termination"
    assert first["language"] == "en"
    assert (
        first["document_type"]
        == "contract"
    )
    assert first["jurisdiction"] == "Egypt"


def test_reindexing_same_chunks_does_not_duplicate_points():
    service, vector_store = make_service()

    chunks = make_chunks()

    service.index_document(chunks)
    service.index_document(chunks)

    stored = vector_store.get_all_chunks()

    assert len(stored) == 2


def test_rejects_empty_document():
    service, _ = make_service()

    try:
        service.index_document([])
    except DocumentIndexingError as error:
        assert "empty" in str(error).lower()
    else:
        raise AssertionError(
            "Expected DocumentIndexingError"
        )


def test_rejects_multiple_document_ids():
    service, _ = make_service()

    chunks = make_chunks()

    second = chunks[1].model_copy(
        update={
            "document_id": "doc_002",
        }
    )

    try:
        service.index_document(
            [
                chunks[0],
                second,
            ]
        )
    except DocumentIndexingError as error:
        assert (
            "exactly one document"
            in str(error)
        )
    else:
        raise AssertionError(
            "Expected DocumentIndexingError"
        )


def test_rejects_duplicate_chunk_ids():
    service, _ = make_service()

    chunks = make_chunks()

    duplicate = chunks[1].model_copy(
        update={
            "chunk_id": "chunk_001",
        }
    )

    try:
        service.index_document(
            [
                chunks[0],
                duplicate,
            ]
        )
    except DocumentIndexingError as error:
        assert "duplicate" in str(error).lower()
    else:
        raise AssertionError(
            "Expected DocumentIndexingError"
        )


def test_rejects_embedding_dimension_mismatch():
    service, _ = make_service(
        embedding_dimension=4,
    )

    try:
        service.index_document(
            make_chunks()
        )
    except DocumentIndexingError as error:
        assert "dimension" in str(error).lower()
    else:
        raise AssertionError(
            "Expected DocumentIndexingError"
        )
