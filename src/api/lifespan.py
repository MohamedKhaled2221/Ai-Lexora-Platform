import asyncio
from collections.abc import Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.orchestration import (
    M3M4RAGService,
)


RAGServiceFactory = Callable[
    [],
    M3M4RAGService,
]


def create_lifespan(
    rag_service_factory: (
        RAGServiceFactory | None
    ) = None,
):
    """
    Build the application lifespan handler.

    Production supplies the real RAG factory.
    Unit tests may omit it or inject a fake factory.
    """

    @asynccontextmanager
    async def lifespan(
        app: FastAPI,
    ):
        app.state.rag_service = None

        if rag_service_factory is not None:
            app.state.rag_service = (
                await asyncio.to_thread(
                    rag_service_factory
                )
            )

        yield

        app.state.rag_service = None

    return lifespan
