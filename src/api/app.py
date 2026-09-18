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
    build_document_ingestion_service,
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

from src.api.risk_routes import router as risk_router

from src.api.document_routes import (
    router as document_router,
)
from src.api.m4_p3_p4_routes import (
    router as m4_p3_p4_router,
)
from src.api.package_routes import (
    router as package_router,
)

from src.api.package_runtime import (
    build_p3_api_runtime,
    build_p4_chat_service,
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
    document_ingestion_service_factory: (
        Callable[
            [
                M3M4RAGService,
                M2M3M4RAGService,
            ],
            object,
        ]
        | None
    ) = None,
    p3_generation_runtime_factory=None,
    p4_chat_service_factory=None,
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
            rag_service_factory=(
                rag_service_factory
            ),
            raw_rag_service_factory=(
                raw_rag_service_factory
            ),
            document_ingestion_service_factory=(
                document_ingestion_service_factory
            ),
            p3_generation_runtime_factory=(
                p3_generation_runtime_factory
            ),
            p4_chat_service_factory=(
                p4_chat_service_factory
            ),
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

    app.include_router(
        document_router
    )

    app.include_router(
        risk_router
    )
    app.include_router(
        m4_p3_p4_router
    )

    app.include_router(
        package_router
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
    document_ingestion_service_factory=(
        build_document_ingestion_service
    ),
    p3_generation_runtime_factory=(
        build_p3_api_runtime
    ),
    p4_chat_service_factory=(
        build_p4_chat_service
    ),
)