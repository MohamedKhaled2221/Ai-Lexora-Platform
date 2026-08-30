"""OCR-tolerant matching for Arabic legal structure markers.

THE FAILURE THIS FIXES (README known limitation #4)
===================================================

Structure detection is regex-based and anchored: a line opens a new article
when it starts with "المادة" and a number. That is exact matching, and OCR is
not exact. Two dots lost off a ﺗ, a ه read for a ة, a join broken in the middle
of the word, and the pattern misses.

The miss itself is a small error. What it *causes* is not: with no marker
found, the document has no structure, `choose_granularity` returns ``None``,
and the whole file silently falls to paragraph chunking. One bad character on
one line costs every clause boundary in the document -- and nothing in the
output says so. **The silence is the actual bug.** A pipeline that mis-reads a
marker and says it mis-read a marker is recoverable; one that quietly returns
worse chunks is not.

So this module does three things, in descending order of importance:

1. **Flags.** Every fuzzy match records that it was fuzzy, what it matched, and
   how far off the text was (:class:`FuzzyMatch`). Every document that finds no
   structure at all raises ``structure_detection_failed``. Both reach the chunk
   metadata and the engine log.
2. **Tolerates the marker word.** Edit distance 1 against a small closed set of
   Arabic structural nouns, after normalization -- see the threshold discussion
   below, which is the part worth arguing about.
3. **Tolerates split digits.** "المادة 1 2" is article 12, not article 1. Fixed
   only in the few characters *following a marker word already matched*, never
   document-wide.

WHY THE THRESHOLD IS 1 AND NOT 2
================================

The Arabic structural nouns are short -- ``مادة`` is four letters -- and Arabic
is morphologically dense, so the distance-1 neighbourhood of a four-letter word
is full of ordinary vocabulary. ``عادة`` (custom/usually), ``سادة``
(gentlemen), ``قادة`` (leaders), ``مدة`` (period), ``زيادة`` (increase) are all
within one edit of ``مادة`` and all common in legal Arabic. At distance 2 the
neighbourhood is unusable: it swallows ``إفادة``, ``شهادة``, ``إعادة``, and the
matcher stops meaning anything.

Distance 1 alone is still not safe enough at these lengths, so three further
constraints apply and each one is doing work:

  * **The first letter must survive.** OCR damages dots, joins and final forms;
    it rarely destroys the leading letter of a word, and the leading letter is
    exactly what separates ``مادة`` from ``عادة``/``سادة``/``قادة``.
  * **A number must follow.** Every structural marker is numbered. A bare word
    is never a marker here, which removes essentially all prose matches.
  * **A short explicit deny-list** (:data:`CONFUSABLE_WORDS`) covers the
    residue -- genuine words that survive both tests, principally ``المدة``
    ("the period"), which is one deletion from ``المادة`` and *does* appear
    before a number in contracts ("المدة 5 سنوات").

Measured, not asserted: ``tests/test_fuzzy_markers.py`` runs the matcher over
non-marker Arabic drawn from the corpus and asserts a zero false-positive rate,
and over synthetically corrupted markers to establish what it does catch.

**What this does not handle, stated plainly:** two or more character errors in
the marker word. "الملاة", "الماىه" with both a substitution and a deletion,
or a word split into three fragments, are not detected and will not be. That is
a deliberate ceiling, not an oversight -- the alternative is a matcher that
fires on ordinary words, and a false marker is worse than a missed one because
it invents a clause boundary that the document does not have.

OUT OF SCOPE: DIGIT ORDER
=========================

This module collapses digits that OCR *split* ("1 2" -> "12"). It never
reorders them. Whether ``٢١`` means 12 or 21 in a right-to-left numeric run is
a question extracted text cannot answer, and getting it wrong silently corrupts
article numbers -- so that stays flagged and unfixed. See
``digit_order_suspect`` in :mod:`src.rtl_fix`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Arabic characters that carry no meaning for matching: tatweel (justification)
# and the harakat (vocalization). Legal Arabic is rarely vocalized and OCR
# invents diacritics freely, so both are dropped before any comparison.
_TATWEEL = "\u0640"
_DIACRITICS = re.compile(r"[\u064B-\u0652\u0670\u0653-\u0655\u0656-\u065F\u06D6-\u06ED]")

# Orthographic variants that are the *same letter* for matching purposes. This
# is folding for comparison only -- nothing here rewrites the document.
_FOLD = str.maketrans({
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ٲ": "ا", "ٳ": "ا",
    "ة": "ه",
    "ى": "ي", "ئ": "ي",
    "ؤ": "و",
    "ک": "ك", "ﻙ": "ك",
    "ی": "ي",
})

# The closed set of Arabic structural nouns, mapped to the marker kind they
# open. Keyed by their *normalized* form, and stored without the definite
# article, which is matched separately because it is optional in practice
# ("المادة 5" and "مادة 5" are both written).
MARKER_WORDS: dict[str, str] = {
    "ماده": "article",
    "بند": "clause",
    "فقره": "clause",
    "فصل": "chapter",
    "باب": "book",
    "كتاب": "book",
    "قسم": "section",
}

# Genuine Arabic words that survive both the first-letter test and the
# followed-by-a-number test, and would otherwise match. Short by design: a long
# deny-list would be a sign the threshold is wrong rather than a fix for it.
#
# ``مدة``/``المدة`` is the one that matters. It is one deletion from ``مادة``,
# it means "period", and Egyptian contracts write "المدة 5 سنوات" -- a line that
# is emphatically not article 5.
CONFUSABLE_WORDS: frozenset[str] = frozenset({
    "مده",      # مدة  -- "period"; one deletion from مادة, appears before numbers
    "عاده",     # عادة -- "custom / usually"
    "ساده",     # سادة -- "gentlemen" (letterheads, address blocks)
    "قاده",     # قادة -- "leaders"
    "شهاده",    # شهادة -- "certificate"; distance 2 but cheap to be explicit
    "افاده",    # إفادة -- "statement"
    "زياده",    # زيادة -- "increase"
    "بنود",     # بنود -- plural of بند; "البنود 2 و3" is a cross-reference
    "فصول",     # فصول -- plural of فصل
    "ابواب",    # أبواب -- plural of باب
    "قسمه",     # قسمة -- "division"
    "نسبه",     # نسبة -- "percentage"; precedes numbers constantly
})

# The maximum edit distance tolerated in the marker word itself. See the module
# docstring: 1 is a ceiling imposed by Arabic morphology at these word lengths,
# not a knob to turn up.
MAX_MARKER_DISTANCE = 1

# Marker words shorter than this are matched exactly and never fuzzily. At
# three letters ("بند", "باب", "فصل") a single edit reaches a third of the
# language, so tolerance there buys nothing and costs a great deal.
MIN_FUZZY_LENGTH = 4


@dataclass
class FuzzyMatch:
    """A structural marker word recovered by tolerant matching.

    Exists so the correction is *visible*. ``distance == 0`` records an exact
    match that only needed the digits repairing; anything above that means the
    marker word itself was damaged and the document is worth spot-checking.
    """

    kind: str
    """Marker kind the word opens: "article", "clause", "chapter", ..."""
    canonical: str
    """The normalized marker word that was matched against."""
    observed: str
    """The token as it actually appeared in the text."""
    distance: int
    """Edit distance between the two, after normalization."""
    digits_joined: bool = False
    """True when spurious separators inside the marker's number were collapsed."""
    repaired_line: str = ""
    """The line as handed on to the regexes, after any digit repair."""

    @property
    def confidence(self) -> float:
        """Crude 0-1 score. 1.0 for an exact word, dropping with distance."""
        return round(max(0.0, 1.0 - 0.35 * self.distance - (0.1 if self.digits_joined else 0.0)), 3)

    def describe(self) -> str:
        bits = []
        if self.distance:
            bits.append(
                f"marker word read as {self.observed!r}, matched to {self.canonical!r} "
                f"at edit distance {self.distance}"
            )
        else:
            bits.append(
                f"marker word {self.observed!r} matched {self.canonical!r} after "
                f"folding tatweel/diacritics/orthographic variants, but the line "
                f"as written did not match any exact pattern"
            )
        if self.digits_joined:
            bits.append("split digits in the marker number were rejoined")
        return "; ".join(bits)


# ---------------------------------------------------------------------------
# Normalization and distance
# ---------------------------------------------------------------------------


def normalize_for_match(word: str) -> str:
    """Fold a token to the form marker words are compared in.

    Drops tatweel and diacritics, folds alef/hamza variants, teh marbuta to heh
    and alef maksura to yeh. Every one of these is a distinction OCR does not
    reliably preserve and none of them changes which structural word is meant,
    so folding them costs nothing and removes a whole class of spurious edit
    distance. Note that this makes several of the commonest OCR errors free
    rather than merely tolerated -- "الماده" and "المـادة" both normalize to the
    canonical form and never spend any of the distance-1 budget.

    The definite article is **not** stripped here; :func:`_candidate_cores` does
    that, because the article is itself a thing OCR damages.
    """
    word = word.replace(_TATWEEL, "")
    word = _DIACRITICS.sub("", word)
    word = word.translate(_FOLD)
    return "".join(c for c in word if not c.isspace())


def _candidate_cores(norm: str) -> list[str]:
    """The forms of ``norm`` worth matching against the bare structural nouns.

    "المادة" is written with the definite article far more often than without,
    and the article is two of the six characters -- so it is also where a
    healthy share of the OCR damage lands. Stripping only a *clean* "ال" would
    leave "لمادة" (alef dropped) unmatchable, and then reject it for the wrong
    reason: the first-letter guard would compare "ل" against "م" and refuse a
    marker that is one edit from correct.

    So the article is peeled optimistically -- "ال", then a bare "ا" or "ل" --
    and every resulting core is tried. The guards downstream are unchanged, so
    this widens what is *considered*, not what is accepted.
    """
    cores = [norm]
    if len(norm) > 3:
        if norm.startswith("ال"):
            cores.append(norm[2:])
        elif norm[0] in "ال":
            cores.append(norm[1:])
    return cores


def edit_distance(a: str, b: str, ceiling: int = 2) -> int:
    """Levenshtein distance, abandoned once it exceeds ``ceiling``.

    Returns ``ceiling + 1`` for anything further apart. Implemented here rather
    than pulled in as a dependency: it is fifteen lines, the strings are always
    single words, and the pinned requirement set is deliberately small.
    """
    if abs(len(a) - len(b)) > ceiling:
        return ceiling + 1
    if a == b:
        return 0

    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(min(
                previous[j] + 1,          # deletion
                current[j - 1] + 1,       # insertion
                previous[j - 1] + (ca != cb),  # substitution
            ))
        if min(current) > ceiling:
            return ceiling + 1
        previous = current
    return previous[-1] if previous[-1] <= ceiling else ceiling + 1


def match_marker_word(token: str) -> tuple[str, str, int] | None:
    """Match one token against the structural nouns.

    Returns ``(kind, canonical, distance)`` or ``None``. Applies the guards
    described in the module docstring: deny-list, minimum length for any
    tolerance at all, and the leading letter must survive.
    """
    norm = normalize_for_match(token)
    if not norm:
        return None

    best: tuple[str, str, int] | None = None
    for core in _candidate_cores(norm):
        if core in CONFUSABLE_WORDS:
            # Checked per-core, not once: "المدة" must be refused on the strength
            # of its stripped form "مده" as well as its written one.
            return None
        if core in MARKER_WORDS:
            return MARKER_WORDS[core], core, 0

    for core in _candidate_cores(norm):
        if len(core) < MIN_FUZZY_LENGTH:
            # "بند" / "باب" / "فصل": exact only. One edit at three letters
            # reaches a third of the language.
            continue
        for canonical, kind in MARKER_WORDS.items():
            if canonical[0] != core[0]:
                # OCR damages dots, joins and final forms; it rarely destroys
                # the leading letter, and the leading letter is what separates
                # مادة from عادة, سادة and قادة.
                continue
            d = edit_distance(core, canonical, MAX_MARKER_DISTANCE)
            if d <= MAX_MARKER_DISTANCE and (best is None or d < best[2]):
                best = (kind, canonical, d)
    return best


# ---------------------------------------------------------------------------
# Digit repair, scoped to the marker
# ---------------------------------------------------------------------------

_ANY_DIGIT = "0-9٠-٩۰-۹"
_IS_DIGIT = re.compile(rf"[{_ANY_DIGIT}]")

# Separators OCR invents between the digits of one number. Deliberately excludes
# "/", "-" and ".", which are *meaningful* inside legal numbering -- "12/2019",
# "5-3", "5.2.1" -- where collapsing them would merge distinct components into
# one wrong number rather than repair a split one.
_STRAY_SEPARATORS = " 	 ،,;:"

# Characters a number may sit behind, between the marker word and its digits.
_LEAD_IN = " 	 ([{:.–—-"

# The longest number a structural marker plausibly carries. Past this the run
# being scanned is not an article number.
MAX_MARKER_DIGITS = 4


def join_split_digits(line: str, start: int) -> tuple[str, bool]:
    """Rejoin the digits of *the marker's own number*, and nothing else.

    ``start`` is the offset just past the marker word. From there the scan skips
    the punctuation a number may sit behind ("(", ":", " "), then walks a single
    digit-and-separator chain dropping the separators, and **stops at the first
    character that is neither**. It cannot reach past the number it is
    repairing, and it stops after :data:`MAX_MARKER_DIGITS` digits.

    That precision is the requirement rather than an optimisation. The same rule
    applied over a character window reads ``"المادة 12 المبلغ 1 500 جنيه"`` and turns the
    amount into 1500; applied document-wide it rewrites every date, monetary
    amount and citation in the file. The repair is worth little and
    over-applying it corrupts a contract, so the scope is drawn as tightly as it
    will go.

    Digit *order* is never touched -- only separators *between* digits are
    removed. Reordering is a different question with a different answer; see the
    module docstring.

    Returns ``(line, changed)``.
    """
    i = start
    while i < len(line) and line[i] in _LEAD_IN:
        i += 1
    if i >= len(line) or not _IS_DIGIT.match(line[i]):
        return line, False

    out: list[str] = []
    j = i
    while j < len(line) and len(out) < MAX_MARKER_DIGITS:
        if _IS_DIGIT.match(line[j]):
            out.append(line[j])
            j += 1
            continue
        # A separator survives the scan only if a digit follows it; otherwise
        # the number has ended, and so has the repair.
        k = j
        while k < len(line) and line[k] in _STRAY_SEPARATORS and k - j < 2:
            k += 1
        if k > j and k < len(line) and _IS_DIGIT.match(line[k]):
            j = k
            continue
        break

    rebuilt = line[:i] + "".join(out) + line[j:]
    return rebuilt, rebuilt != line


# ---------------------------------------------------------------------------
# Line-level entry point
# ---------------------------------------------------------------------------

# The leading token of a line, plus where it ends. Brackets and quotes are
# skipped so '"المادة 5' and '(المادة 5)' both present their word.
_LEADING_TOKEN = re.compile(r"^[\s\"'«»\(\[\{]*(?P<word>\S+)")

# Does something number-like follow the marker word? A marker is always
# numbered; requiring that here is what stops the fuzzy matcher from firing on
# ordinary prose that happens to open with a near-miss word.
_FOLLOWED_BY_NUMBER = re.compile(
    rf"^[\s:\-–—.]*[\(\[]?\s*[{_ANY_DIGIT}]"
    rf"|^[\s:\-–—.]*[\(\[]?\s*(?:ال)?(?:أ|ا)ول|^[\s:\-–—.]*[\(\[]?\s*(?:ال)?ثان"
    rf"|^[\s:\-–—.]*[\(\[]?\s*(?:ال)?ثالث|^[\s:\-–—.]*[\(\[]?\s*(?:ال)?رابع"
    rf"|^[\s:\-–—.]*[\(\[]?\s*(?:ال)?خامس|^[\s:\-–—.]*[\(\[]?\s*(?:ال)?سادس"
    rf"|^[\s:\-–—.]*[\(\[]?\s*(?:ال)?سابع|^[\s:\-–—.]*[\(\[]?\s*(?:ال)?ثامن"
    rf"|^[\s:\-–—.]*[\(\[]?\s*(?:ال)?تاسع|^[\s:\-–—.]*[\(\[]?\s*(?:ال)?عاشر"
)


def repair_marker_line(line: str) -> FuzzyMatch | None:
    """Try to recover a damaged structural marker at the head of ``line``.

    Returns a :class:`FuzzyMatch` whose ``repaired_line`` is the line with the
    marker word restored to canonical spelling and any split digits in its
    number rejoined -- ready to be handed back to the ordinary regexes, which
    then parse it exactly as they always would.

    Rewriting the line rather than parsing it here is deliberate: it keeps a
    single definition of what a marker *is*, in
    ``structure_preservation._MARKER_PATTERNS``, rather than growing a second,
    tolerant parser that can drift away from the strict one.

    Note that this runs in two situations, not one. The obvious one is a damaged
    marker *word*, where the exact patterns have already failed. The other is a
    perfectly readable word whose *number* was split -- "المادة 1 2" matches the
    strict pattern happily and yields article **1**, silently losing the rest of
    the number and merging article 12's text into article 1's chunk. That case
    has to be caught even though nothing appeared to fail, which is why
    ``distance == 0`` matches are returned rather than skipped.
    """
    stripped = line.strip()
    if not stripped or len(stripped) > 300:
        return None

    m = _LEADING_TOKEN.match(stripped)
    if not m:
        return None
    word = m.group("word")
    word_end = m.end("word")

    # The word may have been split by OCR ("الما دة"): try the leading token,
    # then the leading token joined with the one after it.
    candidates = [(word, word_end)]
    nxt = re.match(r"\s*(\S+)", stripped[word_end:])
    if nxt and len(word) <= 4:
        candidates.append((word + nxt.group(1), word_end + nxt.end()))

    for observed, end in candidates:
        # Trailing digits or punctuation glued to the word ("المادة5", "المادة:")
        # belong to the number, not to the word.
        core = re.sub(rf"[{_ANY_DIGIT}\W]+$", "", observed)
        if not core:
            continue
        hit = match_marker_word(core)
        if hit is None:
            continue
        kind, canonical, distance = hit

        # Where the marker word ends in the original line. The regex consumed
        # ``observed``; ``core`` is a prefix of it, so anything trimmed off the
        # end is still part of what follows.
        rest_at = end - (len(observed) - len(core))
        if not _FOLLOWED_BY_NUMBER.match(stripped[rest_at:]):
            continue

        written = _CANONICAL_SPELLING[canonical]
        rebuilt, joined = join_split_digits(written + stripped[rest_at:], len(written))
        if rebuilt == stripped:
            # Nothing needed repairing: the line already reads canonically, so
            # the strict patterns have or will handle it. Returning a match here
            # would label every clean marker "fuzzy" and make the flag useless.
            return None
        return FuzzyMatch(
            kind=kind,
            canonical=canonical,
            observed=core,
            distance=distance,
            digits_joined=joined,
            repaired_line=rebuilt,
        )
    return None


# How each normalized marker word is written back into the repaired line, in the
# spelling the strict patterns expect.
_CANONICAL_SPELLING = {
    "ماده": "المادة",
    "بند": "البند",
    "فقره": "الفقرة",
    "فصل": "الفصل",
    "باب": "الباب",
    "كتاب": "الكتاب",
    "قسم": "القسم",
}
