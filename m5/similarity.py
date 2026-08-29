from __future__ import annotations

import math
import re
from collections import Counter
from typing import Optional


def _tokens(text: str) -> list[str]:
    return re.findall(
        r"[\w\u0600-\u06FF]+",
        (text or "").lower(),
    )


def lexical_cosine(
    a: str,
    b: str,
) -> float:
    """
    Dependency-free cosine similarity fallback.

    Used as a deterministic baseline when no embedding
    model is configured.
    """

    va = Counter(_tokens(a))
    vb = Counter(_tokens(b))

    vocab = set(va) | set(vb)

    if not vocab:
        return 0.0

    dot = sum(
        va[token] * vb[token]
        for token in vocab
    )

    norm_a = math.sqrt(
        sum(
            value * value
            for value in va.values()
        )
    )

    norm_b = math.sqrt(
        sum(
            value * value
            for value in vb.values()
        )
    )

    if not norm_a or not norm_b:
        return 0.0

    return max(
        0.0,
        min(
            1.0,
            dot / (norm_a * norm_b),
        ),
    )


class SimilarityEngine:
    """
    Similarity abstraction used by M5 comparator.

    The engine supports:
        1. lexical cosine baseline
        2. optional sentence-transformer backend

    The final production embedding backend should be aligned
    with the team's M2 embedding infrastructure.
    """

    def __init__(
        self,
        model_name: str = "",
        enabled: bool = False,
    ):
        self.model_name = model_name
        self.enabled = enabled
        self._model: Optional[object] = None

    def _load(self):
        if self._model is not None:
            return self._model

        if not self.enabled or not self.model_name:
            return None

        from sentence_transformers import (
            SentenceTransformer,
        )

        self._model = SentenceTransformer(
            self.model_name
        )

        return self._model

    def score(
        self,
        a: str,
        b: str,
    ) -> float:

        if not a or not b:
            return 0.0

        model = self._load()

        if model is None:
            return lexical_cosine(
                a,
                b,
            )

        vectors = model.encode(
            [a, b],
            normalize_embeddings=True,
        )

        score = float(
            vectors[0] @ vectors[1]
        )

        return max(
            0.0,
            min(
                1.0,
                score,
            ),
        )