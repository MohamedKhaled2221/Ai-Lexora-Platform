import pytest
from pydantic import ValidationError

from src.api.runtime import (
    RAGRuntimeSettings,
    validate_offline_runtime_environment,
)


def test_rag_runtime_defaults():
    settings = RAGRuntimeSettings(
        _env_file=None
    )

    assert (
        settings.qdrant_location
        == "http://localhost:6333"
    )

    assert (
        settings.qdrant_collection_name
        == "legal_documents"
    )

    assert settings.qdrant_vector_size == 1024
    assert settings.candidate_top_k == 20
    assert settings.final_top_k == 5

    assert (
        settings.reranker_model_name
        == "BAAI/bge-reranker-v2-m3"
    )

    assert (
        settings.reranker_use_mock_fallback
        is False
    )


def test_rag_environment_overrides(
    monkeypatch,
):
    monkeypatch.setenv(
        "RAG_QDRANT_LOCATION",
        ":memory:",
    )

    monkeypatch.setenv(
        "RAG_FINAL_TOP_K",
        "3",
    )

    settings = RAGRuntimeSettings(
        _env_file=None
    )

    assert settings.qdrant_location == ":memory:"
    assert settings.final_top_k == 3


def test_final_top_k_cannot_exceed_candidates():
    with pytest.raises(
        ValidationError
    ):
        RAGRuntimeSettings(
            candidate_top_k=3,
            final_top_k=5,
            _env_file=None,
        )

def test_strict_offline_is_default():
    settings = RAGRuntimeSettings(
        _env_file=None
    )

    assert settings.strict_offline is True

    assert (
        settings.reranker_local_files_only
        is True
    )


def test_strict_offline_rejects_network_reranker():
    with pytest.raises(
        ValidationError
    ):
        RAGRuntimeSettings(
            strict_offline=True,
            reranker_local_files_only=False,
            _env_file=None,
        )


def test_offline_environment_is_accepted(
    monkeypatch,
):
    monkeypatch.setenv(
        "HF_HUB_OFFLINE",
        "1",
    )

    monkeypatch.setenv(
        "TRANSFORMERS_OFFLINE",
        "1",
    )

    monkeypatch.setenv(
        "HF_DATASETS_OFFLINE",
        "1",
    )

    settings = RAGRuntimeSettings(
        strict_offline=True,
        _env_file=None,
    )

    validate_offline_runtime_environment(
        settings
    )

def test_offline_environment_is_required(
    monkeypatch,
):
    monkeypatch.delenv(
        "HF_HUB_OFFLINE",
        raising=False,
    )

    settings = RAGRuntimeSettings(
        strict_offline=True,
        _env_file=None,
    )

    with pytest.raises(
        RuntimeError,
        match="HF_HUB_OFFLINE",
    ):
        validate_offline_runtime_environment(
            settings
        )

def test_strict_offline_requires_transformers_offline(
    monkeypatch,
):
    monkeypatch.setenv(
        "HF_HUB_OFFLINE",
        "1",
    )

    monkeypatch.delenv(
        "TRANSFORMERS_OFFLINE",
        raising=False,
    )

    monkeypatch.setenv(
        "HF_DATASETS_OFFLINE",
        "1",
    )

    settings = RAGRuntimeSettings(
        _env_file=None,
        strict_offline=True,
        reranker_local_files_only=True,
    )

    with pytest.raises(
        RuntimeError,
        match="TRANSFORMERS_OFFLINE",
    ):
        validate_offline_runtime_environment(
            settings
        )


def test_strict_offline_requires_datasets_offline(
    monkeypatch,
):
    monkeypatch.setenv(
        "HF_HUB_OFFLINE",
        "1",
    )

    monkeypatch.setenv(
        "TRANSFORMERS_OFFLINE",
        "1",
    )

    monkeypatch.delenv(
        "HF_DATASETS_OFFLINE",
        raising=False,
    )

    settings = RAGRuntimeSettings(
        _env_file=None,
        strict_offline=True,
        reranker_local_files_only=True,
    )

    with pytest.raises(
        RuntimeError,
        match="HF_DATASETS_OFFLINE",
    ):
        validate_offline_runtime_environment(
            settings
        )