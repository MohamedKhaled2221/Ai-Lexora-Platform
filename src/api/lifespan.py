import asyncio
from collections.abc import Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.orchestration import (
    M2M3M4RAGService,
    M3M4RAGService,
)


RAGServiceFactory = Callable[
    [],
    M3M4RAGService,
]


RawRAGServiceFactory = Callable[
    [M3M4RAGService],
    M2M3M4RAGService,
]


def create_lifespan(
    rag_service_factory: (
        RAGServiceFactory | None
    ) = None,
    raw_rag_service_factory: (
        RawRAGServiceFactory | None
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

    @asynccontextmanager
    async def lifespan(
        app: FastAPI,
    ):
        app.state.rag_service = None
        app.state.raw_rag_service = None

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

        yield

        app.state.raw_rag_service = None
        app.state.rag_service = None

    return lifespan