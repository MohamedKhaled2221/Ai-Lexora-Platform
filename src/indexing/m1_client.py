from __future__ import annotations

from typing import BinaryIO

import httpx
from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.schemas import DocumentChunk


class M1ClientSettings(BaseSettings):
    """
    Configuration for the internal M1 document-processing service.
    """

    model_config = SettingsConfigDict(
        env_prefix="M1_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    base_url: str = "http://127.0.0.1:8001"

    timeout_seconds: float = Field(
        default=300.0,
        gt=0,
    )


class M1ServiceError(RuntimeError):
    """Base error for M1 communication failures."""


class M1ServiceUnavailableError(M1ServiceError):
    """M1 cannot currently be reached."""


class M1DocumentProcessingError(M1ServiceError):
    """
    M1 received the upload but rejected or could not
    process the document.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 422,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code


class M1ContractError(M1ServiceError):
    """M1 returned a response that violates the shared contract."""


class M1IngestResponse(BaseModel):
    """
    Internal representation of M1 POST /ingest.

    Diagnostic fields that Package 1 does not need are intentionally ignored.
    """

    model_config = ConfigDict(
        extra="ignore"
    )

    document_id: str = Field(
        ...,
        min_length=1,
    )

    source_file: str

    file_type: str

    pdf_kind: str | None = None

    document_type: str

    language: str

    n_pages: int = Field(
        ...,
        ge=0,
    )

    n_chunks: int = Field(
        ...,
        ge=0,
    )

    succeeded: bool

    chunks: list[DocumentChunk]

    warnings: list[str] = Field(
        default_factory=list
    )


class M1Client:
    """
    Local HTTP adapter for Member 1's document-processing service.

    The client deliberately knows nothing about extraction/OCR internals.
    """

    def __init__(
        self,
        settings: M1ClientSettings | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = (
            settings
            or M1ClientSettings()
        )

        self._http_client = http_client
        self._owns_client = (
            http_client is None
        )

    async def ingest_document(
        self,
        *,
        file_name: str,
        file_object: BinaryIO,
        content_type: str | None = None,
        document_id: str | None = None,
    ) -> M1IngestResponse:
        """
        Send one uploaded document to M1 and validate its response.

        Legal document contents are never included in exception messages.
        """

        client = self._http_client

        if client is None:
            client = httpx.AsyncClient(
                base_url=self.settings.base_url,
                timeout=httpx.Timeout(
                    self.settings.timeout_seconds
                ),
            )

            self._http_client = client

        params: dict[str, str] = {}

        if document_id is not None:
            params["document_id"] = (
                document_id
            )

        try:
            file_object.seek(0)

            response = await client.post(
                "/ingest",
                params=params,
                files={
                    "file": (
                        file_name,
                        file_object,
                        content_type
                        or "application/octet-stream",
                    )
                },
            )

        except (
            httpx.ConnectError,
            httpx.ConnectTimeout,
            httpx.ReadTimeout,
            httpx.WriteTimeout,
        ) as exc:
            raise M1ServiceUnavailableError(
                "The local M1 document-processing "
                "service is unavailable."
            ) from exc

        except httpx.HTTPError as exc:
            raise M1ServiceUnavailableError(
                "Communication with the local M1 "
                "document-processing service failed."
            ) from exc

        if response.status_code == 413:
            raise M1DocumentProcessingError(
                "The uploaded document exceeds "
                "the M1 file-size limit.",
                status_code=413,
            )

        if response.status_code == 415:
            raise M1DocumentProcessingError(
                "The uploaded document type is "
                "not supported by M1.",
                status_code=415,
            )

        if response.status_code == 400:
            raise M1DocumentProcessingError(
                "M1 rejected the uploaded document.",
                status_code=400,
            )

        if response.status_code == 422:
            raise M1DocumentProcessingError(
                "M1 could not extract usable legal "
                "content from the document.",
                status_code=422,
            )

        if response.status_code >= 500:
            raise M1ServiceUnavailableError(
                "The local M1 document-processing "
                "service failed."
            )

        if not response.is_success:
            raise M1DocumentProcessingError(
                "M1 rejected the uploaded document.",
                status_code=422,
            )

        try:
            result = M1IngestResponse.model_validate(
                response.json()
            )

        except (
            ValueError,
            TypeError,
        ) as exc:
            raise M1ContractError(
                "M1 returned an invalid ingestion "
                "response."
            ) from exc

        if (
            not result.succeeded
            or not result.chunks
        ):
            raise M1DocumentProcessingError(
                "M1 did not produce searchable "
                "document chunks."
            )

        if (
            result.n_chunks
            != len(result.chunks)
        ):
            raise M1ContractError(
                "M1 chunk-count metadata does not "
                "match the returned chunks."
            )

        if any(
            chunk.document_id
            != result.document_id
            for chunk in result.chunks
        ):
            raise M1ContractError(
                "M1 returned inconsistent "
                "document identifiers."
            )

        return result

    async def aclose(self) -> None:
        if (
            self._owns_client
            and self._http_client is not None
        ):
            await self._http_client.aclose()

            self._http_client = None
