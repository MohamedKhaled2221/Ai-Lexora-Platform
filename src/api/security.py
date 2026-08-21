from collections import deque
from typing import Literal

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import Field, model_validator
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)
from starlette.datastructures import (
    Headers,
    MutableHeaders,
)
from starlette.middleware.cors import (
    CORSMiddleware,
)
from starlette.types import (
    ASGIApp,
    Message,
    Receive,
    Scope,
    Send,
)

from src.api.errors import (
    APIError,
    APIErrorResponse,
)


class APISecuritySettings(BaseSettings):
    """
    Transport-level security configuration for
    the local AI-Lexora FastAPI application.
    """

    model_config = SettingsConfigDict(
        env_prefix="API_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    environment: Literal[
        "development",
        "production",
    ] = "development"

    debug: bool = False

    docs_enabled: bool | None = None

    max_request_body_bytes: int = Field(
        default=1_048_576,
        ge=1024,
    )

    trusted_host_enforcement: (
        bool | None
    ) = None

    trusted_hosts: list[str] = Field(
        default_factory=lambda: [
            "127.0.0.1",
            "localhost",
            "::1",
        ]
    )

    cors_allowed_origins: list[str] = Field(
        default_factory=list
    )

    cors_allowed_headers: list[str] = Field(
        default_factory=lambda: [
            "Content-Type",
        ]
    )

    cors_allow_credentials: bool = False

    @property
    def effective_docs_enabled(
        self,
    ) -> bool:
        if self.docs_enabled is not None:
            return self.docs_enabled

        return (
            self.environment
            == "development"
        )

    @property
    def effective_trusted_host_enforcement(
        self,
    ) -> bool:
        if (
            self.trusted_host_enforcement
            is not None
        ):
            return (
                self.trusted_host_enforcement
            )

        return (
            self.environment
            == "production"
        )

    @model_validator(mode="after")
    def validate_security_policy(
        self,
    ) -> "APISecuritySettings":
        if any(
            not host.strip()
            for host in self.trusted_hosts
        ):
            raise ValueError(
                "Trusted hosts cannot contain "
                "empty values"
            )

        if any(
            "*" in host
            for host in self.trusted_hosts
        ):
            raise ValueError(
                "Wildcard trusted hosts are "
                "not allowed"
            )

        if (
            self.effective_trusted_host_enforcement
            and not self.trusted_hosts
        ):
            raise ValueError(
                "trusted_hosts cannot be empty "
                "when trusted-host enforcement "
                "is enabled"
            )

        if (
            self.cors_allow_credentials
            and "*" in self.cors_allowed_origins
        ):
            raise ValueError(
                "Credentialed CORS cannot use "
                "a wildcard origin"
            )

        if (
            self.environment
            == "production"
        ):
            if self.debug:
                raise ValueError(
                    "API debug mode must be "
                    "disabled in production"
                )

            if self.docs_enabled is True:
                raise ValueError(
                    "API documentation must be "
                    "disabled in production"
                )

            if (
                self.trusted_host_enforcement
                is False
            ):
                raise ValueError(
                    "Trusted-host enforcement "
                    "cannot be disabled in "
                    "production"
                )

            if (
                "*"
                in self.cors_allowed_origins
            ):
                raise ValueError(
                    "Wildcard CORS origins are "
                    "not allowed in production"
                )

        return self


def _request_id_from_scope(
    scope: Scope,
) -> str:
    state = scope.get(
        "state"
    ) or {}

    return str(
        state.get(
            "request_id",
            "unknown",
        )
    )


def _api_error_response(
    *,
    scope: Scope,
    status_code: int,
    code: str,
    message: str,
) -> JSONResponse:
    request_id = (
        _request_id_from_scope(
            scope
        )
    )

    payload = APIErrorResponse(
        error=APIError(
            code=code,
            message=message,
            request_id=request_id,
        )
    )

    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump(),
        headers={
            "X-Request-ID": request_id,
        },
    )


def _extract_hostname(
    host_header: str,
) -> str:
    host_header = (
        host_header
        .strip()
        .lower()
    )

    if host_header.startswith("["):
        closing_bracket = (
            host_header.find("]")
        )

        if closing_bracket != -1:
            return (
                host_header[
                    1:closing_bracket
                ]
                .rstrip(".")
            )

    return (
        host_header
        .split(
            ":",
            maxsplit=1,
        )[0]
        .rstrip(".")
    )


class TrustedHostProtectionMiddleware:
    """
    Enforce an exact local host allowlist.

    Wildcard host patterns are intentionally not
    supported because AI-Lexora is intended for
    controlled local deployment.
    """

    def __init__(
        self,
        app: ASGIApp,
        allowed_hosts: list[str],
    ) -> None:
        self.app = app

        self.allowed_hosts = {
            host
            .strip()
            .lower()
            .rstrip(".")
            for host in allowed_hosts
        }

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(
                scope,
                receive,
                send,
            )
            return

        headers = Headers(
            scope=scope
        )

        hostname = _extract_hostname(
            headers.get(
                "host",
                "",
            )
        )

        if (
            hostname
            not in self.allowed_hosts
        ):
            response = (
                _api_error_response(
                    scope=scope,
                    status_code=400,
                    code="INVALID_HOST",
                    message=(
                        "The request host "
                        "is not allowed."
                    ),
                )
            )

            await response(
                scope,
                receive,
                send,
            )
            return

        await self.app(
            scope,
            receive,
            send,
        )


class RequestBodyLimitMiddleware:
    """
    Enforce a hard maximum HTTP request-body size.

    The body is buffered only up to the configured
    maximum before being replayed to FastAPI.
    """

    def __init__(
        self,
        app: ASGIApp,
        max_body_bytes: int,
    ) -> None:
        self.app = app

        self.max_body_bytes = (
            max_body_bytes
        )

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(
                scope,
                receive,
                send,
            )
            return

        headers = Headers(
            scope=scope
        )

        content_length = headers.get(
            "content-length"
        )

        if content_length is not None:
            try:
                declared_length = int(
                    content_length
                )
            except ValueError:
                declared_length = None

            if (
                declared_length is not None
                and declared_length
                > self.max_body_bytes
            ):
                response = (
                    _api_error_response(
                        scope=scope,
                        status_code=413,
                        code=(
                            "REQUEST_TOO_LARGE"
                        ),
                        message=(
                            "The request body "
                            "exceeds the "
                            "configured size "
                            "limit."
                        ),
                    )
                )

                await response(
                    scope,
                    receive,
                    send,
                )
                return

        buffered_messages: deque[
            Message
        ] = deque()

        total_bytes = 0

        while True:
            message = await receive()

            if (
                message["type"]
                == "http.disconnect"
            ):
                return

            if (
                message["type"]
                != "http.request"
            ):
                continue

            body = message.get(
                "body",
                b"",
            )

            total_bytes += len(
                body
            )

            if (
                total_bytes
                > self.max_body_bytes
            ):
                response = (
                    _api_error_response(
                        scope=scope,
                        status_code=413,
                        code=(
                            "REQUEST_TOO_LARGE"
                        ),
                        message=(
                            "The request body "
                            "exceeds the "
                            "configured size "
                            "limit."
                        ),
                    )
                )

                await response(
                    scope,
                    receive,
                    send,
                )
                return

            buffered_messages.append(
                message
            )

            if not message.get(
                "more_body",
                False,
            ):
                break

        async def replay_receive(
        ) -> Message:
            if buffered_messages:
                return (
                    buffered_messages
                    .popleft()
                )

            return {
                "type": "http.request",
                "body": b"",
                "more_body": False,
            }

        await self.app(
            scope,
            replay_receive,
            send,
        )


class SecurityHeadersMiddleware:
    """
    Add conservative security headers without
    assuming HTTPS or application authentication.
    """

    def __init__(
        self,
        app: ASGIApp,
    ) -> None:
        self.app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(
                scope,
                receive,
                send,
            )
            return

        async def send_with_headers(
            message: Message,
        ) -> None:
            if (
                message["type"]
                == "http.response.start"
            ):
                headers = MutableHeaders(
                    scope=message
                )

                headers.setdefault(
                    "X-Content-Type-Options",
                    "nosniff",
                )

                headers.setdefault(
                    "X-Frame-Options",
                    "DENY",
                )

                headers.setdefault(
                    "Referrer-Policy",
                    "no-referrer",
                )

                headers.setdefault(
                    "Permissions-Policy",
                    (
                        "camera=(), "
                        "microphone=(), "
                        "geolocation=()"
                    ),
                )

                headers.setdefault(
                    "Cache-Control",
                    "no-store",
                )

            await send(
                message
            )

        await self.app(
            scope,
            receive,
            send_with_headers,
        )


def register_api_security_middleware(
    app: FastAPI,
    settings: APISecuritySettings,
) -> None:
    """
    Register transport-hardening middleware.

    Observability is registered after this function
    by create_app(), which keeps request correlation
    outside the security middleware stack.
    """

    app.add_middleware(
        RequestBodyLimitMiddleware,
        max_body_bytes=(
            settings
            .max_request_body_bytes
        ),
    )

    if (
        settings
        .cors_allowed_origins
    ):
        app.add_middleware(
            CORSMiddleware,
            allow_origins=(
                settings
                .cors_allowed_origins
            ),
            allow_credentials=(
                settings
                .cors_allow_credentials
            ),
            allow_methods=[
                "GET",
                "POST",
            ],
            allow_headers=(
                settings
                .cors_allowed_headers
            ),
            expose_headers=[
                "X-Request-ID",
            ],
            max_age=600,
        )

    if (
        settings
        .effective_trusted_host_enforcement
    ):
        app.add_middleware(
            TrustedHostProtectionMiddleware,
            allowed_hosts=(
                settings.trusted_hosts
            ),
        )

    app.add_middleware(
        SecurityHeadersMiddleware
    )
