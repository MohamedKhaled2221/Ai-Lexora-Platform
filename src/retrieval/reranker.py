import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class BGEReranker:
    """
    BGE-M3 Cross-Encoder Reranker Engine.
    Re-scores candidate chunks retrieved from Hybrid Search to deliver precise evidence ranking.
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-reranker-v2-m3",
        use_mock_fallback: bool = True,
        local_files_only: bool = True,
    ):
        self.model_name = model_name
        self.use_mock_fallback = use_mock_fallback
        self.local_files_only = local_files_only
        self.model = None

        self._init_model()

    def _init_model(self) -> None:
        """
        Attempt to load BGE CrossEncoder model, falling back gracefully if unavailable or offline.
        """
        if not self.model_name:
            logger.info("No HuggingFace model specified. Using fast heuristic/mock reranker.")
            return

        try:
            from sentence_transformers import CrossEncoder
            logger.info(f"Loading CrossEncoder reranker model: {self.model_name}...")
            self.model = CrossEncoder(
                self.model_name,
                local_files_only=self.local_files_only,
            )
        except Exception as e:
            logger.warning(f"Could not load HuggingFace CrossEncoder '{self.model_name}': {e}.")
            if self.use_mock_fallback:
                logger.info("Enabling intelligent heuristic/mock reranker fallback.")
            else:
                raise e

    def rerank(
        self,
        query_text: str,
        candidates: List[Dict[str, Any]],
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Rerank list of candidate chunks against the query.
        Returns top_k items with updated 'score' attribute.
        """
        if not candidates:
            return []

        if self.model is not None:
            pairs = [[query_text, c["text"]] for c in candidates]
            raw_scores = self.model.predict(pairs)

            # Normalize scores using sigmoid for 0.0 - 1.0 output range
            import numpy as np
            scores = 1.0 / (1.0 + np.exp(-np.array(raw_scores)))

            reranked = []
            for idx, item in enumerate(candidates):
                item_copy = dict(item)
                item_copy["score"] = float(scores[idx])
                reranked.append(item_copy)
        else:
            # Smart Fallback Reranking: Token overlap & RRF score boost
            reranked = self._fallback_rerank(query_text, candidates)

        # Sort descending by score
        reranked.sort(key=lambda x: x["score"], reverse=True)
        return reranked[:top_k]

    def _fallback_rerank(
        self,
        query_text: str,
        candidates: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Heuristic fallback reranking when deep model weights are offline.
        Combines keyword coverage, exact match bonuses, and RRF score.
        """
        query_terms = set(query_text.lower().split())
        reranked = []

        for item in candidates:
            text = item.get("text", "").lower()
            text_terms = set(text.split())

            if not query_terms:
                overlap_ratio = 0.5
            else:
                overlap = query_terms.intersection(text_terms)
                overlap_ratio = len(overlap) / len(query_terms)

            rrf_base = item.get("rrf_score", 0.1)
            raw_score = 0.5 * rrf_base + 0.5 * overlap_ratio

            # Clamp between 0.0 and 1.0
            final_score = min(max(raw_score, 0.0), 0.99)

            item_copy = dict(item)
            item_copy["score"] = round(final_score, 4)
            reranked.append(item_copy)

        return reranked
