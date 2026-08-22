from collections.abc import Callable

from fastapi import FastAPI

from src.api.ai_routes import (
    router as ai_router,
)
from src.api.errors import (
    register_exception_handlers,
)
from src.api.lifespan import (
    create_lifespan,
)
from src.api.observability import (
    register_observability_middleware,
)
from src.api.rag_routes import (
    router as rag_router,
)
from src.api.routes import (
    router as system_router,
)
from src.api.runtime import (
    build_rag_service,
    build_raw_rag_service,
)
from src.api.security import (
    APISecuritySettings,
    register_api_security_middleware,
)
from src.orchestration import (
    M2M3M4RAGService,
    M3M4RAGService,
)


def create_app(
    *,
    rag_service_factory: (
        Callable[
            [],
            M3M4RAGService,
        ]
        | None
    ) = None,
    raw_rag_service_factory: (
        Callable[
            [M3M4RAGService],
            M2M3M4RAGService,
        ]
        | None
    ) = None,
    api_security_settings: (
        APISecuritySettings | None
    ) = None,
) -> FastAPI:
    security_settings = (
        api_security_settings
        or APISecuritySettings()
    )

    docs_enabled = (
        security_settings
        .effective_docs_enabled
    )

    app = FastAPI(
        title="AI-Lexora API",
        version="0.1.0",
        description=(
            "Local multilingual legal "
            "intelligence API"
        ),
        debug=(
            security_settings.debug
        ),
        docs_url=(
            "/docs"
            if docs_enabled
            else None
        ),
        redoc_url=(
            "/redoc"
            if docs_enabled
            else None
        ),
        openapi_url=(
            "/openapi.json"
            if docs_enabled
            else None
        ),
        lifespan=create_lifespan(
            rag_service_factory,
            raw_rag_service_factory,
        ),
    )

    app.state.api_security_settings = (
        security_settings
    )

    register_api_security_middleware(
        app,
        security_settings,
    )

    register_observability_middleware(
        app
    )

    register_exception_handlers(
        app
    )

    app.include_router(
        system_router
    )

    app.include_router(
        ai_router
    )

    app.include_router(
        rag_router
    )

    return app


# Production application.
#
# Unit tests that call create_app() without a factory
# will not load Qdrant or the BGE reranker.
app = create_app(
    rag_service_factory=build_rag_service,
    raw_rag_service_factory=(
        build_raw_rag_service
    ),
)