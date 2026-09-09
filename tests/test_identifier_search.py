"""
Exact legal-identifier retrieval.

The failure mode under test
---------------------------
Before this feature the retrieval stack had no equality predicate on anything
except the ACL. Dense vectors and BGE-M3's ``text_sparse`` lexical weights are
both *similarity* signals, so "article 15" and "article 51" are near-identical
inputs: same tokens, same shape, digits that a subword tokenizer barely
distinguishes. A query for ``المادة ١٥`` could -- and in the ranking below,
does -- put article 51 above article 15.

These tests build that situation deliberately: several chunks whose text is
identical apart from the article number, with the *wrong* ones deliberately
favoured by the dense and keyword rankings. If exact matching is working, the
correct article still comes first.

The dense vectors here are hand-built, not encoded. That is the point: the
test has to control what the similarity signal says in order to prove the
exact-match signal overrides it. Using a real encoder would make the test
measure BGE-M3 rather than the fusion logic, and would make it fail for
unrelated reasons whenever the model changed.
"""

from __future__ import annotations

import uuid

import pytest

from src.retrieval.hybrid_search import (
    DEFAULT_DENSE_WEIGHT,
    DEFAULT_IDENTIFIER_WEIGHT,
    HybridSearcher,
)
from src.retrieval.identifiers import (
    article_ref,
    identifier_payload,
    normalize_article_number,
    normalize_case_number,
    normalize_identifier_set,
)
from src.query_processor import QueryProcessor
from src.schemas.access_control import AccessScope
from src.schemas.m2_contract import ProcessedQuery, QueryFilters
from src.vector_store.qdrant_manager import (
    IDENTIFIER_PAYLOAD_FIELDS,
    QdrantVectorStore,
)

from qdrant_client.http.models import PointStruct


LAW_A = "doc_constitution_2014"
LAW_B = "doc_wipo_treaty"

SCOPE = AccessScope(
    client_id="firm_test",
    max_confidentiality="public",
    include_shared_corpus=True,
)


# --------------------------------------------------------------- normalization


def test_arabic_indic_digits_fold_onto_ascii():
    """``المادة ١٥`` and ``Article 15`` must land on one key or nothing matches."""
    assert normalize_article_number("١٥") == "15"
    assert normalize_article_number("۱۵") == "15"
    assert normalize_article_number("15") == "15"
    assert normalize_article_number("015") == "15"


def test_unnormalizable_values_are_dropped_not_stored():
    # An unmatchable key is worse than an absent one: it occupies the index
    # and can never be hit.
    assert normalize_article_number("") is None
    assert normalize_article_number("abc") is None
    assert normalize_article_number("0") is None


def test_case_number_preserves_structure():
    assert normalize_case_number("١٢٣/٢٠١٩") == "123/2019"
    assert normalize_case_number(" 123 / 2019 ") == "123/2019"


def test_m2_identifier_set_is_consumed_not_reimplemented():
    """The query side reads what M2 already produced, unchanged."""
    processed = QueryProcessor().process("ما نص المادة ١٥ من الدستور؟")

    # M2 extracted it (this field previously had no consumer at all).
    assert processed.identifiers.article_numbers == ["١٥"]

    # M3 normalizes it into a lookup token.
    assert normalize_identifier_set(processed.identifiers)["article_numbers"] == ["15"]


def test_compound_key_disambiguates_across_laws():
    """Article 15 of law A and law B must not collide."""
    assert article_ref(LAW_A, "15") != article_ref(LAW_B, "15")
    assert article_ref(LAW_A, "15") == f"{LAW_A}:a15"


def test_index_time_extraction_uses_section_and_text():
    payload = identifier_payload(
        document_id=LAW_A,
        text="نص المادة",
        section="المادة ١٥",
    )
    assert payload["article_no"] == ["15"]
    assert payload["article_ref"] == [f"{LAW_A}:a15"]

    # No identifier -> keys omitted entirely, so an absent key reads as
    # "no article here", never "matches any article".
    assert identifier_payload(document_id=LAW_A, text="مقدمة عامة") == {}


# --------------------------------------------------------------- fixtures


def _vec(similarity: float) -> list[float]:
    """
    A 1024-dim unit vector whose cosine similarity to the probe is ``similarity``.

    Must vary in *direction*, not magnitude. A vector like ``[s] * 1024`` is
    the obvious construction and is silently useless here: cosine normalizes
    away the scale, so every such vector is identical to every other and the
    ranking comes back in arbitrary order. Encoding the similarity as an angle
    against the probe axis is what makes the adversarial ordering real.
    """
    import math

    similarity = max(-1.0, min(1.0, similarity))
    vector = [0.0] * 1024
    vector[0] = similarity
    vector[1] = math.sqrt(1.0 - similarity * similarity)
    return vector


PROBE = _vec(1.0)  # unit vector along axis 0


@pytest.fixture()
def store():
    """
    In-memory collection carrying the adversarial ranking.

    Article 51 is given the vector *closest* to the query probe, and article 15
    the furthest. So dense retrieval alone ranks the wrong article first --
    which is exactly the bug being fixed.
    """
    vs = QdrantVectorStore(
        location=":memory:",
        collection_name=f"identifier_test_{uuid.uuid4().hex[:8]}",
        vector_size=1024,
    )

    rows = [
        # (document, chunk, article, text, dense-similarity rank)
        (LAW_A, "c_a51", "51", "المادة ٥١ الكرامة الإنسانية حق لكل إنسان", 1.00),
        (LAW_A, "c_a150", "150", "المادة ١٥٠ رئيس الجمهورية", 0.99),
        (LAW_A, "c_a15", "15", "المادة ١٥ الإضراب السلمي حق ينظمه القانون", 0.10),
        (LAW_B, "c_b15", "15", "Article 15 of the treaty concerning registration", 0.50),
    ]

    points = []
    for document_id, chunk_id, article, text, sim in rows:
        payload = {
            "document_id": document_id,
            "chunk_id": chunk_id,
            "text": text,
            "page": 1,
            "section": f"Article {article}",
            "language": "ar" if document_id == LAW_A else "en",
            "document_type": "law",
            "jurisdiction": "Egypt",
            "client_id": "_shared",
            "matter_id": "_none",
            "confidentiality_level": "public",
        }
        payload.update(
            identifier_payload(
                document_id=document_id,
                text=text,
                section=payload["section"],
            )
        )
        points.append(
            PointStruct(
                id=str(uuid.uuid4()),
                vector=_vec(sim),
                payload=payload,
            )
        )

    vs.upsert_chunks(points)
    return vs


def _query(text: str, document_ids=None) -> ProcessedQuery:
    """Run M2's real processor, then attach an embedding and a scope."""
    processed = QueryProcessor().process(text)
    return processed.model_copy(
        update={
            "embedding": PROBE,  # closest to article 51 by construction
            "filters": QueryFilters(
                access=SCOPE,
                document_ids=document_ids or [],
            ),
        }
    )


# --------------------------------------------------------------- the regression


def test_identifier_fields_are_indexed_on_a_real_server():
    """
    Payload indices must actually be created for the new identifier fields.

    Runs against a real Qdrant server because the in-memory client accepts
    ``create_payload_index`` and does nothing -- it warns "Payload indexes have
    no effect in the local Qdrant". Asserting this in-memory would pass
    vacuously and prove nothing, so the test skips instead of lying when no
    server is reachable.
    """
    import urllib.error
    import urllib.request

    url = "http://127.0.0.1:6333"
    try:
        urllib.request.urlopen(f"{url}/healthz", timeout=3).read()
    except (urllib.error.URLError, OSError) as exc:  # pragma: no cover
        pytest.skip(f"no Qdrant server on {url} ({exc}); index creation unverified")

    probe = QdrantVectorStore(
        location=url,
        collection_name=f"identifier_index_probe_{uuid.uuid4().hex[:8]}",
        vector_size=1024,
    )
    try:
        schema = probe.client.get_collection(probe.collection_name).payload_schema
        for field in IDENTIFIER_PAYLOAD_FIELDS:
            assert field in schema, f"{field} must be a KEYWORD payload index"
            assert schema[field].data_type == "keyword"
    finally:
        probe.client.delete_collection(probe.collection_name)


def test_dense_alone_ranks_the_wrong_article_first(store):
    """Establish the bug exists before proving it is fixed."""
    query = _query("ما نص المادة ١٥؟")
    qfilter = store.build_qdrant_filter(access=SCOPE)

    dense = store.dense_search(
        query_vector=query.embedding,
        query_filter=qfilter,
        top_k=10,
    )

    assert dense[0]["chunk_id"] == "c_a51", (
        "fixture no longer reproduces the failure mode: dense retrieval was "
        "supposed to rank article 51 above article 15"
    )


def test_exact_article_outranks_lexically_similar_wrong_articles(store):
    """المادة ١٥ must return article 15 first, despite dense favouring 51."""
    searcher = HybridSearcher(vector_store=store, keyword_backend="sparse")
    results = searcher.search(_query("ما نص المادة ١٥؟"), candidate_top_k=10)

    assert results, "identifier query returned nothing"

    top = results[0]
    assert top["article_no"] == ["15"], (
        f"expected article 15 first, got article {top['article_no']} "
        f"(chunk {top['chunk_id']})"
    )
    assert "identifier" in top["matched_by"]

    # The near-miss articles are still retrievable -- fusion, not a filter.
    returned = {row["chunk_id"] for row in results}
    assert "c_a51" in returned, "wrong articles must be demoted, not excluded"


def test_article_51_query_returns_article_51(store):
    """The mirror case: the fix must not merely hard-code a preference for 15."""
    searcher = HybridSearcher(vector_store=store, keyword_backend="sparse")
    results = searcher.search(_query("ما نص المادة ٥١؟"), candidate_top_k=10)

    assert results[0]["article_no"] == ["51"]


def test_document_scope_disambiguates_same_article_across_laws(store):
    """
    Article 15 exists in both laws. Scoping to LAW_B must surface LAW_B's.

    This is the collision the compound key exists for; without article_ref
    both would match on the bare number.
    """
    searcher = HybridSearcher(vector_store=store, keyword_backend="sparse")
    results = searcher.search(
        _query("Article 15", document_ids=[LAW_B]),
        candidate_top_k=10,
    )

    assert results, "scoped identifier query returned nothing"
    assert results[0]["document_id"] == LAW_B
    assert results[0]["chunk_id"] == "c_b15"


def test_query_without_identifier_is_unaffected(store):
    """A non-citation query must behave exactly as before the feature."""
    query = _query("ما هي الحقوق والحريات العامة؟")
    assert not normalize_identifier_set(query.identifiers)["article_numbers"]

    searcher = HybridSearcher(vector_store=store, keyword_backend="sparse")
    results = searcher.search(query, candidate_top_k=10)

    assert results
    for row in results:
        assert "identifier" not in row["matched_by"]


def test_identifier_path_is_access_filtered(store):
    """
    The third read path must not be an ACL bypass.

    A tenant denied the shared corpus retrieves nothing, even with an exact
    identifier that certainly exists in the collection.
    """
    denied = AccessScope(
        client_id="other_firm",
        max_confidentiality="public",
        include_shared_corpus=False,
    )

    hits = store.identifier_search(
        query_filter=store.build_qdrant_filter(access=denied),
        article_numbers=["15"],
        top_k=10,
    )

    assert hits == [], "identifier search leaked across the access scope"


def test_identifier_search_refuses_an_absent_filter(store):
    from src.schemas.access_control import AccessScopeRequired

    with pytest.raises(AccessScopeRequired):
        store.identifier_search(query_filter=None, article_numbers=["15"])


def test_identifier_weight_outranks_best_possible_dense_hit():
    """The weight choice is load-bearing; pin the inequality it relies on."""
    rrf_k = 60
    identifier_top = DEFAULT_IDENTIFIER_WEIGHT / (rrf_k + 1)
    dense_top = DEFAULT_DENSE_WEIGHT / (rrf_k + 1)

    assert identifier_top > dense_top
