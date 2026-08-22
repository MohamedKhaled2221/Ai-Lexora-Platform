import os
from pydantic import Field, model_validator
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)

from src.orchestration import (
    M2M3M4RAGService,
    M3M4RAGService,
    M4OrchestrationService,
)
from src.pipeline import M3RetrievalPipeline
from src.vector_store.qdrant_manager import (
    QdrantVectorStore,
)

_TRUE_VALUES = {
    "1",
    "true",
    "yes",
    "on",
}


def _environment_flag_enabled(
    name: str,
) -> bool:
    value = os.getenv(
        name,
        ""
    )

    return (
        value.strip().lower()
        in _TRUE_VALUES
    )




class RAGRuntimeSettings(BaseSettings):
    """
    Deployment/runtime configuration for the composed
    M3 -> M4 RAG service.
    """

    model_config = SettingsConfigDict(
        env_prefix="RAG_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        str_strip_whitespace=True,
    )

    qdrant_location: str = (
        "http://localhost:6333"
    )

    qdrant_collection_name: str = (
        "legal_documents"
    )

    qdrant_vector_size: int = Field(
        default=1024,
        ge=1,
    )

    candidate_top_k: int = Field(
        default=20,
        ge=1,
    )

    final_top_k: int = Field(
        default=5,
        ge=1,
    )

    reranker_model_name: str = (
        "BAAI/bge-reranker-v2-m3"
    )
    strict_offline: bool = True
    reranker_local_files_only: bool = True
    reranker_use_mock_fallback: bool = False

    @model_validator(mode="after")
    def validate_runtime(
        self,
    ) -> "RAGRuntimeSettings":
        if (
            self.final_top_k
            > self.candidate_top_k
        ):
            raise ValueError(
                "final_top_k cannot exceed "
                "candidate_top_k"
            )

        if (
            self.strict_offline
            and not self.reranker_local_files_only
        ):
            raise ValueError(
                "reranker_local_files_only must be "
                "enabled when strict_offline is enabled"
            )

        return self

def validate_offline_runtime_environment(
    settings: RAGRuntimeSettings,
) -> None:
    """
    Enforce the deployment offline policy before
    loading Hugging Face-backed runtime components.
    """

    if not settings.strict_offline:
        return

    if not _environment_flag_enabled(
        "HF_HUB_OFFLINE"
    ):
        raise RuntimeError(
            "Strict offline mode requires "
            "HF_HUB_OFFLINE=1."
        )

    if not _environment_flag_enabled(
        "TRANSFORMERS_OFFLINE"
    ):
        raise RuntimeError(
            "Strict offline mode requires "
            "TRANSFORMERS_OFFLINE=1."
        )

    if not _environment_flag_enabled(
        "HF_DATASETS_OFFLINE"
    ):
        raise RuntimeError(
            "Strict offline mode requires "
            "HF_DATASETS_OFFLINE=1."
        )

    if not settings.reranker_local_files_only:
        raise RuntimeError(
            "Strict offline mode requires "
            "local-only reranker loading."
        )
def build_rag_service(
    settings: RAGRuntimeSettings | None = None,
) -> M3M4RAGService:
    """
    Construct the complete M3 -> M4 runtime.

    This function is intentionally separate from
    FastAPI route handling so it is testable and
    reusable.
    """

    settings = (
        settings
        or RAGRuntimeSettings()
    )
    
    validate_offline_runtime_environment(
        settings
    )

    vector_store = QdrantVectorStore(
        location=settings.qdrant_location,
        collection_name=(
            settings.qdrant_collection_name
        ),
        vector_size=(
            settings.qdrant_vector_size
        ),
    )

    retrieval_pipeline = M3RetrievalPipeline(
        vector_store=vector_store,
        candidate_top_k=(
            settings.candidate_top_k
        ),
        final_top_k=(
            settings.final_top_k
        ),
        reranker_model_name=(
            settings.reranker_model_name
        ),
        use_mock_fallback=(
            settings.reranker_use_mock_fallback
        ),
        reranker_local_files_only=(
            settings.reranker_local_files_only
        ),
    )

    orchestration_service = (
        M4OrchestrationService()
    )

    return M3M4RAGService(
        retrieval_pipeline=(
            retrieval_pipeline
        ),
        orchestration_service=(
            orchestration_service
        ),
    )

def build_raw_rag_service(
    rag_service: M3M4RAGService,
    settings: RAGRuntimeSettings | None = None,
) -> M2M3M4RAGService:
    """
    Construct and validate the raw-query
    M2 -> M3 -> M4 runtime.

    Startup performs one fixed, non-confidential
    M2 probe so the application does not report
    readiness when BGE-M3 is unusable or returns
    the wrong embedding dimension.
    """

    settings = (
        settings
        or RAGRuntimeSettings()
    )

    from src.query_pipeline import (
        M2QueryPipeline,
    )

    query_pipeline = (
        M2QueryPipeline()
    )

    probe = query_pipeline.process(
        "AI-Lexora local embedding readiness probe"
    )

    actual_dimension = len(
        probe.embedding
    )

    if actual_dimension == 0:
        raise RuntimeError(
            "M2 startup probe returned "
            "an empty embedding."
        )

    if (
        probe.dimension
        != actual_dimension
    ):
        raise RuntimeError(
            "M2 startup probe embedding metadata "
            "does not match the vector length."
        )

    if (
        actual_dimension
        != settings.qdrant_vector_size
    ):
        raise RuntimeError(
            "M2 startup probe returned an "
            "unexpected embedding dimension."
        )

    return M2M3M4RAGService(
        query_pipeline=query_pipeline,
        rag_service=rag_service,
        expected_embedding_dimension=(
            settings.qdrant_vector_size
        ),
        validated_embedding_dimension=(
            actual_dimension
        ),
    )