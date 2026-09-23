from __future__ import annotations

import json
from copy import copy
from dataclasses import dataclass
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)

from src.clause_engine.service import (
    M5ClauseService,
)
from src.document_generator.schemas import (
    TemplateDefinition,
)
from src.document_generator.service import (
    M1DocumentService,
)
from src.document_generator.template_registry import (
    TemplateRegistry,
)
from src.knowledge.access_control import (
    AccessControlService,
)
from src.knowledge.governance import (
    KnowledgeGovernanceService,
)
from src.knowledge.integration import (
    KnowledgeIntegrationService,
)
from src.knowledge.relationships import (
    RelationshipService,
)
from src.knowledge.repository import (
    InMemoryKnowledgeRepository,
)
from src.orchestration.m5_grounding_adapter import (
    M5GroundingAdapter,
)
from src.orchestration.p3_generation_service import (
    P3GenerationService,
)
from src.orchestration.p3_m5_service import (
    P3M5ValidationService,
)
from src.orchestration.p4_chat_service import (
    P4ChatService,
)
from src.orchestration.p4_orchestrator import (
    P4M4Orchestrator,
)
from src.pipeline import (
    M3RetrievalPipeline,
)
from src.retrieval.hybrid_search import (
    HybridSearcher,
)


class P3RuntimeSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="P3_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    enabled: bool = False

    template_registry_path: (
        str | None
    ) = None

    export_dir: str = (
        "outputs/p3_generated"
    )

    @model_validator(mode="after")
    def validate_p3_settings(
        self,
    ) -> "P3RuntimeSettings":

        if (
            self.enabled
            and not self.template_registry_path
        ):
            raise ValueError(
                "P3_TEMPLATE_REGISTRY_PATH is "
                "required when P3_ENABLED=true."
            )

        return self


@dataclass(frozen=True)
class P3APIRuntime:
    service: P3GenerationService
    export_dir: Path


def _project_root() -> Path:
    return (
        Path(__file__)
        .resolve()
        .parents[2]
    )


def _resolve_project_path(
    raw_path: str,
) -> Path:

    path = Path(raw_path)

    if not path.is_absolute():
        path = (
            _project_root()
            / path
        )

    return path.resolve()


def _load_m1_templates(
    registry_path: Path,
) -> list[TemplateDefinition]:

    payload = json.loads(
        registry_path.read_text(
            encoding="utf-8"
        )
    )

    items = payload.get(
        "templates"
    )

    if not isinstance(items, list):
        raise RuntimeError(
            "M1 template registry must contain "
            "a top-level 'templates' list."
        )

    templates: list[
        TemplateDefinition
    ] = []

    for raw in items:
        template = (
            TemplateDefinition
            .model_validate(raw)
        )

        if not template.file_path:
            raise RuntimeError(
                "Every enabled M1 template must "
                "declare file_path."
            )

        file_path = Path(
            template.file_path
        )

        if not file_path.is_absolute():
            file_path = (
                registry_path.parent
                / file_path
            )

        file_path = (
            file_path.resolve()
        )

        if not file_path.is_file():
            raise RuntimeError(
                "Configured M1 template does not "
                f"exist: {file_path}"
            )

        templates.append(
            template.model_copy(
                update={
                    "file_path": str(
                        file_path
                    )
                },
                deep=True,
            )
        )

    if not templates:
        raise RuntimeError(
            "M1 template registry contains "
            "no templates."
        )

    return templates


def build_p3_api_runtime(
    settings: (
        P3RuntimeSettings | None
    ) = None,
) -> P3APIRuntime | None:

    settings = (
        settings
        or P3RuntimeSettings()
    )

    if not settings.enabled:
        return None

    registry_path = (
        _resolve_project_path(
            settings
            .template_registry_path
        )
    )

    if not registry_path.is_file():
        raise RuntimeError(
            "Configured M1 template registry "
            f"does not exist: {registry_path}"
        )

    templates = (
        _load_m1_templates(
            registry_path
        )
    )

    m1_service = M1DocumentService(
        TemplateRegistry(
            templates
        )
    )

    root = _project_root()

    m5_service = M5ClauseService(
        library_path=(
            root
            / "data"
            / "clause_library.json"
        ),
        requirements_path=(
            root
            / "data"
            / "template_requirements.json"
        ),
    )

    validation_service = (
        P3M5ValidationService(
            m5_adapter=(
                M5GroundingAdapter(
                    m5_service
                )
            )
        )
    )

    service = P3GenerationService(
        m5_service=m5_service,
        m1_service=m1_service,
        m4_validation_service=(
            validation_service
        ),
    )

    export_dir = (
        _resolve_project_path(
            settings.export_dir
        )
    )

    export_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    return P3APIRuntime(
        service=service,
        export_dir=export_dir,
    )


def build_p4_chat_service(
    rag_service,
    raw_rag_service,
) -> P4ChatService:
    """
    Build Package 4 without loading a second
    BGE-M3 model or second reranker.

    P1 keeps its existing unversioned-compatible
    retrieval pipeline.

    P4 gets a separate HybridSearcher configured
    CURRENT-only, while sharing:
    - Qdrant
    - BGE-M3 query runtime
    - BGE reranker
    """

    base_retrieval = getattr(
        rag_service,
        "retrieval_pipeline",
        None,
    )

    query_pipeline = getattr(
        raw_rag_service,
        "query_pipeline",
        None,
    )

    if base_retrieval is None:
        raise RuntimeError(
            "Package 4 requires the initialized "
            "M3 retrieval pipeline."
        )

    if query_pipeline is None:
        raise RuntimeError(
            "Package 4 requires the initialized "
            "M2 query pipeline."
        )

    base_searcher = getattr(
        base_retrieval,
        "hybrid_searcher",
        None,
    )

    if base_searcher is None:
        raise RuntimeError(
            "Package 4 requires the initialized "
            "HybridSearcher."
        )

    p4_retrieval: (
        M3RetrievalPipeline
    ) = copy(
        base_retrieval
    )
    p4_retrieval.candidate_top_k = 5
    p4_retrieval.hybrid_searcher = (
        HybridSearcher(
            vector_store=(
                base_retrieval
                .vector_store
            ),
            rrf_k=getattr(
                base_searcher,
                "rrf_k",
                60,
            ),
            keyword_backend=(
                base_retrieval
                .keyword_backend
            ),
            dense_weight=getattr(
                base_searcher,
                "dense_weight",
                0.9,
            ),
            keyword_weight=getattr(
                base_searcher,
                "keyword_weight",
                0.1,
            ),
            identifier_weight=getattr(
                base_searcher,
                "identifier_weight",
                1.0,
            ),
            min_dense_score=getattr(
                base_searcher,
                "min_dense_score",
                None,
            ),
            allowed_validity_statuses=[
                "current"
            ],
            include_unversioned_points=(
                False
            ),
        )
    )

    # Critical: reuse the already-loaded
    # reranker instead of loading it twice.
    p4_retrieval.reranker = (
        base_retrieval.reranker
    )

    knowledge_service = (
        KnowledgeIntegrationService(
            repository=(
                InMemoryKnowledgeRepository()
            ),
            relationship_service=(
                RelationshipService()
            ),
            access_control=(
                AccessControlService()
            ),
            governance=(
                KnowledgeGovernanceService()
            ),
        )
    )

    return P4ChatService(
        query_pipeline=query_pipeline,
        retrieval_pipeline=(
            p4_retrieval
        ),
        knowledge_service=(
            knowledge_service
        ),
        m4_orchestrator=(
            P4M4Orchestrator()
        ),
        expected_embedding_dimension=(
            len(
                raw_rag_service
                .query_pipeline
                .process(
                    "AI-Lexora P4 startup probe"
                )
                .embedding
            )
        ),
    )
