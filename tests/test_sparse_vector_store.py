"""
Steps 2-3 coverage: sparse vectors in the collection and in written points.

Unlike the embedding tests, these run against a real in-memory Qdrant, so the
sparse round trip -- config, upsert, query -- is genuinely exercised rather
than mocked. What in-memory Qdrant cannot show is payload *index* behaviour;
that limitation is unchanged from the ACL work.
"""

from unittest.mock import MagicMock

import pytest
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from src.indexing import DocumentIndexingError, DocumentIndexingService
from src.schemas import DocumentChunk, EmbeddedDocumentChunk
from src.vector_store.qdrant_manager import (
    DENSE_VECTOR_NAME,
    PAYLOAD_SCHEMA_VERSION,
    SPARSE_VECTOR_NAME,
    QdrantVectorStore,
    to_sparse_vector,
)
from tests.access_helpers import access_scope


# ---------------------------------------------------------------------------
# to_sparse_vector
# ---------------------------------------------------------------------------


def test_string_token_ids_become_integer_indices():
    """
    M2 carries token ids as strings (JSON keys are strings); Qdrant wants
    integer indices. The conversion belongs at the storage boundary.
    """

    result = to_sparse_vector({"1045": 0.31, "7890": 0.12})

    assert sorted(result.indices) == [1045, 7890]
    assert all(isinstance(index, int) for index in result.indices)
    assert all(isinstance(value, float) for value in result.values)


def test_indices_and_values_stay_aligned():
    weights = {"5": 0.5, "10": 0.25, "2": 0.75}

    result = to_sparse_vector(weights)

    paired = dict(zip(result.indices, result.values))

    assert paired == {5: 0.5, 10: 0.25, 2: 0.75}


@pytest.mark.parametrize("empty", [None, {}])
def test_absent_weights_produce_no_sparse_vector(empty):
    """
    Qdrant accepts an empty SparseVector but it can never match anything, so
    writing one only costs index space.
    """

    assert to_sparse_vector(empty) is None


# ---------------------------------------------------------------------------
# Collection configuration
# ---------------------------------------------------------------------------


def _store(name="sparse_store_test"):
    return QdrantVectorStore(
        location=":memory:",
        collection_name=name,
        vector_size=4,
    )


def test_new_collection_has_the_sparse_vector():
    store = _store("sparse_config_new")

    info = store.client.get_collection("sparse_config_new")
    configured = info.config.params.sparse_vectors or {}

    assert SPARSE_VECTOR_NAME in configured
    assert store.sparse_enabled is True


def test_sparse_uses_no_idf_modifier():
    """
    BGE-M3's lexical weights are already learned term weights. Qdrant's IDF
    modifier on top would weight rare terms twice.
    """

    store = _store("sparse_config_modifier")

    params = store.client.get_collection(
        "sparse_config_modifier"
    ).config.params.sparse_vectors[SPARSE_VECTOR_NAME]

    assert params.modifier == qmodels.Modifier.NONE


def test_dense_vector_stays_unnamed():
    """
    Keeping the dense vector in Qdrant's default slot is why dense_search
    needed no change: a dense query still needs no `using=` argument.
    """

    assert DENSE_VECTOR_NAME == ""

    store = _store("sparse_config_dense")
    store.upsert_chunks([
        qmodels.PointStruct(
            id=1,
            vector={
                DENSE_VECTOR_NAME: [1.0, 0.0, 0.0, 0.0],
                SPARSE_VECTOR_NAME: qmodels.SparseVector(
                    indices=[7], values=[0.5]
                ),
            },
            payload={
                "document_id": "doc_a",
                "chunk_id": "chunk_1",
                "text": "t",
                "client_id": "client_test",
                "matter_id": "_none",
                "confidentiality_level": "internal",
            },
        )
    ])

    results = store.dense_search(
        query_vector=[1.0, 0.0, 0.0, 0.0],
        query_filter=store.build_qdrant_filter(access=access_scope()),
    )

    assert [item["document_id"] for item in results] == ["doc_a"]


def test_a_collection_without_sparse_is_detected_not_assumed(caplog):
    """
    Qdrant cannot add a sparse vector to an existing collection, so a
    collection created before this change can never gain one. That must be
    reported at startup rather than surfacing as a failed upsert at the
    first ingest.
    """

    import logging

    from src.vector_store import qdrant_manager

    client = QdrantClient(location=":memory:")
    client.create_collection(
        collection_name="legacy",
        vectors_config=qmodels.VectorParams(
            size=4, distance=qmodels.Distance.COSINE
        ),
    )

    original = qdrant_manager.QdrantClient
    qdrant_manager.QdrantClient = lambda **kwargs: client
    try:
        with caplog.at_level(
            logging.ERROR,
            logger="src.vector_store.qdrant_manager",
        ):
            store = QdrantVectorStore(
                location=":memory:",
                collection_name="legacy",
                vector_size=4,
            )
    finally:
        qdrant_manager.QdrantClient = original

    assert store.sparse_enabled is False
    assert any(
        "re-index" in record.message for record in caplog.records
    )


def test_missing_sparse_does_not_break_dense_or_acl():
    """
    A missing sparse vector is a relevance problem, not a security one.
    Dense search and access filtering must be entirely unaffected.
    """

    from src.vector_store import qdrant_manager

    client = QdrantClient(location=":memory:")
    client.create_collection(
        collection_name="legacy2",
        vectors_config=qmodels.VectorParams(
            size=4, distance=qmodels.Distance.COSINE
        ),
    )

    original = qdrant_manager.QdrantClient
    qdrant_manager.QdrantClient = lambda **kwargs: client
    try:
        store = QdrantVectorStore(
            location=":memory:",
            collection_name="legacy2",
            vector_size=4,
        )
    finally:
        qdrant_manager.QdrantClient = original

    store.upsert_chunks([
        qmodels.PointStruct(
            id=1,
            vector=[1.0, 0.0, 0.0, 0.0],
            payload={
                "document_id": "doc_a",
                "chunk_id": "chunk_1",
                "text": "t",
                "client_id": "client_test",
                "matter_id": "_none",
                "confidentiality_level": "internal",
            },
        )
    ])

    results = store.dense_search(
        query_vector=[1.0, 0.0, 0.0, 0.0],
        query_filter=store.build_qdrant_filter(access=access_scope()),
    )

    assert [item["document_id"] for item in results] == ["doc_a"]

    # And another tenant still cannot see it.
    assert store.dense_search(
        query_vector=[1.0, 0.0, 0.0, 0.0],
        query_filter=store.build_qdrant_filter(
            access=access_scope(client_id="client_other")
        ),
    ) == []


# ---------------------------------------------------------------------------
# Ingestion writes sparse alongside dense
# ---------------------------------------------------------------------------


class _SparseEmbeddingService:
    def __init__(self, sparse=True, dimension=4):
        self.model_name = "fake-bge-m3"
        self.dimension = dimension
        self.sparse = sparse

    def embed_document_chunks(self, chunks):
        return [
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
                confidentiality_level=chunk.confidentiality_level,
                embedding=[1.0, 0.0, 0.0, 0.0],
                sparse_embedding=(
                    {"1045": 0.31, "7890": 0.12} if self.sparse else None
                ),
                model=self.model_name,
                dimension=self.dimension,
            )
            for chunk in chunks
        ]


def _chunk(**overrides):
    values = {
        "document_id": "doc_001",
        "chunk_id": "chunk_001",
        "text": "Either party may terminate the agreement.",
        "page": 1,
        "client_id": "client_test",
        "matter_id": "_none",
        "confidentiality_level": "internal",
    }
    values.update(overrides)

    return DocumentChunk(**values)


def _captured_points(sparse=True, sparse_enabled=True):
    store = MagicMock()
    store.vector_size = 4
    store.sparse_enabled = sparse_enabled

    service = DocumentIndexingService(
        embedding_service=_SparseEmbeddingService(sparse=sparse),
        vector_store=store,
    )
    service.index_document([_chunk()])

    (points,) = store.upsert_chunks.call_args.args

    return points


def test_point_carries_both_vectors():
    (point,) = _captured_points()

    assert set(point.vector) == {DENSE_VECTOR_NAME, SPARSE_VECTOR_NAME}
    assert point.vector[DENSE_VECTOR_NAME] == [1.0, 0.0, 0.0, 0.0]
    assert sorted(point.vector[SPARSE_VECTOR_NAME].indices) == [1045, 7890]


def test_acl_payload_is_untouched_by_the_sparse_addition():
    """
    Sparse lives in the vector, ACL in the payload. Both were added to this
    same method weeks apart, so it is worth pinning that neither displaced
    the other.
    """

    (point,) = _captured_points()

    assert point.payload["client_id"] == "client_test"
    assert point.payload["matter_id"] == "_none"
    assert point.payload["confidentiality_level"] == "internal"
    assert point.payload["schema_version"] == PAYLOAD_SCHEMA_VERSION
    assert SPARSE_VECTOR_NAME not in point.payload


def test_chunk_without_sparse_is_written_dense_only():
    (point,) = _captured_points(sparse=False)

    assert point.vector == [1.0, 0.0, 0.0, 0.0]


def test_sparse_is_skipped_when_the_collection_cannot_hold_it():
    """
    Qdrant rejects an upsert naming a vector the collection does not have,
    which would fail the whole document. Indexing dense-only is the graceful
    path.
    """

    (point,) = _captured_points(sparse_enabled=False)

    assert point.vector == [1.0, 0.0, 0.0, 0.0]


def test_unstamped_chunk_is_still_refused_with_sparse_present():
    """The ACL refusal from the previous work must not have been weakened."""

    store = MagicMock()
    store.vector_size = 4
    store.sparse_enabled = True

    service = DocumentIndexingService(
        embedding_service=_SparseEmbeddingService(),
        vector_store=store,
    )

    with pytest.raises(DocumentIndexingError):
        service.index_document([_chunk(client_id=None)])


# ---------------------------------------------------------------------------
# Full round trip against real Qdrant
# ---------------------------------------------------------------------------


def test_written_sparse_vectors_are_searchable_and_acl_scoped():
    """
    End-to-end: index through the real service into real Qdrant, then query
    the sparse vector directly and confirm the access filter still applies.
    """

    store = _store("sparse_roundtrip")

    service = DocumentIndexingService(
        embedding_service=_SparseEmbeddingService(),
        vector_store=store,
    )
    service.index_document([_chunk()])
    service.index_document([
        _chunk(
            document_id="doc_other",
            client_id="client_other",
        )
    ])

    query = qmodels.SparseVector(indices=[1045], values=[1.0])

    unscoped = store.client.query_points(
        collection_name="sparse_roundtrip",
        query=query,
        using=SPARSE_VECTOR_NAME,
        limit=10,
        with_payload=True,
    )
    assert len(unscoped.points) == 2

    scoped = store.client.query_points(
        collection_name="sparse_roundtrip",
        query=query,
        using=SPARSE_VECTOR_NAME,
        query_filter=store.build_qdrant_filter(access=access_scope()),
        limit=10,
        with_payload=True,
    )

    assert [p.payload["document_id"] for p in scoped.points] == ["doc_001"]


# ---------------------------------------------------------------------------
# Upsert batching
# ---------------------------------------------------------------------------


def test_large_documents_are_upserted_in_batches():
    """
    Qdrant refuses a request body over 32 MiB. A point carries a 1024-float
    dense vector -- roughly 20 KB of JSON -- and token-aware chunking made a
    single dense Arabic statute produce enough chunks to cross that on its
    own, which failed the whole document with a 400.
    """

    from src.vector_store.qdrant_manager import UPSERT_BATCH_SIZE

    store = _store("upsert_batching")
    store.client = MagicMock()

    points = [
        qmodels.PointStruct(id=i, vector=[0.0, 0.0, 0.0, 1.0], payload={})
        for i in range(UPSERT_BATCH_SIZE * 2 + 5)
    ]

    store.upsert_chunks(points)

    calls = store.client.upsert.call_args_list

    assert len(calls) == 3
    assert [len(c.kwargs["points"]) for c in calls] == [
        UPSERT_BATCH_SIZE,
        UPSERT_BATCH_SIZE,
        5,
    ]


def test_every_point_is_sent_exactly_once():
    store = _store("upsert_batching_ids")
    store.client = MagicMock()

    points = [
        qmodels.PointStruct(id=i, vector=[0.0, 0.0, 0.0, 1.0], payload={})
        for i in range(600)
    ]

    store.upsert_chunks(points)

    sent = [
        p.id
        for call in store.client.upsert.call_args_list
        for p in call.kwargs["points"]
    ]

    assert sent == list(range(600))


def test_small_documents_still_take_one_request():
    store = _store("upsert_batching_small")
    store.client = MagicMock()

    store.upsert_chunks([
        qmodels.PointStruct(id=1, vector=[0.0, 0.0, 0.0, 1.0], payload={})
    ])

    assert store.client.upsert.call_count == 1


def test_empty_upsert_makes_no_request():
    store = _store("upsert_batching_empty")
    store.client = MagicMock()

    store.upsert_chunks([])

    assert store.client.upsert.call_count == 0
