import logging
import re
from typing import List, Dict, Any, Literal, Optional, Sequence
from rank_bm25 import BM25Okapi

from src.vector_store.qdrant_manager import (
    QdrantVectorStore,
    VALID_LIFECYCLE_STATUSES,
    to_sparse_vector,
)
from src.retrieval.identifiers import (
    article_ref,
    date_ref,
    money_ref,
    normalize_identifier_set,
    rank_identifier_candidates,
)
from src.schemas.access_control import AccessScopeRequired
from src.schemas.m2_contract import ProcessedQuery

logger = logging.getLogger(__name__)


KeywordBackend = Literal["sparse", "bm25"]
"""Which keyword retriever supplies the second half of the hybrid.

``"sparse"``
    BGE-M3 lexical weights stored as a Qdrant sparse vector and searched
    natively, scoped by the same access filter as dense search.
``"bm25"``
    The original path: scroll the (access-filtered) collection and score it
    with rank_bm25 in Python. Retained for A/B comparison, not as a fallback.

Both are ACL-equivalent -- they consume the same ``Filter`` -- so switching
between them is a relevance decision, never a security one.
"""

DEFAULT_IDENTIFIER_WEIGHT = 1.0
"""RRF weight for the exact-identifier ranking. **Un-tuned, like the other two.**

Chosen so that an exact identifier hit at rank 1 scores just above the best
possible dense hit and below nothing else:

    identifier rank 1 -> 1.0 / (60 + 1) = 0.01639
    dense      rank 1 -> 0.9 / (60 + 1) = 0.01475

That ordering is the whole point -- when a caller asks for article 15 by
number, the chunk that *is* article 15 should outrank the chunk that merely
reads like it. But 1.0 is a first principled guess, not a measured optimum: it
was picked to satisfy that single inequality, against no labeled data.

It is deliberately not set high enough to dominate outright. Identifier
extraction can be wrong (a stray number in prose, an OCR digit error), and a
weight that buried every semantic candidate would turn one bad extraction into
a query that returns nothing useful. Fusing rather than short-circuiting keeps
a wrong identifier survivable.

**All three weights now need real tuning together**, and there is still no
labeled evaluation set to tune them against. Adding this one did not make the
other two more trustworthy -- it made the untuned surface larger.
"""

DEFAULT_DENSE_WEIGHT = 0.9
DEFAULT_KEYWORD_WEIGHT = 0.1
"""RRF weights, carried over unchanged from the BM25 era.

These were tuned -- to whatever extent they were tuned -- against Python BM25
scores over a full-collection scroll. Native sparse retrieval has a different
score distribution and a different candidate set, so 0.9/0.1 is a *starting
point for re-tuning*, not a validated setting. Re-tune empirically against the
evaluation harness once real sparse retrieval is live; the fact that the
numbers did not change when the retriever underneath them did is a reason to
distrust them, not to trust them.
"""

MEASURED_MIN_DENSE_SCORE = 0.515
"""Candidate evidence-sufficiency gate on the **top dense cosine score**.
**Not enabled by default** -- see ``HybridSearcher.min_dense_score``.

Measured 2026-09-15 on ``benchmark_cases_v2.json`` (62 cases) against the live
``legal_documents_v2`` collection (BGE-M3 dense, unscoped queries):

    answerable cases (n=50)   top-1 dense cosine  min 0.521  median 0.649
    no-answer cases  (n=12)   top-1 dense cosine  max 0.542  median 0.496

    threshold   no-answer blocked   answerable wrongly blocked
    0.510            8 / 12                 0 / 50
    0.515            9 / 12                 0 / 50
    0.530           10 / 12                 2 / 50
    0.545           12 / 12                 4 / 50

**The classes overlap, so this is a partial filter, not an abstention
decision.** 0.515 is the highest value that wrongly blocks no answerable case,
and it still lets 3 of 12 no-answer queries through (overtime hours 0.542,
joint-stock shareholder rights 0.533, divorce grounds 0.528 -- all phrased in
legal vocabulary close to material the corpus does hold). Those must still be
caught downstream by M4's grounding and citation checks.

With the first 5 negatives alone the classes separated perfectly; adding 7 more
broke that. Expect the numbers to move again as cases are added, and
re-measure whenever the embedding model or corpus changes. Two other signals
were measured and rejected because they overlap far more: the top-1 sparse
score and the dense top-1 minus top-5 gap.
"""


def tokenize_text(text: str) -> List[str]:
    """
    Simple whitespace/punctuation tokenizer supporting Arabic and English.
    """
    text_clean = re.sub(r'[^\w\s]', ' ', text.lower())
    return [t for t in text_clean.split() if t]

def build_retrieval_text(
    query: ProcessedQuery,
) -> str:
    """
    Build lexical/reranker text strictly from M2-owned
    outputs.

    M3 does not translate, extract entities, or invent
    query variants.

    It consumes:
    - normalized text;
    - M2 controlled query variants;
    - M2 preserved party names;
    - M2 named legal terms.
    """

    normalized_identifiers = (
        normalize_identifier_set(
            query.identifiers
        )
    )

    candidates = [
        (
            query.normalized_text
            or query.text_original
        ),
        *query.query_variants,
        *normalized_identifiers[
            "party_names"
        ],
        *normalized_identifiers[
            "named_legal_terms"
        ],
    ]

    seen: set[str] = set()
    parts: list[str] = []

    for value in candidates:

        cleaned = " ".join(
            str(value or "").split()
        ).strip()

        if not cleaned:
            continue

        dedupe_key = cleaned.casefold()

        if dedupe_key in seen:
            continue

        seen.add(
            dedupe_key
        )

        parts.append(
            cleaned
        )

    return "\n".join(
        parts
    )
class HybridSearcher:
    """
    Hybrid search: dense vector retrieval fused with keyword retrieval via
    Reciprocal Rank Fusion.

    Expects ``query.embedding`` from M2, and -- for the native sparse
    backend -- ``query.sparse_embedding`` as well.

    Access control
    --------------
    Both halves of the hybrid consume the *same* ``Filter`` object, built once
    per query by ``build_qdrant_filter`` from the caller's ``AccessScope``.
    Adding sparse retrieval added a read path, not an access path: there is
    still exactly one place where access conditions are constructed, and every
    retriever is filtered by Qdrant during the search rather than afterwards.
    """

    def __init__(
        self,
        vector_store: QdrantVectorStore,
        rrf_k: int = 60,
        keyword_backend: KeywordBackend = "sparse",
        dense_weight: float = DEFAULT_DENSE_WEIGHT,
        keyword_weight: float = DEFAULT_KEYWORD_WEIGHT,
        identifier_weight: float = DEFAULT_IDENTIFIER_WEIGHT,
        min_dense_score: Optional[float] = None,
        allowed_validity_statuses: Optional[Sequence[str]] = None,
        include_unversioned_points: bool = False,
    ):
        self.vector_store = vector_store
        self.rrf_k = rrf_k
        self.keyword_backend = keyword_backend

        if min_dense_score is not None and not 0.0 <= min_dense_score <= 1.0:
            raise ValueError("min_dense_score must be between 0.0 and 1.0")

        self.min_dense_score = min_dense_score
        """Abstain (return no candidates) when the best dense cosine score is
        below this. ``None`` disables the gate, which is the default.

        Returning nothing rather than weak candidates is deliberate: M4
        already answers an empty ``RetrievedEvidence`` with a deterministic
        insufficient-evidence response and no LLM call, so the gate needs no
        contract change. See :data:`MEASURED_MIN_DENSE_SCORE` for the
        measured value, its trade-off, and why it is a partial filter that
        stays off by default."""

        if allowed_validity_statuses is None:

            self.allowed_validity_statuses = (
                None
            )

        else:

            normalized_statuses = list(
                dict.fromkeys(
                    str(status)
                    .strip()
                    .lower()
                    for status
                    in allowed_validity_statuses
                    if str(status).strip()
                )
            )

            if not normalized_statuses:
                raise ValueError(
                    "allowed_validity_statuses "
                    "must be None or a "
                    "non-empty list"
                )

            invalid_statuses = sorted(
                set(normalized_statuses)
                - VALID_LIFECYCLE_STATUSES
            )

            if invalid_statuses:
                raise ValueError(
                    "Unsupported validity_status "
                    "value(s): "
                    + ", ".join(
                        invalid_statuses
                    )
                )

            self.allowed_validity_statuses = (
                normalized_statuses
            )
        """Restrict retrieval to these ``validity_status`` payload values
        (M6's ``current`` / ``superseded`` / ``review_required``). ``None``
        applies no status condition, which is today's behaviour: no point in
        the live collection carries the field yet."""

        self.include_unversioned_points = include_unversioned_points
        """When the status filter is on, whether points with no
        ``validity_status`` at all still match. Defaults to False (fail
        closed). Every point indexed before M6 sync existed has no status, so
        turning the filter on with this False hides the whole current corpus
        -- that trade-off is a team decision, so it is an explicit switch."""

        # Fusion weights were previously reachable only as default arguments
        # on a private method, so nothing could vary them without editing the
        # module -- which is why three weights are documented as un-tuned and
        # none has ever been measured. Surfacing them here changes no
        # behaviour (the defaults are the same constants) and is what lets the
        # tuning harness sweep them through the public API.
        self.dense_weight = dense_weight
        self.keyword_weight = keyword_weight
        self.identifier_weight = identifier_weight

    def search(self, query: ProcessedQuery, candidate_top_k: int = 20) -> List[Dict[str, Any]]:
        """
        Execute Hybrid Search (Dense + BM25) filtered by metadata constraints.
        Requires query.embedding to be set by M2 upstream.
        """
        if not query.embedding:
            raise ValueError(
                "query.embedding is empty. M2 must provide a dense embedding vector before M3 search."
            )

        # Access scope is checked before anything touches the vector store.
        # QueryFilters.access is Optional in the schema so that non-retrieval
        # callers can construct filters without one; retrieval is where that
        # optionality ends.
        if query.filters.access is None:
            raise AccessScopeRequired(
                "Hybrid search requires QueryFilters.access. The server sets "
                "it from the authenticated caller; its absence means the "
                "request reached retrieval without an identity, and an "
                "unscoped search would return every tenant's documents."
            )

        # 1. Build Metadata Filter (access conditions included, always)
        qdrant_filter = (
            self.vector_store.build_qdrant_filter(
                access=query.filters.access,
                document_ids=(
                    query.filters.document_ids
                ),
                document_type=(
                    query.filters.document_type
                ),
                jurisdiction=(
                    query.filters.jurisdiction
                ),
                language=query.filters.language,
                extra_filters=(
                    query.filters.extra_filters
                ),
                validity_statuses=(
                    self.allowed_validity_statuses
                ),
                include_unversioned_points=(
                    self.include_unversioned_points
                ),
            )
        )

        # 2. Dense Vector Search (embedding provided by M2)
        dense_results = self.vector_store.dense_search(
            query_vector=query.embedding,
            query_filter=qdrant_filter,
            top_k=candidate_top_k
        )

        # 2b. Evidence-sufficiency gate. Runs before the keyword and
        # identifier searches, so an abstained query costs one search.
        if self.min_dense_score is not None:
            top_dense = (
                dense_results[0].get("score", 0.0)
                if dense_results
                else 0.0
            )

            if top_dense < self.min_dense_score:
                logger.info(
                    "retrieval_abstained query_id=%s top_dense_score=%.4f "
                    "min_dense_score=%.4f",
                    query.query_id,
                    top_dense,
                    self.min_dense_score,
                )
                return []

        # 3. Keyword search over the same access-filtered scope.
        keyword_results = self._keyword_search(
            query=query,
            qdrant_filter=qdrant_filter,
            top_k=candidate_top_k,
        )

        # 3b. Exact identifier lookup, when M2 found an identifier in the
        # query. Same filter object again -- a third retriever, still one
        # place where access conditions are built.
        #
        # Dense results are handed over as a tie-breaker: exact matching alone
        # cannot tell article 4 of the supply law from article 4 of the
        # constitution, because both genuinely are article 4.
        identifier_results = self._identifier_search(
            query=query,
            qdrant_filter=qdrant_filter,
            top_k=candidate_top_k,
            dense_results=dense_results,
        )

        # 4. Fuse using Reciprocal Rank Fusion (RRF)
        fused_candidates = self._reciprocal_rank_fusion(
            dense_results=dense_results,
            keyword_results=keyword_results,
            identifier_results=identifier_results,
            top_k=candidate_top_k
        )

        return fused_candidates

    def _identifier_search(
        self,
        query: ProcessedQuery,
        qdrant_filter,
        top_k: int,
        dense_results: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Exact structured lookup, when the query carries a legal identifier.

        Consumes ``ProcessedQuery.identifiers``, which M2 has populated on
        every query since the original contract and which had **no consumer
        anywhere in the codebase** until now -- extraction ran and the result
        was discarded on every request. Nothing in M2 changed to enable this;
        the field was already there.

        Returns ``[]`` when the query names no identifier, which is the common
        case. Fusion then sees an empty third ranking and behaves exactly as
        it did before, so a non-citation query is unaffected.

        Precision scales with the context the caller supplied. When
        ``filters.document_ids`` scopes the query to specific laws, the
        law-scoped ``article_ref`` key is used and "article 15" means article
        15 *of those laws*. With no document scope there is nothing to
        disambiguate against, so the bare ``article_no`` key is used and every
        law's article 15 is a candidate -- deliberately, because that is the
        honest answer to an under-specified question, and RRF still lets the
        semantic halves decide which of them is relevant.

        Four identifier kinds feed this path -- articles, case numbers, dates
        and monetary values -- and all four take the same bare/compound switch.

       
        Party names are treated as entity-like exact lookup
        tokens.

        Named legal terms and controlled query variants are
        not treated as exact identifiers because concepts such
        as force majeure or arbitration can occur across many
        documents. They participate through lexical retrieval
        and final reranking instead.

        """

        normalized = normalize_identifier_set(query.identifiers)

        article_numbers = normalized["article_numbers"]
        case_numbers = normalized["case_numbers"]
        dates = normalized["dates"]
        money_values = normalized["money_values"]
        party_names = normalized[
            "party_names"
        ]

        if not any(
            (
                article_numbers,
                case_numbers,
                dates,
                money_values,
                party_names,
            )
        ):
            return []

        scoped_document_ids = query.filters.document_ids

        article_refs = None
        if article_numbers and scoped_document_ids:
            article_refs = [
                article_ref(document_id, number)
                for document_id in scoped_document_ids
                for number in article_numbers
            ]
            # The compound key already encodes the document, so passing the
            # bare numbers as well would re-widen the lookup to every law and
            # undo the disambiguation.
            article_numbers = None

        # Dates and monetary values take the same bare-vs-compound switch, and
        # they need it at least as much. In the live collection a single
        # payment-milestone date is carried by five chunks across three
        # documents -- the Arabic contract, its English counterpart, and a
        # standalone payment annex -- so an unscoped date lookup returns every
        # copy of the same schedule. Amounts are worse still: round figures
        # are shared by unrelated matters for no reason at all.
        date_refs = None
        if dates and scoped_document_ids:
            date_refs = [
                date_ref(document_id, value)
                for document_id in scoped_document_ids
                for value in dates
            ]
            dates = None

        money_refs = None
        if money_values and scoped_document_ids:
            money_refs = [
                money_ref(document_id, value)
                for document_id in scoped_document_ids
                for value in money_values
            ]
            money_values = None

        results = self.vector_store.identifier_search(
            query_filter=qdrant_filter,
            article_numbers=article_numbers,
            article_refs=article_refs,
            case_numbers=case_numbers,
            dates=dates,
            date_refs=date_refs,
            money_values=money_values,
            money_refs=money_refs,
            top_k=top_k,
            party_names=party_names,
        )

        # Exact matching is boolean, so Qdrant returned these in scroll order --
        # arbitrary. Ordering them by subject strength is what separates the
        # chunk that *is* the article from a contents line or a chunk that
        # carries the number among five others. Dense rank breaks ties between
        # chunks that are equally the subject but belong to different laws.
        dense_rank = {
            (item.get("document_id"), item.get("chunk_id")): rank
            for rank, item in enumerate(dense_results or [], start=1)
        }

        # Document-level tie-breaking was tried here -- propagating a
        # document's best dense rank to its article chunks, on the theory that
        # "article 4 of the supply law" names the law in prose and the semantic
        # half knows which law that is. Measured against the eval set it made
        # things *worse* (the target case moved 6 -> 7) because every competing
        # statute also has highly-ranked chunks, so the signal favoured whichever
        # document was largest rather than whichever was meant. Not kept.
        results = rank_identifier_candidates(
            results,
            wanted_articles=normalized["article_numbers"],
            tie_breaker=dense_rank,
        )

        logger.info(
            "identifier_search query_id=%s articles=%s cases=%s dates=%s "
            "money=%s scoped=%s hits=%d top_subject_score=%s",
            query.query_id,
            normalized["article_numbers"],
            normalized["case_numbers"],
            normalized["dates"],
            normalized["money_values"],
            bool(scoped_document_ids),
            len(results),
            results[0].get("subject_score") if results else None,
        )

        return results

    def _keyword_search(
        self,
        query: ProcessedQuery,
        qdrant_filter,
        top_k: int,
    ) -> List[Dict[str, Any]]:
        """
        Run the configured keyword retriever.

        ``qdrant_filter`` is passed in rather than rebuilt: both halves of the
        hybrid must be scoped by the same access conditions, and rebuilding it
        here would create a second place where those conditions are assembled.
        """

        if self.keyword_backend == "bm25":
            return self._bm25_backend(
                query=query,
                qdrant_filter=qdrant_filter,
                top_k=top_k,
            )

        return self._sparse_backend(
            query=query,
            qdrant_filter=qdrant_filter,
            top_k=top_k,
        )

    def _sparse_backend(
        self,
        query: ProcessedQuery,
        qdrant_filter,
        top_k: int,
    ) -> List[Dict[str, Any]]:
        """
        Native Qdrant sparse retrieval over BGE-M3 lexical weights.

        Replaces scrolling the whole (filtered) collection into Python and
        scoring it with rank_bm25: the keyword index now lives in Qdrant, is
        searched by Qdrant, and is filtered by Qdrant using the same access
        conditions as the dense side.

        Degrades to no keyword candidates -- dense-only retrieval -- when M2
        supplied no sparse vector for the query. That is a relevance loss and
        is logged as such; it is not an access decision, and the dense half
        remains fully scoped either way.
        """

        query_sparse = to_sparse_vector(
            query.sparse_embedding
        )

        if query_sparse is None:
            logger.warning(
                "No sparse query vector on query_id=%s; falling back to "
                "dense-only retrieval. Check that M2 ran with "
                "return_sparse enabled.",
                query.query_id,
            )
            return []

        return self.vector_store.sparse_search(
            query_sparse=query_sparse,
            query_filter=qdrant_filter,
            top_k=top_k,
        )

    def _bm25_backend(
        self,
        query: ProcessedQuery,
        qdrant_filter,
        top_k: int,
    ) -> List[Dict[str, Any]]:
        """
        The original keyword path, retained for A/B comparison.

        Scrolls the access-filtered collection and scores it in Python. Kept
        reachable so native-sparse retrieval quality can be measured against
        the behaviour it replaced, on the same corpus and the same queries.

        Note the cost this path carries and sparse does not: it materializes
        up to ``get_all_chunks``'s scroll limit of documents per query, so its
        keyword recall silently depends on how much of the tenant's corpus
        fits in that limit.
        """

        all_chunks = self.vector_store.get_all_chunks(
            query_filter=qdrant_filter
        )

        return self._bm25_search(
            query_text=(
                build_retrieval_text(
                    query
                )
            ),
            chunks=all_chunks,
            top_k=top_k,
        )

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
        dense_results: List[
            Dict[str, Any]
        ],
        keyword_results: List[
            Dict[str, Any]
        ],
        identifier_results: Optional[
            List[Dict[str, Any]]
        ] = None,
        top_k: int = 20,
        dense_weight: Optional[float] = None,
        keyword_weight: Optional[float] = None,
        identifier_weight: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Combine the dense and keyword rankings using
        weighted Reciprocal Rank Fusion.

        The keyword ranking comes from whichever backend
        is configured; fusion does not care which, since
        both produce the same candidate shape and both
        were filtered by the same access conditions.

        Candidate identity is the pair:

            (document_id, chunk_id)

        because chunk IDs are only guaranteed to be
        unique within one document.
        """

        CandidateKey = tuple[str, str]

        rrf_scores: Dict[
            CandidateKey,
            float,
        ] = {}

        chunk_map: Dict[
            CandidateKey,
            Dict[str, Any],
        ] = {}

        def candidate_key(
            item: Dict[str, Any],
        ) -> CandidateKey:
            return (
                str(
                    item.get(
                        "document_id",
                        "",
                    )
                ),
                str(item["chunk_id"]),
            )

        matched_by: Dict[
            CandidateKey,
            List[str],
        ] = {}

        # None means "use the instance's configured weight". An explicit
        # argument still wins, so a caller can override per call without
        # rebuilding the searcher.
        if dense_weight is None:
            dense_weight = self.dense_weight
        if keyword_weight is None:
            keyword_weight = self.keyword_weight
        if identifier_weight is None:
            identifier_weight = self.identifier_weight

        rankings = (
            ("dense", dense_results, dense_weight),
            ("keyword", keyword_results, keyword_weight),
            (
                "identifier",
                identifier_results or [],
                identifier_weight,
            ),
        )

        # One accumulation loop rather than one per retriever. The two
        # original blocks were identical apart from the weight, and adding a
        # third copy for identifiers is how the fusion layer ends up with a
        # retriever whose candidates silently never reach chunk_map.
        for source, results, weight in rankings:
            for rank, item in enumerate(
                results,
                start=1,
            ):
                key = candidate_key(item)

                chunk_map[key] = item

                rrf_scores[key] = (
                    rrf_scores.get(
                        key,
                        0.0,
                    )
                    + weight
                    * (
                        1.0
                        / (
                            self.rrf_k
                            + rank
                        )
                    )
                )

                matched_by.setdefault(
                    key,
                    [],
                ).append(source)

        sorted_keys = sorted(
            rrf_scores,
            key=rrf_scores.get,
            reverse=True,
        )

        fused_results = []

        for key in sorted_keys[:top_k]:
            item = dict(
                chunk_map[key]
            )

            item["rrf_score"] = (
                rrf_scores[key]
            )

            # Retrieval provenance: which of the three paths produced this
            # candidate. Internal only -- it stays on the candidate dict and
            # is dropped when EvidenceItem is built, so the M4 contract is
            # unchanged. Without it there is no way to tell an exact-identifier
            # hit from a semantic one when debugging a ranking.
            item["matched_by"] = matched_by.get(
                key,
                [],
            )

            fused_results.append(item)

        return fused_results
