# M3 — Knowledge Retrieval, Indexing & Evidence: session summary

**Date:** 2026-09-08 → 2026-09-09 · **Module:** M3 · **Collection:** `legal_documents_v2`
**Audience:** M4 (LLM orchestration), M6 (knowledge base & governance), M2 (query
processing), team update

**Status at close:** test suite **436 passed, 0 failed**. Evaluation harness
**MRR 0.707 · R@5 0.875 · 36/36 found** over 41 cases (36 scorable + 5
negatives). Live collection **green, 1,945 points, 14 payload indices**.
Snapshot taken before any write this session:
`legal_documents_v2-5638308777856478-2026-09-09-13-43-15.snapshot`
(1,530,683,904 bytes, checksum `0d40e563f2f9fa…96440466`).

---

## OPEN ITEMS

Nothing below is in progress. Each item is waiting on a named person or is a
deliberate deferral.

### Needs a decision from Youssef

| # | Item | Why it needs you |
|---|---|---|
| 1 | **Minimum-relevance threshold design** — §10 | Changes the `RetrievedEvidence` contract. My recommendation is a *flag*, not a filter: `low_confidence = (no identifier match in top-k) AND (dense top-1 < 0.52)`. Separates 5/5 negatives from 32/32 positives on current data, but the margin is 0.023 fitted to five negative points — treat 0.52 as the shape, not the value. **Not implemented.** |
| 2 | **Reranker model** — `bge-reranker-v2-m3` (~2.2 GB) into the local HF cache, or keep the fail-loud posture? | Unchanged from 2026-09-08. Nothing deploys with current defaults until it is cached. Policy call about firm infrastructure. |
| 3 | **RRF weights** — §3 | Recommendation stands: **do not apply** `0.5/0.1/2.0`. Split disagreement (~0.10 MRR) exceeds the effect size (~0.012 MRR). |
| ~~4~~ | ~~**`uv.lock` vs `requirements.txt` authority**~~ | **CLOSED 2026-09-09.** `requirements.txt` is authoritative; see §12 and docs/ENVIRONMENT.md. Both verified in agreement (0 mismatches). |

### Needs another teammate

| # | Item | Owner | Detail |
|---|---|---|---|
| 5 | **ISSUE-3 — money regex** | **M2** | `MONEY_RE` accepts ASCII `,` only; the corpus uses U+066C. Every genuine amount extracts truncated. One character class (`[\d,٬]`), plus a currency-code-prefix alternative for `EGP 3,000,000`. Alters extraction on every query and every chunk, then needs a `backfill_identifiers.py` re-run. **Blocks the monetary half of §11.** |
| 6 | **ISSUE-1 — reversed-RTL / parenthesised article extraction** | **M2** | 279 chunks (14.3%) carry zero article identifiers. Needs a deliberate regex design decision. |
| 7 | **`party_names` — extract it or drop it?** | **M2** | `IdentifierSet.party_names` is declared in the M2 contract and hardcoded to `[]` at `query_processor.py:123` — there is no party extraction. M3 deliberately does not consume it (pinned by a test), because wiring an always-empty field reads as coverage and is not. Either implement extraction or remove the field. *(No `named_legal_terms` field exists anywhere in the codebase — if one is wanted, that is a new contract proposal, not a gap.)* |
| 8 | **Threshold contract proposal** | **M4** | Item 1 above, once Youssef signs off. M4's abstention path is currently **dead code** — see §10. |
| 9 | **`EvidenceItem` drops 12 fields** | **M4** | Unchanged, no code touched. See §5. Now also drops `date_no`, `date_ref`, `money_no`, `money_ref`. |
| 10 | **Lawyer review of 4 eval cases** | **legal** | `evaluation/NEEDS_LAWYER_REVIEW.md`. The other 37 are usable now. |

### Blocked on M6

None of these exist in the codebase; unchanged from the previous handoff.

- **`index_sync` change events** (`create`/`update`/`delete`). No producer. Without it M3's index and M6's canonical store drift silently — a superseded law stays retrievable and nothing notices.
- **Status / lifecycle fields** (`current`/`superseded`/`review_required`, effective dates). Zero of 1,945 points carry any. Not filterable today.
- **Related-record queries** (case-cites-law, judge/court history, article relationships) for fusion into retrieval as a ranking signal — not a post-rerank decoration.

### Deferred — not urgent, not blocked

- **Grow the eval set to 60–100 cases**, weighted toward semantic and adversarial. This is the prerequisite for settling the RRF weights *and* for trusting a threshold value. Currently 41.
- **`query_variants` scoping.** `build_variants` returns `[normalized_text]` — a deliberate MVP no-op. Query expansion needs evaluation before it earns a place.
- **End-to-end reranked quality is unmeasured.** Every number in this document is at the **fusion** stage; the cross-encoder has never run on this host.
- **Multi-tenant behaviour against real client data.** Enforced and tested in code, never exercised against real per-matter documents — the corpus has a uniform ACL.

---

## 1. Headline

The live index is restored, verified, and now supports exact legal-identifier
lookup end to end — articles, case numbers, and, as of 2026-09-09, **dates**.
Retrieval quality has a real, measured baseline for the first time — built on an
evaluation set authored from actual document content rather than assumptions.
Two defects in the reranker's failure behaviour were found and fixed. One
weight-tuning question was investigated and deliberately **left unanswered**,
because the evidence does not support an answer yet.

The 2026-09-09 half of the session was audit and reconciliation rather than
features, and it found three things worth stating plainly:

1. **There is no minimum relevance threshold anywhere**, and M4's
   "insufficient evidence" branch is unreachable — §10.
2. **Monetary extraction is broken upstream**, and wiring it briefly wrote
   *wrong* data to the live collection before a guard was added — §11.
3. **The project declared Python 3.12 in three files while running on 3.14**,
   and because 3.12 is installed, that silently built the wrong environment
   rather than failing — §12.

Full test suite: **436 passed, 0 failed** (was 414; +22 new).

---

## 2. Confirmed done and verified live

### 2.1 Live instance restored — and an earlier conclusion corrected

A previous report concluded the collection was unreachable because it lived in
an external Docker volume and Docker was unavailable. **That was wrong about the
hosting model.** The instance was never containerised on this host: it runs as a
native `qdrant.exe` against on-disk storage. `infrastructure/qdrant/compose.yml`
describes an intended deployment that was never used here.

Docker genuinely is unavailable (Windows 11 Home, no WSL, no admin rights,
firmware virtualization off) — it simply was never the answer.

**Verified live state:**

| | |
|---|---|
| Points | **1,945** (matches `M3_HANDOFF.md` exactly) |
| Distinct documents | **19** |
| Status | green · indexed vectors 1,945 |
| Dense | 1024-dim, unnamed default vector |
| Sparse | `text_sparse` configured and populated |
| Payload indices | **10** (was 7) |

### 2.2 Identifier payload backfill — applied

The 1,945 points predated identifier search. Backfilled via
`scripts/backfill_identifiers.py --apply`, reusing the *same* function the
indexing service calls, so backfilled and newly-indexed points cannot diverge.

Payload-only: no re-embedding, no vector reads or writes. Verified afterwards
that a sampled point still carries dense(1024) + `text_sparse`.

| | count | share |
|---|---|---|
| Points written | **1,120** | 57.6% |
| No identifier to extract | **825** | 42.4% |
| — article only | 1,025 | |
| — case only | 6 | |
| — both | 89 | |

Reconciles exactly: 1,114 article + 6 case-only = 1,120 written; +825 = 1,945.
The 825 are headings, preambles and connective prose — expected, not a defect.
247 distinct article numbers across 11 of 19 documents.

Point count unchanged at 1,945; new indices `article_no` (1,114),
`article_ref` (1,114), `case_no` (95).

### 2.3 Exact identifier search — live and verified

Consumes `ProcessedQuery.identifiers`, which M2 had populated since the original
contract and which **had no consumer anywhere in the codebase**. `query_processor.py`
was not modified.

The collision problem (an article number is unique only *within* a law) is
solved with two keys: `article_no` (bare `"15"`) and `article_ref`
(`"doc_0422a112599d:a15"`). The query path switches to the compound key
automatically when `document_ids` scopes the search, so precision rises with the
context the caller supplies — no separate code path. The identifier lookup
consumes the **same access `Filter`** as dense and sparse; there is still exactly
one place where access conditions are built.

Verified on live data, each query run twice — once with identifiers stripped
(reproducing pre-fix behaviour), once with the path active:

| Query | Correct chunk before | After |
|---|---|---|
| `ما نص المادة ١٥؟` | rank 9 | **rank 1** |
| `What does article 15 say?` | rank 8 | **rank 1** |

### 2.4 Mention-vs-subject fix — real, but smaller than advertised

**I need to correct my own earlier claim.** I previously reported that chunks
citing `المادة (4)` in passing were outranking the real Article 4. That was
wrong, and I confirmed it by inspection: `ARTICLE_RE` does not match a
parenthesised number, so those chunks never carried `article_no='4'` and never
appeared in the results at all. The real competition is **article 4 of other
laws** — the IP authority law, a WIPO treaty, the constitution. 18 chunks
corpus-wide carry `article_no='4'`.

The genuine defect found: `identifier_search` returned every exact match in
Qdrant's arbitrary scroll order, with no notion of which chunk was *about* the
article. A table-of-contents line carrying six article numbers ranked
identically to the article's actual text.

**Investigating the signal before building on it** (measured across all 1,190
article assignments):

| signal | coverage |
|---|---|
| chunk **opening** declares the article | 90.7% |
| `section` declares the article | **11.4%** |
| either | 92.8% |

`section` is 100% reliable on the two synthetic statute documents and **0.0% on
the four largest real documents** — a section-based boost would have fixed the
case being debugged and done nothing for 88% of the corpus. It is used only as a
secondary signal, never alone.

A leader-dot detector demotes contents lines. The distribution is bimodal with an
empty gap (≥20% dots: 114 chunks; 10–20%: **0 chunks**; <5%: 992), so the
threshold sits in dead space rather than being tuned to a target.

**Honest result:** on the eval set this is **1 case better, 1 worse, 30
unchanged** — aggregate MRR 0.670 → 0.671, R@5 0.844 → 0.859, identifier P@5
0.320 → 0.340, adversarial MRR 0.535 → 0.538. The target case moved 9 → 7, i.e.
improved but **not fixed**. The regression (`adv_contract_article_4_vs_definitions`,
10 → 12) is a case whose ground-truth chunks carry no `article_no` at all — the
same parenthesis gap — so it is reachable only semantically.

The change is principled and structurally correct, and it is close to neutral on
current evidence. I am flagging that rather than presenting it as a win.

A document-level tie-break was also tried and **discarded because it measured
worse** (target case 6 → 7, and it floated a contents line to rank 1).

### 2.5 Reranker fail-loud — two defects fixed, model NOT downloaded

`bge-reranker-v2-m3` was **not** downloaded. That is a policy call about what may
be placed on firm infrastructure, not mine to make by acting.

**Defect 1 — untyped error.** Previously raised a bare `OSError` reading *"Check
your internet connection"*. On a deliberately air-gapped host that describes
policy, not a fault, and sends an operator to chase a non-existent network
problem. Now raises typed `RerankerUnavailable` naming the model, the real
reason, and how to opt into degrading, with the original preserved as
`__cause__`. It is a `RuntimeError`, **not** an `OSError` subclass, so an
`except OSError` for sockets and disks no longer swallows it.

**Defect 2 — silent degradation hole (not previously known).** Setting
`reranker_model_name=""` bypassed `use_mock_fallback=False` entirely:
`_init_model` returned early leaving `model=None`, and `rerank()` then served
heuristic scores with no error at all. That defeated the precise guarantee the
flag exists to provide. Now raises, with a defence-in-depth guard in `rerank()`
for any future path that constructs a reranker differently.

`reranker_use_mock_fallback` default **unchanged at `False`**, pinned by a test.
Startup behaviour confirmed correct and unchanged: the FastAPI lifespan does not
swallow the error, so the app fails to boot rather than serving degraded results.

**Verdict: safe to leave fail-loud in production.** The remaining rough edge is
operational, not code — no deploy with these defaults will boot until the model
is in the local cache.

### 2.6 Evaluation set v2 — first legitimate baseline

`evaluation/benchmark_cases_v2.json` — **37 cases**, every one authored after
reading actual chunk text from the live collection.

The old `evaluation/benchmark_cases.json` is **left in place, unmodified**, and
should not be used: its ground truth is bare `chunk_id`s, and `chunk_017` alone
resolves to 12 different live points, so a "hit" cannot be distinguished from a
coincidence. One of its cases filters `jurisdiction=KSA`, which matches zero
points.

| Category | Cases |
|---|---|
| Plain semantic | 11 |
| Exact identifier | 10 |
| Adversarial / near-miss | 6 |
| Language variation | 5 |
| Negative / no-answer | 5 |

All **47 ground-truth pairs verified to resolve to exactly one live point**; the
build fails hard otherwise. Separately confirmed all 1,945 `(document_id,
chunk_id)` pairs in the collection are unique. 33 cases self-verified, **4 need
lawyer sign-off** (see `evaluation/NEEDS_LAWYER_REVIEW.md`).

No jurisdiction-discriminating cases: the corpus is 100% Egypt, so any other
filter is vacuous — the exact defect that made the old set useless.

**Baseline** (weights 0.9/0.1/1.0, fusion stage, 32 scorable + 5 negatives held
out):

| k | P@k | R@k | MRR | found |
|---|---|---|---|---|
| 5 | 0.244 | 0.859 | 0.671 | 32/32 |
| 10 | 0.131 | 0.906 | 0.671 | 32/32 |

| Category | n | MRR |
|---|---|---|
| identifier | 10 | 0.775 |
| language_variation | 5 | 0.750 |
| semantic | 11 | 0.612 |
| adversarial | 6 | 0.538 |

Read R@k and MRR as the real signals — P@5 is capped at 0.2 for a single-answer
case, so the low absolute number is an artifact of the metric.

Negatives are held out rather than scored: retrieval always returns top-k, so
"insufficient evidence" is M4's decision, not fusion's.

---

## 3. RRF weight tuning — investigated, deliberately not applied

27-combo grid across dense/keyword/identifier, evaluated on the 32 scorable
cases.

Best combo keeping full coverage: **`dense 0.5 / keyword 0.1 / identifier 2.0`**
— MRR 0.683 (vs 0.671 current), R@10 0.906, found 32/32. Its gain concentrates
in the weakest category: adversarial MRR 0.538 → **0.709**. It gives up a little
elsewhere (identifier 0.775 → 0.733, language 0.750 → 0.707).

`0.5/0.3/2.0` scored a nominally higher MRR (0.687) but **loses a case entirely**
(found 31/32, adversarial 5/6) — an aggregate win bought by dropping a case.
Rejected.

**The result did not validate, and I recommend not applying it.** A stratified
split of the 32 cases into halves picked **different winners** (`0.5/0.1/2.0` on
one, `0.9/0.3/1.0` on the other), and the disagreement between halves (~0.10
MRR) is roughly eight times the improvement being chased (~0.012 MRR). The set
is too small to choose between these combos. Saying so is more useful than
shipping a number.

**One finding is robust** across every split and combo: identifier weight `0.0`
is clearly worse — coverage 32/32 → 28/32, MRR ~0.67 → ~0.55. The identifier
path earns its place; its exact weight does not yet have an answer.

Production defaults in `HybridSearcher.__init__` are **unchanged**.

---

## 4. Still blocked on M6

Unchanged from the previous handoff — none of these exist in the codebase.

- **Status / lifecycle fields** (`current` / `superseded` / `review_required`,
  effective dates). Confirmed by direct scroll: **zero of 1,945 points** carry
  any of them. Not filterable today.
- **Related-record queries** (case-cites-law, judge/court history, article
  relationships) for fusion into retrieval as a ranking signal — not a
  post-rerank decoration.
- **`index_sync` change events** (`create` / `update` / `delete`). No producer
  exists. Without it M3's index and M6's canonical store drift silently: a
  superseded law stays retrievable and nothing notices.

The dense/sparse/identifier half of fusion is live and unaffected.

---

## 5. Needs an M4 conversation

**`EvidenceItem` drops fields.** Confirmed again this session — unchanged, no
code touched. `EvidenceItem` carries exactly 7 fields: `document_id`,
`chunk_id`, `text`, `page`, `section`, `language`, `score`.

Present on the internal candidate dict and **dropped** when the M4 contract is
built: `client_id`, `matter_id`, `confidentiality_level`, `jurisdiction`,
`document_type`, `point_id`, `rrf_score`, plus this session's `article_no`,
`article_ref`, `case_no`, `subject_score` and `matched_by`.

Nothing added this session changed the M4 contract. If M4 or M6 needs access
metadata or retrieval provenance alongside evidence, that is a contract change
and needs agreement first.

---

## 6. Decisions needed from a human

> **Superseded by [OPEN ITEMS](#open-items) at the top of this document**, which
> covers the whole session and splits items by who is waiting on them. This
> section is the 2026-09-08 snapshot, kept for history. Where the two differ,
> OPEN ITEMS is current — in particular the eval set is now 41 cases, not 37,
> and a fourth M2 item (ISSUE-3, the money regex) has been added.

1. **Reranker model** — download `bge-reranker-v2-m3` (~2.2 GB) into the local
   HF cache, or keep the fail-loud posture? Nothing deploys with current
   defaults until it is cached. The "nothing leaves firm infrastructure"
   constraint makes this a policy call.
2. **Lawyer review of 4 eval cases** — `evaluation/NEEDS_LAWYER_REVIEW.md`. The
   other 33 are factual/structural and usable now.
3. **RRF weights** — my recommendation is **do not apply** `0.5/0.1/2.0` yet.
   The split disagreement exceeds the effect size. The better spend is growing
   the eval set to 60–100 cases, weighted toward semantic and adversarial, then
   re-running the sweep. Overrule me if you want the nominal MRR gain now.
4. **OCR/extraction gap** — `docs/KNOWN_ISSUES.md` ISSUE-1. 279 chunks (14.3%)
   have no article identifiers. Scoped for a future session; needs an M2
   sign-off on the pattern, not a rushed fix.

---

## 7. Current live Qdrant state

> **The payload-index row below is the 2026-09-08 state (10 indices).** Four
> more were added on 2026-09-09 for dates and monetary values — see
> [§13](#13-final-verification-2026-09-09-session-close) for the current
> 14-index reading. Everything else in this table still holds.

**Verified this session** (read from the running server, not assumed):

| | |
|---|---|
| Endpoint | `http://127.0.0.1:6333` (native `qdrant.exe`) |
| **Storage root** | **`E:\Trend Egypt\Law firm 34\qdrant_data`** — moved off `%TEMP%` 2026-09-09; start with `qdrant_data\start_qdrant.ps1` |
| Collection | `legal_documents_v2`, status **green** |
| Points | **1,945** · indexed vectors 1,945 · 19 documents |
| Vectors | dense 1024-dim + sparse `text_sparse` |
| Payload indices | **10** — `article_no` 1,114 · `article_ref` 1,114 · `case_no` 95 · `client_id` / `matter_id` / `confidentiality_level` / `document_id` / `document_type` / `jurisdiction` / `language` all 1,945 |
| ACL coverage | 1,945/1,945 (`_shared` / `_none` / `public`) |
| Jurisdiction | 1,945/1,945 populated — **all `Egypt`** |

**Still assumed, not verified:**

- **Jurisdiction filtering works as a discriminator.** 100% populated but
  single-valued, so it is fully covered and completely untested — no query in
  this corpus can be narrowed by it.
- **End-to-end reranked quality.** Every number here is measured at the
  **fusion** stage. The cross-encoder has never run on this host, so real
  reranked relevance is unmeasured.
- **Behaviour on real client documents.** The corpus is public statutes and
  synthetic material with a uniform ACL. Multi-tenant behaviour is enforced and
  tested in code, but has never been exercised against real per-matter data.

---

## 8. Files changed this session

| Path | Change |
|---|---|
| `src/retrieval/identifiers.py` | subject ranking, contents-line detector, paren-tolerant ranking pattern |
| `src/retrieval/hybrid_search.py` | identifier results ordered by subject strength; configurable fusion weights |
| `src/retrieval/reranker.py` | `RerankerUnavailable`; both fail-loud defects |
| `src/retrieval/__init__.py` | export `RerankerUnavailable` |
| `src/vector_store/qdrant_manager.py` | identifier payload indices, `identifier_search` |
| `src/indexing/service.py` | writes identifier payload keys at index time |
| `scripts/backfill_identifiers.py` | **new** — payload-only backfill |
| `scripts/tune_rrf_weights.py` | **new** — weight sweep harness |
| `evaluation/benchmark_cases_v2.json` | **new** — 37 verified cases |
| `evaluation/NEEDS_LAWYER_REVIEW.md` | **new** — 4 flagged cases |
| `docs/KNOWN_ISSUES.md` | **new** — OCR gap, unvalidated weights |
| `tests/test_identifier_search.py` | **new** — 15 tests |
| `tests/test_reranker_fail_loud.py` | **new** — 9 tests |
| `evaluation/benchmark_cases.json` | **untouched**, retained, do not use |

**Test suite at that point: 414 passed, 0 failed.**

### 8.1 Files changed 2026-09-09 (second half of the session)

| Path | Change |
|---|---|
| `src/retrieval/identifiers.py` | `normalize_date`, `normalize_money` (incl. U+066C fold and zero-amount guard), `date_ref`, `money_ref`; `normalize_identifier_set` and `extract_from_text` extended |
| `src/retrieval/hybrid_search.py` | date/money consumed in `_identifier_search`; bare-vs-compound switch; log line widened |
| `src/vector_store/qdrant_manager.py` | 4 new `IDENTIFIER_PAYLOAD_FIELDS`; `identifier_search` takes dates/money; `_project` carries the new keys |
| `tests/test_date_money_identifiers.py` | **new** — 22 tests |
| `tests/test_vector_store_payload_schema.py` | `EXPECTED_INDEXED_FIELDS` updated 10 → 14 |
| `evaluation/benchmark_cases_v2.json` | +4 `identifier_date` cases (37 → 41), counts and provenance note updated |
| `docs/KNOWN_ISSUES.md` | **ISSUE-3** — Arabic thousands separator defeats monetary extraction |
| `docs/M3_SESSION_SUMMARY.md` | OPEN ITEMS; §10–§13; §6/§7 marked superseded |
| `docs/M3_INTEGRATION_STATUS.json` | `python_version_note` corrected (the "3.12 not installed" claim was wrong) |
| `docs/ENVIRONMENT.md` | **new** — environment and dependency authority (written as a root `README.md` section; moved when main's .NET backend README took that filename) |
| `pyproject.toml` | `requires-python` 3.12 → 3.14; dev group pinned to validated versions; `[tool.uv]` authority note |
| `.python-version` | `3.12` → `3.14` |
| `uv.lock` | regenerated — `requires-python` `==3.14.*`, 3 dev pins realigned |
| `qdrant_data/rebuild_venv.ps1` | corrected the "3.12 is NOT installed" note; expected counts 414 → 436, MRR 0.671 → 0.707 |
| `src/query_processor.py` | **untouched** — M2 owns extraction; see ISSUE-3 |
| `src/pipeline.py`, `src/orchestration/service.py` | **untouched** — the threshold design is proposed, not implemented |

**Live data:** `date_no`/`date_ref` backfilled to 17 points, `money_no`/`money_ref`
to 4. Point count unchanged at 1,945. Three erroneous `EGP:0` keys written and
then deleted — see §11.4.

**Test suite: 436 passed, 0 failed.**

---

## 9. Storage relocation (2026-09-09)

The live index and the `qdrant.exe` binary both sat under `%TEMP%` and were one temp cleanup away from being lost. Both now live at
`E:\Trend Egypt\Law firm 34\qdrant_data` — a **sibling of the repo, not inside it**, so no `.gitignore` entry is needed.

Start with `qdrant_data\start_qdrant.ps1`; see `qdrant_data\README.md`.

Copied rather than moved, and verified before retiring the original: 1,945 points, 1,945 indexed vectors, green, all 10 payload indices — and the real pipeline re-run (`ما نص المادة ١٥؟` → rank 1, matching pre-move exactly), which proves the *data* survived rather than just the folder.

`infrastructure/qdrant/compose.yml` now carries a header saying it is **not** the live deployment; an earlier audit lost time trusting it over the running process.

**Update 2026-09-09:** `%TEMP%` was subsequently deleted, which did exactly what was predicted — the index and binary survived on E:, the venv did not. It has been rebuilt at `E:\Trend Egypt\Law firm 34env` (Python 3.14, matching the environment the baseline was measured in). Nothing under `%TEMP%` is load-bearing any more.

**Baseline reproduced exactly.** After the rebuild the harness returns MRR 0.671, R@5 0.859, R@10 0.906, 32/32 found, and per-category MRR identifier 0.775 / language 0.750 / semantic 0.612 / adversarial 0.538 — identical to the pre-deletion numbers, down to the individual per-case rank string. The test suite is 414 passed. Newer `sentence-transformers` (5.7.0) and `transformers` (5.15.0) pins did not perturb BGE-M3 embeddings.

That rebuild exposed a reproducibility gap: `requirements.txt` was missing `pytest`, `pytest-asyncio` and `python-multipart`, so a clean rebuild from it could not run the test suite. Added as `requirements-dev.txt`.

---

## 10. Minimum relevance thresholds — audited, absent, design proposed (2026-09-09)

An explicit M3 deliverable that had never been checked. Investigated rather than
assumed, in both directions.

### 10.1 There is no threshold, anywhere

Traced the full path. No minimum-score, floor, or confidence gate exists at any
stage:

| stage | behaviour |
|---|---|
| `HybridSearcher._reciprocal_rank_fusion` | sorts by RRF score, returns `sorted_keys[:top_k]` |
| `BGEReranker.rerank` | sorts by score, returns `reranked[:top_k]` |
| `M3RetrievalPipeline.run` | builds an `EvidenceItem` for every surviving chunk, unconditionally |
| `config/retrieval_config.yaml` | `candidate_top_k`, `final_top_k`, `rrf_k` — no threshold key |

**Retrieval always returns top-k regardless of how weak the matches are.**

### 10.2 M4's abstention path is dead code

The only "no confident answer" branch in the system is
`M4OrchestrationService.answer_search`:

```python
if not retrieved_evidence.retrieved_evidence:
    return self._build_insufficient_evidence_response(processed_query)
```

That triggers only on **zero** retrieved items, which cannot happen against a
non-empty collection. The bilingual "insufficient evidence" messages, and the
`confidence=0.0` response they build, are unreachable in practice.

### 10.3 What the 5 negative cases actually return

All five ran through the live pipeline. Every one returned a **full 20
candidates**, top-5 handed to M4 as ordinary evidence with no signal of any
kind. `neg_insurance_premium` returns rent and supply non-payment clauses at
dense 0.51 — precisely the plausible-looking wrong answer that case was written
to catch.

### 10.4 Measured score distributions

| | dense top-1 |
|---|---|
| 5 negatives | 0.4689 – **0.5100** |
| 32 positives | **0.4336** – 0.8602 |

Those overlap — but the *only* positive below the negative ceiling
(`id_collision_article_4_scoped`, 0.4336) is an **exact identifier hit at rank
1**: correct answer, low dense score. And **no negative case produced an
identifier match at all** (0/5, against 16/32 positives).

That is what makes a usable rule out of two individually-useless signals:

```
low_confidence = (no identifier match in top-k) AND (dense top-1 < T)
```

| T | negatives flagged | positives wrongly flagged |
|---|---|---|
| 0.50 | 3/5 | 0/32 |
| **0.52** | **5/5** | **0/32** |
| 0.54 | 5/5 | 1/32 |
| 0.56 | 5/5 | 3/32 |

**`rrf_score` is the wrong signal and must not be used as the floor.** It is
rank-derived, so it is near-constant regardless of match quality — negatives
0.0148–0.0162 against positives 0.0148–0.0328, overlapping at the bottom. Dense
cosine is the only score here comparable across queries.

### 10.5 Recommendation — flag, do not drop

Add a field to `EvidenceItem`/`RetrievedEvidence` and keep returning the chunks.
Dropping would make a relevance judgment inside the retrieval layer with no way
for M4 to see what was withheld — and the same argument the ACL post-retrieval
check makes applies: a silent drop turns a ranking problem into an invisible one.

**Honest caveat.** T=0.52 sits in a gap of **0.023** between 5 negative points
and 32 positive ones. That is *not* the situation the leader-dot threshold had
(an empty region in a bimodal distribution of 1,190 samples). It is fitted to
five points and sits near the edge. Treat 0.52 as the shape of the answer;
settling the value needs more negative cases — see the deferred item on growing
the eval set.

**Not implemented.** Contract change, so it needs Youssef's sign-off, then an M4
conversation. OPEN ITEMS #1 and #8.

---

## 11. Dates and monetary values wired into retrieval (2026-09-09)

`ProcessedQuery.identifiers.dates` and `.monetary_values` had been populated by
M2 since the original contract and, like `article_numbers` before them, had **no
consumer anywhere**. `query_processor.py` was not modified.

### 11.1 A correction to the brief: M2 extracts, it does not normalize

The premise going in was that M2 "extracts and normalizes" these. It does not.
Both fields carry the **raw matched substring**:

| field | real values from M2 |
|---|---|
| `dates` | `2026-01-15`, `15/03/2026`, `1 February 2026`, `11 Nov 2023` |
| `monetary_values` | `$50,000`, `500,000 جنيه`, `1,250.50 EGP`, `٥٠٠٠ جنيه` |

Normalization is M3's job, exactly as it already is for
`normalize_article_number`. Added `normalize_date` (to ISO `YYYY-MM-DD`) and
`normalize_money` (to `CURRENCY:amount`).

**Day-first is not a locale guess.** The corpus contains `20/03/2026`, which has
no month-first reading; `15/03/2026` and `12/03/2026` agree. ISO ordering is
detected structurally (four-digit leading component), not by separator.

### 11.2 Wiring — same pattern, same collision reasoning as articles

Four new payload keys, KEYWORD-indexed, OR-ed into `identifier_search`, fused
through the existing RRF path with no new retriever and no new place where
access conditions are built:

| key | meaning |
|---|---|
| `date_no` / `money_no` | bare token — "this date, in any document" |
| `date_ref` / `money_ref` | `{document_id}:d{iso}` / `{document_id}:m{cur}:{amt}` |

The bare/compound switch fires on `filters.document_ids`, identically to
`article_ref`. **Dates need it more than articles do:** `2026-05-30` is carried
by **5 chunks across 3 documents** in the live collection — the Arabic supply
contract, its near-duplicate, and a standalone payment annex.

Currency is part of the money key deliberately: amount alone is the monetary
equivalent of the bare-`article_no` collision, and there is no reason to accept
it.

### 11.3 Result — dates work, and the MRR gain is zero

| | P@5 | R@5 | MRR | found |
|---|---|---|---|---|
| Original 32, before | 0.244 | 0.859 | 0.671 | 32/32 |
| Original 32, after | 0.244 | 0.859 | **0.671** | 32/32 |
| 4 date cases, before | 0.400 | 0.950 | 1.000 | 4/4 |
| 4 date cases, after | 0.450 | 1.000 | **1.000** | 4/4 |
| All 36, before to after | 0.261 to 0.267 | 0.869 to 0.875 | **0.707 to 0.707** | 36/36 |

**MRR delta is +0.000, and the per-case ranks on the original 32 are
byte-identical.** The date path genuinely fires — `identifier` appears in
`matched_by` on every ground-truth chunk — but dense+sparse already had a correct
chunk at rank 1 on all four cases, because a date is a lexically distinctive
string that the sparse half already matched.

What it actually bought is ordering *within* the correct set: the milestone
collision case moved 6 to 5, the promulgation case 4 to 2, giving R@5 +0.050 on
that subset. That is a real but modest gain and is not being presented as more.
The corpus holds only 12 distinct dates across 17 chunks, so there is little
room for it to show more here.

### 11.4 Monetary is wired, unit-tested, and cannot retrieve — ISSUE-3

`QueryProcessor.MONEY_RE` accepts ASCII `,` as its only thousands separator. The
real Egyptian contracts use **U+066C ARABIC THOUSANDS SEPARATOR**:

| source text | M2 extracts | true value |
|---|---|---|
| `2٬450٬000 جنيه مصري` | `000 جنيه` | 2,450,000 EGP |
| `480٬000 جنيه مصري` | `000 جنيه` | 480,000 EGP |

**This briefly corrupted live data.** The first backfill wrote `EGP:0` as the
contract value of three unrelated agreements — a 2.45 M supply contract and a
480 K lease sharing one key, silently joined. Fixed by refusing zero amounts in
`normalize_money` (mirroring `normalize_article_number` refusing article 0),
deleting the three keys from the live collection, and re-running the backfill.
`money_no` went 7 to 4 points.

The 4 survivors are all from `doc_9a12cb861d01`, which is OCR failure
(`REY RAP I ie PP ore hare IP pee Ik Key`), not currency. **Net: zero real
amounts are retrievable by value.**

Deliberately **not** worked around in M3. `normalize_money` folds U+066C, so
this layer is correct the moment extraction is — but re-extracting from raw text
inside M3 would put a second money pattern in the codebase and let the index
side and query side drift silently, which is the exact failure the `identifiers`
module docstring argues against for article numbers. See OPEN ITEMS #5.

### 11.5 Evaluation set: 37 to 41 cases

Four `identifier_date` cases, every ground-truth pair read from full live chunk
text and re-verified to resolve to exactly one point, matching the file's own
provenance rule. **No monetary case was authored** — doing so would mean
asserting behaviour that is wrong upstream.

`tests/test_date_money_identifiers.py` — **22 new tests**, including a paired
"dense alone ranks the wrong milestone first" assertion so the exact-match tests
cannot pass vacuously.

---

## 12. Python version and dependency authority reconciled (2026-09-09)

### 12.1 A three-way mismatch that failed silently

The project declared **3.12** in three places while running on **3.14**:

| file | was | now |
|---|---|---|
| `.python-version` | `3.12` | `3.14` |
| `pyproject.toml` `requires-python` | `>=3.12,<3.13` — *excluded* the actual runtime | `>=3.14,<3.15` |
| `uv.lock` | `==3.12.*` | `==3.14.*` |

**The previously-recorded reason this was "safe" was wrong.** `rebuild_venv.ps1`
and `M3_INTEGRATION_STATUS.json` both stated 3.12 "is NOT installed on this
host". It is: `uv python list` finds CPython 3.12.10 at `pythoncore-3.12-64`,
and `uv python find` inside `AI-Lexora/` resolved to it. So the mismatch did not
fail loudly — it silently built a **3.12** environment for anyone running
`uv venv` without the explicit `--python 3.14` that `rebuild_venv.ps1` passes.

Verified after the fix: `uv python find` gives CPython **3.14.0**. Both stale
notes corrected.

### 12.2 Dependency authority — `requirements.txt`

**`requirements.txt` (plus `requirements-dev.txt`) is the source of truth.** It
is what `rebuild_venv.ps1` installs from and the only file used to build the
venv the baseline was validated on. `uv.lock` is kept in sync but **nothing runs
`uv sync`**.

The note lives in `docs/ENVIRONMENT.md` and `pyproject.toml`, **not** as a comment at the
top of `uv.lock`: `uv lock` rewrites that file wholesale and would strip it.

The real chain is
`pyproject.toml` to `uv.lock` (via `uv lock`) to `requirements.txt` (via
`uv export`), so `pyproject.toml` is the only one of the three to edit by hand.

### 12.3 They were not actually in agreement — now they are

Checking rather than assuming found **3 version mismatches**:

| package | requirements | uv.lock (was) |
|---|---|---|
| `pytest` | 8.4.2 | **9.1.1** — a major version ahead of anything this suite has run on |
| `pytest-asyncio` | 1.2.0 | 1.4.0 |
| `python-multipart` | 0.0.20 | 0.0.32 |

Cause: `pyproject.toml` declared `pytest>=7.0.0`, `pytest-asyncio>=1.4.0` and
`python-multipart==0.0.32`. The `pytest-asyncio` constraint **excluded the
installed 1.2.0**, and the `python-multipart` hard pin contradicted the
validated 0.0.20 outright. The dev group is now pinned to the validated
versions and the lock regenerated.

**Verified state:** 127 pinned packages, **0 mismatches between the two files**,
**0 mismatches between `requirements.txt` and the installed venv**. The 3
packages present only in `uv.lock` are the project itself plus `iniconfig` and
`pluggy`, transitive test dependencies the dev requirements do not pin directly.

---

## 13. Final verification (2026-09-09, session close)

**Live collection — read from the running server:**

| | |
|---|---|
| Status | **green** · 1,945 points · indexed vectors **1,945** · 8 segments |
| Vectors | dense 1024-dim Cosine + sparse `text_sparse` |
| Payload indices | **14** — `article_no` 1,114 · `article_ref` 1,114 · `case_no` 95 · `date_no` 17 · `date_ref` 17 · `money_no` 4 · `money_ref` 4 · `client_id` / `matter_id` / `confidentiality_level` / `document_id` / `document_type` / `jurisdiction` / `language` all 1,945 |
| Snapshot | `legal_documents_v2-5638308777856478-2026-09-09-13-43-15.snapshot` — 1,530,683,904 bytes, checksum `0d40e563f2f9faa473c2a6ae30d9ee5a06c9e26fa0356814cbc1495296440466`, taken **before** any write this session |

**Live reference queries — real pipeline, real collection, all rank 1:**

| query | rank | matched via |
|---|---|---|
| `ما نص المادة ١٥؟` | **1** | dense + identifier |
| `What does article 15 say?` | **1** | dense + identifier |
| `Which milestone is due on 2026-05-30?` | **1** | dense + keyword + identifier |

The first two match the pre-`%TEMP%`-deletion behaviour exactly, which is what
proves the *data* survived rather than just the folder.

**Test suite:** 436 passed, 0 failed.
**Evaluation harness:** MRR 0.707 · R@5 0.875 · P@5 0.267 · 36/36 found, over
41 cases at the fusion stage with weights 0.9/0.1/1.0.

Per-category MRR: `identifier_date` 1.000 · `identifier` 0.775 ·
`language_variation` 0.750 · `semantic` 0.612 · `adversarial` 0.538.
