# M2 Handoff to M3

## Owner

Member 2 — Embedding & Multilingual Retrieval Engineer

## Handoff contract

M2 receives:

```json
{
  "document_id": "doc_001",
  "chunk_id": "chunk_017",
  "text": "Termination may occur after written notice.",
  "page": 12,
  "section": "Termination",
  "language": "en"
}
```

M2 returns/stores an embedding for that chunk:

```json
{
  "document_id": "doc_001",
  "chunk_id": "chunk_017",
  "embedding": [0.01, -0.02, 0.03],
  "model": "BAAI/bge-m3"
}
```

For user queries, M2 returns:

```json
{
  "original_text": "ايه شروط termination في Article 69؟",
  "normalized_text": "ايه شروط termination في Article 69؟",
  "language": "ar-en",
  "query_variants": [
    "ايه شروط termination في Article 69؟"
  ],
  "identifiers": {
    "article_numbers": ["69"],
    "case_numbers": [],
    "dates": [],
    "monetary_values": [],
    "party_names": []
  },
  "embedding": [0.01, -0.02, 0.03],
  "model": "BAAI/bge-m3"
}
```

## What M3 should rely on

M3 can rely on:
- stable `chunk_id`
- stable `document_id`
- embedding dimensionality being consistent for one model
- normalized query text
- detected language label
- preserved identifiers
- query variants when available

M3 owns:
- Qdrant
- metadata filtering
- hybrid search
- Top-K
- reranking
- retrieval metrics such as Recall@5, Recall@10, MRR and nDCG

## Integration assumptions

1. M1 provides valid text and document metadata.
2. M2 does not modify the legal source document.
3. M2 does not decide legal relevance.
4. M2 does not generate answers.
5. M2 does not perform final retrieval.
6. If M3 changes the embedding model, the vector collection must be rebuilt because embeddings from different models should not be mixed.
