"""Visual-order detection and repair for Arabic text, including bilingual lines.

WHAT "VISUAL ORDER" IS, AND WHY IT SILENTLY DESTROYS A DOCUMENT
===============================================================

Arabic is stored *logically*: the first character of a word is the first
character in the string, whichever way the glyphs are painted. Some producers
do not store it that way. Arabic DTP software that shapes text before writing
it, and OCR engines that emit words in screen order, both write the string in
**visual** order -- left-to-right across the page, so the RTL runs come out
backwards relative to how they are read.

The result looks perfect on screen (the pixels were always fine) and is
completely wrong to every consumer that reads the string sequentially: the
clause-marker regex is anchored at line start and the marker has moved to the
line *end*; chunking cuts in the wrong place; embeddings see reversed tokens.

On ``stress_inline_bilingual.pdf`` this was total structural failure, not
degradation -- 5 numbered memorandum paragraphs, 0 clause markers recovered.

THE TWO STAGES THAT CAN PRODUCE IT (as opposed to merely propagate it)
======================================================================

1. **PDF text-layer extraction.** The glyphs are painted left-to-right at
   ascending x. Their *content-stream* order is whatever the producer wrote,
   and MuPDF then applies a bidi pass of its own on top. On a pre-shaped
   bilingual file that pass produces a hybrid -- Arabic runs internally
   logical, the run *sequence* still visual, neutrals displaced -- which is not
   cleanly repairable from the string alone. The page geometry is, though: see
   :func:`visual_line_from_chars`.
2. **OCR output assembly.** Boxes come back positioned, not ordered. Sorting a
   mixed line entirely right-to-left fixes the Arabic and reverses the English
   inside it; see :func:`reorder_tokens_visual_to_logical`.

Chunking, normalization and marker detection only *propagate* the damage. They
are not where it should be fixed.

HOW THE DECISION IS MADE (the promoted reversal test)
=====================================================

``scripts/audit_ground_truth.py`` distinguishes "this reference is in visual
order" from "this is a genuine recognition error" by *reversing it and seeing
whether that helps by a material margin* -- ``REVERSAL_HELPS = 0.10``. Offline
it can score against OCR output. Live there is no reference, so the same shape
of test is run against an intrinsic, dictionary-free measure of how much a
string looks like ordered text: :func:`order_score`.

    repaired = visual_to_logical(text)
    if order_score(repaired) - order_score(text) >= margin: use repaired

That framing is what makes the repair safe to turn on. Genuine OCR damage is
damaged in *both* directions, so the margin is not met and nothing is touched --
which is the outcome that matters, because a false positive here reverses
correct text and is strictly worse than leaving a known-bad line alone.

**Two criteria, both required** (:func:`choose_reading`). The order score alone
is not sufficient, and the corpus says so: on ``wipo_eg081ar_1.pdf`` -- a
published statute whose reference the audit classifies as *logical* -- the
geometric reading scores **better** (+0.73 -> +0.94), because that file has
mirrored sentence punctuation which the reordering tidies up. Accepting it on
score alone would have reversed a correct document. What exposes it is the
second criterion: the same reordering takes that file's recovered structural
markers from **3 to 0**. So a reading is only accepted when it *both* scores
materially better *and* recovers at least as much legal structure --
:func:`marker_recovery`. Each criterion catches a case the other misses:

    file                          markers      order score      verdict
    constitute_egypt_2014_ar      0 -> 59    +0.01 -> +0.76     repair
    stress_inline_bilingual        0 -> 5    +0.43 -> +0.72     repair
    synthetic_contract_bilingual   6 -> 15   +0.74 -> +0.88     repair
    wipo_eg081ar_1                 3 -> 0    +0.73 -> +0.94     LEAVE (markers)
    stress_exhibits_footnotes     11 -> 13   +0.86 -> +0.86     LEAVE (score)

WHAT IS DELIBERATELY NOT DONE HERE
==================================

**Digit order is never touched.** ``٢١`` and ``١٢`` are indistinguishable in
extracted text, so a guess silently corrupts article numbers and amounts. That
remains flagged, not fixed, and is out of scope for this module by design --
see ``digit_order_suspect`` in :mod:`src.rtl_fix`.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from .structure_preservation import is_arabic_char, is_latin_char

# Bracket-like characters that mirror when a run's direction flips.
_MIRROR = {"(": ")", ")": "(", "[": "]", "]": "[", "{": "}", "}": "{",
           "<": ">", ">": "<", "“": "”", "”": "“"}

_SENTENCE_FINAL = ".!?؟؛،:"

_AR_RANGE = "؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿"
_SCRIPT_GLUE = re.compile(rf"[{_AR_RANGE}][A-Za-z]|[A-Za-z][{_AR_RANGE}]")

# How much better the reordered candidate must score before it is accepted.
# Mirrors ``audit_ground_truth.REVERSAL_HELPS`` in both value and intent: small
# improvements are noise, a genuine visual-order line improves dramatically.
REVERSAL_HELPS = 0.10

# Below this many scoring observations a line carries too little evidence to
# convict. Short headings are exactly where a false positive is most visible.
MIN_OBSERVATIONS = 4


# ---------------------------------------------------------------------------
# The order score
# ---------------------------------------------------------------------------


@dataclass
class OrderScore:
    """How much a string looks like it is in logical reading order.

    ``score`` runs -1 (every signal says reversed) to +1 (every signal says
    logical). ``observations`` is how much evidence there was; a score computed
    from two observations means nothing and callers must check it.
    """

    score: float
    observations: int
    evidence: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:  # pragma: no cover - convenience only
        return self.observations >= MIN_OBSERVATIONS


def order_score(text: str) -> OrderScore:
    """Score ``text`` for logical-vs-visual reading order, without a dictionary.

    Five independent orthographic and typographic signals, each of which is a
    statement about *position* rather than meaning, so none of them needs a
    lexicon or a language model:

    ``ال`` **prefix.** The Arabic definite article is word-initial and is
        extremely frequent in legal Arabic. Reverse the string and it appears
        as ``لا`` word-*finally* instead.

    **Final-form letters.** ``ة`` and ``ى`` occur only at the end of a word.
        Finding them opening tokens is not a spelling variant, it is a reversal.

    **Latin capitalisation.** English tokens capitalise their first letter;
        ``Clause`` reversed is ``esualC``, with the capital at the end. This is
        the signal that carries bilingual lines, where the Arabic evidence may
        be thin.

    **Sentence-final punctuation.** A full stop closes a line. Leading it is the
        classic mirrored-neutral tell.

    **Bracket direction.** ``(x)`` is a span; ``)x(`` is a flipped one.

    Signals are pooled as weighted counts rather than averaged, so a line with
    one weak signal and forty strong ones is scored by the forty. Punctuation
    and bracket evidence is weighted double because it is nearly noise-free,
    where Arabic morphology has genuine (if rare) counter-examples.

    Presentation forms are folded to base letters first. A visual-order string
    usually arrives as glyph codepoints (U+FB50-U+FEFF), and every signal above
    is written against base letters -- so without the fold, the *original*
    reading scores near zero for want of evidence while the reordered candidate
    (which folds as part of the transform) scores normally, and the comparison
    measures the fold rather than the order. Scoring is read-only; the fold
    never reaches the returned text.
    """
    text = unicodedata.normalize("NFKC", text)

    pos = 0.0
    neg = 0.0
    obs = 0
    evidence: list[str] = []

    tokens = [t for t in re.split(r"\s+", text) if t]

    # --- 1. Arabic definite article ---------------------------------------
    ar_tokens = [t for t in tokens if any(is_arabic_char(c) for c in t)]
    al_head = sum(1 for t in ar_tokens if _strip_edges(t).startswith("ال"))
    al_tail = sum(1 for t in ar_tokens if _strip_edges(t).endswith("لا"))
    if al_head or al_tail:
        pos += al_head
        neg += al_tail
        obs += al_head + al_tail
        evidence.append(f"'ال' opens {al_head} token(s), "
                        f"'لا' closes {al_tail}")

    # --- 2. Final-form-only letters ---------------------------------------
    final_only = "ةى"          # taa marbuta, alef maqsura
    fin_tail = sum(1 for t in ar_tokens if _strip_edges(t)[-1:] in final_only)
    fin_head = sum(1 for t in ar_tokens if _strip_edges(t)[:1] in final_only)
    if fin_head or fin_tail:
        pos += fin_tail
        neg += fin_head
        obs += fin_head + fin_tail
        evidence.append(f"final-form letters close {fin_tail} token(s), open {fin_head}")

    # --- 3. Latin capitalisation ------------------------------------------
    cap_head = cap_tail = 0
    for t in tokens:
        core = _strip_edges(t)
        if len(core) < 2 or not all(is_latin_char(c) for c in core):
            continue
        if core[0].isupper() and not core[-1].isupper():
            cap_head += 1
        elif core[-1].isupper() and not core[0].isupper():
            cap_tail += 1
    if cap_head or cap_tail:
        pos += cap_head
        neg += cap_tail
        obs += cap_head + cap_tail
        evidence.append(f"{cap_head} Latin token(s) capitalise their first letter, "
                        f"{cap_tail} their last")

    # --- 4. Sentence-final punctuation -------------------------------------
    stop_tail = stop_head = 0
    for line in text.splitlines():
        s = line.strip()
        if not s or not any(is_arabic_char(c) for c in s):
            continue
        if s[-1] in _SENTENCE_FINAL:
            stop_tail += 1
        elif s[0] in _SENTENCE_FINAL:
            stop_head += 1
    if stop_head or stop_tail:
        pos += 2 * stop_tail
        neg += 2 * stop_head
        obs += stop_head + stop_tail
        evidence.append(f"{stop_tail} line(s) end with sentence punctuation, "
                        f"{stop_head} begin with it")

    # --- 5. Bracket direction ----------------------------------------------
    normal = len(re.findall(r"\([^()]{1,80}\)", text)) + len(re.findall(r"\[[^\[\]]{1,80}\]", text))
    flipped = len(re.findall(r"\)[^()]{1,80}\(", text)) + len(re.findall(r"\][^\[\]]{1,80}\[", text))
    if normal or flipped:
        pos += 2 * normal
        neg += 2 * flipped
        obs += normal + flipped
        evidence.append(f"{normal} normal bracket span(s), {flipped} mirrored")

    # --- 6. Script glue -----------------------------------------------------
    # An Arabic letter touching a Latin letter with no separator between them.
    # Correctly ordered bilingual text essentially never does this -- the two
    # scripts meet at a space or a bracket. It appears when a bidi pass has
    # reordered runs without carrying the whitespace with them, which is exactly
    # the hybrid MuPDF hands back for a pre-shaped Arabic PDF
    # ("...الدوريةthe Lessor..."). Pure negative evidence: its absence proves
    # nothing, its presence is damage.
    glue = len(_SCRIPT_GLUE.findall(text))
    if glue:
        neg += 2 * glue
        obs += glue
        evidence.append(f"{glue} Arabic/Latin adjacency(ies) with no separator "
                        f"-- runs were reordered without their whitespace")

    total = pos + neg
    return OrderScore(
        score=0.0 if total == 0 else round((pos - neg) / total, 4),
        observations=obs,
        evidence=evidence,
    )


def _strip_edges(token: str) -> str:
    """Drop surrounding punctuation so position tests see the word itself."""
    return token.strip("،؛؟.,;:!?()[]{}\"'«»“”-–—")


def marker_recovery(text: str) -> int:
    """How many lines of ``text`` open with a legal structural marker.

    The second, decisive criterion in :func:`choose_reading`, and the one that
    is actually about the thing being fixed. Marker detection is anchored at
    line start, so it is *definitionally* sensitive to reading order: a line
    stored in visual order has pushed its "المادة 12" or its "5.1" to the far
    end, where no anchored pattern can see it.

    That makes it a far better arbiter than any orthographic score, because it
    measures the downstream consequence rather than a proxy for it. A reading
    that recovers fewer markers than the one it would replace is rejected
    however good it looks by every other measure -- which is what stops a
    correctly-ordered statute with untidy punctuation from being reversed.
    """
    from .structure_preservation import detect_marker

    return sum(
        1 for line in text.splitlines()
        if line.strip() and detect_marker(line) is not None
    )


# ---------------------------------------------------------------------------
# The transform
# ---------------------------------------------------------------------------


def visual_to_logical(text: str, base_dir: str = "R") -> str:
    """Reorder one visual-order line into logical order.

    ``python-bidi``'s ``get_display`` implements the Unicode Bidi Algorithm's
    reordering: reverse the RTL runs of a logical string, leave the LTR runs
    forward, mirror the neutrals between them. On a string that is *already*
    visual that operation is its own inverse, so it recovers logical order --
    and, crucially, it does so **per run**. That is what makes it correct for
    the bilingual case: an embedded ``(the Lessor)`` keeps its internal English
    word order and its brackets while the Arabic around it is put back.

    Reordering happens **before** presentation forms are folded, not after.
    ``NFKC`` decomposes the lam-alef ligature ``ﻻ`` into two characters, and if
    that happens first those two characters get reversed independently -- which
    is how ``الإيجار`` came back as ``اإليجار``. One ligature glyph is one
    position in the visual string; it must stay one position through the
    reversal and be decomposed afterwards.

    Digits are untouched: the UBA moves numeric *runs* as units and never
    reorders the digits inside one.
    """
    if not text.strip():
        return text
    try:
        from bidi.algorithm import get_display

        reordered = get_display(text, base_dir=base_dir)
    except Exception:  # noqa: BLE001 -- python-bidi is optional at runtime
        return text
    return unicodedata.normalize("NFKC", reordered)


# ---------------------------------------------------------------------------
# The live reversal test
# ---------------------------------------------------------------------------


@dataclass
class ReorderVerdict:
    """The outcome of testing a body of text for visual order.

    Carried through to document warnings and chunk metadata so a repair is
    auditable rather than silent: every accepted reading records what it scored
    and what it recovered, and every *rejected* one records why.
    """

    text: str
    repaired: bool
    score_before: float
    score_after: float
    observations: int
    reason: str
    markers_before: int = 0
    markers_after: int = 0

    @property
    def gain(self) -> float:
        return round(self.score_after - self.score_before, 4)

    def as_dict(self) -> dict:
        return {
            "repaired": self.repaired,
            "score_before": self.score_before,
            "score_after": self.score_after,
            "gain": self.gain,
            "observations": self.observations,
            "markers_before": self.markers_before,
            "markers_after": self.markers_after,
            "reason": self.reason,
        }


def choose_reading(
    stream: str,
    candidate: str,
    margin: float = REVERSAL_HELPS,
    min_observations: int = MIN_OBSERVATIONS,
) -> ReorderVerdict:
    """Pick between two readings of the same text. **The live reversal test.**

    ``stream`` is what the extractor produced by default; ``candidate`` is the
    reading reconstructed from glyph geometry (PDF) or by
    :func:`visual_to_logical` (everything else). ``candidate`` is accepted only
    when **both** criteria hold -- see the module docstring for the corpus
    evidence that each one is load-bearing:

      1. it recovers at least as many structural markers as ``stream``, and
         strictly more if ``stream`` found any at all;
      2. it beats ``stream`` on :func:`order_score` by ``margin``, ends up
         positively scored, and had at least ``min_observations`` observations
         to say so.

    Rejection is the default and every rejection carries its reason, so a
    document that *should* have been repaired and was not is discoverable in
    the engine log rather than invisible.
    """
    if not stream.strip() or not any(is_arabic_char(c) for c in stream):
        return ReorderVerdict(stream, False, 0.0, 0.0, 0, "no Arabic content")
    if candidate.strip() == stream.strip():
        return ReorderVerdict(stream, False, 0.0, 0.0, 0,
                              "reordering is a no-op for this text")

    before, after = order_score(stream), order_score(candidate)
    mk_before, mk_after = marker_recovery(stream), marker_recovery(candidate)
    gain = after.score - before.score

    def verdict(ok: bool, reason: str) -> ReorderVerdict:
        return ReorderVerdict(
            candidate if ok else stream, ok, before.score, after.score,
            before.observations, reason, mk_before, mk_after,
        )

    # Criterion 1 first: it is the one about the actual failure, and it is the
    # one that vetoes the corpus's real false positive.
    if mk_after < mk_before or (mk_before > 0 and mk_after == mk_before):
        return verdict(
            False,
            f"reordering recovers {mk_after} structural marker(s) against "
            f"{mk_before} in the extracted text; it does not improve legal "
            f"structure, so the extracted reading is kept",
        )
    if before.observations < min_observations:
        return verdict(
            False,
            f"only {before.observations} reading-order observations "
            f"(need {min_observations}); too little evidence to reverse anything",
        )
    if gain < margin:
        return verdict(
            False,
            f"reordering recovers {mk_after} marker(s) vs {mk_before} but the "
            f"order score gains only {gain:+.3f} (need {margin:+.3f}); left "
            f"as-is -- consistent with logical order, or with genuine "
            f"extraction damage that reordering does not fix",
        )
    if after.score <= 0:
        return verdict(
            False,
            f"reordering gains {gain:+.3f} but still scores {after.score:+.3f}; "
            f"the text is damaged rather than reversed, and was left as-is",
        )

    return verdict(
        True,
        f"visual order confirmed: structural markers {mk_before} -> {mk_after}, "
        f"order score {before.score:+.3f} -> {after.score:+.3f} "
        f"(gain {gain:+.3f} over {before.observations} observations). "
        + "; ".join(after.evidence[:2]),
    )


def detect_and_repair(
    text: str,
    margin: float = REVERSAL_HELPS,
    min_observations: int = MIN_OBSERVATIONS,
    candidate: str | None = None,
) -> ReorderVerdict:
    """Test one span for visual order with no geometry available.

    Used on the OCR, DOCX and plaintext paths, where there are no glyph
    positions to reconstruct from and the only candidate reading is the one
    :func:`visual_to_logical` derives from the string itself. Same two criteria
    as :func:`choose_reading`.
    """
    proposed = candidate if candidate is not None else visual_to_logical(text)
    return choose_reading(text, proposed, margin, min_observations)


# ---------------------------------------------------------------------------
# Geometry-based reconstruction (PDF text layer)
# ---------------------------------------------------------------------------


def visual_line_from_chars(chars: list[dict]) -> str:
    """Rebuild the true painted order of a PDF text line from glyph geometry.

    PyMuPDF's ``get_text("dict")`` hands back the content stream *after* MuPDF's
    own bidi pass, which on a pre-shaped Arabic file leaves a hybrid that cannot
    be repaired from the string. The glyph x-positions are not ambiguous:
    sorting by them gives exactly the sequence a reader's eye sweeps, which is
    the visual order :func:`visual_to_logical` inverts.

    ``chars`` is PyMuPDF's ``rawdict`` char list -- dicts with ``"c"`` and
    ``"bbox"``. Zero-width and degenerate boxes keep their relative position
    via a stable sort.
    """
    if not chars:
        return ""
    ordered = sorted(range(len(chars)), key=lambda i: chars[i]["bbox"][0])
    return "".join(chars[i]["c"] for i in ordered)


# ---------------------------------------------------------------------------
# Token-level reordering (OCR path)
# ---------------------------------------------------------------------------


def _token_direction(token: str) -> str:
    """``R`` / ``L`` / ``N`` for a whole token, by its first strong character."""
    for ch in token:
        if is_arabic_char(ch):
            return "R"
        if is_latin_char(ch):
            return "L"
    return "N"


def reorder_tokens_visual_to_logical(tokens: list[str], base_dir: str = "R") -> list[int]:
    """Permutation putting visually-ordered *tokens* into logical order.

    Returns indices into ``tokens``, so a caller holding OCR boxes can reorder
    the boxes and keep their geometry rather than re-joining strings.

    This is the token-granularity form of the same algorithm
    :func:`visual_to_logical` applies to characters, and it exists because OCR
    gives a different starting point: each recognised word is *internally*
    logical already (the recogniser read it as a word), but their left-to-right
    sequence on the page is visual. Reversing the whole line -- which is what
    sorting a mixed line by descending x amounts to -- therefore fixes the
    Arabic and breaks any English inside it, turning "the Lessor" into
    "Lessor the".

    So: reverse the token sequence for an RTL base, then reverse each maximal
    run of LTR tokens back. Neutral tokens (a bare number, a lone bracket)
    inherit the direction of the run they sit inside, matching the UBA's
    treatment of neutrals.
    """
    n = len(tokens)
    if n < 2:
        return list(range(n))

    dirs = [_token_direction(t) for t in tokens]
    # Resolve neutrals to the surrounding direction; the paragraph direction
    # decides at the edges and where a neutral run separates opposite runs.
    resolved: list[str] = []
    for i, d in enumerate(dirs):
        if d != "N":
            resolved.append(d)
            continue
        prev = next((x for x in reversed(dirs[:i]) if x != "N"), None)
        nxt = next((x for x in dirs[i + 1:] if x != "N"), None)
        resolved.append(prev if prev is not None and prev == nxt else base_dir)

    order = list(range(n))
    if base_dir == "R":
        order.reverse()
        flip = "L"
    else:
        flip = "R"

    out: list[int] = []
    run: list[int] = []
    for idx in order:
        if resolved[idx] == flip:
            run.append(idx)
        else:
            if run:
                out.extend(reversed(run))
                run = []
            out.append(idx)
    if run:
        out.extend(reversed(run))
    return out


# ---------------------------------------------------------------------------
# Shared with scripts/audit_ground_truth.py
# ---------------------------------------------------------------------------


def reverse_line_words(text: str) -> str:
    """Reverse the word order of every line.

    The offline audit's coarse reversal, kept here so the audit script and the
    live pipeline cannot drift apart on what "reversed" means.
    """
    return "\n".join(" ".join(reversed(line.split())) for line in text.splitlines())


def mirror_neutrals(text: str) -> str:
    """Flip bracket-like characters. Exposed for tests and for callers that
    reorder tokens themselves and still need the neutrals corrected."""
    return "".join(_MIRROR.get(c, c) for c in text)
