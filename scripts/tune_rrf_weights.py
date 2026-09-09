"""RRF weight-sweep harness.

What this is for
----------------
Three fusion weights (dense, keyword, identifier) are documented as un-tuned,
and until now they could not even be varied without editing the module. This
harness sweeps them against the live collection and reports, per combo, where
the known-correct chunk actually landed.

**It does not tune anything.** It has no optimizer and picks no winner: it
runs combos and prints the numbers. Choosing weights from those numbers is a
judgement call that needs a real evaluation set first.

Why it evaluates FUSION output by default
-----------------------------------------
``--stage fusion`` (the default) measures the ranking that comes out of RRF,
before reranking. That is deliberate. The cross-encoder re-scores whatever
fusion hands it, so a good reranker masks a bad fusion ranking for anything
inside the candidate window and a weight change becomes invisible. Measuring
fusion directly is what makes the weights attributable.

``--stage reranked`` measures end-to-end instead. It needs the cross-encoder,
which is absent on this host by policy, so it raises ``RerankerUnavailable``
rather than silently substituting heuristic scores -- exactly the fail-loud
behaviour the reranker work established.

Ground-truth precision
----------------------
``chunk_id`` is unique only *within* a document. In the live collection
``chunk_017`` resolves to five different points in five different documents,
so a case whose ground truth is a bare chunk id is genuinely ambiguous: a hit
cannot be distinguished from a coincidence. The harness accepts both forms and
says which one a case used:

* ``ground_truth_chunk_ids: ["chunk_017"]`` -- the existing schema. Matched on
  chunk id alone, and reported as AMBIGUOUS when the id resolves to more than
  one live point.
* ``ground_truth: [{"document_id": "...", "chunk_id": "..."}]`` -- preferred.
  Matched on the full identity pair, which is what the retrieval layer itself
  treats as a candidate's identity.
"""

from __future__ import annotations

import argparse
import itertools
import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.embedding_service import EmbeddingService  # noqa: E402
from src.query_processor import QueryProcessor  # noqa: E402
from src.retrieval.hybrid_search import (  # noqa: E402
    DEFAULT_DENSE_WEIGHT,
    DEFAULT_IDENTIFIER_WEIGHT,
    DEFAULT_KEYWORD_WEIGHT,
    HybridSearcher,
)
from src.schemas.access_control import AccessScope  # noqa: E402
from src.vector_store.qdrant_manager import QdrantVectorStore  # noqa: E402

log = logging.getLogger("tune")


# ---------------------------------------------------------------------------
# SMOKE-TEST STUB -- NOT A REAL EVALUATION SET
# ---------------------------------------------------------------------------
# Two cases only, both derived from the Stage 3 identifier work, and both
# verified to resolve against live data. They exist ONLY to prove the harness
# runs end to end. Two identifier-shaped cases cannot measure retrieval quality
# and MUST NOT be used to pick weights: they exercise the identifier path and
# say nothing about dense/keyword balance on ordinary semantic queries.
# ---------------------------------------------------------------------------
SMOKE_TEST_CASES: list[dict[str, Any]] = [
    {
        "case_id": "smoke_ar_article_15",
        "category": "smoke_test_only",
        "language": "ar",
        "question": "ما نص المادة ١٥؟",
        "ground_truth": [
            {"document_id": "doc_22afd9d663b8", "chunk_id": "chunk_092"},
            {"document_id": "doc_641a63c3a69e", "chunk_id": "chunk_026"},
            {"document_id": "doc_b8294a1bd6da", "chunk_id": "chunk_056"},
            {"document_id": "doc_7983400b1672", "chunk_id": "chunk_026"},
            {"document_id": "doc_6450dfd093f8", "chunk_id": "chunk_090"},
        ],
    },
    {
        "case_id": "smoke_en_article_15",
        "category": "smoke_test_only",
        "language": "en",
        "question": "What does article 15 say?",
        "ground_truth": [
            {"document_id": "doc_22afd9d663b8", "chunk_id": "chunk_092"},
            {"document_id": "doc_641a63c3a69e", "chunk_id": "chunk_026"},
            {"document_id": "doc_b8294a1bd6da", "chunk_id": "chunk_056"},
            {"document_id": "doc_7983400b1672", "chunk_id": "chunk_026"},
            {"document_id": "doc_6450dfd093f8", "chunk_id": "chunk_090"},
        ],
    },
]


@dataclass(frozen=True)
class Combo:
    dense: float
    keyword: float
    identifier: float

    def __str__(self) -> str:
        return f"d={self.dense:<4g} k={self.keyword:<4g} i={self.identifier:<4g}"


@dataclass
class CaseResult:
    case_id: str
    rank_of_correct: Optional[int]
    precision_at_k: float
    recall_at_k: float
    reciprocal_rank: float
    ambiguous_ground_truth: bool = False
    notes: list[str] = field(default_factory=list)


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cases", type=Path, default=None,
                   help="Path to a benchmark_cases.json. Omit to use the "
                        "two-case SMOKE TEST STUB (not a real eval set).")
    p.add_argument("--qdrant-url", default="http://127.0.0.1:6333")
    p.add_argument("--collection", default="legal_documents_v2")
    p.add_argument("--client-id", default="firm_eval")
    p.add_argument("--max-confidentiality", default="public")
    p.add_argument("-k", "--top-k", type=int, default=5)
    p.add_argument("--candidate-top-k", type=int, default=20)
    p.add_argument("--stage", choices=["fusion", "reranked"], default="fusion")
    p.add_argument("--weights", action="append", default=[],
                   help="A combo as 'dense,keyword,identifier', repeatable. "
                        "Omit to use the built-in exploratory grid.")
    p.add_argument("--grid", action="store_true",
                   help="Use the built-in exploratory grid explicitly.")
    p.add_argument("--json-out", type=Path, default=None)
    return p.parse_args(argv)


def build_combos(args) -> list[Combo]:
    if args.weights:
        combos = []
        for raw in args.weights:
            parts = [float(x) for x in raw.split(",")]
            if len(parts) != 3:
                raise SystemExit(f"--weights needs 3 numbers, got {raw!r}")
            combos.append(Combo(*parts))
        return combos

    # Exploratory only. Deliberately small and round-numbered: a fine grid
    # would imply a precision the (absent) eval set cannot support.
    current = Combo(DEFAULT_DENSE_WEIGHT, DEFAULT_KEYWORD_WEIGHT,
                    DEFAULT_IDENTIFIER_WEIGHT)
    grid = [current]
    for dense, keyword in itertools.product((0.9, 0.7, 0.5), (0.1, 0.3, 0.5)):
        for identifier in (0.0, 1.0, 2.0):
            combo = Combo(dense, keyword, identifier)
            if combo not in grid:
                grid.append(combo)
    return grid


def load_cases(path: Optional[Path]) -> tuple[list[dict], bool]:
    if path is None:
        return SMOKE_TEST_CASES, True

    data = json.loads(path.read_text(encoding="utf-8"))
    cases = data["cases"] if isinstance(data, dict) else data
    if not cases:
        raise SystemExit(f"{path} contains no cases")
    return cases, False


def case_query(case: dict) -> str:
    """v2 uses 'query'; the original schema used 'question'."""
    text = case.get("query") or case.get("question")
    if not text:
        raise SystemExit(f"case {case.get('case_id')!r} has no query/question")
    return text


def is_negative(case: dict) -> bool:
    """
    A no-answer case: ground truth is explicitly an empty list.

    Distinct from a case that simply omits ground truth. ``"ground_truth": []``
    is an assertion that the corpus contains no correct chunk, so it is carried
    through rather than skipped.
    """
    return case.get("ground_truth") == [] and "ground_truth" in case


def ground_truth_keys(case: dict) -> tuple[set, str]:
    """Return (keys, mode). Keys are (document_id, chunk_id) or (None, chunk_id)."""
    explicit = case.get("ground_truth")
    if explicit:
        return {
            (row["document_id"], row["chunk_id"]) for row in explicit
        }, "pair"

    chunk_ids = case.get("ground_truth_chunk_ids") or []
    return {(None, cid) for cid in chunk_ids}, "chunk_id_only"


def matches(row: dict, keys: set, mode: str) -> bool:
    if mode == "pair":
        return (row.get("document_id"), row.get("chunk_id")) in keys
    return (None, row.get("chunk_id")) in keys


def evaluate(rows: list[dict], keys: set, mode: str, k: int) -> tuple:
    top = rows[:k]
    hits = [i for i, row in enumerate(top, 1) if matches(row, keys, mode)]

    rank = None
    for i, row in enumerate(rows, 1):
        if matches(row, keys, mode):
            rank = i
            break

    precision = len(hits) / k if k else 0.0
    recall = (len(hits) / len(keys)) if keys else 0.0
    rr = (1.0 / rank) if rank else 0.0
    return rank, precision, recall, rr


def main(argv=None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    cases, is_smoke = load_cases(args.cases)
    combos = build_combos(args)

    store = QdrantVectorStore(location=args.qdrant_url,
                              collection_name=args.collection,
                              vector_size=1024)
    info = store.client.get_collection(args.collection)

    print("=" * 78)
    print("RRF WEIGHT SWEEP")
    print("=" * 78)
    print(f"  collection      : {args.collection} "
          f"({info.points_count} points, status={info.status})")
    print(f"  stage measured  : {args.stage}"
          + ("  (pre-rerank fusion ranking)" if args.stage == "fusion" else ""))
    print(f"  k               : {args.top_k}  (candidate_top_k={args.candidate_top_k})")
    print(f"  combos          : {len(combos)}")
    print(f"  cases           : {len(cases)}")
    if is_smoke:
        print()
        print("  " + "!" * 66)
        print("  !! SMOKE TEST STUB -- NOT A REAL EVALUATION SET.")
        print("  !! 2 identifier-shaped cases, present only to prove the harness runs.")
        print("  !! These numbers MUST NOT be used to choose weights.")
        print("  " + "!" * 66)
    print()

    reranker = None
    if args.stage == "reranked":
        # Constructed with the production posture: no mock fallback. If the
        # cross-encoder is absent this raises RerankerUnavailable here rather
        # than quietly scoring with the heuristic and reporting it as a real
        # measurement.
        from src.retrieval.reranker import BGEReranker

        reranker = BGEReranker(model_name="BAAI/bge-reranker-v2-m3",
                               use_mock_fallback=False, local_files_only=True)

    processor, embedder = QueryProcessor(), EmbeddingService()
    scope = AccessScope(client_id=args.client_id,
                        max_confidentiality=args.max_confidentiality,
                        include_shared_corpus=True)

    # Embed once per case and reuse across every combo: the query vector does
    # not depend on fusion weights, and re-encoding would make the sweep cost
    # scale with the grid for no reason.
    prepared = []
    negatives = []
    for case in cases:
        if is_negative(case):
            # Retrieval always returns its top-k; deciding that none of it is
            # sufficient is M4's job, not the fusion layer's. Scoring these with
            # P@k would report a constant 0 for every weight combo and make the
            # sweep look worse without telling anyone anything. Counted and
            # reported separately instead.
            negatives.append(case)
            continue

        processed = processor.process(case_query(case))
        embedded = embedder.embed_processed_query(processed)
        query = embedded.processed_query.model_copy(
            update={"embedding": embedded.embedding})

        # Apply the case's own relevance filters. Skipping them would measure
        # a different query than the case describes -- a case scoped to
        # document_type=contract is asking about ranking *within* contracts,
        # and evaluating it unscoped silently changes the question.
        case_filters = case.get("filters") or {}
        for name in ("document_type", "jurisdiction", "language"):
            if case_filters.get(name):
                setattr(query.filters, name, case_filters[name])
        if case_filters.get("document_ids"):
            query.filters.document_ids = case_filters["document_ids"]

        # access is server-derived and never taken from a case file.
        query.filters.access = scope

        keys, mode = ground_truth_keys(case)
        if not keys:
            log.warning("case %s has no ground truth; skipped", case.get("case_id"))
            continue

        ambiguous = False
        if mode == "chunk_id_only":
            from qdrant_client.http import models as qm
            for _, chunk_id in keys:
                pts, _ = store.client.scroll(
                    args.collection, limit=10,
                    scroll_filter=qm.Filter(must=[qm.FieldCondition(
                        key="chunk_id", match=qm.MatchValue(value=chunk_id))]),
                    with_payload=False, with_vectors=False)
                if len(pts) > 1:
                    ambiguous = True

        prepared.append((case, query, keys, mode, ambiguous))

    results: dict[str, list[CaseResult]] = {}

    for combo in combos:
        searcher = HybridSearcher(vector_store=store, keyword_backend="sparse",
                                  dense_weight=combo.dense,
                                  keyword_weight=combo.keyword,
                                  identifier_weight=combo.identifier)
        per_case = []
        for case, query, keys, mode, ambiguous in prepared:
            rows = searcher.search(query, candidate_top_k=args.candidate_top_k)
            if reranker is not None:
                rows = reranker.rerank(
                    query_text=query.normalized_text or query.text_original,
                    candidates=rows, top_k=args.top_k)

            rank, precision, recall, rr = evaluate(rows, keys, mode, args.top_k)
            per_case.append(CaseResult(
                case_id=case.get("case_id", "?"), rank_of_correct=rank,
                precision_at_k=precision, recall_at_k=recall,
                reciprocal_rank=rr, ambiguous_ground_truth=ambiguous))
        results[str(combo)] = per_case

    k = args.top_k
    print(f"{'weights':26s} {'P@'+str(k):>7s} {'R@'+str(k):>7s} {'MRR':>7s} "
          f"{'found':>7s}  ranks")
    print("-" * 78)
    for combo_label, per_case in results.items():
        n = len(per_case) or 1
        mp = sum(r.precision_at_k for r in per_case) / n
        mr = sum(r.recall_at_k for r in per_case) / n
        mrr = sum(r.reciprocal_rank for r in per_case) / n
        found = sum(1 for r in per_case if r.rank_of_correct is not None)
        ranks = ",".join(str(r.rank_of_correct or "-") for r in per_case)
        print(f"{combo_label:26s} {mp:7.3f} {mr:7.3f} {mrr:7.3f} "
              f"{found:>4d}/{len(per_case):<2d}  {ranks}")

    print()
    print("  ranks = rank of the first correct chunk per case, in case order;")
    print("  '-' means not found anywhere in the candidate window.")

    # Per-category breakdown for the first combo: an aggregate hides which
    # class of query is actually failing.
    if results:
        first = next(iter(results))
        cats = {}
        for (case, *_), res in zip(prepared, results[first]):
            cats.setdefault(case.get("category", "?"), []).append(res)
        print()
        print(f"  per-category breakdown for {first}:")
        for cat, rs in sorted(cats.items()):
            n = len(rs)
            print(f"    {cat:20s} n={n:<3d} P@{k}={sum(r.precision_at_k for r in rs)/n:.3f}"
                  f"  MRR={sum(r.reciprocal_rank for r in rs)/n:.3f}"
                  f"  found={sum(1 for r in rs if r.rank_of_correct)}/{n}")

    if negatives:
        print()
        print(f"  {len(negatives)} negative (no-answer) case(s) held out of the metrics:")
        for c in negatives:
            print(f"    - {c.get('case_id')}")
        print("    Retrieval always returns top-k, so these are not scorable at the")
        print("    fusion layer. They exist to test whether M4 declines to answer.")

    if any(r.ambiguous_ground_truth for rs in results.values() for r in rs):
        print()
        print("  WARNING: at least one case used bare chunk_id ground truth that")
        print("  resolves to MULTIPLE live points. Those hits may be coincidental.")
        print("  Use the ground_truth [{document_id, chunk_id}] form instead.")

    print()
    print("  NOTE: this harness reports numbers only; it selects no winner.")
    if is_smoke:
        print("  No weight change may be made from the smoke-test stub.")
    else:
        print(f"  P@{k} is bounded by how many correct chunks a case has: a")
        print(f"  single-answer case can never exceed {1.0/k:.2f}. Read R@{k} and MRR")
        print("  as the primary signals and P@k only within a category.")

    if args.json_out:
        payload = {
            "collection": args.collection,
            "points": info.points_count,
            "stage": args.stage,
            "k": k,
            "is_smoke_test_stub": is_smoke,
            "WARNING": ("smoke test stub - not a real evaluation set; "
                        "do not tune from these numbers") if is_smoke else None,
            "results": {c: [vars(r) for r in rs] for c, rs in results.items()},
        }
        args.json_out.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n  wrote {args.json_out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
