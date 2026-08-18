from fastapi import (
    APIRouter,
    Depends,
    Response,
    status,
)

from src.api.health import (
    HealthResponse,
    M4ReadinessChecker,
    ReadinessResponse,
)


router = APIRouter()


def get_readiness_checker(
) -> M4ReadinessChecker:
    return M4ReadinessChecker()


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
    checker: M4ReadinessChecker = Depends(
        get_readiness_checker
    ),
) -> ReadinessResponse:
    """
    Readiness endpoint.

    Verifies that Ollama is reachable and that the
    configured M4 model is installed.
    """

    readiness = await checker.check()

    if readiness.status != "ready":
        response.status_code = (
            status.HTTP_503_SERVICE_UNAVAILABLE
        )

    return readiness
