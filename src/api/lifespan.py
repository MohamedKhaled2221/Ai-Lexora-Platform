import asyncio
from collections.abc import Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.orchestration import (
    M2M3M4RAGService,
    M3M4RAGService,
)
from src.indexing import (
    DocumentIngestionService,
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
):
    """
    Build the application lifespan handler.

    Production may initialize:
    - the existing M3 -> M4 RAG runtime
    - the new M2 -> M3 -> M4 raw-query runtime

    Unit tests may omit either runtime or inject fakes.
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

    @asynccontextmanager
    async def lifespan(
        app: FastAPI,
    ):
        app.state.rag_service = None
        app.state.raw_rag_service = None
        app.state.document_ingestion_service = None

        if rag_service_factory is not None:
            app.state.rag_service = (
                await asyncio.to_thread(
                    rag_service_factory
                )
            )

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

        try:
            yield

        finally:
            document_ingestion_service = getattr(
                app.state,
                "document_ingestion_service",
                None,
            )

            if document_ingestion_service is not None:
                await (
                    document_ingestion_service
                    .aclose()
                )

            app.state.document_ingestion_service = None
            app.state.raw_rag_service = None
            app.state.rag_service = None

    return lifespan