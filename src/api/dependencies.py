from functools import lru_cache

from src.orchestration import (
    M2M3M4RAGService,
    M4OrchestrationService,
    M3M4RAGService,
)

from fastapi import (
    HTTPException,
    Request,
    status,
)
from src.indexing import (
    DocumentIngestionService,
)
from src.orchestration.p3_orchestrator import (
    P3M4Orchestrator,
)
from src.orchestration.p4_orchestrator import (
    P4M4Orchestrator,
)
from pathlib import Path

from src.clause_engine.service import (
    M5ClauseService,
)
from src.orchestration.m5_grounding_adapter import (
    M5GroundingAdapter,
)
from src.orchestration.p3_m5_service import (
    P3M5ValidationService,
)
def get_document_ingestion_service(
    request: Request,
) -> DocumentIngestionService:
    """
    Retrieve the process-wide M1 -> M2 -> Qdrant
    document ingestion runtime.
    """

    service = getattr(
        request.app.state,
        "document_ingestion_service",
        None,
    )

    if service is None:
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail=(
                "The document-ingestion runtime "
                "is not initialized."
            ),
        )

    return service

def get_rag_service(
    request: Request,
) -> M3M4RAGService:
    """
    Retrieve the process-wide RAG service created
    during FastAPI lifespan startup.
    """

    service = getattr(
        request.app.state,
        "rag_service",
        None,
    )

    if service is None:
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail=(
                "The RAG runtime is not initialized."
            ),
        )

    return service

def get_raw_rag_service(
    request: Request,
) -> M2M3M4RAGService:
    """
    Retrieve the process-wide raw-query
    M2 -> M3 -> M4 service.
    """

    service = getattr(
        request.app.state,
        "raw_rag_service",
        None,
    )

    if service is None:
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail=(
                "The raw-query RAG runtime "
                "is not initialized."
            ),
        )

    return service

@lru_cache(maxsize=1)
def get_m4_orchestration_service(
) -> M4OrchestrationService:
    """
    Return the process-wide M4 orchestration service.

    The service is created lazily on the first request
    and reused for subsequent requests.
    """

    return M4OrchestrationService()

@lru_cache(maxsize=1)
def get_p3_m4_orchestrator(
) -> P3M4Orchestrator:
    return P3M4Orchestrator()


@lru_cache(maxsize=1)
def get_p4_m4_orchestrator(
) -> P4M4Orchestrator:
    return P4M4Orchestrator()

@lru_cache(maxsize=1)
def get_m5_clause_service(
) -> M5ClauseService:
    """
    Load the authoritative local M5 clause library.

    Resolve paths relative to the repository rather than the current
    working directory so API startup is stable.
    """

    project_root = (
        Path(__file__)
        .resolve()
        .parents[2]
    )

    return M5ClauseService(
        library_path=(
            project_root
            / "data"
            / "clause_library.json"
        ),
        requirements_path=(
            project_root
            / "data"
            / "template_requirements.json"
        ),
    )


@lru_cache(maxsize=1)
def get_m5_grounding_adapter(
) -> M5GroundingAdapter:
    return M5GroundingAdapter(
        get_m5_clause_service()
    )


@lru_cache(maxsize=1)
def get_p3_m5_validation_service(
) -> P3M5ValidationService:
    return P3M5ValidationService(
        m5_adapter=(
            get_m5_grounding_adapter()
        ),
        m4_orchestrator=(
            get_p3_m4_orchestrator()
        ),
    )
