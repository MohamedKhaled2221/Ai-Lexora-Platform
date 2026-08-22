from pathlib import Path
import os
import pytest
from dotenv import load_dotenv
from pydantic import (
    ValidationError,
)

from src.api.deployment import (
    DeploymentSettings,
    validate_production_deployment,
)


def make_local_model(
    root: Path,
    name: str,
) -> str:
    model_dir = root / name

    model_dir.mkdir()

    (
        model_dir / "config.json"
    ).write_text(
        "{}",
        encoding="utf-8",
    )

    (
        model_dir / "model.safetensors"
    ).write_bytes(
        b"test"
    )

    return str(
        model_dir.resolve()
    )
    
def test_dotenv_loads_offline_environment(
    tmp_path,
    monkeypatch,
):
    env_file = (
        tmp_path / ".env"
    )

    env_file.write_text(
        "\n".join(
            [
                "HF_HUB_OFFLINE=1",
                "TRANSFORMERS_OFFLINE=1",
                "HF_DATASETS_OFFLINE=1",
            ]
        ),
        encoding="utf-8",
    )

    for name in (
        "HF_HUB_OFFLINE",
        "TRANSFORMERS_OFFLINE",
        "HF_DATASETS_OFFLINE",
    ):
        monkeypatch.delenv(
            name,
            raising=False,
        )

    load_dotenv(
        dotenv_path=env_file,
        override=False,
    )

    assert (
        os.getenv(
            "HF_HUB_OFFLINE"
        )
        == "1"
    )

    assert (
        os.getenv(
            "TRANSFORMERS_OFFLINE"
        )
        == "1"
    )

    assert (
        os.getenv(
            "HF_DATASETS_OFFLINE"
        )
        == "1"
    )

def test_deployment_settings_accept_loopback():
    settings = DeploymentSettings(
        _env_file=None,
        host="127.0.0.1",
        port=8000,
        workers=1,
    )

    assert (
        settings.host
        == "127.0.0.1"
    )

    assert settings.workers == 1


def test_deployment_settings_reject_public_binding():
    with pytest.raises(
        ValidationError,
        match="loopback",
    ):
        DeploymentSettings(
            _env_file=None,
            host="0.0.0.0",
            workers=1,
        )


def test_deployment_settings_reject_multiple_workers():
    with pytest.raises(
        ValidationError,
    ):
        DeploymentSettings(
            _env_file=None,
            host="127.0.0.1",
            workers=2,
        )


def test_production_deployment_accepts_local_runtime(
    tmp_path,
):
    embedding_model = make_local_model(
        tmp_path,
        "bge-m3",
    )

    reranker_model = make_local_model(
        tmp_path,
        "reranker",
    )

    validate_production_deployment(
        api_environment="production",
        log_output_format="json",
        disable_uvicorn_access_log=True,
        strict_offline=True,
        embedding_model=embedding_model,
        reranker_model=reranker_model,
        ollama_base_url=(
            "http://127.0.0.1:11434"
        ),
        qdrant_location=(
            "http://localhost:6333"
        ),
    )


def test_production_rejects_huggingface_model_id(
    tmp_path,
):
    reranker_model = make_local_model(
        tmp_path,
        "reranker",
    )

    with pytest.raises(
        RuntimeError,
        match=(
            "absolute local model directory"
        ),
    ):
        validate_production_deployment(
            api_environment="production",
            log_output_format="json",
            disable_uvicorn_access_log=True,
            strict_offline=True,
            embedding_model="BAAI/bge-m3",
            reranker_model=reranker_model,
            ollama_base_url=(
                "http://127.0.0.1:11434"
            ),
            qdrant_location=(
                "http://127.0.0.1:6333"
            ),
        )


def test_production_rejects_remote_qdrant(
    tmp_path,
):
    embedding_model = make_local_model(
        tmp_path,
        "bge-m3",
    )

    reranker_model = make_local_model(
        tmp_path,
        "reranker",
    )

    with pytest.raises(
        RuntimeError,
        match="Qdrant.*loopback",
    ):
        validate_production_deployment(
            api_environment="production",
            log_output_format="json",
            disable_uvicorn_access_log=True,
            strict_offline=True,
            embedding_model=embedding_model,
            reranker_model=reranker_model,
            ollama_base_url=(
                "http://127.0.0.1:11434"
            ),
            qdrant_location=(
                "http://192.168.1.50:6333"
            ),
        )


def test_production_rejects_standard_logging(
    tmp_path,
):
    embedding_model = make_local_model(
        tmp_path,
        "bge-m3",
    )

    reranker_model = make_local_model(
        tmp_path,
        "reranker",
    )

    with pytest.raises(
        RuntimeError,
        match="JSON",
    ):
        validate_production_deployment(
            api_environment="production",
            log_output_format="standard",
            disable_uvicorn_access_log=True,
            strict_offline=True,
            embedding_model=embedding_model,
            reranker_model=reranker_model,
            ollama_base_url=(
                "http://127.0.0.1:11434"
            ),
            qdrant_location=(
                "http://127.0.0.1:6333"
            ),
        )
