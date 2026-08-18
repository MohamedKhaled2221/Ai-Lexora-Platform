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

    return SystemReadinessChecker(
        rag_runtime_initialized=(
            rag_service is not None
        )
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
