import asyncio
from collections.abc import Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api.package_runtime import (
    P3APIRuntime,
)
from src.indexing import (
    DocumentIngestionService,
)
from src.orchestration import (
    M2M3M4RAGService,
    M3M4RAGService,
)
from src.orchestration.p4_chat_service import (
    P4ChatService,
)


RAGServiceFactory = Callable[
    [],
    M3M4RAGService,
]


RawRAGServiceFactory = Callable[
    [M3M4RAGService],
    M2M3M4RAGService,
]


DocumentIngestionServiceFactory = Callable[
    [
        M3M4RAGService,
        M2M3M4RAGService,
    ],
    DocumentIngestionService,
]


P3GenerationRuntimeFactory = Callable[
    [],
    P3APIRuntime | None,
]


P4ChatServiceFactory = Callable[
    [
        M3M4RAGService,
        M2M3M4RAGService,
    ],
    P4ChatService,
]


def create_lifespan(
    rag_service_factory: (
        RAGServiceFactory | None
    ) = None,
    raw_rag_service_factory: (
        RawRAGServiceFactory | None
    ) = None,
    document_ingestion_service_factory: (
        DocumentIngestionServiceFactory
        | None
    ) = None,
    p3_generation_runtime_factory: (
        P3GenerationRuntimeFactory
        | None
    ) = None,
    p4_chat_service_factory: (
        P4ChatServiceFactory
        | None
    ) = None,
):
    """
    Build the application lifespan handler.

    Production may initialize:

    - M3 -> M4 legacy RAG runtime
    - M2 -> M3 -> M4 raw-query runtime
    - document ingestion/indexing runtime
    - Package 3 M5 -> M1 -> M4 generation runtime
    - Package 4 M6 -> M2 -> M3 -> M6 -> M4 runtime

    Tests may omit runtimes or inject fakes.
    """

    if (
        raw_rag_service_factory is not None
        and rag_service_factory is None
    ):
        raise ValueError(
            "raw_rag_service_factory requires "
            "rag_service_factory"
        )

    if (
        document_ingestion_service_factory
        is not None
        and (
            rag_service_factory is None
            or raw_rag_service_factory is None
        )
    ):
        raise ValueError(
            "document_ingestion_service_factory "
            "requires both RAG runtime factories"
        )

    if (
        p4_chat_service_factory is not None
        and (
            rag_service_factory is None
            or raw_rag_service_factory is None
        )
    ):
        raise ValueError(
            "p4_chat_service_factory requires "
            "both RAG runtime factories"
        )

    @asynccontextmanager
    async def lifespan(
        app: FastAPI,
    ):
        # -------------------------------------------------
        # Initialize state consistently for production
        # and tests.
        # -------------------------------------------------

        app.state.rag_service = None
        app.state.raw_rag_service = None
        app.state.document_ingestion_service = None
        app.state.p3_generation_runtime = None
        app.state.p4_chat_service = None

        # -------------------------------------------------
        # Existing RAG runtime
        # -------------------------------------------------

        if rag_service_factory is not None:
            app.state.rag_service = (
                await asyncio.to_thread(
                    rag_service_factory
                )
            )

        # -------------------------------------------------
        # Existing raw-query M2 -> M3 -> M4 runtime
        # -------------------------------------------------

        if (
            raw_rag_service_factory
            is not None
        ):
            app.state.raw_rag_service = (
                await asyncio.to_thread(
                    raw_rag_service_factory,
                    app.state.rag_service,
                )
            )

        # -------------------------------------------------
        # Existing document ingestion runtime
        # -------------------------------------------------

        if (
            document_ingestion_service_factory
            is not None
        ):
            app.state.document_ingestion_service = (
                document_ingestion_service_factory(
                    app.state.rag_service,
                    app.state.raw_rag_service,
                )
            )

        # -------------------------------------------------
        # Package 3
        #
        # May legitimately return None when P3_ENABLED
        # is false or approved M1 templates have not
        # been configured yet.
        # -------------------------------------------------

        if (
            p3_generation_runtime_factory
            is not None
        ):
            app.state.p3_generation_runtime = (
                await asyncio.to_thread(
                    p3_generation_runtime_factory
                )
            )

        # -------------------------------------------------
        # Package 4
        #
        # Reuses the already-loaded M2/M3 resources.
        # -------------------------------------------------

        if (
            p4_chat_service_factory
            is not None
        ):
            app.state.p4_chat_service = (
                await asyncio.to_thread(
                    p4_chat_service_factory,
                    app.state.rag_service,
                    app.state.raw_rag_service,
                )
            )

        try:
            yield

        finally:
            # ---------------------------------------------
            # Preserve existing async document cleanup.
            # ---------------------------------------------

            document_ingestion_service = getattr(
                app.state,
                "document_ingestion_service",
                None,
            )

            if (
                document_ingestion_service
                is not None
            ):
                await (
                    document_ingestion_service
                    .aclose()
                )

            # ---------------------------------------------
            # Drop references in reverse-ish dependency
            # order.
            # ---------------------------------------------

            app.state.p4_chat_service = None
            app.state.p3_generation_runtime = None
            app.state.document_ingestion_service = None
            app.state.raw_rag_service = None
            app.state.rag_service = None

    return lifespan