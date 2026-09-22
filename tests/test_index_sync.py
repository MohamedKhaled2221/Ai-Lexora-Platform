"""
M3 IndexUpdate consumer: idempotent, order-safe, replace-not-append, and
fail-closed on access metadata it cannot express.
"""

from datetime import date

import pytest

from src.indexing.index_sync import IndexSyncError, IndexSyncService
from src.schemas import EmbeddedDocumentChunk
from src.schemas.m6_knowledge import (
    AccessLevel,
    AccessMetadata,
    IndexUpdate,
    KnowledgeRecord,
    KnowledgeRecordType,
    SourcePassage,
    ValidityStatus,
)
from src.vector_store.qdrant_manager import QdrantVectorStore
from tests.access_helpers import access_scope


class FakeEmbeddingService:
    model_name = "fake-embedder"

    def __init__(self):
        self.calls = 0

    def embed_document_chunks(self, chunks):
        self.calls += 1
        return [
            EmbeddedDocumentChunk(
                **chunk.model_dump(),
                embedding=[1.0, float(index), 0.0],
                model=self.model_name,
                dimension=3,
            )
            for index, chunk in enumerate(chunks)
        ]


def _store(name):
    return QdrantVectorStore(location=":memory:", collection_name=name, vector_size=3)


def _record(version=1, passages=None, **overrides):
    values = dict(
        record_id="rec-law-1",
        record_type=KnowledgeRecordType.LAW,
        canonical_name="Labour Law",
        normalized_data={"source_document_id": "doc_law_1", "language": "ar",
                         "jurisdiction": "Egypt"},
        source_passages=passages if passages is not None else [
            SourcePassage(source_id="doc_law_1", passage="Article 1 text", page=1,
                          chunk_id="chunk_001"),
            SourcePassage(source_id="doc_law_1", passage="Article 2 text", page=2,
                          chunk_id="chunk_002"),
        ],
        access=AccessMetadata(access_level=AccessLevel.PUBLIC),
        validity_status=ValidityStatus.CURRENT,
        effective_from=date(2020, 1, 1),
        version=version,
    )
    values.update(overrides)
    return KnowledgeRecord(**values)


def _update(record, operation="upsert"):
    return IndexUpdate(record_id=record.record_id, operation=operation,
                       version=record.version)


def _payloads(store):
    points, _ = store.client.scroll(store.collection_name, limit=100, with_payload=True)
    return sorted((p.payload for p in points), key=lambda p: p["chunk_id"])


def test_upsert_writes_points_with_lifecycle_and_shared_acl():
    store = _store("sync_upsert")
    service = IndexSyncService(FakeEmbeddingService(), store)
    record = _record()

    result = service.apply(_update(record), record)

    assert result.outcome == "applied" and result.points_written == 2
    payloads = _payloads(store)
    assert [p["chunk_id"] for p in payloads] == ["chunk_001", "chunk_002"]
    first = payloads[0]
    assert first["record_id"] == "rec-law-1"
    assert first["record_version"] == 1
    assert first["validity_status"] == "current"
    assert first["effective_from"] == "2020-01-01"
    assert first["client_id"] == "_shared"
    assert first["matter_id"] == "_none"
    assert first["confidentiality_level"] == "public"
    assert first["jurisdiction"] == "Egypt"
    assert first["document_type"] == "law"


def test_replaying_the_same_version_is_a_no_op():
    store = _store("sync_replay")
    embedder = FakeEmbeddingService()
    service = IndexSyncService(embedder, store)
    record = _record()

    service.apply(_update(record), record)
    again = service.apply(_update(record), record)

    assert again.outcome == "skipped_stale"
    assert embedder.calls == 1
    assert len(_payloads(store)) == 2


def test_out_of_order_older_version_cannot_roll_back():
    store = _store("sync_order")
    service = IndexSyncService(FakeEmbeddingService(), store)
    v2 = _record(version=2, validity_status=ValidityStatus.SUPERSEDED)
    v1 = _record(version=1)

    service.apply(_update(v2), v2)
    result = service.apply(_update(v1), v1)

    assert result.outcome == "skipped_stale"
    assert {p["validity_status"] for p in _payloads(store)} == {"superseded"}


def test_new_version_removes_passages_it_no_longer_has():
    store = _store("sync_replace")
    service = IndexSyncService(FakeEmbeddingService(), store)
    v1 = _record(version=1)
    v2 = _record(version=2, passages=[
        SourcePassage(source_id="doc_law_1", passage="Article 1 amended", page=1,
                      chunk_id="chunk_001"),
    ])

    service.apply(_update(v1), v1)
    result = service.apply(_update(v2), v2)

    assert result.points_deleted == 1
    payloads = _payloads(store)
    assert [(p["chunk_id"], p["text"], p["record_version"]) for p in payloads] == [
        ("chunk_001", "Article 1 amended", 2)
    ]


def test_delete_removes_all_record_points_and_leaves_others():
    store = _store("sync_delete")
    service = IndexSyncService(FakeEmbeddingService(), store)
    keep = _record(record_id="rec-other",
                   normalized_data={"source_document_id": "doc_other"})
    gone = _record()

    service.apply(_update(keep), keep)
    service.apply(_update(gone), gone)
    result = service.apply(IndexUpdate(record_id="rec-law-1", operation="delete", version=2))

    assert result.outcome == "applied" and result.points_deleted == 2
    assert {p["record_id"] for p in _payloads(store)} == {"rec-other"}


def test_stale_delete_does_not_remove_a_newer_version():
    store = _store("sync_stale_delete")
    service = IndexSyncService(FakeEmbeddingService(), store)
    v3 = _record(version=3)
    service.apply(_update(v3), v3)

    result = service.apply(IndexUpdate(record_id="rec-law-1", operation="delete", version=2))

    assert result.outcome == "skipped_stale"
    assert len(_payloads(store)) == 2


def test_record_points_never_collide_with_document_pipeline_ids():
    from src.indexing.service import DocumentIndexingService

    assert IndexSyncService.point_id("doc_law_1", "chunk_001") != (
        DocumentIndexingService._point_id("doc_law_1", "chunk_001")
    )


@pytest.mark.parametrize(
    ("access", "message"),
    [
        (AccessMetadata(access_level=AccessLevel.RESTRICTED), "no client_id"),
        (AccessMetadata(access_level=AccessLevel.INTERNAL), "no client_id"),
        (AccessMetadata(access_level=AccessLevel.PUBLIC, allowed_roles=["partner"]),
         "role"),
    ],
)
def test_unexpressible_access_is_refused_and_nothing_is_written(access, message):
    store = _store("sync_refuse")
    service = IndexSyncService(FakeEmbeddingService(), store)
    record = _record(access=access)

    with pytest.raises(IndexSyncError, match=message):
        service.apply(_update(record), record)

    assert _payloads(store) == []


def test_confidential_and_restricted_map_to_privileged_for_their_client():
    for level in (AccessLevel.CONFIDENTIAL, AccessLevel.RESTRICTED):
        record = _record(access=AccessMetadata(access_level=level, client_id="client_a",
                                               matter_id="m1"))
        assert IndexSyncService.chunk_acl(record) == {
            "client_id": "client_a",
            "matter_id": "m1",
            "confidentiality_level": "privileged",
        }


def test_upsert_requires_the_record_and_matching_version():
    service = IndexSyncService(FakeEmbeddingService(), _store("sync_contract"))
    record = _record(version=2)

    with pytest.raises(IndexSyncError, match="needs the KnowledgeRecord"):
        service.apply(_update(record))
    with pytest.raises(IndexSyncError, match="version"):
        service.apply(IndexUpdate(record_id=record.record_id, operation="upsert",
                                  version=1), record)
    with pytest.raises(IndexSyncError, match="Unsupported"):
        service.apply(IndexUpdate(record_id=record.record_id, operation="merge",
                                  version=2), record)


def test_passage_without_page_is_refused_rather_than_given_a_fake_page():
    store = _store("sync_no_page")
    service = IndexSyncService(FakeEmbeddingService(), store)
    record = _record(passages=[SourcePassage(source_id="d", passage="text")])

    with pytest.raises(IndexSyncError, match="no page"):
        service.apply(_update(record), record)
    assert _payloads(store) == []


def test_synced_points_are_retrievable_under_an_access_scope():
    store = _store("sync_retrievable")
    service = IndexSyncService(FakeEmbeddingService(), store)
    record = _record()
    service.apply(_update(record), record)

    hits = store.dense_search(
        [1.0, 0.0, 0.0],
        store.build_qdrant_filter(access=access_scope()),
        top_k=5,
    )

    assert {h["document_id"] for h in hits} == {"doc_law_1"}
def test_index_sync_persists_canonical_name_as_title_metadata():
    store = _store("sync_title_metadata")
    service = IndexSyncService(
        FakeEmbeddingService(),
        store,
    )
    record = _record(
        canonical_name="Current Employment Agreement",
    )

    service.apply(
        _update(record),
        record,
    )

    payloads = _payloads(store)

    assert payloads
    assert {
        payload["metadata"]["title"]
        for payload in payloads
    } == {"Current Employment Agreement"}
