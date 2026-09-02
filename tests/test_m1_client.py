import io

import httpx
import pytest

from src.indexing import (
    M1Client,
    M1ClientSettings,
    M1ContractError,
    M1DocumentProcessingError,
    M1ServiceUnavailableError,
)


def make_settings():
    return M1ClientSettings(
        base_url="http://m1.test",
        timeout_seconds=5,
    )


def valid_response():
    return {
        "document_id": "doc_001",
        "source_file": "contract.pdf",
        "file_type": "pdf",
        "pdf_kind": "text",
        "document_type": "contract",
        "language": "en",
        "n_pages": 2,
        "n_chunks": 2,
        "succeeded": True,
        "chunks": [
            {
                "document_id": "doc_001",
                "chunk_id": "chunk_001",
                "text": "Termination clause.",
                "page": 1,
                "section": "Termination",
                "clause": "Clause 1",
                "language": "en",
                "document_type": "contract",
                "metadata": {
                    "jurisdiction": "Egypt"
                },
            },
            {
                "document_id": "doc_001",
                "chunk_id": "chunk_002",
                "text": "Payment clause.",
                "page": 2,
                "section": "Payment",
                "clause": "Clause 2",
                "language": "en",
                "document_type": "contract",
                "metadata": {
                    "jurisdiction": "Egypt"
                },
            },
        ],
        "warnings": [],
    }


@pytest.mark.asyncio
async def test_m1_client_validates_success_response():
    async def handler(request):
        assert request.url.path == "/ingest"

        return httpx.Response(
            200,
            json=valid_response(),
        )

    transport = httpx.MockTransport(
        handler
    )

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://m1.test",
    ) as http_client:
        client = M1Client(
            settings=make_settings(),
            http_client=http_client,
        )

        result = await client.ingest_document(
            file_name="contract.pdf",
            file_object=io.BytesIO(
                b"fake-pdf"
            ),
            content_type="application/pdf",
        )

    assert result.document_id == "doc_001"
    assert len(result.chunks) == 2
    assert (
        result.chunks[0].section
        == "Termination"
    )


@pytest.mark.asyncio
async def test_m1_client_rejects_chunk_count_mismatch():
    payload = valid_response()
    payload["n_chunks"] = 3

    async def handler(request):
        return httpx.Response(
            200,
            json=payload,
        )

    transport = httpx.MockTransport(
        handler
    )

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://m1.test",
    ) as http_client:
        client = M1Client(
            settings=make_settings(),
            http_client=http_client,
        )

        with pytest.raises(
            M1ContractError
        ):
            await client.ingest_document(
                file_name="contract.pdf",
                file_object=io.BytesIO(
                    b"fake-pdf"
                ),
            )


@pytest.mark.asyncio
async def test_m1_client_maps_processing_failure():
    async def handler(request):
        return httpx.Response(
            422,
            json={
                "detail": "private diagnostic"
            },
        )

    transport = httpx.MockTransport(
        handler
    )

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://m1.test",
    ) as http_client:
        client = M1Client(
            settings=make_settings(),
            http_client=http_client,
        )

        with pytest.raises(
            M1DocumentProcessingError
        ):
            await client.ingest_document(
                file_name="bad.pdf",
                file_object=io.BytesIO(
                    b"bad"
                ),
            )


@pytest.mark.asyncio
async def test_m1_client_maps_service_failure():
    async def handler(request):
        return httpx.Response(
            503
        )

    transport = httpx.MockTransport(
        handler
    )

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://m1.test",
    ) as http_client:
        client = M1Client(
            settings=make_settings(),
            http_client=http_client,
        )

        with pytest.raises(
            M1ServiceUnavailableError
        ):
            await client.ingest_document(
                file_name="contract.pdf",
                file_object=io.BytesIO(
                    b"fake"
                ),
            )
