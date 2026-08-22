import json
import logging

from src.api.logging_config import (
    APILoggingSettings,
    SafeJSONFormatter,
    configure_application_logging,
)


def make_log_record(
    *,
    message: str = (
        "rag_request_completed"
    ),
) -> logging.LogRecord:
    return logging.LogRecord(
        name="ai_lexora.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )


def test_json_formatter_contains_base_fields():
    formatter = (
        SafeJSONFormatter()
    )

    record = make_log_record()

    payload = json.loads(
        formatter.format(
            record
        )
    )

    assert (
        payload["event"]
        == "rag_request_completed"
    )

    assert (
        payload["level"]
        == "INFO"
    )

    assert (
        payload["logger"]
        == "ai_lexora.test"
    )

    assert (
        payload["timestamp"]
        .endswith("Z")
    )


def test_json_formatter_contains_safe_metadata():
    formatter = (
        SafeJSONFormatter()
    )

    record = make_log_record()

    record.request_id = (
        "request_001"
    )

    record.query_id = (
        "query_001"
    )

    record.status = "success"
    record.retrieval_ms = 25.5
    record.generation_ms = 100.0
    record.total_rag_ms = 126.0
    record.retrieved_chunk_count = 4
    record.citation_count = 2

    payload = json.loads(
        formatter.format(
            record
        )
    )

    assert (
        payload["request_id"]
        == "request_001"
    )

    assert (
        payload["query_id"]
        == "query_001"
    )

    assert (
        payload["status"]
        == "success"
    )

    assert (
        payload["retrieval_ms"]
        == 25.5
    )

    assert (
        payload["generation_ms"]
        == 100.0
    )

    assert (
        payload["total_rag_ms"]
        == 126.0
    )

    assert (
        payload[
            "retrieved_chunk_count"
        ]
        == 4
    )

    assert (
        payload["citation_count"]
        == 2
    )


def test_json_formatter_drops_sensitive_extras():
    formatter = (
        SafeJSONFormatter()
    )

    record = make_log_record()

    record.question = (
        "confidential legal question"
    )

    record.normalized_text = (
        "confidential normalized text"
    )

    record.embedding = [
        0.1,
        0.2,
    ]

    record.evidence = (
        "confidential evidence"
    )

    record.prompt = (
        "confidential prompt"
    )

    record.answer = (
        "confidential generated answer"
    )

    record.authorization = (
        "Bearer secret-token"
    )

    record.cookie = (
        "session=secret"
    )

    payload_text = (
        formatter.format(
            record
        )
    )

    payload = json.loads(
        payload_text
    )

    for field_name in (
        "question",
        "normalized_text",
        "embedding",
        "evidence",
        "prompt",
        "answer",
        "authorization",
        "cookie",
    ):
        assert (
            field_name
            not in payload
        )

    assert (
        "confidential legal question"
        not in payload_text
    )

    assert (
        "secret-token"
        not in payload_text
    )


def test_json_formatter_contains_error_type():
    formatter = (
        SafeJSONFormatter()
    )

    record = make_log_record(
        message=(
            "unexpected_api_error"
        )
    )

    record.request_id = (
        "request_002"
    )

    record.error_type = (
        "RuntimeError"
    )

    payload = json.loads(
        formatter.format(
            record
        )
    )

    assert (
        payload["error_type"]
        == "RuntimeError"
    )


def test_json_configuration_is_idempotent():
    logger = logging.getLogger(
        "ai_lexora"
    )

    original_handlers = list(
        logger.handlers
    )

    original_level = (
        logger.level
    )

    original_propagate = (
        logger.propagate
    )

    uvicorn_access_logger = (
        logging.getLogger(
            "uvicorn.access"
        )
    )

    original_uvicorn_disabled = (
        uvicorn_access_logger.disabled
    )

    try:
        settings = (
            APILoggingSettings(
                _env_file=None,
                output_format="json",
                level="INFO",
                disable_uvicorn_access_log=True,
            )
        )

        configure_application_logging(
            settings
        )

        configure_application_logging(
            settings
        )

        managed_handlers = [
            handler
            for handler
            in logger.handlers
            if getattr(
                handler,
                "_ai_lexora_managed",
                False,
            )
        ]

        assert (
            len(managed_handlers)
            == 1
        )

        assert isinstance(
            managed_handlers[0]
            .formatter,
            SafeJSONFormatter,
        )

        assert (
            logger.propagate
            is False
        )

        assert (
            uvicorn_access_logger.disabled
            is True
        )

    finally:
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

        for handler in (
            original_handlers
        ):
            if (
                handler
                not in logger.handlers
            ):
                logger.addHandler(
                    handler
                )

        logger.setLevel(
            original_level
        )

        logger.propagate = (
            original_propagate
        )

        uvicorn_access_logger.disabled = (
            original_uvicorn_disabled
        )


def test_standard_mode_does_not_add_json_handler():
    logger = logging.getLogger(
        "ai_lexora"
    )

    original_handlers = list(
        logger.handlers
    )

    original_level = logger.level
    original_propagate = logger.propagate

    try:
        settings = (
            APILoggingSettings(
                _env_file=None,
                output_format="standard",
                level="INFO",
                disable_uvicorn_access_log=False,
            )
        )

        configure_application_logging(
            settings
        )

        managed_handlers = [
            handler
            for handler
            in logger.handlers
            if getattr(
                handler,
                "_ai_lexora_managed",
                False,
            )
        ]

        assert managed_handlers == []

        assert (
            logger.propagate
            is True
        )

    finally:
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

        logger.handlers = (
            original_handlers
        )

        logger.setLevel(
            original_level
        )

        logger.propagate = (
            original_propagate
        )
