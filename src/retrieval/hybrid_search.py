import logging
import re
from typing import List, Dict, Any, Optional
from rank_bm25 import BM25Okapi

from src.vector_store.qdrant_manager import QdrantVectorStore
from src.schemas.m2_contract import ProcessedQuery

logger = logging.getLogger(__name__)


def tokenize_text(text: str) -> List[str]:
    """
    Simple whitespace/punctuation tokenizer supporting Arabic and English.
    """
    text_clean = re.sub(r'[^\w\s]', ' ', text.lower())
    return [t for t in text_clean.split() if t]


class HybridSearcher:
    """
    Hybrid Search Engine combining Dense Vector Search + BM25 Keyword Search
    fused via Reciprocal Rank Fusion (RRF).

    Expects query.embedding to be provided by M2 (upstream embedding module).
    """

    def __init__(self, vector_store: QdrantVectorStore, rrf_k: int = 60):
        self.vector_store = vector_store
        self.rrf_k = rrf_k

    def search(self, query: ProcessedQuery, candidate_top_k: int = 20) -> List[Dict[str, Any]]:
        """
        Execute Hybrid Search (Dense + BM25) filtered by metadata constraints.
        Requires query.embedding to be set by M2 upstream.
        """
        if not query.embedding:
            raise ValueError(
                "query.embedding is empty. M2 must provide a dense embedding vector before M3 search."
            )

        # 1. Build Metadata Filter
        qdrant_filter = self.vector_store.build_qdrant_filter(
            document_type=query.filters.document_type,
            jurisdiction=query.filters.jurisdiction,
            language=query.filters.language,
            extra_filters=query.filters.extra_filters
        )

        # 2. Dense Vector Search (embedding provided by M2)
        dense_results = self.vector_store.dense_search(
            query_vector=query.embedding,
            query_filter=qdrant_filter,
            top_k=candidate_top_k
        )

        # 3. Keyword / BM25 Search over filtered candidate scope
        all_chunks = self.vector_store.get_all_chunks(query_filter=qdrant_filter)
        bm25_results = self._bm25_search(
            query_text=query.normalized_text or query.text_original,
            chunks=all_chunks,
            top_k=candidate_top_k
        )

        # 4. Fuse using Reciprocal Rank Fusion (RRF)
        fused_candidates = self._reciprocal_rank_fusion(
            dense_results=dense_results,
            bm25_results=bm25_results,
            top_k=candidate_top_k
        )

        return fused_candidates

    def _bm25_search(
        self,
        query_text: str,
        chunks: List[Dict[str, Any]],
        top_k: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Execute BM25 keyword search over available payload chunks.
        """
        if not chunks:
            return []

        corpus_tokens = [tokenize_text(c["text"]) for c in chunks]
        query_tokens = tokenize_text(query_text)

        if not any(corpus_tokens) or not query_tokens:
            return chunks[:top_k]

        bm25 = BM25Okapi(corpus_tokens)
        scores = bm25.get_scores(query_tokens)

        scored_chunks = []
        for idx, score in enumerate(scores):
            chunk_copy = dict(chunks[idx])
            chunk_copy["bm25_score"] = float(score)
            scored_chunks.append(chunk_copy)

        scored_chunks.sort(key=lambda x: x["bm25_score"], reverse=True)
        return scored_chunks[:top_k]

    def _reciprocal_rank_fusion(
        self,
        dense_results: List[Dict[str, Any]],
        bm25_results: List[Dict[str, Any]],
        top_k: int = 20,
        dense_weight: float = 0.9,
        bm25_weight: float = 0.1
    ) -> List[Dict[str, Any]]:
        """
        Combine Dense & BM25 rankings using Weighted Reciprocal Rank Fusion (RRF).
        RRF_Score = sum(weight * (1 / (k + rank)))
        """
        rrf_scores: Dict[str, float] = {}
        chunk_map: Dict[str, Dict[str, Any]] = {}

        # Process Dense Ranks
        for rank, item in enumerate(dense_results, start=1):
            chunk_id = item["chunk_id"]
            chunk_map[chunk_id] = item
            rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + dense_weight * (1.0 / (self.rrf_k + rank))

        # Process BM25 Ranks
        for rank, item in enumerate(bm25_results, start=1):
            chunk_id = item["chunk_id"]
            chunk_map[chunk_id] = item
            rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + bm25_weight * (1.0 / (self.rrf_k + rank))

        # Sort combined results by RRF score descending
        sorted_chunk_ids = sorted(rrf_scores.keys(), key=lambda cid: rrf_scores[cid], reverse=True)

        fused_results = []
        for cid in sorted_chunk_ids[:top_k]:
            item = dict(chunk_map[cid])
            item["rrf_score"] = rrf_scores[cid]
            fused_results.append(item)

        return fused_results
