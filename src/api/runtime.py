from pydantic import Field, model_validator
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)

from src.orchestration import (
    M3M4RAGService,
    M4OrchestrationService,
)
from src.pipeline import M3RetrievalPipeline
from src.vector_store.qdrant_manager import (
    QdrantVectorStore,
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

    reranker_use_mock_fallback: bool = False

    @model_validator(mode="after")
    def validate_top_k(
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

        return self


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
