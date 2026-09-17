"""
Normalization and lookup keys for exact legal-identifier matching.

Why this module exists
----------------------
Retrieval had no exact matching of any kind. Dense vectors and BGE-M3's
lexical weights are both *similarity* signals: a query for ``المادة 15`` can
rank a chunk about article 51 above the one about article 15, because the two
are lexically and semantically near-identical. Nothing in the stack had an
equality predicate on a legal identifier.

M2 already solved the hard half. ``QueryProcessor.extract_identifiers``
produces an ``IdentifierSet`` on every ``ProcessedQuery``, and it handles both
scripts and Arabic-Indic digits. That field had no consumer anywhere in the
codebase -- extraction ran on every query and the result was discarded. This
module is the missing half: it turns those extracted values into a *stable
lookup key* that is written into the Qdrant payload at index time and matched
exactly at query time.

Deliberately consuming M2's patterns, not restating them
--------------------------------------------------------
``extract_from_text`` calls ``QueryProcessor.extract_identifiers`` rather than
defining its own regexes. The index side and the query side must agree on what
counts as an article number, and the only way to guarantee that permanently is
for both to run the same code. A second copy of the patterns here would work on
the day it was written and silently drift the first time M2 tuned one of them
-- and the failure mode of that drift is invisible: identifiers would be
written under one spelling and looked up under another, so exact search would
simply stop matching while every test that used a single spelling kept passing.

The collision problem
---------------------
**An article number is only unique within one law.** ``Article 15`` exists in
the 2014 constitution, the 2019 amendments, and every WIPO instrument in the
corpus. Matching on the bare number across a multi-statute collection returns
every law's article 15, which is worse than useless for a citation lookup --
it is confidently wrong.

So two keys are written per identifier, and they answer different questions:

``article_no``
    The bare normalized number, e.g. ``"15"``. Answers "article 15 of
    *something*" -- the right key when the user named no law, which is the
    common case in a search box. Deliberately low-precision.

``article_ref``
    The compound ``{document_id}:a{number}``, e.g. ``"doc_0422a112599d:a15"``.
    Answers "article 15 *of this law*". This is the key that actually
    disambiguates, and it is what a citation-following or
    contract-cross-reference flow should filter on once the governing document
    is known.

The query path uses ``article_no`` when the query names no document and
``article_ref`` when ``QueryFilters.document_ids`` scopes the search to
specific laws -- so precision rises automatically as the caller supplies more
context, with no separate code path.
"""

from __future__ import annotations

import re

from typing import Any, Dict, Iterable, List, Optional, Sequence

from src.schemas.m2_contract import IdentifierSet
import unicodedata
# Arabic-Indic (U+0660-0669) and Extended/Persian Arabic-Indic (U+06F0-06F9)
# digits both appear in Egyptian legal PDFs, sometimes in the same document.
# Normalizing to ASCII at both ends is what lets "المادة ١٥" and "Article 15"
# collapse onto the same key.
_DIGIT_TRANSLATION = {
    **{0x0660 + i: str(i) for i in range(10)},
    **{0x06F0 + i: str(i) for i in range(10)},
}


def fold_digits(value: str) -> str:
    """Fold Arabic-Indic and Persian digits onto ASCII digits."""
    return value.translate(_DIGIT_TRANSLATION)


def normalize_article_number(raw: str) -> Optional[str]:
    """
    Reduce one raw article number to its canonical lookup token.

    Returns ``None`` for anything that does not normalize to a positive
    integer. A value that cannot be normalized must not be written to the
    payload: an unnormalized key is unmatchable by construction, and storing
    one produces an index entry that can never be hit.

    >>> normalize_article_number("١٥")
    '15'
    >>> normalize_article_number("015")
    '15'
    """

    if raw is None:
        return None

    folded = fold_digits(str(raw)).strip()
    digits = "".join(ch for ch in folded if ch.isdigit())

    if not digits:
        return None

    stripped = digits.lstrip("0")

    # "0" and "000" normalize to empty after stripping; there is no article 0.
    return stripped or None


def normalize_case_number(raw: str) -> Optional[str]:
    """
    Canonicalize a case/docket number.

    Unlike article numbers these are alphanumeric and carry separators
    (``123/2019``), so the number is preserved rather than reduced to an
    integer. Case is folded and internal whitespace removed so that
    ``"123 / 2019"`` and ``"123/2019"`` land on one key.
    """

    if raw is None:
        return None

    folded = fold_digits(str(raw)).strip().upper()
    compact = "".join(folded.split())

    # Trim separators that a regex capture commonly picks up at the edges.
    compact = compact.strip("-/:#.,")

    return compact or None


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------
#
# M2 hands over the *raw matched substring*, not a normalized value -- exactly
# as it does for article and case numbers. ``QueryProcessor.DATE_RE`` matches
# three shapes, and all three occur in this corpus:
#
#     "2026-01-15"       ISO, from the payment-schedule tables
#     "15/03/2026"       slash form, from the internal memo header
#     "1 February 2026"  spelled month, from the lease term clause
#     "11 Nov 2023"      abbreviated month, from the constituteproject headers
#
# Matching those as raw strings would mean "15/03/2026" and "2026-03-15" never
# meet, which is the same class of failure Arabic-Indic digits caused for
# article numbers. Everything is reduced to ISO ``YYYY-MM-DD`` so one calendar
# day is one key regardless of how either side spelled it.

_MONTH_NAMES = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

_NUMERIC_DATE = re.compile(r"^(\d{1,4})[/-](\d{1,2})[/-](\d{1,4})$")
_SPELLED_DATE = re.compile(r"^(\d{1,2})\s+([A-Za-z]+)\s+(\d{2,4})$")

_DAY_FIRST = True
"""Read an ambiguous ``dd/mm`` vs ``mm/dd`` numeric date as **day first**.

Not a guess about locale in general -- it is what this corpus actually
contains. The three slash-form dates in the live collection are ``20/03/2026``,
``15/03/2026`` and ``12/03/2026``. Under a month-first reading the first two
would be months 20 and 15, which do not exist, so day-first is the only reading
under which the real data parses at all.

An ISO-looking value (four-digit first component) is detected structurally and
is never subject to this rule.
"""


def _iso(year: int, month: int, day: int) -> Optional[str]:
    """Format a Y/M/D triple as ISO, rejecting anything not a real date."""
    if not (1 <= month <= 12):
        return None
    if not (1 <= day <= 31):
        return None
    if year < 100:
        # Two-digit years appear only in the abbreviated-month form. A legal
        # corpus spans centuries, so there is no safe pivot -- refuse rather
        # than invent one and index a chunk under the wrong century.
        return None
    if year < 1000:
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def normalize_date(raw: str) -> Optional[str]:
    """
    Reduce one raw date to a canonical ISO ``YYYY-MM-DD`` lookup token.

    Returns ``None`` for anything that does not resolve to a real calendar
    date. As with :func:`normalize_article_number`, an unnormalizable value
    must not be written to the payload: a key nothing can ever match is worse
    than an absent key, because it looks like coverage.

    >>> normalize_date("2026-01-15")
    '2026-01-15'
    >>> normalize_date("15/03/2026")
    '2026-03-15'
    >>> normalize_date("1 February 2026")
    '2026-02-01'
    >>> normalize_date("11 Nov 2023")
    '2023-11-11'
    >>> normalize_date("32/01/2026") is None
    True
    """

    if raw is None:
        return None

    folded = fold_digits(str(raw)).strip()
    folded = re.sub(r"\s+", " ", folded)

    numeric = _NUMERIC_DATE.match(folded)
    if numeric:
        first, middle, last = (int(g) for g in numeric.groups())

        # A four-digit leading component is unambiguously ISO ordering; there
        # is no calendar in which it is a day. Detected from the digit count
        # rather than the separator, because the corpus writes ISO with
        # hyphens and day-first with slashes but nothing guarantees that.
        if len(numeric.group(1)) == 4:
            return _iso(first, middle, last)

        if _DAY_FIRST:
            return _iso(last, middle, first)
        return _iso(last, first, middle)

    spelled = _SPELLED_DATE.match(folded)
    if spelled:
        day = int(spelled.group(1))
        month = _MONTH_NAMES.get(spelled.group(2).lower())
        year = int(spelled.group(3))
        if month is None:
            return None
        return _iso(year, month, day)

    return None


# ---------------------------------------------------------------------------
# Monetary values
# ---------------------------------------------------------------------------

_CURRENCY_TOKENS = {
    "$": "USD", "usd": "USD", "دولار": "USD",
    "€": "EUR", "eur": "EUR", "يورو": "EUR",
    "£": "GBP", "gbp": "GBP",
    "egp": "EGP", "جنيه": "EGP",
}

_ARABIC_THOUSANDS_SEPARATOR = "٬"
_ARABIC_DECIMAL_SEPARATOR = "٫"

_MONEY_AMOUNT = re.compile(r"\d[\d,]*(?:\.\d+)?")


def normalize_money(raw: str) -> Optional[str]:
    """
    Reduce one raw monetary value to a ``CURRENCY:amount`` lookup token.

    The currency is part of the key on purpose. ``2450000`` is not one value
    in a corpus that mixes EGP, USD and GBP -- treating it as one would fuse
    a 2.45 million pound figure with a 2.45 million pound-sterling figure and
    call them the same fact. Amount alone is the monetary equivalent of the
    bare ``article_no`` collision, and here there is no reason to accept it.

    Trailing zeros after a decimal point are dropped so ``"1,250.50 EGP"`` and
    ``"1250.5 EGP"`` land on one key; a whole amount carries no decimal part.

    Returns ``None`` when either half is missing. An amount with no currency
    is not a monetary value for lookup purposes -- it is a number.

    A zero amount is also refused, for the same reason
    :func:`normalize_article_number` refuses article 0: there is no legal fact
    that is zero money, so a zero can only be a parse artifact. This is not
    hypothetical here -- it is what the live corpus produced. The Arabic
    thousands separator (U+066C) in ``2٬450٬000 جنيه`` is outside M2's
    ``[\\d,]`` character class, so extraction truncates the value to
    ``"000 جنيه"`` and this function would otherwise write ``EGP:0`` as the
    contract value of a 2.45 million pound agreement -- and, worse, as the
    *same* key on three unrelated contracts, silently joining them. Refusing
    zero turns a wrong answer into an absent one, which is the correct failure
    while the upstream pattern is unfixed.

    >>> normalize_money("$50,000")
    'USD:50000'
    >>> normalize_money("2,450,000 جنيه")
    'EGP:2450000'
    >>> normalize_money("1,250.50 EGP")
    'EGP:1250.5'
    >>> normalize_money("50,000") is None
    True
    >>> normalize_money("000 جنيه") is None
    True
    """

    if raw is None:
        return None

    folded = fold_digits(str(raw))
    folded = folded.replace(_ARABIC_THOUSANDS_SEPARATOR, ",")
    folded = folded.replace(_ARABIC_DECIMAL_SEPARATOR, ".")
    folded = folded.strip()

    currency = None
    for token, code in _CURRENCY_TOKENS.items():
        if token in folded.lower():
            currency = code
            break

    if currency is None:
        return None

    match = _MONEY_AMOUNT.search(folded)
    if match is None:
        return None

    amount = match.group(0).replace(",", "")

    try:
        value = float(amount)
    except ValueError:
        return None

    if value <= 0:
        return None

    if value.is_integer():
        return f"{currency}:{int(value)}"

    # Normalize the decimal tail without floating-point formatting artifacts.
    return f"{currency}:{('%f' % value).rstrip('0').rstrip('.')}"


def article_ref(document_id: str, article_number: str) -> str:
    """
    Build the law-scoped compound key.

    This is the answer to the collision problem described in the module
    docstring: ``article_no`` alone cannot distinguish article 15 of the 2014
    constitution from article 15 of a WIPO treaty, and in this corpus both
    exist.
    """
    return f"{document_id}:a{article_number}"


def date_ref(document_id: str, iso_date: str) -> str:
    """
    Build the document-scoped compound key for a date.

    Dates collide harder than article numbers do, not more softly. ``2026-05-30``
    is a payment-milestone due date carried by **five chunks across three
    documents** in the live collection -- the same schedule reproduced in an
    Arabic contract, its English counterpart and a standalone payment annex.
    A bare-date lookup returns all three documents' copies, which is right when
    the caller named no document and useless when they did.
    """
    return f"{document_id}:d{iso_date}"


def money_ref(document_id: str, money_value: str) -> str:
    """
    Build the document-scoped compound key for a monetary value.

    Same collision shape as dates: ``EGP:612500`` is the first milestone
    payment in every copy of the supply-contract schedule, and a round figure
    like ``EGP:500000`` is exactly the sort of value two unrelated matters
    share by coincidence.
    """
    return f"{document_id}:m{money_value}"

def normalize_preserved_text(
    raw: str | None,
) -> str | None:
    """
    Conservatively normalize text that M2 already preserved.

    M3 does not re-extract party names or legal terms.
    It only normalizes them enough for deterministic lookup.
    """

    if raw is None:
        return None

    value = unicodedata.normalize(
        "NFKC",
        str(raw),
    )

    value = " ".join(
        value.split()
    ).strip()

    if not value:
        return None

    return value.casefold()
def normalize_identifier_set(
    identifiers: Optional[IdentifierSet],
) -> Dict[str, List[str]]:
    """
    Normalize the IdentifierSet already produced by M2.

    M3 does not perform query-side identifier extraction.

    Articles, cases, dates and monetary values use their
    structured normalization rules.

    Party names and named legal terms receive only
    conservative text normalization.
    """

    articles: List[str] = []
    cases: List[str] = []
    dates: List[str] = []
    money: List[str] = []
    party_names: List[str] = []
    named_legal_terms: List[str] = []

    if identifiers is not None:

        articles = _dedupe(
            normalize_article_number(value)
            for value in (
                identifiers.article_numbers
                or []
            )
        )

        cases = _dedupe(
            normalize_case_number(value)
            for value in (
                identifiers.case_numbers
                or []
            )
        )

        dates = _dedupe(
            normalize_date(value)
            for value in (
                identifiers.dates
                or []
            )
        )

        money = _dedupe(
            normalize_money(value)
            for value in (
                identifiers.monetary_values
                or []
            )
        )

        party_names = _dedupe(
            normalize_preserved_text(value)
            for value in (
                identifiers.party_names
                or []
            )
        )

        named_legal_terms = _dedupe(
            normalize_preserved_text(value)
            for value in (
                identifiers.named_legal_terms
                or []
            )
        )

    return {
        "article_numbers": articles,
        "case_numbers": cases,
        "dates": dates,
        "money_values": money,
        "party_names": party_names,
        "named_legal_terms":
            named_legal_terms,
    }

def _dedupe(values: Iterable[Optional[str]]) -> List[str]:
    """Drop ``None`` and duplicates while preserving first-seen order."""
    seen = set()
    out: List[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def extract_from_text(
    *,
    document_id: str,
    text: str,
    section: Optional[str] = None,
    clause: Optional[str] = None,
) -> Dict[str, List[str]]:
    """
    Derive the identifier payload for one chunk at index time.

    ``section`` and ``clause`` are scanned first and matter more than they
    look: in this corpus the article heading usually lives in the section
    (``"Article 211"``, ``"الباب الثالث"``) while the body text quotes *other*
    articles by number. Both are indexed, because a chunk that cites article 15
    is a legitimate hit for a query about article 15 -- but the heading is what
    makes the chunk *about* that article.

    Returns a dict of payload keys to write. Values are deduplicated lists,
    and empty lists are returned rather than ``None`` so the caller can decide
    whether to omit the key.
    """

    # Imported here rather than at module scope: this module is imported by
    # the vector store, and a top-level import would make the storage layer
    # depend on M2's query processor at import time.
    from src.query_processor import QueryProcessor

    processor = QueryProcessor()

    parts = [part for part in (section, clause, text) if part]
    combined = "\n".join(parts)

    found: IdentifierSet = (
        processor.extract_identifiers(
            combined
        )
    )

    normalized = normalize_identifier_set(
        found
    )

    article_numbers = normalized[
        "article_numbers"
    ]

    dates = normalized["dates"]

    money_values = normalized[
        "money_values"
    ]

    party_names = normalized[
        "party_names"
    ]

    return {
        "article_no": article_numbers,
        "article_ref": [
            article_ref(document_id, number) for number in article_numbers
        ],
        "case_no": normalized["case_numbers"],
        # Same bare/compound pair as articles, for the same reason: the bare
        # key answers "this date, in any document" and the compound key
        # answers "this date, in this document". Which one the query path
        # uses depends on whether the caller scoped the search -- see
        # HybridSearcher._identifier_search.
        "date_no": dates,
        "date_ref": [date_ref(document_id, value) for value in dates],
        "money_no": money_values,
        "money_ref": [money_ref(document_id, value) for value in money_values],
        "party_name": party_names,
    }


def identifier_payload(
    *,
    document_id: str,
    text: str,
    section: Optional[str] = None,
    clause: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Same as :func:`extract_from_text` but omits keys with nothing in them.

    Qdrant will happily store an empty list, and it would even match nothing
    as intended -- but it still occupies space in the payload index for every
    chunk that contains no identifier, which in this corpus is most of them.
    """

    extracted = extract_from_text(
        document_id=document_id,
        text=text,
        section=section,
        clause=clause,
    )

    return {key: value for key, value in extracted.items() if value}


def has_identifiers(tokens: Sequence[str] | None) -> bool:
    """Readability helper for the query-path branch."""
    return bool(tokens)


# ---------------------------------------------------------------------------
# Subject ranking: which exact match is the chunk the query is actually about
# ---------------------------------------------------------------------------
#
# Exact matching is boolean, so every chunk carrying ``article_no = "4"`` was
# equally a hit and they reached fusion in Qdrant's scroll order -- arbitrary.
# In this corpus 18 chunks carry article 4: article 4 of the constitution
# ("Sovereignty"), of the IP authority law, of a WIPO treaty, of the supply
# law, plus table-of-contents lines. Returning them unordered means the one the
# caller wants arrives wherever the storage layer happened to put it.
#
# The signals below were measured across all 1,190 article assignments in the
# live collection before being used, because the obvious signal turned out not
# to work:
#
#   opening declaration ("Article 4." / "المادة (4)" at the top)  90.7%
#   section declaration (section == "المادة 4")                   11.4%
#   either                                                        92.8%
#
# ``section`` is 100% reliable on the two synthetic statute documents and
# **0.0%** on the four largest real documents, so a section-only boost would
# have fixed the one case being debugged and done nothing for 88% of the
# corpus. Opening position carries the signal; section is kept as a secondary
# because it is the *only* signal on the documents where the opening pattern
# is parenthesised. Neither is used alone.
#
# This is ranking only. It never filters: a chunk with no subject signal still
# reaches fusion, just below the chunks that declare the article.

_SUBJECT_DECLARATION = re.compile(
    r"(?:article|art\.?|المادة|مادة)\s*[-:#(\[]*\s*([0-9٠-٩۰-۹]+)",
    re.IGNORECASE,
)
"""Paren-tolerant declaration pattern, used **only** for ranking.

Deliberately more permissive than ``QueryProcessor.ARTICLE_RE``, which
requires the number to follow the keyword with at most one of ``-:#`` between.
Real headings in this corpus are written ``المادة (4)`` and ``Article 4[2]``,
which that pattern does not match -- which is why the supply law's article-4
heading was only ever found through its ``section`` field.

M2's extraction pattern is deliberately **not** changed to match this: what
gets indexed is M2's decision, and widening it would alter every stored
payload. This pattern only decides the order of results that exact matching
has already selected.
"""

OPENING_WINDOW = 80
"""Characters from the start of a chunk treated as its heading region.

Sized from the real data: headings in this corpus sit within the first line or
two, but a chunk may open with a chapter line (``الفصل الثاني / في اجراءات
التعاقد``) before the article heading, which pushes the declaration to roughly
character 35.
"""

SUBJECT_WEIGHT_OPENING = 3.0
SUBJECT_WEIGHT_SECTION = 2.0
DILUTION_PENALTY = 0.5
"""Per-extra-article penalty for chunks that carry many article numbers.

A chunk tagged ``['1','2','3','4','5','6']`` is a table of contents or a
cross-reference list, not the text of any one article. It is a legitimate hit
and is not removed -- it is simply a worse answer than a chunk that carries
article 4 and nothing else.
"""


LEADER_DOT_RATIO = 0.20
"""Fraction of '.' characters above which a chunk is a contents line.

A table-of-contents entry ("Article 70. Freedom of the press . . . . . 17")
declares the article number exactly like the real heading does, so the opening
and section signals both fire on it and it wins ties against the actual text.
It is never the answer to "what does article 70 say".

Measured over all 1,190 article-carrying chunks in the live collection, the
distribution is bimodal with an empty gap:

    >= 20% dots : 114 chunks   (leader-dot contents lines)
    10-20%      :   0 chunks   <- nothing lives here
    5-10%       :   8 chunks
    < 5%        : 992 chunks   (body text, 0.5-1.8% typical)

The threshold sits in that empty gap rather than being tuned to a target, so
it is not balanced on the edge of the data. Known contents lines measured
36-47%; known body chunks 0.5-1.8%.

This demotes rather than filters. One scanned contents page (an OCR'd table of
contents) measures 6.6% and is not caught -- a filter would need to be right
about that; a ranking penalty does not.
"""


def is_contents_line(text: Optional[str]) -> bool:
    """Leader-dot contents entry rather than substantive text."""
    if not text:
        return False
    return (text.count(".") / max(len(text), 1)) >= LEADER_DOT_RATIO


def _declares(text: Optional[str], article: str) -> bool:
    if not text:
        return False
    for match in _SUBJECT_DECLARATION.finditer(text):
        if normalize_article_number(match.group(1)) == article:
            return True
    return False


def subject_score(
    *,
    text: Optional[str],
    section: Optional[str],
    article_numbers: Sequence[str],
    wanted: Sequence[str],
) -> float:
    """
    How strongly is this chunk *about* one of the wanted article numbers?

    Higher is better. Zero means the chunk matched the exact index but shows no
    structural sign of being the article itself -- a passing citation, a
    contents line, or a heading the patterns could not read.
    """

    if not wanted:
        return 0.0

    best = 0.0
    for article in wanted:
        score = 0.0
        if _declares((text or "")[:OPENING_WINDOW], article):
            score += SUBJECT_WEIGHT_OPENING
        if _declares(section, article):
            score += SUBJECT_WEIGHT_SECTION
        best = max(best, score)

    if best > 0.0:
        # Only dilute a chunk that actually declared something; a chunk with no
        # declaration is already at zero and must not go negative, or ordering
        # among non-declaring chunks would become meaningless.
        extra = max(0, len(set(article_numbers or [])) - 1)
        best -= DILUTION_PENALTY * extra

        # A contents line declares the article exactly as the real heading
        # does, so it survives every signal above. Drop it below any genuine
        # declaration rather than removing it: it is still a correct exact
        # match, just never the passage a reader wants.
        if is_contents_line(text):
            best = 0.0

    return max(best, 0.0)


def rank_identifier_candidates(
    candidates: List[Dict[str, Any]],
    wanted_articles: Sequence[str],
    tie_breaker: Optional[Dict[tuple, int]] = None,
) -> List[Dict[str, Any]]:
    """
    Order exact-match candidates by how strongly each is the article's subject.

    ``tie_breaker`` maps ``(document_id, chunk_id)`` to that candidate's rank in
    another retriever (in practice, dense). Subject strength cannot tell article
    4 of the supply law from article 4 of the constitution -- both genuinely
    *are* article 4 -- so among equally-strong subjects the semantic ranking
    decides which law the caller meant. Candidates absent from that ranking sort
    last among their tier rather than being dropped.

    Annotates each candidate with ``subject_score`` for debugging; that key is
    internal and never reaches the M4 contract.
    """

    scored = []
    for item in candidates:
        score = subject_score(
            text=item.get("text"),
            section=item.get("section"),
            article_numbers=item.get("article_no") or [],
            wanted=wanted_articles,
        )
        item["subject_score"] = score
        key = (item.get("document_id"), item.get("chunk_id"))
        fallback = (tie_breaker or {}).get(key, 10**6)
        scored.append((-score, fallback, item))

    scored.sort(key=lambda row: (row[0], row[1]))
    return [item for _, _, item in scored]
