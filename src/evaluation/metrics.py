import math
from typing import List, Set, Dict, Any


class RetrievalEvaluator:
    """
    Evaluation Metrics Utility for Module M3.
    Computes Recall@K, MRR, nDCG@K, and Latency statistics.
    """

    @staticmethod
    def recall_at_k(retrieved_chunk_ids: List[str], ground_truth_chunk_ids: Set[str], k: int) -> float:
        """
        Compute Recall@K.
        """
        if not ground_truth_chunk_ids:
            return 0.0

        retrieved_k = set(retrieved_chunk_ids[:k])
        hits = len(retrieved_k.intersection(ground_truth_chunk_ids))
        return hits / float(len(ground_truth_chunk_ids))

    @staticmethod
    def reciprocal_rank(retrieved_chunk_ids: List[str], ground_truth_chunk_ids: Set[str]) -> float:
        """
        Compute Reciprocal Rank (RR).
        """
        for rank, cid in enumerate(retrieved_chunk_ids, start=1):
            if cid in ground_truth_chunk_ids:
                return 1.0 / float(rank)
        return 0.0

    @staticmethod
    def ndcg_at_k(retrieved_chunk_ids: List[str], ground_truth_chunk_ids: Set[str], k: int) -> float:
        """
        Compute nDCG@K (binary relevance).
        """
        if not ground_truth_chunk_ids:
            return 0.0

        dcg = 0.0
        for i, cid in enumerate(retrieved_chunk_ids[:k], start=1):
           if cid in ground_truth_chunk_ids:
                dcg += 1.0 / math.log2(i + 1)

        idcg = sum(1.0 / math.log2(i + 1) for i in range(1, min(len(ground_truth_chunk_ids), k) + 1))
        return dcg / idcg if idcg > 0 else 0.0

    @classmethod
    def evaluate_query(
        cls,
        retrieved_chunk_ids: List[str],
        ground_truth_chunk_ids: Set[str],
        latency_ms: float
    ) -> Dict[str, float]:
        """
        Evaluate single query performance metrics.
        """
        return {
            "Recall@5": cls.recall_at_k(retrieved_chunk_ids, ground_truth_chunk_ids, k=5),
            "Recall@10": cls.recall_at_k(retrieved_chunk_ids, ground_truth_chunk_ids, k=10),
            "MRR": cls.reciprocal_rank(retrieved_chunk_ids, ground_truth_chunk_ids),
            "nDCG@5": cls.ndcg_at_k(retrieved_chunk_ids, ground_truth_chunk_ids, k=5),
            "latency_ms": latency_ms
        }
