"""
Upload path -> M6 canonical record -> IndexUpdate -> Qdrant.
"""

import asyncio
from types import SimpleNamespace

import pytest

from src.indexing.index_sync import IndexSyncError, IndexSyncService
from src.indexing.ingestion_service import DocumentIngestionService
from src.indexing.knowledge_sync import KnowledgeSyncService
from src.knowledge.repository import InMemoryKnowledgeRepository
from src.schemas import DocumentChunk
from src.schemas.access_control import ChunkACL
from src.schemas.m6_knowledge import AccessLevel
from src.vector_store.qdrant_manager import QdrantVectorStore
from tests.test_index_sync import FakeEmbeddingService


def _chunks(document_type="law", texts=("Article 15\nStrikes are a right.", "Article 16\nText.")):
    return [
        DocumentChunk(
            document_id="doc_law",
            chunk_id=f"chunk_{i:03d}",
            text=text,
            page=i,
            section=f"Article {14 + i}",
            language="en",
            document_type=document_type,
            metadata={"jurisdiction": "Egypt"},
            client_id="client_a",
            matter_id="matter_1",
            confidentiality_level="privileged",
        )
        for i, text in enumerate(texts, start=1)
    ]


def _service(name, repository=None):
    store = QdrantVectorStore(location=":memory:", collection_name=name, vector_size=3)
    repository = repository or InMemoryKnowledgeRepository()
    sync = KnowledgeSyncService(
        repository_factory=lambda: repository,
        index_sync=IndexSyncService(FakeEmbeddingService(), store),
    )
    return sync, repository, store


def _payloads(store):
    points, _ = store.client.scroll(store.collection_name, limit=100, with_payload=True)
    return sorted((p.payload for p in points), key=lambda p: p["chunk_id"])


def test_document_becomes_one_record_and_is_indexed_with_its_acl_and_structure():
    sync, repository, store = _service("ks_basic")

    result = sync.sync_document(_chunks(), title="Labour Law")

    record = repository.get("doc:doc_law")
    assert record.canonical_name == "Labour Law"
    assert record.access.access_level == AccessLevel.RESTRICTED
    assert (record.access.client_id, record.access.matter_id) == ("client_a", "matter_1")
    assert [p.chunk_id for p in record.source_passages] == ["chunk_001", "chunk_002"]

    assert result.outcome == "applied" and result.points_written == 2
    first = _payloads(store)[0]
    assert (first["client_id"], first["matter_id"], first["confidentiality_level"]) == (
        "client_a", "matter_1", "privileged"
    )
    assert first["record_id"] == "doc:doc_law"
    assert first["section"] == "Article 15"
    assert first["jurisdiction"] == "Egypt"
    assert "article_no" in first  # identifier extraction still sees the heading


def test_reingesting_bumps_version_and_replaces_points():
    sync, repository, store = _service("ks_reingest")
    sync.sync_document(_chunks())

    result = sync.sync_document(_chunks(texts=("Article 15\nAmended.",)))

    assert repository.get("doc:doc_law").version == 2
    assert result.points_deleted == 1
    assert [(p["chunk_id"], p["record_version"]) for p in _payloads(store)] == [("chunk_001", 2)]


def test_shared_public_corpus_round_trips():
    sync, _, store = _service("ks_shared")
    chunks = [
        c.model_copy(update={"client_id": "_shared", "matter_id": "_none",
                             "confidentiality_level": "public"})
        for c in _chunks()
    ]
    sync.sync_document(chunks)
    assert {(p["client_id"], p["confidentiality_level"]) for p in _payloads(store)} == {
        ("_shared", "public")
    }


@pytest.mark.parametrize(
    ("chunks", "message"),
    [
        (_chunks(document_type="contract"), "no M6 record type"),
        ([], "no chunks"),
        ([_chunks()[0], _chunks()[1].model_copy(update={"client_id": "client_b"})],
         "same, complete access-control"),
        ([c.model_copy(update={"confidentiality_level": None}) for c in _chunks()],
         "same, complete access-control"),
    ],
)
def test_unsafe_or_unsupported_documents_are_refused(chunks, message):
    sync, repository, store = _service("ks_refuse")
    with pytest.raises(IndexSyncError, match=message):
        sync.sync_document(chunks)
    assert repository.list_records() == [] and _payloads(store) == []


def test_postgres_repository_keeps_one_row_per_document(monkeypatch):
    pytest.importorskip("sqlalchemy")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from src.knowledge.database import Base
    from src.knowledge.postgres_repository import PostgresKnowledgeRepository
    import src.knowledge.db_models  # noqa: F401

    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)

    store = QdrantVectorStore(location=":memory:", collection_name="ks_pg", vector_size=3)
    sync = KnowledgeSyncService(
        repository_factory=lambda: PostgresKnowledgeRepository(sessions()),
        index_sync=IndexSyncService(FakeEmbeddingService(), store),
    )

    sync.sync_document(_chunks())
    sync.sync_document(_chunks())

    rows = PostgresKnowledgeRepository(sessions()).list_records()
    assert [(r.record_id, r.version) for r in rows] == [("doc:doc_law", 2)]
    assert {p["record_version"] for p in _payloads(store)} == {2}


# -------------------------------------------------------- ingestion routing


class FakeM1:
    def __init__(self, chunks):
        self.chunks = chunks

    async def ingest_document(self, **kwargs):
        return SimpleNamespace(
            document_id="doc_law", source_file="law.pdf", file_type="pdf",
            document_type=self.chunks[0].document_type, language="en",
            n_pages=2, chunks=self.chunks,
        )


class RecordingIndexer:
    def __init__(self):
        self.called = False

    def index_document(self, chunks):
        self.called = True
        return SimpleNamespace(document_id="doc_law", chunks_indexed=len(chunks),
                               embedding_model="direct", embedding_dimension=3)


ACL = ChunkACL(client_id="client_a", matter_id="matter_1", confidentiality_level="privileged")


def _ingest(service):
    return asyncio.run(service.ingest_document(file_name="law.pdf", file_object=None, acl=ACL))


def test_laws_go_through_knowledge_sync_and_are_not_indexed_directly():
    sync, repository, store = _service("ks_route_law")
    indexer = RecordingIndexer()
    service = DocumentIngestionService(m1_client=FakeM1(_chunks()), indexing_service=indexer,
                                       knowledge_sync=sync)

    result = _ingest(service)

    assert indexer.called is False
    assert result.knowledge_record_id == "doc:doc_law"
    assert result.chunks_indexed == 2 and result.embedding_model == "fake-embedder"
    assert repository.get("doc:doc_law") is not None


def test_types_m6_cannot_represent_keep_the_direct_path():
    sync, repository, _ = _service("ks_route_contract")
    indexer = RecordingIndexer()
    service = DocumentIngestionService(m1_client=FakeM1(_chunks(document_type="contract")),
                                       indexing_service=indexer, knowledge_sync=sync)

    result = _ingest(service)

    assert indexer.called is True and result.knowledge_record_id is None
    assert repository.list_records() == []


def test_without_knowledge_sync_behaviour_is_unchanged():
    indexer = RecordingIndexer()
    service = DocumentIngestionService(m1_client=FakeM1(_chunks()), indexing_service=indexer)

    result = _ingest(service)

    assert indexer.called is True and result.knowledge_record_id is None
