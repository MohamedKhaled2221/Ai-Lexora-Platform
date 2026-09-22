"""
Stage 3 coverage: v2 payload shape and payload-index creation.

The index-creation tests use a fake Qdrant client rather than the in-memory
one, because in-memory Qdrant accepts create_payload_index and then warns that
indices have no effect there -- so it cannot witness the bug these tests exist
to pin down (indices never being created on an already-existing collection).
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.indexing import (
    DocumentIndexingError,
    DocumentIndexingService,
)
from src.schemas import DocumentChunk, EmbeddedDocumentChunk
from src.vector_store.qdrant_manager import (
    ACL_PAYLOAD_FIELDS,
    DEFAULT_COLLECTION_NAME,
    PAYLOAD_SCHEMA_VERSION,
    QdrantVectorStore,
)


EXPECTED_INDEXED_FIELDS = {
    # Relevance filters.
    "document_type",
    "jurisdiction",
    "language",
    "document_id",
    # Access control -- every query filters on these.
    "client_id",
    "matter_id",
    "confidentiality_level",
    # Exact legal-identifier lookup. The only fields in the collection that
    # support equality rather than similarity; see IDENTIFIER_PAYLOAD_FIELDS.
    # Each kind carries a bare token (`_no`) and a document-scoped compound
    # key (`_ref`); `case_no` has no compound form because a docket number is
    # already unique across documents.
    "article_no",
    "article_ref",
    "case_no",
    "date_no",
    "date_ref",
    "money_no",
    "money_ref",
    # M6 knowledge-record lifecycle, written by index sync: record_id scopes a
    # record's points for delete/re-sync, validity_status feeds the optional
    # status filter.
    "record_id",
    "validity_status",
    "party_name",
}


def _fake_client(existing_collections):
    client = MagicMock()
    client.get_collections.return_value = SimpleNamespace(
        collections=[
            SimpleNamespace(name=name) for name in existing_collections
        ]
    )
    return client


def _indexed_fields(client):
    return {
        call.kwargs["field_name"]
        for call in client.create_payload_index.call_args_list
    }


# ---------------------------------------------------------------------------
# Payload index creation
# ---------------------------------------------------------------------------


def test_indices_are_created_on_a_new_collection():
    client = _fake_client([])

    with patch(
        "src.vector_store.qdrant_manager.QdrantClient",
        return_value=client,
    ):
        QdrantVectorStore(collection_name="fresh")

    client.create_collection.assert_called_once()
    assert _indexed_fields(client) == EXPECTED_INDEXED_FIELDS


def test_indices_are_backfilled_on_an_existing_collection():
    """
    The regression this stage fixes.

    Index creation used to sit inside the create-if-missing branch, so a
    collection that already existed never received a newly-added index and
    every ACL filter would have run unindexed.
    """

    client = _fake_client(["existing"])

    with patch(
        "src.vector_store.qdrant_manager.QdrantClient",
        return_value=client,
    ):
        QdrantVectorStore(collection_name="existing")

    client.create_collection.assert_not_called()
    assert _indexed_fields(client) == EXPECTED_INDEXED_FIELDS


def test_every_acl_field_is_indexed():
    client = _fake_client(["existing"])

    with patch(
        "src.vector_store.qdrant_manager.QdrantClient",
        return_value=client,
    ):
        QdrantVectorStore(collection_name="existing")

    assert set(ACL_PAYLOAD_FIELDS) <= _indexed_fields(client)


def test_index_failures_do_not_prevent_startup():
    """One unindexable field must not take the whole store down."""

    client = _fake_client(["existing"])
    client.create_payload_index.side_effect = RuntimeError("nope")

    with patch(
        "src.vector_store.qdrant_manager.QdrantClient",
        return_value=client,
    ):
        store = QdrantVectorStore(collection_name="existing")

    assert store.collection_name == "existing"


# ---------------------------------------------------------------------------
# Collection cut-over
# ---------------------------------------------------------------------------


def test_default_collection_is_v2():
    assert DEFAULT_COLLECTION_NAME == "legal_documents_v2"

    client = _fake_client([])

    with patch(
        "src.vector_store.qdrant_manager.QdrantClient",
        return_value=client,
    ):
        store = QdrantVectorStore()

    assert store.collection_name == "legal_documents_v2"


# ---------------------------------------------------------------------------
# v2 payload shape
# ---------------------------------------------------------------------------


class _StampingEmbeddingService:
    """Stands in for M2, preserving the ACL the way the real service does."""

    def __init__(self, dimension: int = 3) -> None:
        self.model_name = "fake-bge-m3"
        self.dimension = dimension

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
                embedding=[float(index)] * self.dimension,
                model=self.model_name,
                dimension=self.dimension,
            )
            for index, chunk in enumerate(chunks, start=1)
        ]


def _stamped_chunk(**overrides):
    values = {
        "document_id": "doc_001",
        "chunk_id": "chunk_001",
        "text": "Either party may terminate the agreement.",
        "page": 12,
        "section": "Termination",
        "clause": "Clause 7",
        "language": "en",
        "document_type": "contract",
        "metadata": {"jurisdiction": "Egypt"},
        "client_id": "client_042",
        "matter_id": "matter_7",
        "confidentiality_level": "privileged",
    }
    values.update(overrides)

    return DocumentChunk(**values)


def _index_and_capture_payloads(chunks):
    store = MagicMock()
    store.vector_size = 3

    service = DocumentIndexingService(
        embedding_service=_StampingEmbeddingService(),
        vector_store=store,
    )

    service.index_document(chunks)

    (points,) = store.upsert_chunks.call_args.args

    return [point.payload for point in points]


def test_v2_payload_carries_the_acl_and_schema_version():
    (payload,) = _index_and_capture_payloads([_stamped_chunk()])

    assert payload["client_id"] == "client_042"
    assert payload["matter_id"] == "matter_7"
    assert payload["confidentiality_level"] == "privileged"
    assert payload["schema_version"] == PAYLOAD_SCHEMA_VERSION == 2


def test_acl_survives_the_m2_hop():
    """
    EmbeddedDocumentChunk is extra="forbid" and M2 copies field by field, so
    an undeclared ACL field would be dropped between M1 and Qdrant without
    any error -- the chunk would index with no owner.
    """

    embedded = _StampingEmbeddingService().embed_document_chunks(
        [_stamped_chunk()]
    )

    assert embedded[0].client_id == "client_042"
    assert embedded[0].matter_id == "matter_7"
    assert embedded[0].confidentiality_level == "privileged"


@pytest.mark.parametrize(
    "missing_field",
    ["client_id", "matter_id", "confidentiality_level"],
)
def test_unstamped_chunk_is_refused_at_indexing(missing_field):
    """
    An unstamped chunk is never written.

    It would not have been readable either way -- a null client_id matches no
    allowed-client set -- so this is not the difference between private and
    public. It is the difference between a document that works and one that
    indexes silently and can never be retrieved by anyone, which is worth
    failing loudly at write time.
    """

    with pytest.raises(DocumentIndexingError) as excinfo:
        _index_and_capture_payloads(
            [_stamped_chunk(**{missing_field: None})]
        )

    assert missing_field in str(excinfo.value)


def test_a_fully_unstamped_chunk_is_refused():
    with pytest.raises(DocumentIndexingError):
        _index_and_capture_payloads(
            [
                _stamped_chunk(
                    client_id=None,
                    matter_id=None,
                    confidentiality_level=None,
                )
            ]
        )
def test_project_exposes_title_from_trusted_metadata():
    projected = QdrantVectorStore._project(
        point_id="point-1",
        payload={
            "document_id": "doc-1",
            "chunk_id": "chunk-1",
            "text": "The contractual notice period is 30 calendar days.",
            "metadata": {
                "title": "Current Employment Agreement",
            },
        },
        score=0.9,
    )

    assert (
        projected["title"]
        == "Current Employment Agreement"
    )
    assert (
        projected["text"]
        == "The contractual notice period is 30 calendar days."
    )
