import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import (
    HTTPException as StarletteHTTPException,
)


logger = logging.getLogger(
    "ai_lexora.errors"
)


class APIError(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    code: str
    message: str
    request_id: str


class APIErrorResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    error: APIError


def get_request_id(
    request: Request,
) -> str:
    """
    Return the server-generated request ID.

    The observability middleware should populate this
    before request processing reaches the route.
    """

    return getattr(
        request.state,
        "request_id",
        "unknown",
    )


def _error_response(
    *,
    request: Request,
    status_code: int,
    code: str,
    message: str,
) -> JSONResponse:
    payload = APIErrorResponse(
        error=APIError(
            code=code,
            message=message,
            request_id=get_request_id(
                request
            ),
        )
    )

    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump(),
        headers={
            "X-Request-ID": (
                payload.error.request_id
            )
        },
    )


def register_exception_handlers(
    app: FastAPI,
) -> None:
    """
    Register the common AI-Lexora API error format.
    """

    @app.exception_handler(
        StarletteHTTPException
    )
    async def http_exception_handler(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        message = (
            exc.detail
            if isinstance(
                exc.detail,
                str,
            )
            else "The request could not be completed."
        )

        code = (
            "NOT_FOUND"
            if exc.status_code == 404
            else "HTTP_ERROR"
        )

        return _error_response(
            request=request,
            status_code=exc.status_code,
            code=code,
            message=message,
        )

    @app.exception_handler(
        RequestValidationError
    )
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        logger.warning(
            "request_validation_failed",
            extra={
                "request_id": (
                    get_request_id(
                        request
                    )
                ),
                "error_count": len(
                    exc.errors()
                ),
            },
        )

        return _error_response(
            request=request,
            status_code=422,
            code="VALIDATION_ERROR",
            message=(
                "The request payload is invalid."
            ),
        )

    @app.exception_handler(
        Exception
    )
    async def unexpected_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        logger.error(
            "unexpected_api_error",
            extra={
                "request_id": (
                    get_request_id(
                        request
                    )
                ),
                "error_type": (
                    type(exc).__name__
                ),
            },
        )

        return _error_response(
            request=request,
            status_code=500,
            code="INTERNAL_ERROR",
            message=(
                "An unexpected internal error occurred."
            ),
        )
