from io import BytesIO

from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.dependencies import (
    get_document_ingestion_service,
)
from src.api.security import (
    APISecuritySettings,
)
from src.indexing import (
    DocumentIngestionResult,
    M1DocumentProcessingError,
    M1ServiceUnavailableError,
)


class FakeDocumentIngestionService:
    def __init__(
        self,
        *,
        error=None,
    ):
        self.error = error
        self.calls = []

    async def ingest_document(
        self,
        *,
        file_name,
        file_object,
        content_type=None,
        document_id=None,
    ):
        self.calls.append(
            {
                "file_name": file_name,
                "content_type": content_type,
                "document_id": document_id,
                "bytes": file_object.read(),
            }
        )

        if self.error is not None:
            raise self.error

        return DocumentIngestionResult(
            document_id=(
                document_id
                or "doc_001"
            ),
            source_file=file_name,
            file_type="pdf",
            document_type="contract",
            language="en",
            pages=2,
            chunks_indexed=4,
            embedding_model="fake-bge-m3",
            embedding_dimension=1024,
        )


def make_app(
    service,
    *,
    max_body_bytes=5_242_880,
):
    app = create_app(
        api_security_settings=(
            APISecuritySettings(
                environment="development",
                trusted_host_enforcement=False,
                max_request_body_bytes=(
                    max_body_bytes
                ),
            )
        )
    )

    app.dependency_overrides[
        get_document_ingestion_service
    ] = lambda: service

    return app


def test_document_ingestion_endpoint():
    service = (
        FakeDocumentIngestionService()
    )

    app = make_app(service)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/documents/ingest",
            params={
                "document_id": "doc_001",
            },
            files={
                "file": (
                    "contract.pdf",
                    BytesIO(b"%PDF-fake"),
                    "application/pdf",
                )
            },
        )

    assert response.status_code == 200

    body = response.json()

    assert (
        body["document_id"]
        == "doc_001"
    )
    assert body["status"] == "indexed"
    assert body["chunks_indexed"] == 4
    assert (
        body["embedding_dimension"]
        == 1024
    )

    assert len(service.calls) == 1
    assert (
        service.calls[0]["file_name"]
        == "contract.pdf"
    )


def test_document_ingestion_maps_unsupported_file():
    service = FakeDocumentIngestionService(
        error=M1DocumentProcessingError(
            "private diagnostic",
            status_code=415,
        )
    )

    app = make_app(service)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/documents/ingest",
            files={
                "file": (
                    "bad.exe",
                    b"bad",
                    "application/octet-stream",
                )
            },
        )

    assert response.status_code == 415

    assert (
        "private diagnostic"
        not in response.text
    )


def test_document_ingestion_maps_m1_unavailable():
    service = FakeDocumentIngestionService(
        error=M1ServiceUnavailableError(
            "secret connection detail"
        )
    )

    app = make_app(service)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/documents/ingest",
            files={
                "file": (
                    "contract.pdf",
                    b"fake",
                    "application/pdf",
                )
            },
        )

    assert response.status_code == 503

    assert (
        "secret connection detail"
        not in response.text
    )


def test_document_ingestion_respects_body_limit():
    service = (
        FakeDocumentIngestionService()
    )

    app = make_app(
        service,
        max_body_bytes=1024,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/documents/ingest",
            files={
                "file": (
                    "large.pdf",
                    b"x" * 2048,
                    "application/pdf",
                )
            },
        )

    assert response.status_code == 413
    assert len(service.calls) == 0
