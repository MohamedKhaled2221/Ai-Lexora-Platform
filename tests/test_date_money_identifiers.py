"""
Exact retrieval on dates and monetary values.

Companion to ``test_identifier_search.py``, which covers article and case
numbers. The failure mode is the same one: dense vectors and BGE-M3 lexical
weights are similarity signals, so ``2026-05-30`` and ``2026-11-30`` are
near-identical inputs -- same tokens, same shape, digits a subword tokenizer
barely separates. Nothing in the stack could express "this date, not that one"
until these payload keys existed.

The fixture below builds that situation deliberately: four payment-milestone
chunks differing only in their date and amount, with the *wrong* ones favoured
by the dense ranking. Vectors are hand-built for the reason given in
``test_identifier_search._vec`` -- the test must control what similarity says
in order to prove exact matching overrides it.

On the monetary tests
---------------------
``normalize_money`` and the payload/fusion wiring are exercised here with
values written the way M2 can actually read them. They do **not** assert that
the live corpus is retrievable by amount, because it is not: see
``docs/KNOWN_ISSUES.md`` ISSUE-3. That is an upstream extraction defect, and a
test that papered over it by pre-folding the separator itself would assert a
pipeline this codebase does not have.
"""

from __future__ import annotations

import math
import uuid

import pytest
from qdrant_client.http.models import PointStruct

from src.query_processor import QueryProcessor
from src.retrieval.hybrid_search import HybridSearcher
from src.retrieval.identifiers import (
    date_ref,
    identifier_payload,
    money_ref,
    normalize_date,
    normalize_identifier_set,
    normalize_money,
)
from src.schemas.access_control import AccessScope
from src.schemas.m2_contract import ProcessedQuery, QueryFilters
from src.vector_store.qdrant_manager import QdrantVectorStore

CONTRACT_A = "doc_supply_contract_a"
CONTRACT_B = "doc_supply_contract_b"

SCOPE = AccessScope(
    client_id="firm_test",
    max_confidentiality="public",
    include_shared_corpus=True,
)


# --------------------------------------------------------------- date normalization


def test_every_date_form_in_the_corpus_folds_onto_one_iso_key():
    """
    All four shapes M2's DATE_RE matches must reduce to the same key when they
    name the same day, or the index and the query never meet.
    """
    assert normalize_date("2026-03-15") == "2026-03-15"
    assert normalize_date("15/03/2026") == "2026-03-15"
    assert normalize_date("15-03-2026") == "2026-03-15"
    assert normalize_date("1 February 2026") == "2026-02-01"
    assert normalize_date("11 Nov 2023") == "2023-11-11"


def test_numeric_dates_are_read_day_first():
    """
    The corpus settles this: it contains 20/03/2026, which has no month-first
    reading. Day-first is the only interpretation under which the real data
    parses at all.
    """
    assert normalize_date("20/03/2026") == "2026-03-20"
    assert normalize_date("12/03/2026") == "2026-03-12"


def test_iso_ordering_is_detected_structurally_not_by_separator():
    """
    A four-digit leading component is unambiguously a year. This must not
    depend on the separator, because nothing guarantees the corpus writes ISO
    with hyphens and day-first with slashes.
    """
    assert normalize_date("2026/03/15") == "2026-03-15"
    assert normalize_date("2026-03-15") == "2026-03-15"


def test_arabic_indic_digits_fold_in_dates():
    assert normalize_date("١٥/٠٣/٢٠٢٦") == "2026-03-15"


def test_impossible_dates_are_dropped_not_stored():
    # Same rule as article numbers: an unmatchable key is worse than an absent
    # one, because it looks like coverage.
    assert normalize_date("32/01/2026") is None
    assert normalize_date("15/13/2026") is None
    assert normalize_date("not a date") is None
    assert normalize_date("") is None


def test_two_digit_years_are_refused_rather_than_pivoted():
    """
    A legal corpus spans centuries, so there is no safe pivot. Refusing is the
    honest failure; guessing would index a chunk under the wrong century.
    """
    assert normalize_date("11 Nov 23") is None


# --------------------------------------------------------------- money normalization


def test_money_key_carries_the_currency():
    """
    Amount alone is the monetary equivalent of the bare article_no collision,
    and here there is no reason to accept it: 2,450,000 EGP and 2,450,000 USD
    are not the same fact.
    """
    assert normalize_money("$50,000") == "USD:50000"
    assert normalize_money("50,000 EGP") == "EGP:50000"
    assert normalize_money("$50,000") != normalize_money("50,000 EGP")


def test_arabic_currency_words_and_digits_fold():
    assert normalize_money("2,450,000 جنيه") == "EGP:2450000"
    assert normalize_money("٥٠٠٠ جنيه") == "EGP:5000"


def test_arabic_thousands_separator_is_folded():
    """
    U+066C is what the real corpus uses. This layer handles it; M2's extractor
    does not, which is ISSUE-3 -- see the module docstring.
    """
    assert normalize_money("2٬450٬000 جنيه") == "EGP:2450000"


def test_decimal_amounts_land_on_one_key():
    assert normalize_money("1,250.50 EGP") == "EGP:1250.5"
    assert normalize_money("1250.5 EGP") == "EGP:1250.5"


def test_amount_without_currency_is_not_a_monetary_value():
    assert normalize_money("50,000") is None


def test_zero_amounts_are_refused():
    """
    The guard that keeps ISSUE-3 from writing wrong data rather than no data.

    M2 truncates ``2٬450٬000 جنيه`` to ``"000 جنيه"``. Without this, that
    becomes EGP:0 -- and becomes the *same* key on three unrelated contracts,
    silently joining them.
    """
    assert normalize_money("000 جنيه") is None
    assert normalize_money("0 EGP") is None


# --------------------------------------------------------------- M2 consumption


def test_m2_date_and_money_fields_are_consumed_not_reimplemented():
    """
    The query side reads what M2 already produced. These two fields were
    populated on every ProcessedQuery and had no consumer anywhere.
    """
    processed = QueryProcessor().process(
        "What milestone is due on 2026-05-30 for $50,000?"
    )

    assert processed.identifiers.dates == ["2026-05-30"]
    assert processed.identifiers.monetary_values == ["$50,000"]

    normalized = normalize_identifier_set(processed.identifiers)
    assert normalized["dates"] == ["2026-05-30"]
    assert normalized["money_values"] == ["USD:50000"]


def test_party_names_is_deliberately_not_consumed():
    """
    M2 populates party_names as an empty list on every query -- it has no
    party extraction. Wiring it would add a retriever input that is always
    empty, which reads as coverage and is not.
    """
    processed = QueryProcessor().process("claim by Blue Nile Engineering Supplies")
    assert processed.identifiers.party_names == []
    assert "party_names" not in normalize_identifier_set(processed.identifiers)


def test_compound_keys_disambiguate_across_documents():
    """
    A date collides harder than an article number does. In the live collection
    2026-05-30 is carried by five chunks across three documents.
    """
    assert date_ref(CONTRACT_A, "2026-05-30") != date_ref(CONTRACT_B, "2026-05-30")
    assert date_ref(CONTRACT_A, "2026-05-30") == f"{CONTRACT_A}:d2026-05-30"
    assert money_ref(CONTRACT_A, "EGP:735000") == f"{CONTRACT_A}:mEGP:735000"


def test_index_time_payload_carries_both_forms():
    payload = identifier_payload(
        document_id=CONTRACT_A,
        text="Delivery of phase 1 falls due on 2026-05-30 against 735,000 EGP.",
    )

    assert payload["date_no"] == ["2026-05-30"]
    assert payload["date_ref"] == [f"{CONTRACT_A}:d2026-05-30"]
    assert payload["money_no"] == ["EGP:735000"]
    assert payload["money_ref"] == [f"{CONTRACT_A}:mEGP:735000"]

    # Keys stay omitted when there is nothing to write.
    assert "date_no" not in identifier_payload(
        document_id=CONTRACT_A, text="general preamble"
    )


# --------------------------------------------------------------- fixtures


def _vec(similarity: float) -> list[float]:
    """See test_identifier_search._vec -- direction, not magnitude."""
    similarity = max(-1.0, min(1.0, similarity))
    vector = [0.0] * 1024
    vector[0] = similarity
    vector[1] = math.sqrt(1.0 - similarity * similarity)
    return vector


PROBE = _vec(1.0)


@pytest.fixture()
def store():
    """
    Milestone chunks whose dense ranking is deliberately wrong.

    The 2026-11-30 row is given the vector closest to the probe, so dense
    retrieval alone answers a 2026-05-30 query with the November milestone --
    the near-miss that exact matching exists to prevent. The same schedule is
    duplicated into a second contract so the collision is real.
    """
    vs = QdrantVectorStore(
        location=":memory:",
        collection_name=f"date_money_test_{uuid.uuid4().hex[:8]}",
        vector_size=1024,
    )

    rows = [
        # (document, chunk, text, dense-similarity)
        (
            CONTRACT_A,
            "c_nov",
            "Delivery of phase 2 is due on 2026-11-30 against 735,000 EGP.",
            1.00,
        ),
        (
            CONTRACT_A,
            "c_jan",
            "Advance on signature is due on 2026-01-15 against 612,500 EGP.",
            0.99,
        ),
        (
            CONTRACT_A,
            "c_may",
            "Delivery of phase 1 is due on 2026-05-30 against 735,000 EGP.",
            0.10,
        ),
        (
            CONTRACT_B,
            "c_may",
            "Phase 1 delivery under the second contract: 2026-05-30, 735,000 EGP.",
            0.50,
        ),
    ]

    points = []
    for document_id, chunk_id, text, sim in rows:
        payload = {
            "document_id": document_id,
            "chunk_id": chunk_id,
            "text": text,
            "page": 1,
            "section": None,
            "language": "en",
            "document_type": "contract",
            "jurisdiction": "Egypt",
            "client_id": "_shared",
            "matter_id": "_none",
            "confidentiality_level": "public",
        }
        payload.update(identifier_payload(document_id=document_id, text=text))
        points.append(
            PointStruct(id=str(uuid.uuid4()), vector=_vec(sim), payload=payload)
        )

    vs.upsert_chunks(points)
    return vs


def _query(text: str, document_ids=None) -> ProcessedQuery:
    processed = QueryProcessor().process(text)
    return processed.model_copy(
        update={
            "embedding": PROBE,
            "filters": QueryFilters(
                access=SCOPE,
                document_ids=document_ids or [],
            ),
        }
    )


# --------------------------------------------------------------- the regression


def test_dense_alone_ranks_the_wrong_milestone_first(store):
    """Establish the bug exists before proving it is fixed."""
    query = _query("Which milestone is due on 2026-05-30?")
    dense = store.dense_search(
        query_vector=query.embedding,
        query_filter=store.build_qdrant_filter(access=SCOPE),
        top_k=10,
    )
    assert dense[0]["chunk_id"] == "c_nov", (
        "fixture no longer reproduces the near-miss ranking"
    )


def test_exact_date_match_beats_the_near_miss(store):
    searcher = HybridSearcher(vector_store=store, keyword_backend="bm25")
    results = searcher.search(
        _query("Which milestone is due on 2026-05-30?"), candidate_top_k=10
    )

    assert results[0]["chunk_id"] == "c_may"
    assert "identifier" in results[0]["matched_by"]

    # Both documents' copies are legitimate answers to an unscoped query.
    top_two = {(r["document_id"], r["chunk_id"]) for r in results[:2]}
    assert top_two == {(CONTRACT_A, "c_may"), (CONTRACT_B, "c_may")}


def test_document_scope_switches_to_the_compound_date_key(store):
    """
    Precision rises with the context the caller supplied, with no separate code
    path -- the same behaviour article numbers get from article_ref.
    """
    searcher = HybridSearcher(vector_store=store, keyword_backend="bm25")
    results = searcher.search(
        _query(
            "Which milestone is due on 2026-05-30?",
            document_ids=[CONTRACT_B],
        ),
        candidate_top_k=10,
    )

    identifier_hits = [r for r in results if "identifier" in r["matched_by"]]
    assert identifier_hits, "the compound date key matched nothing"
    assert all(r["document_id"] == CONTRACT_B for r in identifier_hits), (
        "a document-scoped date query matched another document's copy"
    )


def test_exact_money_match_beats_the_near_miss(store):
    """
    612,500 belongs to one milestone only. Dense ranking favours the other two.
    """
    searcher = HybridSearcher(vector_store=store, keyword_backend="bm25")
    results = searcher.search(
        _query("Which milestone is worth 612,500 EGP?"), candidate_top_k=10
    )

    assert results[0]["chunk_id"] == "c_jan"
    assert "identifier" in results[0]["matched_by"]


def test_a_query_with_no_date_or_money_is_unaffected(store):
    """
    The common case. An empty identifier ranking must leave fusion behaving
    exactly as it did before this feature existed.
    """
    searcher = HybridSearcher(vector_store=store, keyword_backend="bm25")
    results = searcher.search(_query("delivery obligations"), candidate_top_k=10)

    assert results
    assert all("identifier" not in r["matched_by"] for r in results)


def test_date_and_money_in_one_query_are_unioned_not_intersected(store):
    """
    OR across identifier kinds. Requiring both would make the exact path return
    nothing whenever either was mis-extracted -- and extraction is the least
    reliable link in this chain.
    """
    searcher = HybridSearcher(vector_store=store, keyword_backend="bm25")
    results = searcher.search(
        _query("milestone due 2026-01-15 or worth 735,000 EGP"),
        candidate_top_k=10,
    )

    identifier_hits = {
        r["chunk_id"] for r in results if "identifier" in r["matched_by"]
    }
    # c_jan matches on the date; c_may / c_nov match on the amount.
    assert {"c_jan", "c_may", "c_nov"} <= identifier_hits
