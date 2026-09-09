# M3 Handoff — Knowledge Retrieval, Indexing & Evidence

**Audience:** M4 (Shared LLM & AI Orchestration), M6 (Legal Knowledge Base, Governance & Evaluation)
**Status:** current as of the code in this repo. Everything below is pulled from source; file references are clickable.

---

## 1. What M3 provides today

M3 owns the retrieval half of the stack: indexing embedded chunks into Qdrant, retrieving them under access control, and handing a reranked evidence bundle to M4.

- **Vector store:** a single Qdrant collection, `legal_documents_v2` (`DEFAULT_COLLECTION_NAME`, [qdrant_manager.py:43](../src/vector_store/qdrant_manager.py#L43)). v1 is dead — v2 points carry `client_id` / `matter_id` / `confidentiality_level`, v1 points carry none and are permanently invisible under fail-closed filtering.
- **Dense retrieval:** BGE-M3, 1024-dim, stored as Qdrant's *unnamed* default vector (`DENSE_VECTOR_NAME = ""`). Vector size is configurable but defaults to 1024 ([runtime.py:72](../src/api/runtime.py#L72)).
- **Native sparse retrieval:** BGE-M3 lexical weights stored as a named sparse vector `text_sparse` ([qdrant_manager.py:51](../src/vector_store/qdrant_manager.py#L51)) and searched natively by Qdrant. A collection created before sparse landed has no sparse vector and must be dropped and re-indexed; `_detect_sparse_support` reports this at startup.
- **Hybrid fusion:** dense + keyword results fused with weighted Reciprocal Rank Fusion, `rrf_k = 60`, weights dense `0.9` / keyword `0.1` ([hybrid_search.py:31-33](../src/retrieval/hybrid_search.py#L31-L33)). Candidate identity is the pair `(document_id, chunk_id)` — chunk ids are only unique within a document.
- **Reranking:** BGE cross-encoder `BAAI/bge-reranker-v2-m3`, scores squashed through a sigmoid into `[0,1]` ([reranker.py](../src/retrieval/reranker.py)). Runs offline (`local_files_only=True`, `strict_offline=True` in production wiring). A heuristic fallback reranker exists but `reranker_use_mock_fallback` defaults to **False** in the API runtime, so a missing model fails loudly rather than silently degrading.
- **Access control on every read path:** an `AccessScope` is required before anything touches the vector store. `HybridSearcher.search` raises `AccessScopeRequired` if `filters.access` is `None`; `build_qdrant_filter` refuses to run without a real `AccessScope` and always returns a non-empty `Filter`, so there is no code path that produces an unfiltered search. Both halves of the hybrid consume the *same* `Filter` object — adding sparse retrieval added a read path, not an access path.
- **Defence in depth:** after reranking, `M3RetrievalPipeline._assert_within_scope` re-checks every surviving candidate against the same scope. A violation raises `AccessScopeViolation` and fails the **whole request** — offending results are never silently dropped ([pipeline.py:129-194](../src/pipeline.py#L129-L194)).
- **Token-budget-enforced chunking:** upstream chunking is sized against the embedding model's own tokenizer, hard cap `max_chunk_tokens = 480` ([m1/src/config.py:485](../m1/src/config.py#L485)) against BGE-M3's 512-token encoder window. The encoder-side `max_length = 512` truncation is a safety net, not a policy, and truncation is logged when it happens (`warn_on_truncation`).
- **Defaults:** `candidate_top_k = 20`, `final_top_k = 5`, `keyword_backend = "sparse"` ([runtime.py:77-87](../src/api/runtime.py#L77-L87)).

---

### Current index state — verified 2026-09-06

Everything above is designed behaviour. This is the measured state of the live
collection after the v2 re-index, so M4 and M6 can treat it as real rather than
intended. Numbers were read back from a running Qdrant server (not the
in-memory client) by scrolling every point and re-checking it independently of
the script that wrote it.

| | |
|---|---|
| Collection | `legal_documents_v2`, status **green** |
| Points | **1,945** across **19 documents** |
| Corpus | `m1/test_corpus` — 8 real Egyptian legal PDFs (~342 pages: constitutions 2014/2019 ar+en, official gazette, three WIPO instruments), 3 rasterized scans, 8 synthetic contracts/leases/statutes/memos |
| Dense vectors | 1,945 / 1,945 present, all 1024-dim |
| Sparse vectors | 1,945 / 1,945 present; 1–236 terms per point, median 40 |
| Payload indices | 7 KEYWORD, each covering all 1,945 points |

**ACL coverage — 0 / 1,945 points with a wrong or absent stamp.** Every point
carries `client_id="_shared"`, `matter_id="_none"`,
`confidentiality_level="public"`, `schema_version=2`. That policy is correct
for this corpus specifically: it is public statute and synthetic benchmark
material with no real client or matter behind it. Real firm documents are
ingested through `POST /api/v1/documents/ingest` with a per-document ACL
derived from the authenticated caller — **not** through the bulk re-index path.

**Token distribution** (measured with BGE-M3's own tokenizer, not estimated):

| min | p50 | p90 | p99 | max |
|---|---|---|---|---|
| 3 | 147 | 423 | 477 | **480** |

- over 512 (encoder window): **0 / 1,945**
- over 480 (chunk budget): **0 / 1,945**

`max` sitting exactly on 480 is the point worth reading twice: the corpus
presses right up against the budget and never crosses it, so the limit is
demonstrably enforced rather than merely un-exercised. Before token-aware
chunking, 47% of chunks across this corpus exceeded 512 tokens (78% of Arabic
ones, worst case 1,332 tokens — 62% of that chunk was never embedded while
remaining fully matchable by keyword search).

**Foreign-tenant enforcement, executed against the live server:**

| Scope | Dense hits | Sparse hits |
|---|---|---|
| foreign tenant, `include_shared_corpus=True` | 1,945 | 1,441 |
| foreign tenant, `include_shared_corpus=False` | **0** | **0** |

The second row is the one that matters: a caller from another tenant, denied
the shared corpus, retrieves nothing on **either** path. Enforcement is done by
Qdrant during the search, not by filtering results afterwards.

> Reproducing this: `scripts/reindex_v2.py` takes the ACL policy as required
> arguments and refuses to run without them. It purges a document's existing
> points before rewriting them, so a re-index after a chunking change is a
> replacement rather than a merge — otherwise points from the old boundaries
> survive as orphans: correct ACL, stale text, indefinitely retrievable.

---

## 2. RetrievedEvidence schema — the primary contract

Defined in [src/schemas/m4_contract.py](../src/schemas/m4_contract.py). This is what M3 returns from `M3RetrievalPipeline.run()` and what M4 consumes; M6 should treat it as the shape evidence takes at the retrieval boundary.

### `RetrievedEvidence`

| Field | Type | Required | Meaning |
|---|---|---|---|
| `query_id` | `str` | **required** | Query ID corresponding to the M2 `ProcessedQuery`; propagated unchanged through to `AIResponse.query_id`. |
| `retrieved_evidence` | `List[EvidenceItem]` | optional (`default_factory=list`) | Top-K reranked evidence chunks, ordered by relevance score descending. Empty list is a legitimate result, not an error. |

No `model_config` is set on `RetrievedEvidence`, so it uses Pydantic defaults — extra fields are **ignored**, not forbidden. (Contrast with `M4ModelOutput` / `Citation` / `AIResponse`, which are `extra="forbid"`.)

### `EvidenceItem`

| Field | Type | Required | Meaning |
|---|---|---|---|
| `document_id` | `str` | **required** | Source legal document ID. |
| `chunk_id` | `str` | **required** | Unique chunk ID *within the document* — not globally unique. Identity is the `(document_id, chunk_id)` pair. |
| `text` | `str` | **required** | Extracted legal snippet text. |
| `page` | `Optional[int]` | optional, default `None` | Page number, used by M4 for citation validation. |
| `section` | `Optional[str]` | optional, default `None` | Document section or article title. |
| `language` | `str` | optional, default `"ar"` | Language of the chunk text. |
| `score` | `float` | **required** | Final reranked relevance score, documented as `[0.0 - 1.0]`. |

**Notes M4 and M6 should build against:**

- `score` is documented as `[0.0, 1.0]` but is **not validated** — there is no `ge`/`le` constraint on the field. Under the real cross-encoder it is a sigmoid output and genuinely in range; under the heuristic fallback it is clamped to `[0.0, 0.99]`. Do not assume the schema enforces it.
- Values are filled defensively in [pipeline.py:105-118](../src/pipeline.py#L105-L118): a missing `document_id` becomes `"doc_unknown"`, a missing `chunk_id` becomes `"chunk_unknown"`, missing `text` becomes `""`, missing `score` becomes `0.0`, and `language` falls back to the query's language.
- **ACL fields are deliberately not on `EvidenceItem`.** `client_id`, `matter_id`, and `confidentiality_level` are carried on the internal candidate dicts (`QdrantVectorStore._project`) and consumed by the post-retrieval assertion, but they are dropped when the M4 contract is built. If M4 or M6 needs access metadata alongside evidence, that is a contract change, not something to read off the current object.
- `RetrievedEvidence` carries no retrieval diagnostics — no `rrf_score`, no backend used, no latency. Latency is returned separately as the second element of `M3RetrievalPipeline.run()`'s tuple and surfaced only in structured logs.

---

## 3. Endpoints M4 and M6 should call

All live routes, from [src/api/app.py](../src/api/app.py) and the routers it includes.

### Identity headers (required on every access-controlled route)

Read by `get_caller_identity` ([identity.py](../src/api/identity.py)):

| Header | Required | Notes |
|---|---|---|
| `X-Client-Id` | **yes** | The caller's tenant. `401` if missing/blank. `403` if it equals `_shared` — that is a document owner, not a tenant. |
| `X-Matter-Id` | no | Narrows to one matter. Absent means every matter belonging to the client. |
| `X-Confidentiality-Ceiling` | **yes** | One of `public` \| `internal` \| `privileged`. `401` if missing, `400` if not a valid rung. |

Identity is header-based only while `identity_mode = "header"` (Phase 1). It is **rejected in production** by `APISecuritySettings.validate_security_policy` — `X-Client-Id` is trivially spoofable. If `identity_mode` is `"disabled"`, every identity-requiring route returns `503`: fail-closed by design.

### `POST /api/v1/rag/ask` — raw question → answer *(recommended for M4)*

Full M2 → M3 → M4 pipeline from a raw question string.

- **Request:** `RawRAGAnswerRequest` — `question: str` (stripped, min length 1), `filters: QueryFilters` (defaulted). `extra="forbid"`.
- **Response:** `AIResponse` (`query_id`, `answer`, `citations: List[Citation]`, `confidence`).
- **Access:** `filters.access` must be **absent**. A body carrying its own scope is rejected with `400` and logged (`client_supplied_access_scope_rejected`) — see `reject_client_supplied_access`. The server then stamps the scope from the authenticated caller.
- **Errors:** `400` invalid question / invalid query for retrieval; `502` invalid embedding, LLM invocation failure, or citation-validation failure; `503` embedding runtime or LLM runtime unavailable.

### `POST /api/v1/rag/answer` — pre-processed query → answer ⚠️

- **Request:** `RAGAnswerRequest` — `processed_query: ProcessedQuery`. `extra="forbid"`.
- **Response:** `AIResponse`.
- **Access:** same rule — `processed_query.filters.access` must be absent; server-stamped from identity.

> **⚠️ UNRESOLVED — do not build against this as final.**
> This endpoint accepts a **fully client-constructed `ProcessedQuery`, including the dense embedding vector and the normalized text**. ACL filtering constrains *which documents* the search may return; it cannot constrain a caller who chooses the query vector itself. Such a caller can probe their own tenant's vector space freely, and the embedding never has to correspond to the text shown to the user. This is an argument for making the endpoint internal-only. It is **flagged for M4's owner to decide**; M3 has not changed the behaviour. The flag is written into the route docstring itself ([rag_routes.py](../src/api/rag_routes.py)). Neither M4 nor M6 should treat the embedding-injection capability as a stable contract.

### `POST /api/v1/ai/answer` — M4 orchestration boundary

- **Request:** `M4AnswerRequest` — `processed_query: ProcessedQuery` + `retrieved_evidence: RetrievedEvidence`. `extra="forbid"`.
- **Response:** `AIResponse`.
- **Note:** this route takes **no identity dependency** — it does no retrieval, so it enforces no scope. Evidence is supplied by the caller. Anyone calling it is responsible for having obtained that evidence through a scoped path.

### `POST /api/v1/documents/ingest` — index a document

- **Request:** `multipart/form-data`, `file` (required); query params `document_id` (optional, 1–200 chars) and `confidentiality_level` (optional, one of the three rungs).
- **Response:** `DocumentIngestionResult` — `document_id`, `source_file`, `file_type`, `document_type`, `language`, `pages`, `chunks_indexed` (≥1), `embedding_model`, `embedding_dimension`, `status: "indexed"`.
- **Access:** the ACL is built from the authenticated caller and **overwrites** whatever M1 or the uploader supplied. `confidentiality_level` may only *lower* the caller's ceiling; raising it returns `403`.

### `POST /api/v1/risk/analyze` — M6 risk engine (already wired)

- **Request:** `M6RiskRequest` — `clauses: List[Dict[str, Any]]` from M5.
- **Response:** `M6RiskResponse` — `risks: List[ContractRisk]`.
- **Note:** no identity dependency, no retrieval.

### System routes

- `GET /health` → `HealthResponse` (liveness).
- `GET /ready` → `ReadinessResponse`, `503` when not ready.

### What does **not** exist

There is **no standalone retrieval endpoint** — no route returning a bare `RetrievedEvidence`. Retrieval is only reachable through the two `/rag` routes, which always generate an answer. If M6 needs evidence without generation (for eval harnesses, say), that endpoint has to be built.

---

## 4. AccessScope / ACL model

Defined in [src/schemas/access_control.py](../src/schemas/access_control.py). M6's `KnowledgeRecord` access metadata must be producible in exactly this shape.

### The three payload fields

Every indexed chunk carries these three keys, indexed in Qdrant as `KEYWORD` so every ACL condition is a flat exact match (`ACL_PAYLOAD_FIELDS`):

| Field | Type | Meaning |
|---|---|---|
| `client_id` | `str`, min length 1 | Owning tenant. Never `None` once stored. |
| `matter_id` | `str`, min length 1, default `"_none"` | Owning matter. Never `None` once stored. |
| `confidentiality_level` | `"public" \| "internal" \| "privileged"` | Access rung. Required. |

Both id fields are validated: stripped, non-empty, and **no internal whitespace**.

### Sentinel values

| Sentinel | Field | Meaning |
|---|---|---|
| `_shared` (`SHARED_CLIENT_ID`) | `client_id` | The cross-tenant legal corpus — statutes, court rulings, clause templates. Readable by every tenant whose scope opts in via `include_shared_corpus`. **A caller can never authenticate as `_shared`**: `AccessScope` rejects it as a `client_id`, and the identity layer returns `403`. It is a document owner, not a tenant. |
| `_none` (`NO_MATTER_ID`) | `matter_id` | A client-level document not tied to any single matter. Always appended to `allowed_matter_ids`, so client-level documents stay visible even when a caller narrows to specific matters. |

`_shared` rather than `_public` on purpose: `confidentiality_level` already has a `"public"` value meaning something entirely different (an access rung, not an owner), and two unrelated concepts must not both read as "public" in one payload.

**"Unset" is never "unrestricted."** Absent ACL keys stay absent in `_project` rather than defaulting, and `AccessScope.permits` refuses a payload with a missing `client_id` or `confidentiality_level` — an unstamped payload is *unverifiable*, not permitted.

### Confidentiality ladder

```
CONFIDENTIALITY_LADDER = ("public", "internal", "privileged")   # least → most restricted
```

A ceiling is expanded into an **explicit set** of readable rungs by `levels_up_to()`, never queried as a range:

```
levels_up_to("public")     -> ["public"]
levels_up_to("internal")   -> ["public", "internal"]
levels_up_to("privileged") -> ["public", "internal", "privileged"]
```

Set expansion rather than ordering, because Qdrant keyword indices do not order, and an explicit set is auditable at the point of the query.

The ladder also bounds **writes**: `CallerIdentity.to_chunk_acl` refuses a `confidentiality_level` above the caller's own ceiling — a caller cannot create content they would not be allowed to read back.

### `AccessScope` (what a caller may retrieve)

`extra="forbid"`, **frozen** — a scope cannot be widened in flight after the identity layer produced it.

| Field | Type | Required | Meaning |
|---|---|---|---|
| `client_id` | `str` | **required** | The caller's own tenant. Cannot be `_shared`. |
| `matter_ids` | `list[str] \| None` | optional, default `None` | Restrict to these matters. `None` = every matter for this client. An **empty list is rejected** — it would read as "no matters", which is never intended. Duplicates are de-duplicated. |
| `max_confidentiality` | `"public" \| "internal" \| "privileged"` | **required** | Highest rung this caller may read. |
| `include_shared_corpus` | `bool` | optional, default `True` | Whether the `_shared` corpus is in scope alongside the caller's own documents. |

Derived properties, which are what `build_qdrant_filter` compiles into `must` conditions:

- `allowed_client_ids` → `[client_id, "_shared"]` when `include_shared_corpus`, else `[client_id]`.
- `allowed_matter_ids` → `None` (no restriction), or `[*matter_ids, "_none"]`.
- `allowed_confidentiality_levels` → `levels_up_to(max_confidentiality)`.

### `ChunkACL` (what is stamped at ingest)

`extra="forbid"`, frozen. `client_id` (required), `matter_id` (default `_none`), `confidentiality_level` (required). Built server-side from the authenticated caller at the ingest boundary and written onto **every chunk** of the document, overwriting whatever M1 or the uploader supplied. **A document's ACL is never derived from its contents** — M1 sees only the file, and the uploader can put anything in it, so neither is an authority on who may read the result.

### Trust rule for M6

Nothing in this module is ever populated from a request body. A client that supplies an `access` scope gets a `400`, not a silent overwrite. **M6's `KnowledgeRecord` access metadata must therefore be applied server-side at the ingest/sync boundary**, from an authenticated principal — not carried as client-declared data.

Relevance filters (`document_type`, `jurisdiction`, `language`, `document_ids`, `extra_filters`) are ANDed with the access conditions and can only ever *narrow*. `extra_filters` containing any of the three ACL keys is **rejected**, not absorbed.

---

## 5. What M3 needs from M6 (currently blocking)

These are M3's asks. None of the three exists in the codebase today — `KnowledgeRecord`, `index_sync`, and `evidence_fusion` return zero hits across the repo.

### 5.1 `KnowledgeRecord` schema

Canonical case / law / article records, carrying:

- **Status:** `current` / `superseded` / `review_required`.
- **Effective dates** — when the record took effect, and when it stopped.
- **Jurisdiction.**
- **Access metadata matching M3's `AccessScope` shape** — the `client_id` / `matter_id` / `confidentiality_level` triple documented in §4, including correct use of the `_shared` and `_none` sentinels. Statutes and rulings belong to the shared corpus; anything client-specific does not.

### 5.2 Related-record queries

Structured relationship lookups:

- case-cites-law
- judge / court history
- law / article relationships

These are needed **for fusion into retrieval** — as a signal that participates in candidate selection and ranking alongside dense and sparse retrieval. They are explicitly **not** a post-rerank decoration stage. A relationship discovered only after reranking cannot influence which candidates survived, which is the point of having it.

### 5.3 `index_sync` change events

A signal — `create` / `update` / `delete` — emitted whenever a canonical record changes, so M3 can create, update, or delete the matching Qdrant vector. **No producer of this exists yet.** Without it, M3's index and M6's canonical store drift apart silently: a superseded law stays retrievable, a deleted record stays citable, and nothing in the system notices.

### Blocking statement

**`index_sync` is blocked outright, and the structured half of `evidence_fusion` is blocked, until these exist.** M3 can build neither against an absent schema nor against an absent event producer. The dense/sparse half of fusion is live and unaffected.

---

## 6. Known open items (not blocking — transparency)

- **RRF weights are un-tuned.** Dense `0.9` / keyword `0.1` were carried over unchanged from the BM25 era and were tuned — to whatever extent they were tuned — against Python BM25 scores over a full-collection scroll. Native sparse retrieval has a different score distribution and a different candidate set, so these are a *starting point for re-tuning*, not a validated setting. The fact that the numbers did not change when the retriever underneath them did is a reason to distrust them. Re-tuning needs a labeled eval set, which does not exist yet. ([hybrid_search.py:31-42](../src/retrieval/hybrid_search.py#L31-L42))
- **BM25 is retained behind a config flag.** `keyword_backend` (settable as `RAG_KEYWORD_BACKEND`) selects `"sparse"` (default) or `"bm25"`. Both are ACL-equivalent — they consume the same `Filter` — so switching is a relevance decision, never a security one. BM25 is kept reachable so native-sparse quality can be measured against what it replaced, on the same corpus and the same queries; removing it is an A/B outcome, not yet decided. Note the cost the BM25 path carries and sparse does not: it materializes up to `get_all_chunks`'s scroll limit per query, so its keyword recall silently depends on how much of the tenant's corpus fits in that limit.
- **`/rag/answer` embedding injection** — see §3. Flagged for M4's owner; behaviour unchanged pending that decision.
- **Tokenizer loading contacts Hugging Face before falling back to cache.**
  `token_budget._load_tokenizer` calls `AutoTokenizer.from_pretrained("BAAI/bge-m3")`
  without `local_files_only=True`, and nothing sets `HF_HUB_OFFLINE`. In
  practice it resolves from the local cache, but it issues live HTTPS requests
  to `huggingface.co` first. **This should be fixed before any production
  deployment**: the project's stated constraint is that nothing leaves firm
  infrastructure, and a network call that merely happens to be satisfiable
  from cache still violates that — it would also fail or hang outright on a
  genuinely air-gapped host, despite `strict_offline: True` being set
  elsewhere in the runtime. Fix is one of `local_files_only=True` at the call
  site or `HF_HUB_OFFLINE=1` in the service environment.
  ([m1/src/token_budget.py](../m1/src/token_budget.py))
- **Dense-only degradation is invisible to the caller.** If M2 supplies no sparse query vector, `_sparse_backend` returns no keyword candidates and retrieval proceeds dense-only. This is logged as a warning but is not surfaced in `RetrievedEvidence`, so a consumer cannot tell a hybrid result from a dense-only one.
