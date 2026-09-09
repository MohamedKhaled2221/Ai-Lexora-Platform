"""
Stage 7 coverage: identity at the API boundary.

Two distinct properties:

* Ingestion stamps the ACL from the authenticated caller and overwrites
  whatever arrived with the document.
* Retrieval routes set the access scope themselves and refuse a request that
  tried to set its own.
"""

from io import BytesIO

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.dependencies import (
    get_document_ingestion_service,
    get_rag_service,
    get_raw_rag_service,
)
from src.api.identity import CallerIdentity
from src.api.security import APISecuritySettings
from src.indexing import DocumentIngestionResult
from src.schemas import AIResponse
from src.schemas.access_control import NO_MATTER_ID, ChunkACL
from tests.access_helpers import (
    IDENTITY_HEADERS,
    TEST_CLIENT_ID,
    identity_headers,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _RecordingIngestionService:
    def __init__(self):
        self.acl = None

    async def ingest_document(
        self,
        *,
        file_name,
        file_object,
        acl,
        content_type=None,
        document_id=None,
    ):
        self.acl = acl
        file_object.read()

        return DocumentIngestionResult(
            document_id="doc_001",
            source_file=file_name,
            file_type="pdf",
            document_type="contract",
            language="en",
            pages=1,
            chunks_indexed=1,
            embedding_model="fake",
            embedding_dimension=1024,
        )


class _RecordingRAGService:
    """Captures the filters/query the route actually forwarded."""

    def __init__(self):
        self.filters = None
        self.processed_query = None

    def _response(self):
        from src.orchestration import (
            RAGExecutionMetrics,
            RAGExecutionResult,
        )

        return RAGExecutionResult(
            response=AIResponse(
                query_id="q_001",
                answer="ok",
                citations=[],
                confidence=0.5,
            ),
            metrics=RAGExecutionMetrics(
                retrieval_ms=1.0,
                generation_ms=1.0,
                total_rag_ms=2.0,
                retrieved_chunk_count=0,
                citation_count=0,
            ),
        )

    async def aanswer_with_metrics(
        self,
        processed_query=None,
        *,
        question=None,
        filters=None,
    ):
        self.filters = filters
        self.processed_query = processed_query

        return self._response()


def _app(overrides):
    app = create_app(
        api_security_settings=APISecuritySettings(
            _env_file=None,
            environment="development",
            trusted_host_enforcement=False,
        )
    )

    for dependency, value in overrides.items():
        # A zero-argument closure, not `lambda v=value: v`: FastAPI reads the
        # override's signature and would treat a defaulted parameter as a
        # query parameter, injecting None in place of the service.
        app.dependency_overrides[dependency] = _returning(value)

    return app


def _returning(value):
    def _override():
        return value

    return _override


def _upload():
    return {
        "file": (
            "contract.pdf",
            BytesIO(b"%PDF-fake"),
            "application/pdf",
        )
    }


# ---------------------------------------------------------------------------
# Ingest: identity required, ACL stamped server-side
# ---------------------------------------------------------------------------


def test_ingest_requires_identity():
    service = _RecordingIngestionService()
    app = _app({get_document_ingestion_service: service})

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/documents/ingest",
            files=_upload(),
        )

    assert response.status_code == 401
    assert service.acl is None


def test_ingest_stamps_the_acl_from_the_caller():
    service = _RecordingIngestionService()
    app = _app({get_document_ingestion_service: service})

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/documents/ingest",
            files=_upload(),
            headers=identity_headers(
                client_id="client_042",
                matter_id="matter_7",
                max_confidentiality="privileged",
            ),
        )

    assert response.status_code == 200
    assert service.acl == ChunkACL(
        client_id="client_042",
        matter_id="matter_7",
        confidentiality_level="privileged",
    )


def test_ingest_without_a_matter_uses_the_client_level_sentinel():
    service = _RecordingIngestionService()
    app = _app({get_document_ingestion_service: service})

    with TestClient(app) as client:
        client.post(
            "/api/v1/documents/ingest",
            files=_upload(),
            headers=identity_headers(max_confidentiality="internal"),
        )

    assert service.acl.matter_id == NO_MATTER_ID
    assert service.acl.client_id == TEST_CLIENT_ID


def test_ingest_may_classify_below_the_ceiling():
    service = _RecordingIngestionService()
    app = _app({get_document_ingestion_service: service})

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/documents/ingest",
            params={"confidentiality_level": "public"},
            files=_upload(),
            headers=identity_headers(max_confidentiality="internal"),
        )

    assert response.status_code == 200
    assert service.acl.confidentiality_level == "public"


def test_ingest_cannot_classify_above_the_ceiling():
    service = _RecordingIngestionService()
    app = _app({get_document_ingestion_service: service})

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/documents/ingest",
            params={"confidentiality_level": "privileged"},
            files=_upload(),
            headers=identity_headers(max_confidentiality="internal"),
        )

    assert response.status_code == 403
    assert service.acl is None


def test_ingest_rejects_an_unknown_confidentiality_level():
    service = _RecordingIngestionService()
    app = _app({get_document_ingestion_service: service})

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/documents/ingest",
            params={"confidentiality_level": "secret"},
            files=_upload(),
            headers=IDENTITY_HEADERS,
        )

    assert response.status_code == 422
    assert service.acl is None


def test_ingest_service_refuses_a_call_with_no_acl():
    """The service is the backstop if a future route forgets."""

    from src.indexing import DocumentIndexingError
    from src.indexing.ingestion_service import (
        DocumentIngestionService,
    )

    service = DocumentIngestionService(
        m1_client=object(),
        indexing_service=object(),
    )

    with pytest.raises(DocumentIndexingError):
        import asyncio

        asyncio.run(
            service.ingest_document(
                file_name="x.pdf",
                file_object=BytesIO(b""),
                acl=None,
            )
        )


def test_stamping_overwrites_whatever_arrived_with_the_document():
    """
    M1 sees only the file and the uploader controls its contents, so neither
    is an authority on who may read the result.
    """

    from src.indexing.ingestion_service import (
        DocumentIngestionService,
    )
    from src.schemas import DocumentChunk

    hostile = DocumentChunk(
        document_id="doc_001",
        chunk_id="chunk_001",
        text="text",
        page=1,
        client_id="client_victim",
        matter_id="matter_victim",
        confidentiality_level="public",
    )

    stamped = DocumentIngestionService._stamp(
        [hostile],
        ChunkACL(
            client_id="client_042",
            matter_id="matter_7",
            confidentiality_level="internal",
        ),
    )

    assert stamped[0].client_id == "client_042"
    assert stamped[0].matter_id == "matter_7"
    assert stamped[0].confidentiality_level == "internal"


# ---------------------------------------------------------------------------
# /rag/ask
# ---------------------------------------------------------------------------


def _ask_body(**extra):
    body = {"question": "What are the termination terms?"}
    body.update(extra)

    return body


def test_ask_requires_identity():
    app = _app({get_raw_rag_service: _RecordingRAGService()})

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/rag/ask",
            json=_ask_body(),
        )

    assert response.status_code == 401


def test_ask_sets_the_scope_from_the_caller():
    service = _RecordingRAGService()
    app = _app({get_raw_rag_service: service})

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/rag/ask",
            json=_ask_body(),
            headers=identity_headers(
                client_id="client_042",
                max_confidentiality="internal",
            ),
        )

    assert response.status_code == 200
    assert service.filters.access is not None
    assert service.filters.access.client_id == "client_042"
    assert service.filters.access.max_confidentiality == "internal"


def test_ask_rejects_a_client_supplied_scope():
    service = _RecordingRAGService()
    app = _app({get_raw_rag_service: service})

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/rag/ask",
            json=_ask_body(
                filters={
                    "access": {
                        "client_id": "client_victim",
                        "max_confidentiality": "privileged",
                    }
                }
            ),
            headers=IDENTITY_HEADERS,
        )

    assert response.status_code == 400
    assert service.filters is None


def test_ask_probing_attempt_is_logged(caplog):
    import logging

    service = _RecordingRAGService()
    app = _app({get_raw_rag_service: service})

    with caplog.at_level(logging.WARNING, logger="src.api.identity"):
        with TestClient(app) as client:
            client.post(
                "/api/v1/rag/ask",
                json=_ask_body(
                    filters={
                        "access": {
                            "client_id": "client_victim",
                            "max_confidentiality": "privileged",
                        }
                    }
                ),
                headers=IDENTITY_HEADERS,
            )

    assert any(
        record.message == "client_supplied_access_scope_rejected"
        for record in caplog.records
    )


def test_ask_still_accepts_ordinary_relevance_filters():
    service = _RecordingRAGService()
    app = _app({get_raw_rag_service: service})

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/rag/ask",
            json=_ask_body(
                filters={
                    "document_type": "contract",
                    "language": "ar",
                }
            ),
            headers=IDENTITY_HEADERS,
        )

    assert response.status_code == 200
    assert service.filters.document_type == "contract"
    assert service.filters.access.client_id == TEST_CLIENT_ID


# ---------------------------------------------------------------------------
# /rag/answer
# ---------------------------------------------------------------------------


def _answer_body(filters=None):
    return {
        "processed_query": {
            "query_id": "q_001",
            "text_original": "termination",
            "normalized_text": "termination",
            "language": "en",
            "embedding": [0.1, 0.2, 0.3],
            "filters": filters or {},
        }
    }


def test_answer_requires_identity():
    app = _app({get_rag_service: _RecordingRAGService()})

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/rag/answer",
            json=_answer_body(),
        )

    assert response.status_code == 401


def test_answer_sets_the_scope_from_the_caller():
    service = _RecordingRAGService()
    app = _app({get_rag_service: service})

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/rag/answer",
            json=_answer_body(),
            headers=identity_headers(client_id="client_042"),
        )

    assert response.status_code == 200
    assert (
        service.processed_query.filters.access.client_id
        == "client_042"
    )


def test_answer_rejects_a_client_supplied_scope():
    service = _RecordingRAGService()
    app = _app({get_rag_service: service})

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/rag/answer",
            json=_answer_body(
                filters={
                    "access": {
                        "client_id": "client_victim",
                        "max_confidentiality": "privileged",
                    }
                }
            ),
            headers=IDENTITY_HEADERS,
        )

    assert response.status_code == 400
    assert service.processed_query is None


def test_a_caller_cannot_widen_scope_by_claiming_another_tenant():
    """
    The end-to-end property: what the body says about access is irrelevant,
    only the identity counts.
    """

    service = _RecordingRAGService()
    app = _app({get_raw_rag_service: service})

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/rag/ask",
            json=_ask_body(),
            headers=identity_headers(client_id="client_042"),
        )

    assert response.status_code == 200

    scope = service.filters.access

    assert scope.client_id == "client_042"
    assert scope.allowed_client_ids == ["client_042", "_shared"]


def test_identity_to_scope_is_the_only_source_of_a_scope():
    identity = CallerIdentity(
        client_id="client_042",
        max_confidentiality="internal",
    )

    scope = identity.to_scope()

    assert scope.client_id == "client_042"
    assert scope.allowed_confidentiality_levels == [
        "public",
        "internal",
    ]
