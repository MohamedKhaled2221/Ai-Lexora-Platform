import asyncio
import logging
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict

from src.api.runtime import RAGRuntimeSettings
from src.orchestration import M4Settings


logger = logging.getLogger(__name__)


class HealthResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    status: Literal["ok"]


class ReadinessResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    status: Literal[
        "ready",
        "not_ready",
    ]

    ollama_reachable: bool
    model_available: bool
    model_name: str

    qdrant_reachable: bool
    qdrant_collection_available: bool
    qdrant_collection_name: str

    rag_runtime_initialized: bool
    raw_rag_runtime_initialized: bool

    embedding_runtime_ready: bool

    embedding_dimension: int | None

    expected_embedding_dimension: int

    detail: str | None = None


class SystemReadinessChecker:
    """
    Check whether the dependencies required by the
    local RAG application are currently usable.

    Readiness covers:
    - Ollama reachability
    - configured Qwen model availability
    - Qdrant reachability
    - configured Qdrant collection availability
    - initialized M3 -> M4 RAG runtime
    """

    def __init__(
        self,
        *,
        m4_settings: M4Settings | None = None,
        rag_settings: RAGRuntimeSettings | None = None,
        rag_runtime_initialized: bool = False,
        raw_rag_runtime_initialized: bool = False,
        embedding_runtime_ready: bool = False,
        embedding_dimension: int | None = None,
    ) -> None:
        self.m4_settings = (
            m4_settings
            or M4Settings()
        )

        self.rag_settings = (
            rag_settings
            or RAGRuntimeSettings()
        )

        self.rag_runtime_initialized = (
            rag_runtime_initialized
        )
        
        self.raw_rag_runtime_initialized = (
            raw_rag_runtime_initialized
        )

        self.embedding_runtime_ready = (
            embedding_runtime_ready
        )

        self.embedding_dimension = (
            embedding_dimension
        )

    async def check(
        self,
    ) -> ReadinessResponse:
        timeout_seconds = min(
            self.m4_settings.request_timeout_seconds,
            5.0,
        )

        async with httpx.AsyncClient(
            timeout=timeout_seconds,
        ) as client:
            (
                ollama_result,
                qdrant_result,
            ) = await asyncio.gather(
                self._check_ollama(
                    client
                ),
                self._check_qdrant(
                    client
                ),
            )

        (
            ollama_reachable,
            model_available,
        ) = ollama_result

        (
            qdrant_reachable,
            qdrant_collection_available,
        ) = qdrant_result

        issues: list[str] = []

        if not ollama_reachable:
            issues.append(
                "Ollama is unreachable."
            )
        elif not model_available:
            issues.append(
                "Configured Ollama model "
                "is unavailable."
            )

        if not qdrant_reachable:
            issues.append(
                "Qdrant is unreachable."
            )
        elif not qdrant_collection_available:
            issues.append(
                "Configured Qdrant collection "
                "is unavailable."
            )

        if not self.rag_runtime_initialized:
            issues.append(
                "RAG runtime is not initialized."
            )
        
        if not self.raw_rag_runtime_initialized:
            issues.append(
                "Raw-query RAG runtime is not initialized."
            )

        if not self.embedding_runtime_ready:
            issues.append(
                "M2 embedding runtime is not ready."
            )

        ready = (
            ollama_reachable
            and model_available
            and qdrant_reachable
            and qdrant_collection_available
            and self.rag_runtime_initialized
            and self.raw_rag_runtime_initialized
            and self.embedding_runtime_ready
        )

        return ReadinessResponse(
            status=(
                "ready"
                if ready
                else "not_ready"
            ),
            ollama_reachable=(
                ollama_reachable
            ),
            model_available=(
                model_available
            ),
            model_name=(
                self.m4_settings.model_name
            ),
            qdrant_reachable=(
                qdrant_reachable
            ),
            qdrant_collection_available=(
                qdrant_collection_available
            ),
            qdrant_collection_name=(
                self.rag_settings
                .qdrant_collection_name
            ),
            rag_runtime_initialized=(
                self.rag_runtime_initialized
            ),
            raw_rag_runtime_initialized=(
                self.raw_rag_runtime_initialized
            ),
            embedding_runtime_ready=(
                self.embedding_runtime_ready
            ),
            embedding_dimension=(
                self.embedding_dimension
            ),
            expected_embedding_dimension=(
                self.rag_settings
                .qdrant_vector_size
            ),
            detail=(
                "; ".join(issues)
                if issues
                else None
            ),
        )

    async def _check_ollama(
        self,
        client: httpx.AsyncClient,
    ) -> tuple[bool, bool]:
        url = (
            f"{self.m4_settings.ollama_base_url}"
            "/api/tags"
        )

        try:
            response = await client.get(
                url
            )

            response.raise_for_status()

            payload = response.json()

        except (
            httpx.HTTPError,
            OSError,
            ValueError,
        ) as exc:
            logger.warning(
                "ollama_readiness_check_failed",
                extra={
                    "error_type": (
                        type(exc).__name__
                    ),
                },
            )

            return False, False

        if not isinstance(
            payload,
            dict,
        ):
            return False, False

        models = payload.get(
            "models",
            []
        )

        available_names: set[str] = set()

        if isinstance(
            models,
            list,
        ):
            for model in models:
                if not isinstance(
                    model,
                    dict,
                ):
                    continue

                for field in (
                    "name",
                    "model",
                ):
                    value = model.get(
                        field
                    )

                    if isinstance(
                        value,
                        str,
                    ):
                        available_names.add(
                            value
                        )

        return (
            True,
            (
                self.m4_settings.model_name
                in available_names
            ),
        )

    async def _check_qdrant(
        self,
        client: httpx.AsyncClient,
    ) -> tuple[bool, bool]:
        location = (
            self.rag_settings
            .qdrant_location
            .rstrip("/")
        )

        if not location.startswith(
            (
                "http://",
                "https://",
            )
        ):
            logger.warning(
                "Qdrant readiness requires an "
                "HTTP(S) Qdrant server location."
            )

            return False, False

        url = (
            f"{location}/collections"
        )

        try:
            response = await client.get(
                url
            )

            response.raise_for_status()

            payload = response.json()

        except (
            httpx.HTTPError,
            OSError,
            ValueError,
        ) as exc:
            logger.warning(
                "qdrant_readiness_check_failed",
                extra={
                    "error_type": (
                        type(exc).__name__
                    ),
                },
            )

            return False, False

        if not isinstance(
            payload,
            dict,
        ):
            return False, False

        result = payload.get(
            "result"
        )

        if not isinstance(
            result,
            dict,
        ):
            return True, False

        collections = result.get(
            "collections",
            []
        )

        collection_names: set[str] = set()

        if isinstance(
            collections,
            list,
        ):
            for collection in collections:
                if not isinstance(
                    collection,
                    dict,
                ):
                    continue

                name = collection.get(
                    "name"
                )

                if isinstance(
                    name,
                    str,
                ):
                    collection_names.add(
                        name
                    )

        return (
            True,
            (
                self.rag_settings
                .qdrant_collection_name
                in collection_names
            ),
        )