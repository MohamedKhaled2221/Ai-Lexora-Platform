import json
import logging
import sys
from datetime import (
    datetime,
    timezone,
)
from typing import Literal

from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)


_SAFE_EXTRA_FIELDS = (
    "request_id",
    "http_method",
    "http_path",
    "status_code",
    "duration_ms",
    "query_id",
    "retrieval_ms",
    "generation_ms",
    "total_rag_ms",
    "retrieved_chunk_count",
    "citation_count",
    "status",
    "failure_stage",
    "error_type",
    "error_count",
)


_APPLICATION_LOGGERS = (
    "ai_lexora",
    "src.api.rag_routes",
    "src.api.ai_routes",
    "src.api.health",
)


class APILoggingSettings(BaseSettings):
    """
    Configuration for AI-Lexora operational logging.
    """

    model_config = SettingsConfigDict(
        env_prefix="API_LOG_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    output_format: Literal[
        "standard",
        "json",
    ] = "standard"

    level: Literal[
        "DEBUG",
        "INFO",
        "WARNING",
        "ERROR",
        "CRITICAL",
    ] = "INFO"

    disable_uvicorn_access_log: bool = True


class SafeJSONFormatter(
    logging.Formatter
):
    """
    Serialize only explicitly approved operational
    metadata.

    Arbitrary LogRecord fields are intentionally
    ignored so confidential legal data cannot be
    accidentally serialized.
    """

    def format(
        self,
        record: logging.LogRecord,
    ) -> str:
        timestamp = (
            datetime.now(
                timezone.utc
            )
            .isoformat(
                timespec="milliseconds"
            )
            .replace(
                "+00:00",
                "Z",
            )
        )

        payload: dict[
            str,
            str | int | float | bool | None,
        ] = {
            "timestamp": timestamp,
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }

        for field_name in (
            _SAFE_EXTRA_FIELDS
        ):
            if not hasattr(
                record,
                field_name,
            ):
                continue

            value = getattr(
                record,
                field_name,
            )

            if (
                value is None
                or isinstance(
                    value,
                    (
                        str,
                        int,
                        float,
                        bool,
                    ),
                )
            ):
                payload[
                    field_name
                ] = value

        return json.dumps(
            payload,
            ensure_ascii=False,
            separators=(
                ",",
                ":",
            ),
        )


def _remove_managed_handlers(
    logger: logging.Logger,
) -> None:
    for handler in list(
        logger.handlers
    ):
        if getattr(
            handler,
            "_ai_lexora_managed",
            False,
        ):
            logger.removeHandler(
                handler
            )

            handler.close()


def configure_application_logging(
    settings: APILoggingSettings,
) -> None:
    """
    Configure only AI-Lexora-owned operational
    loggers.

    JSON mode uses one controlled stdout handler and
    prevents duplicate root propagation.
    """

    log_level = getattr(
        logging,
        settings.level,
    )

    for logger_name in (
        _APPLICATION_LOGGERS
    ):
        app_logger = logging.getLogger(
            logger_name
        )

        _remove_managed_handlers(
            app_logger
        )

        app_logger.setLevel(
            log_level
        )

        if (
            settings.output_format
            == "json"
        ):
            handler = logging.StreamHandler(
                sys.stdout
            )

            handler.setLevel(
                log_level
            )

            handler.setFormatter(
                SafeJSONFormatter()
            )

            setattr(
                handler,
                "_ai_lexora_managed",
                True,
            )

            app_logger.addHandler(
                handler
            )

            app_logger.propagate = False

        else:
            app_logger.propagate = True

    uvicorn_access_logger = (
        logging.getLogger(
            "uvicorn.access"
        )
    )

    uvicorn_access_logger.disabled = (
        settings
        .disable_uvicorn_access_log
    )
