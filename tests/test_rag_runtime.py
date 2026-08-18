import pytest
from pydantic import ValidationError

from src.api.runtime import (
    RAGRuntimeSettings,
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