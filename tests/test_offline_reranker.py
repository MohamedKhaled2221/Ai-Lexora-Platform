import sentence_transformers

from src.retrieval.reranker import (
    BGEReranker,
)


def test_reranker_uses_local_files_only(
    monkeypatch,
):
    captured = {}

    class FakeCrossEncoder:
        def __init__(
            self,
            model_name,
            **kwargs,
        ):
            captured["model_name"] = (
                model_name
            )

            captured.update(
                kwargs
            )

    monkeypatch.setattr(
        sentence_transformers,
        "CrossEncoder",
        FakeCrossEncoder,
    )

    BGEReranker(
        model_name=(
            "BAAI/bge-reranker-v2-m3"
        ),
        use_mock_fallback=False,
        local_files_only=True,
    )

    assert (
        captured["model_name"]
        == "BAAI/bge-reranker-v2-m3"
    )

    assert (
        captured["local_files_only"]
        is True
    )
def test_reranker_uses_title_for_scoring_but_preserves_passage_text(
    monkeypatch,
):
    captured = {}

    class FakeCrossEncoder:
        def __init__(
            self,
            model_name,
            **kwargs,
        ):
            captured["model_name"] = model_name

        def predict(self, pairs):
            captured["pairs"] = pairs
            return [4.0]

    monkeypatch.setattr(
        sentence_transformers,
        "CrossEncoder",
        FakeCrossEncoder,
    )

    reranker = BGEReranker(
        model_name="local-test-reranker",
        use_mock_fallback=False,
        local_files_only=True,
    )

    passage = (
        "مدة الإخطار التعاقدي هي خمسة عشر "
        "يومًا تقويميًا."
    )

    candidate = {
        "document_id": "qa-arabic-contract",
        "chunk_id": "qa-arabic-contract-001",
        "title": "Arabic Test Contract",
        "text": passage,
        "score": 0.1,
    }

    results = reranker.rerank(
        query_text=(
            "What is the notice period "
            "in the Arabic test contract?"
        ),
        candidates=[candidate],
        top_k=1,
    )

    assert captured["pairs"] == [[
        (
            "What is the notice period "
            "in the Arabic test contract?"
        ),
        (
            "Document title: Arabic Test Contract\n"
            f"Document text: {passage}"
        ),
    ]]

    assert results[0]["title"] == "Arabic Test Contract"
    assert results[0]["text"] == passage
