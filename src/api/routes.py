from fastapi import (
    APIRouter,
    Depends,
    Request,
    Response,
    status,
)

from src.api.health import (
    HealthResponse,
    ReadinessResponse,
    SystemReadinessChecker,
)


router = APIRouter()


def get_readiness_checker(
    request: Request,
) -> SystemReadinessChecker:
    rag_service = getattr(
        request.app.state,
        "rag_service",
        None,
    )

    raw_rag_service = getattr(
        request.app.state,
        "raw_rag_service",
        None,
    )

    embedding_runtime_ready = False
    embedding_dimension = None

    if raw_rag_service is not None:
        embedding_runtime_ready = bool(
            getattr(
                raw_rag_service,
                "embedding_runtime_ready",
                False,
            )
        )

        embedding_dimension = getattr(
            raw_rag_service,
            "validated_embedding_dimension",
            None,
        )

    return SystemReadinessChecker(
        rag_runtime_initialized=(
            rag_service is not None
        ),
        raw_rag_runtime_initialized=(
            raw_rag_service is not None
        ),
        embedding_runtime_ready=(
            embedding_runtime_ready
        ),
        embedding_dimension=(
            embedding_dimension
        ),
    )
@router.get(
    "/health",
    response_model=HealthResponse,
    tags=["System"],
)
async def health(
) -> HealthResponse:
    """
    Liveness endpoint.

    A successful response means the FastAPI process
    is running and accepting requests.
    """

    return HealthResponse(
        status="ok"
    )


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    tags=["System"],
)
async def ready(
    response: Response,
    checker: SystemReadinessChecker = Depends(
        get_readiness_checker
    ),
) -> ReadinessResponse:
    readiness = await checker.check()

    if readiness.status != "ready":
        response.status_code = (
            status.HTTP_503_SERVICE_UNAVAILABLE
        )

    return readiness
