from functools import lru_cache

from src.orchestration import (
    M4OrchestrationService,
)


@lru_cache(maxsize=1)
def get_m4_orchestration_service(
) -> M4OrchestrationService:
    """
    Return the process-wide M4 orchestration service.

    The service is created lazily on the first request
    and reused for subsequent requests.
    """

    return M4OrchestrationService()
