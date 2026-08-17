import pytest
from pydantic import ValidationError

from src.orchestration import M4Settings


def test_default_settings():
    settings = M4Settings(_env_file=None)

    assert settings.ollama_base_url == "http://localhost:11434"
    assert settings.model_name == "qwen3.5:4b"
    assert settings.temperature == 0.1
    assert settings.num_ctx == 4096
    assert settings.num_predict == 512
    assert settings.keep_alive == "10m"
    assert settings.reasoning is False
    assert settings.validate_model_on_init is True
    assert settings.request_timeout_seconds == 120.0
    assert settings.max_retries == 2
    assert settings.seed == 42


def test_environment_variables_override_defaults(monkeypatch):
    monkeypatch.setenv("M4_MODEL_NAME", "test-model:latest")
    monkeypatch.setenv("M4_TEMPERATURE", "0.25")
    monkeypatch.setenv("M4_NUM_CTX", "8192")
    monkeypatch.setenv("M4_NUM_PREDICT", "1024")
    monkeypatch.setenv("M4_REASONING", "true")

    settings = M4Settings(_env_file=None)

    assert settings.model_name == "test-model:latest"
    assert settings.temperature == 0.25
    assert settings.num_ctx == 8192
    assert settings.num_predict == 1024
    assert settings.reasoning is True


def test_base_url_trailing_slash_is_removed():
    settings = M4Settings(
        ollama_base_url="http://localhost:11434/",
        _env_file=None,
    )

    assert settings.ollama_base_url == "http://localhost:11434"


@pytest.mark.parametrize(
    "url",
    [
        "localhost:11434",
        "ftp://localhost:11434",
        "",
    ],
)
def test_invalid_base_url_is_rejected(url):
    with pytest.raises(ValidationError):
        M4Settings(
            ollama_base_url=url,
            _env_file=None,
        )


@pytest.mark.parametrize(
    "temperature",
    [-0.1, 1.1],
)
def test_invalid_temperature_is_rejected(temperature):
    with pytest.raises(ValidationError):
        M4Settings(
            temperature=temperature,
            _env_file=None,
        )


def test_context_window_too_small_is_rejected():
    with pytest.raises(ValidationError):
        M4Settings(
            num_ctx=512,
            _env_file=None,
        )


def test_num_predict_must_be_smaller_than_context():
    with pytest.raises(ValidationError):
        M4Settings(
            num_ctx=4096,
            num_predict=4096,
            _env_file=None,
        )


@pytest.mark.parametrize(
    "timeout",
    [0, -1],
)
def test_invalid_timeout_is_rejected(timeout):
    with pytest.raises(ValidationError):
        M4Settings(
            request_timeout_seconds=timeout,
            _env_file=None,
        )


@pytest.mark.parametrize(
    "retries",
    [-1, 6],
)
def test_invalid_retry_count_is_rejected(retries):
    with pytest.raises(ValidationError):
        M4Settings(
            max_retries=retries,
            _env_file=None,
        )


def test_empty_keep_alive_is_rejected():
    with pytest.raises(ValidationError):
        M4Settings(
            keep_alive="",
            _env_file=None,
        )
