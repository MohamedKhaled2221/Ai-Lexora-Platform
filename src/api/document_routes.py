import logging
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)

from src.api.dependencies import (
    get_document_ingestion_service,
)
from src.api.identity import CallerIdentityDependency
from src.indexing import (
    DocumentIndexingError,
    DocumentIndexingRuntimeError,
    DocumentIngestionResult,
    DocumentIngestionService,
    M1DocumentProcessingError,
    M1ServiceUnavailableError,
)
from src.schemas.access_control import ConfidentialityLevel


logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/api/v1/documents",
    tags=["Documents"],
)


DocumentIngestionDependency = Annotated[
    DocumentIngestionService,
    Depends(
        get_document_ingestion_service
    ),
]


def _request_id(
    request: Request,
) -> str:
    return str(
        getattr(
            request.state,
            "request_id",
            "unknown",
        )
    )


@router.post(
    "/ingest",
    response_model=DocumentIngestionResult,
)
async def ingest_document(
    request: Request,
    service: DocumentIngestionDependency,
    identity: CallerIdentityDependency,
    file: UploadFile = File(...),
    document_id: Annotated[
        str | None,
        Query(
            min_length=1,
            max_length=200,
        ),
    ] = None,
    confidentiality_level: Annotated[
        ConfidentialityLevel | None,
        Query(
            description=(
                "Classification for this document. May only lower the "
                "caller's own ceiling, never raise it. Defaults to the "
                "ceiling itself."
            ),
        ),
    ] = None,
) -> DocumentIngestionResult:
    """
    Process and index one legal document.

    Flow:
        upload
            -> M1
            -> M2 BGE-M3
            -> Qdrant

    The access-control stamp comes from the authenticated caller and is
    written onto every chunk, overwriting anything M1 or the uploader
    supplied. A document's ACL is never derived from its contents.

    File contents and filenames are never written
    to operational logs.
    """

    file_name = (
        file.filename
        or "upload"
    )

    try:
        acl = identity.to_chunk_acl(
            confidentiality_level=(
                confidentiality_level
            ),
        )

    except ValueError as exc:
        logger.warning(
            "document_ingestion_rejected",
            extra={
                "request_id": (
                    _request_id(request)
                ),
                "failure_stage": (
                    "access_control"
                ),
                "error_type": (
                    type(exc).__name__
                ),
            },
        )

        raise HTTPException(
            status_code=(
                status.HTTP_403_FORBIDDEN
            ),
            detail=(
                "Cannot ingest a document above "
                "your own confidentiality "
                "ceiling."
            ),
        ) from exc

    try:
        result = await service.ingest_document(
            file_name=file_name,
            file_object=file.file,
            acl=acl,
            content_type=file.content_type,
            document_id=document_id,
        )

        logger.info(
            "document_ingestion_completed",
            extra={
                "request_id": (
                    _request_id(request)
                ),
                "chunks_indexed": (
                    result.chunks_indexed
                ),
                "status": "success",
            },
        )

        return result

    except M1DocumentProcessingError as exc:
        logger.warning(
            "document_ingestion_rejected",
            extra={
                "request_id": (
                    _request_id(request)
                ),
                "failure_stage": (
                    "document_processing"
                ),
                "error_type": (
                    type(exc).__name__
                ),
            },
        )

        allowed_statuses = {
            400,
            413,
            415,
            422,
        }

        safe_status = (
            exc.status_code
            if exc.status_code
            in allowed_statuses
            else 422
        )

        raise HTTPException(
            status_code=safe_status,
            detail=(
                "The uploaded document could "
                "not be processed."
            ),
        ) from exc

    except M1ServiceUnavailableError as exc:
        logger.error(
            "document_ingestion_failed",
            extra={
                "request_id": (
                    _request_id(request)
                ),
                "failure_stage": "m1",
                "error_type": (
                    type(exc).__name__
                ),
            },
        )

        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail=(
                "The local document-processing "
                "service is unavailable."
            ),
        ) from exc

    except DocumentIndexingError as exc:
        logger.error(
            "document_ingestion_failed",
            extra={
                "request_id": (
                    _request_id(request)
                ),
                "failure_stage": (
                    "indexing_contract"
                ),
                "error_type": (
                    type(exc).__name__
                ),
            },
        )

        raise HTTPException(
            status_code=(
                status.HTTP_502_BAD_GATEWAY
            ),
            detail=(
                "The document could not be "
                "indexed because an internal "
                "contract was invalid."
            ),
        ) from exc

    except DocumentIndexingRuntimeError as exc:
        logger.error(
            "document_ingestion_failed",
            extra={
                "request_id": (
                    _request_id(request)
                ),
                "failure_stage": "indexing",
                "error_type": (
                    type(exc).__name__
                ),
            },
        )

        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail=(
                "The local document-indexing "
                "runtime is unavailable."
            ),
        ) from exc

    finally:
        await file.close()
