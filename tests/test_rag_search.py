"""
POST /api/v1/rag/search: ranked documents, M2 -> M3 only, no LLM.
"""

import logging

import pytest
from fastapi.testclient import TestClient
from qdrant_client.http.models import PointStruct

from src.api.app import create_app
from src.api.dependencies import get_raw_rag_service
from src.api.security import APISecuritySettings
from src.orchestration import (
    M2EmbeddingContractError,
    M2M3M4RAGService,
    M2QueryRuntimeError,
    M2QueryValidationError,
    M3M4RAGService,
)
from src.orchestration.raw_rag_service import DocumentSearchResult
from src.pipeline import M3RetrievalPipeline
from src.retrieval.document_search import DocumentSearchHit, group_by_document, make_snippet
from src.retrieval.reranker import RerankerUnavailable
from src.schemas import EmbeddedQuery, ProcessedQuery
from src.schemas.access_control import AccessScopeRequired
from src.vector_store.qdrant_manager import QdrantVectorStore
from tests.access_helpers import (
    IDENTITY_HEADERS,
    OTHER_CLIENT_ID,
    TEST_CLIENT_ID,
    acl_payload,
    scoped_filters,
    shared_corpus_payload,
)


# ---------------------------------------------------------------- grouping


def test_group_by_document_keeps_one_hit_per_document_ranked_by_best_chunk():
    chunks = [
        {"document_id": "a", "chunk_id": "c1", "text": "a one", "score": 0.4, "page": 1},
        {"document_id": "b", "chunk_id": "c9", "text": "b nine", "score": 0.9, "page": 3,
         "section": "Article 9"},
        {"document_id": "a", "chunk_id": "c2", "text": "a two", "score": 0.7, "page": 2},
        {"document_id": "", "chunk_id": "x", "text": "no doc", "score": 1.0},
    ]

    hits = group_by_document(chunks)

    assert [(h.document_id, h.chunk_id, h.score, h.matched_chunks) for h in hits] == [
        ("b", "c9", 0.9, 1),
        ("a", "c2", 0.7, 2),
    ]
    assert (hits[0].page, hits[0].section, hits[0].snippet) == (3, "Article 9", "b nine")


def test_snippet_is_whitespace_normalised_and_truncated_on_a_word():
    assert make_snippet("a\n\n b  c") == "a b c"
    long = "word " * 200
    snippet = make_snippet(long, max_chars=50)
    assert len(snippet) <= 52 and snippet.endswith(" …") and "wor …" not in snippet


# ------------------------------------------------- service over real Qdrant


class FakeQueryPipeline:
    def __init__(self, vector=(1.0, 0.0, 0.0), error=None):
        self.vector = list(vector)
        self.error = error

    def process(self, raw_query):
        if self.error:
            raise self.error
        return EmbeddedQuery(
            processed_query=ProcessedQuery(
                query_id="q_search", text_original=raw_query,
                normalized_text=raw_query, language="en",
            ),
            embedding=self.vector,
            model="fake",
            dimension=len(self.vector),
        )


def _point(pid, vector, document_id, chunk_id, text, **acl):
    return PointStruct(id=pid, vector=vector, payload={
        "document_id": document_id, "chunk_id": chunk_id, "text": text, "page": pid,
        **(acl or acl_payload()),
    })


@pytest.fixture
def service():
    store = QdrantVectorStore(location=":memory:", collection_name="rag_search", vector_size=3)
    store.upsert_chunks([
        _point(1, [1.0, 0.0, 0.0], "doc_a", "chunk_001", "termination for breach"),
        _point(2, [0.95, 0.05, 0.0], "doc_a", "chunk_002", "termination notice"),
        _point(3, [0.9, 0.1, 0.0], "doc_b", "chunk_001", "breach of contract"),
        _point(4, [0.8, 0.2, 0.0], "doc_shared", "chunk_001", "civil code", **shared_corpus_payload()),
        _point(5, [1.0, 0.0, 0.0], "doc_other_tenant", "chunk_001", "termination",
               **acl_payload(client_id=OTHER_CLIENT_ID)),
    ])
    pipeline = M3RetrievalPipeline(
        vector_store=store, candidate_top_k=20, final_top_k=5,
        reranker_model_name="", use_mock_fallback=True,
    )
    return M2M3M4RAGService(
        query_pipeline=FakeQueryPipeline(),
        rag_service=M3M4RAGService(retrieval_pipeline=pipeline, orchestration_service=None),
        expected_embedding_dimension=3,
    )


def test_service_returns_documents_not_chunks_and_respects_tenant(service):
    result = service.search(query="termination", filters=scoped_filters())

    ids = [h.document_id for h in result.hits]
    assert sorted(ids) == ["doc_a", "doc_b", "doc_shared"]
    assert len(ids) == len(set(ids))
    assert "doc_other_tenant" not in ids
    assert next(h for h in result.hits if h.document_id == "doc_a").matched_chunks == 2
    assert result.total == 3 and result.query_id == "q_search"


def test_service_scopes_to_requested_document_ids(service):
    result = service.search(query="termination",
                            filters=scoped_filters(document_ids=["doc_b"]))
    assert [h.document_id for h in result.hits] == ["doc_b"]


def test_service_paginates(service):
    first = service.search(query="t", filters=scoped_filters(), page=1, page_size=2)
    second = service.search(query="t", filters=scoped_filters(), page=2, page_size=2)
    beyond = service.search(query="t", filters=scoped_filters(), page=3, page_size=2)

    assert (len(first.hits), len(second.hits), beyond.hits) == (2, 1, [])
    assert first.total == second.total == 3
    assert not {h.document_id for h in first.hits} & {h.document_id for h in second.hits}


def test_service_requires_an_access_scope_before_embedding(service):
    service.query_pipeline = FakeQueryPipeline(error=AssertionError("must not embed"))
    with pytest.raises(AccessScopeRequired):
        service.search(query="termination", filters=None)


def test_service_candidate_window_grows_with_page_and_is_capped(service):
    seen = []
    retrieval = service.rag_service.retrieval_pipeline
    original = retrieval.search_candidates
    retrieval.search_candidates = lambda q, candidate_top_k: seen.append(candidate_top_k) or original(q, candidate_top_k)

    service.search(query="t", filters=scoped_filters(), page=1, page_size=5)
    service.search(query="t", filters=scoped_filters(), page=3, page_size=10)
    service.search(query="t", filters=scoped_filters(), page=40, page_size=50)

    assert seen == [20, 90, 100]


def test_search_does_not_call_the_llm(service):
    assert service.rag_service.orchestration_service is None
    service.search(query="termination", filters=scoped_filters())


# ------------------------------------------------------------------ route


class RecordingSearchService:
    def __init__(self, error=None):
        self.error = error
        self.kwargs = None

    async def asearch(self, **kwargs):
        self.kwargs = kwargs
        if self.error:
            raise self.error
        return DocumentSearchResult(
            query_id="q_route",
            hits=[DocumentSearchHit(document_id="doc_a", score=0.91, snippet="termination …",
                                    chunk_id="chunk_002", page=4, section="Article 6",
                                    matched_chunks=2)],
            total=7, page=kwargs["page"], page_size=kwargs["page_size"],
            retrieval_ms=12.3, candidate_chunk_count=20,
        )


def _client(service):
    app = create_app(api_security_settings=APISecuritySettings(
        _env_file=None, environment="development", trusted_host_enforcement=False))
    app.dependency_overrides[get_raw_rag_service] = lambda: service
    return TestClient(app)


def test_route_returns_ranked_documents_with_server_side_scope():
    service = RecordingSearchService()
    with _client(service) as client:
        response = client.post(
            "/api/v1/rag/search",
            headers=IDENTITY_HEADERS,
            json={"query": "termination terms", "filters": {"document_ids": ["doc_a", "doc_b"]},
                  "page": 2, "page_size": 5},
        )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "query_id": "q_route",
        "hits": [{"document_id": "doc_a", "score": 0.91, "snippet": "termination …",
                  "chunk_id": "chunk_002", "page": 4, "section": "Article 6",
                  "matched_chunks": 2}],
        "total": 7, "page": 2, "page_size": 5,
    }
    assert service.kwargs["query"] == "termination terms"
    assert service.kwargs["filters"].document_ids == ["doc_a", "doc_b"]
    # Scope comes from the identity headers, never from the body.
    assert service.kwargs["filters"].access.client_id == TEST_CLIENT_ID


def test_route_requires_identity():
    with _client(RecordingSearchService()) as client:
        response = client.post("/api/v1/rag/search", json={"query": "x"})
    assert response.status_code == 401


def test_route_refuses_client_supplied_access_scope():
    service = RecordingSearchService()
    with _client(service) as client:
        response = client.post(
            "/api/v1/rag/search", headers=IDENTITY_HEADERS,
            json={"query": "x", "filters": {"access": {"client_id": "victim",
                                                       "max_confidentiality": "privileged"}}},
        )
    assert response.status_code == 400
    assert service.kwargs is None


@pytest.mark.parametrize("body", [
    {"query": "   "},
    {"query": "x", "page": 0},
    {"query": "x", "page_size": 51},
    {"query": "x", "unexpected": True},
])
def test_route_validates_request(body):
    service = RecordingSearchService()
    with _client(service) as client:
        response = client.post("/api/v1/rag/search", headers=IDENTITY_HEADERS, json=body)
    assert response.status_code == 422
    assert service.kwargs is None


@pytest.mark.parametrize(("error", "code"), [
    (M2QueryValidationError("bad"), 400),
    (M2EmbeddingContractError("bad"), 502),
    (M2QueryRuntimeError("down"), 503),
    (RerankerUnavailable("missing"), 503),
    (ValueError("bad"), 400),
])
def test_route_maps_runtime_errors(error, code):
    with _client(RecordingSearchService(error=error)) as client:
        response = client.post("/api/v1/rag/search", headers=IDENTITY_HEADERS,
                               json={"query": "termination"})
    assert response.status_code == code


def test_route_logs_metrics_without_query_text(caplog):
    with caplog.at_level(logging.INFO, logger="src.api.rag_routes"):
        with _client(RecordingSearchService()) as client:
            client.post("/api/v1/rag/search", headers=IDENTITY_HEADERS,
                        json={"query": "SECRET CLIENT QUESTION"})

    record = next(r for r in caplog.records if r.getMessage() == "rag_search_completed")
    assert record.document_count == 7 and record.candidate_chunk_count == 20
    assert all("SECRET CLIENT QUESTION" not in r.getMessage() + str(r.__dict__)
               for r in caplog.records)
