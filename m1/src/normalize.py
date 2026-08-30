"""Arabic text normalization, one toggleable step at a time.

Runs after :mod:`src.rtl_fix` and before :mod:`src.chunking`, on output from
both the text-layer path and the OCR path.

WHY EVERY STEP IS A SEPARATE TOGGLE
===================================

Normalization trades precision for recall, and the right trade depends on the
corpus. Folding ``ة -> ه`` helps you find a clause when the typist was
careless; it also merges genuinely different legal terms. Which effect
dominates cannot be decided from public documents -- it depends on how the
firm's own documents were typed and scanned.

So each step is independently switchable in
:class:`~src.config.NormalizationConfig`, every step that fired is recorded in
``metadata.normalization_applied``, and the untouched source text is kept in
``metadata.raw_text``. When real firm documents arrive, A/B-ing a step is a
config flip and a re-run, not a code change, and the effect is measurable
because you still have the original.

Defaults are the conservative set. ``normalize_hamza`` and
``normalize_teh_marbuta`` are OFF by default because they are the two most
aggressive folds and the most likely to need corpus-specific evidence.

WHAT IS DELIBERATELY *NOT* NORMALIZED
=====================================

* **Stemming / lemmatization.** M1 emits text, not tokens. Morphological
  analysis is a retrieval concern and belongs to M2/M3, who need to apply the
  same analysis to the query side.
* **Stopword removal.** Destroys legal meaning (negation particles ``لا``,
  ``غير``, ``دون`` are load-bearing in contract clauses).
* **Spelling correction.** Would silently rewrite party names and defined terms.
"""

from __future__ import annotations

import re
import unicodedata

from .config import NormalizationConfig
from .document_chunk_schema import Language
from .structure_preservation import (
    ARABIC_INDIC_DIGITS,
    EXTENDED_ARABIC_INDIC_DIGITS,
    WESTERN_DIGITS,
    ExtractedDocument,
    TextBlock,
    detect_language,
)

# --- character tables ------------------------------------------------------

ALEF_VARIANTS = "أإآٱٲٳٵ"          # hamza-above/below, madda, wasla, and rarer forms
ALEF_PLAIN = "ا"

HAMZA_CARRIERS = {"ؤ": "و", "ئ": "ي", "ء": ""}

TEH_MARBUTA = "ة"
HEH = "ه"

ALEF_MAKSURA = "ى"
YEH = "ي"

TATWEEL = "ـ"

# Harakat / tashkeel, including the Quranic marks that occasionally survive OCR.
DIACRITICS = "".join(
    chr(c) for c in
    [*range(0x064B, 0x0660), 0x0670, *range(0x06D6, 0x06ED + 1), 0x0653, 0x0654, 0x0655]
)
_DIACRITIC_RE = re.compile(f"[{re.escape(DIACRITICS)}]")

# Lam-alef presentation ligatures -> two characters.
LIGATURES = {
    "ﻻ": "لا", "ﻼ": "لا",
    "ﻷ": "لأ", "ﻸ": "لأ",
    "ﻹ": "لإ", "ﻺ": "لإ",
    "ﻵ": "لآ", "ﻶ": "لآ",
}

# Punctuation variants seen in Egyptian legal documents and OCR output.
# Applied to text of any script -- these are unambiguous cleanups.
PUNCT_MAP = {
    "٪": "%",                                       # Arabic percent sign
    "“": '"', "”": '"', "„": '"',         # curly double quotes
    "«": '"', "»": '"',                        # guillemets
    "‘": "'", "’": "'",                        # curly single quotes
    "–": "-", "—": "-", "‑": "-", "−": "-",  # dashes
    "…": "...",                                     # ellipsis
}

# Applied only when the surrounding text is Arabic-dominant. A Latin comma
# inside an Arabic clause is nearly always a mis-typed ، -- but inside an
# English clause it is simply a comma, and rewriting it would corrupt the
# English half of a bilingual contract.
ARABIC_ONLY_PUNCT_MAP = {
    ",": "،",   # ARABIC COMMA
    ";": "؛",   # ARABIC SEMICOLON
    "?": "؟",   # ARABIC QUESTION MARK
}

# Whitespace lookalikes that survive extraction and break tokenizers.
_SPACE_LIKE = (
    " "  # no-break space
    "            "
    "  　"  # narrow/medium/ideographic spaces
)
_ZERO_WIDTH = "​‌‍﻿"  # ZWSP, ZWNJ, ZWJ, BOM

_TO_WESTERN = {
    **{ord(a): w for a, w in zip(ARABIC_INDIC_DIGITS, WESTERN_DIGITS)},
    **{ord(a): w for a, w in zip(EXTENDED_ARABIC_INDIC_DIGITS, WESTERN_DIGITS)},
}
_TO_ARABIC = {ord(w): a for w, a in zip(WESTERN_DIGITS, ARABIC_INDIC_DIGITS)}


def pyarabic_available() -> bool:
    try:
        import pyarabic.araby  # noqa: F401

        return True
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# Individual steps. Each takes and returns str, and is independently testable.
# ---------------------------------------------------------------------------


def step_strip_presentation_forms(text: str) -> str:
    """Fold Arabic Presentation Forms A/B to base letters via NFKC.

    OCR engines and old DTP-produced PDFs emit contextual glyph codepoints.
    Two visually identical strings that differ only in presentation form will
    not compare equal and will not retrieve each other -- so this runs first,
    before any other step inspects letters.
    """
    return unicodedata.normalize("NFKC", text)


def step_normalize_ligatures(text: str) -> str:
    """Decompose lam-alef ligatures. Uses pyarabic when available."""
    try:
        from pyarabic import araby

        text = araby.normalize_ligature(text)
    except Exception:  # noqa: BLE001
        pass
    for lig, repl in LIGATURES.items():
        text = text.replace(lig, repl)
    return text


def step_strip_diacritics(text: str) -> str:
    """Remove harakat/tashkeel. pyarabic's ``strip_tashkeel`` plus a regex
    sweep for the marks it does not cover."""
    try:
        from pyarabic import araby

        text = araby.strip_tashkeel(text)
    except Exception:  # noqa: BLE001
        pass
    return _DIACRITIC_RE.sub("", text)


def step_strip_tatweel(text: str) -> str:
    """Remove kashida/tatweel -- justification glyphs with no phonetic value."""
    try:
        from pyarabic import araby

        return araby.strip_tatweel(text)
    except Exception:  # noqa: BLE001
        return text.replace(TATWEEL, "")


def step_normalize_alef(text: str) -> str:
    """Fold أ إ آ ٱ -> ا.

    Standard for Arabic IR. Egyptian legal typing is wildly inconsistent about
    hamza-on-alef, and OCR is worse, so this is the single highest-value fold.
    """
    return text.translate({ord(c): ALEF_PLAIN for c in ALEF_VARIANTS})


def step_normalize_hamza(text: str) -> str:
    """Fold hamza carriers: ؤ -> و, ئ -> ي, and drop bare ء.

    OFF by default. More aggressive than alef folding: it changes the spelling
    of ordinary legal vocabulary (مسؤولية, هيئة), so it should be A/B tested
    against real documents before being switched on.
    """
    try:
        from pyarabic import araby

        text = araby.normalize_hamza(text)
    except Exception:  # noqa: BLE001
        pass
    return text.translate({ord(k): v for k, v in HAMZA_CARRIERS.items()})


def step_normalize_teh_marbuta(text: str) -> str:
    """Fold ة -> ه. OFF by default; it merges words that legal Arabic
    distinguishes."""
    return text.replace(TEH_MARBUTA, HEH)


def step_normalize_alef_maksura(text: str) -> str:
    """Fold word-final ى -> ي.

    Restricted to word-final position on purpose: ى only occurs word-finally in
    correct orthography, so an interior ى is an OCR error and folding it would
    hide that error rather than fix it.
    """
    return re.sub(f"{ALEF_MAKSURA}(?=\\s|$|[^\\w])", YEH, text)


def step_normalize_punctuation(text: str, arabic_context: bool | None = None) -> str:
    """Canonicalize punctuation variants and collapse dot leaders.

    ``arabic_context`` controls whether the Arabic-only substitutions
    (``, ; ?`` -> ``، ؛ ؟``) are applied. When ``None`` it is decided from the
    text itself. Passing ``False`` for an English block keeps English
    punctuation intact -- important for bilingual contracts.

    Dot leaders (``......``) are how blanks are drawn in Egyptian form
    contracts. Collapsing them to a short marker keeps the "this is a blank"
    signal for M5 without flooding the token stream.
    """
    for src, dst in PUNCT_MAP.items():
        text = text.replace(src, dst)

    if arabic_context is None:
        arabic_context = detect_language(text) in (Language.AR, Language.AR_EN)
    if arabic_context:
        for src, dst in ARABIC_ONLY_PUNCT_MAP.items():
            text = text.replace(src, dst)

    text = re.sub(r"[.․۔]{4,}", "....", text)
    text = re.sub(r"[_\-]{4,}", "____", text)
    return text


def step_normalize_digits(text: str, mode: str) -> str:
    if mode == "to_western":
        return text.translate(_TO_WESTERN)
    if mode == "to_arabic":
        return text.translate(_TO_ARABIC)
    return text


def step_collapse_whitespace(text: str) -> str:
    """Collapse runs of spaces/tabs, trim line ends, cap blank-line runs at one.

    Paragraph breaks are preserved because :mod:`src.chunking` uses them as
    fallback boundaries when no structural marker is present.
    """
    text = text.translate({ord(c): " " for c in _SPACE_LIKE})
    text = text.translate({ord(c): None for c in _ZERO_WIDTH})
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

# (config attribute, step name, callable). Order matters: presentation forms
# and ligatures must be folded before letter-level rules inspect the text, and
# whitespace collapse must come last.
_STEPS = [
    ("strip_presentation_forms", "strip_presentation_forms", step_strip_presentation_forms),
    ("normalize_ligatures", "normalize_ligatures", step_normalize_ligatures),
    ("strip_diacritics", "strip_diacritics", step_strip_diacritics),
    ("strip_tatweel", "strip_tatweel", step_strip_tatweel),
    ("normalize_alef", "normalize_alef", step_normalize_alef),
    ("normalize_hamza", "normalize_hamza", step_normalize_hamza),
    ("normalize_teh_marbuta", "normalize_teh_marbuta", step_normalize_teh_marbuta),
    ("normalize_alef_maksura", "normalize_alef_maksura", step_normalize_alef_maksura),
    ("normalize_punctuation", "normalize_punctuation", step_normalize_punctuation),
]


def normalize_text(text: str, cfg: NormalizationConfig) -> tuple[str, list[str]]:
    """Apply the enabled normalization steps.

    Returns ``(normalized_text, steps_that_changed_something)``. Only steps
    that actually altered the text are reported, so
    ``metadata.normalization_applied`` describes what happened to *this* chunk
    rather than what was merely switched on.

    >>> cfg = NormalizationConfig()
    >>> out, steps = normalize_text("المادة ١٢ : الإنهــاء", cfg)
    >>> "12" in out and "ـ" not in out
    True
    """
    if not cfg.enabled or not text:
        return text, []

    applied: list[str] = []
    for attr, name, fn in _STEPS:
        if not getattr(cfg, attr, False):
            continue
        new = fn(text)
        if new != text:
            applied.append(name)
            text = new

    if cfg.normalize_digits != "none":
        new = step_normalize_digits(text, cfg.normalize_digits)
        if new != text:
            applied.append(f"normalize_digits:{cfg.normalize_digits}")
            text = new

    if cfg.collapse_whitespace:
        new = step_collapse_whitespace(text)
        if new != text:
            applied.append("collapse_whitespace")
            text = new

    return text, applied


def _normalize_latin_only(text: str, cfg: NormalizationConfig) -> tuple[str, list[str]]:
    """Script-neutral cleanups for a Latin-only block.

    The Arabic letter rules are skipped (they are no-ops on Latin text) and
    ``, ; ?`` are left alone, so English clauses in a bilingual contract keep
    English punctuation.
    """
    applied: list[str] = []
    for name, fn in (
        ("normalize_punctuation",
         (lambda t: step_normalize_punctuation(t, arabic_context=False))
         if cfg.normalize_punctuation else None),
        (f"normalize_digits:{cfg.normalize_digits}",
         (lambda t: step_normalize_digits(t, cfg.normalize_digits))
         if cfg.normalize_digits != "none" else None),
        ("collapse_whitespace",
         step_collapse_whitespace if cfg.collapse_whitespace else None),
    ):
        if fn is None:
            continue
        new = fn(text)
        if new != text:
            applied.append(name)
            text = new
    return text, applied


def normalize_block(block: TextBlock, cfg: NormalizationConfig) -> TextBlock:
    """Normalize one block in place.

    Latin-only blocks skip the Arabic letter rules entirely (they would be
    no-ops) but still get punctuation and whitespace treatment, so an English
    clause in a bilingual contract is cleaned consistently with its Arabic
    neighbours.
    """
    if not cfg.enabled or block.is_empty():
        return block
    if block.raw_text is None:
        block.raw_text = block.text

    lang = detect_language(block.text)
    if lang is Language.EN:
        text, applied = _normalize_latin_only(block.text, cfg)
    else:
        text, applied = normalize_text(block.text, cfg)

    block.text = text
    block.normalization_applied = applied
    return block


def apply_normalization(doc: ExtractedDocument, cfg: NormalizationConfig) -> ExtractedDocument:
    """Normalize every block and table cell in the document."""
    if not cfg.enabled:
        return doc

    changed = 0
    for page in doc.pages:
        for block in page.blocks:
            before = block.text
            normalize_block(block, cfg)
            if block.text != before:
                changed += 1
        for table in page.tables:
            table.rows = [
                [normalize_text(cell, cfg)[0] if cell else cell for cell in row]
                for row in table.rows
            ]

    doc.log_engine(None, "normalize", blocks_changed=changed,
                   pyarabic=pyarabic_available())
    if not pyarabic_available():
        doc.warnings.append(
            "pyarabic not importable; normalization ran on built-in tables only "
            "(equivalent for the enabled steps, but flagged for transparency)"
        )
    return doc
