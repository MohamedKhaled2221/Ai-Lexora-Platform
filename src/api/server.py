from src.api.app import (
    create_app,
)
from src.api.logging_config import (
    APILoggingSettings,
    configure_application_logging,
)
from src.api.runtime import (
    build_document_ingestion_service,
    build_rag_service,
    build_raw_rag_service,
)
from src.api.package_routes import (
    router as package_router,
)

from src.api.package_runtime import (
    build_p3_api_runtime,
    build_p4_chat_service,
)

logging_settings = (
    APILoggingSettings()
)

configure_application_logging(
    logging_settings
)


app = create_app(
    rag_service_factory=(
        build_rag_service
    ),
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
