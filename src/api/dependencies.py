from functools import lru_cache

from src.orchestration import (
    M4OrchestrationService,
    M3M4RAGService,
)

from fastapi import (
    HTTPException,
    Request,
    status,
)

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


@lru_cache(maxsize=1)
def get_m4_orchestration_service(
) -> M4OrchestrationService:
    """
    Return the process-wide M4 orchestration service.

    The service is created lazily on the first request
    and reused for subsequent requests.
    """

    return M4OrchestrationService()
