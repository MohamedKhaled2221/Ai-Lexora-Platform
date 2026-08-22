from src.api.app import (
    create_app,
)
from src.api.logging_config import (
    APILoggingSettings,
    configure_application_logging,
)
from src.api.runtime import (
    build_rag_service,
    build_raw_rag_service,
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
)
