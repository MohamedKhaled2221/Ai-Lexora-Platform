import uvicorn
from dotenv import load_dotenv
from src.api.deployment import (
    DeploymentSettings,
    validate_production_deployment,
)
from src.api.logging_config import (
    APILoggingSettings,
)
from src.api.runtime import (
    RAGRuntimeSettings,
    validate_offline_runtime_environment,
)
from src.api.security import (
    APISecuritySettings,
)
from src.config import (
    settings as m2_settings,
)
from src.orchestration import (
    M4Settings,
)


def main() -> None:
    load_dotenv(
        dotenv_path=".env",
        override=False,
    )

    deployment_settings = (
        DeploymentSettings()
    )

    security_settings = (
        APISecuritySettings()
    )

    logging_settings = (
        APILoggingSettings()
    )

    rag_settings = (
        RAGRuntimeSettings()
    )

    m4_settings = (
        M4Settings()
    )

    validate_offline_runtime_environment(
        rag_settings
    )

    validate_production_deployment(
        api_environment=(
            security_settings.environment
        ),
        log_output_format=(
            logging_settings.output_format
        ),
        disable_uvicorn_access_log=(
            logging_settings
            .disable_uvicorn_access_log
        ),
        strict_offline=(
            rag_settings.strict_offline
        ),
        embedding_model=(
            m2_settings.embedding_model
        ),
        reranker_model=(
            rag_settings
            .reranker_model_name
        ),
        ollama_base_url=(
            m4_settings.ollama_base_url
        ),
        qdrant_location=(
            rag_settings.qdrant_location
        ),
    )

    uvicorn.run(
        "src.api.server:app",
        host=deployment_settings.host,
        port=deployment_settings.port,
        workers=(
            deployment_settings.workers
        ),
        access_log=False,
        proxy_headers=False,
        server_header=False,
        reload=False,
    )


if __name__ == "__main__":
    main()
