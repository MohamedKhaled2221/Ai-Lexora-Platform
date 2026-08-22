import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response


logger = logging.getLogger(
    "ai_lexora.http"
)


def register_observability_middleware(
    app: FastAPI,
) -> None:
    """
    Add request correlation and safe HTTP timing logs.

    The middleware intentionally does not inspect or log
    request bodies, query contents, authorization headers,
    retrieved evidence, or generated prompts.
    """

    @app.middleware("http")
    async def request_observability(
        request: Request,
        call_next: Callable[
            [Request],
            Awaitable[Response],
        ],
    ) -> Response:
        request_id = uuid.uuid4().hex

        request.state.request_id = (
            request_id
        )

        start_time = (
            time.perf_counter()
        )

        status_code = 500

        try:
            response = await call_next(
                request
            )

            status_code = (
                response.status_code
            )

            response.headers[
                "X-Request-ID"
            ] = request_id

            return response

        finally:
            duration_ms = (
                time.perf_counter()
                - start_time
            ) * 1000.0

            logger.info(
                "http_request_completed",
                extra={
                    "request_id": (
                        request_id
                    ),
                    "http_method": (
                        request.method
                    ),
                    "http_path": (
                        request.url.path
                    ),
                    "status_code": (
                        status_code
                    ),
                    "duration_ms": round(
                        duration_ms,
                        2,
                    ),
                },
            )
