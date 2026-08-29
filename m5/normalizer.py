from __future__ import annotations

import re
import unicodedata


_ARABIC_DIACRITICS = re.compile(
    r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]"
)

_WHITESPACE = re.compile(r"\s+")

_ARABIC = re.compile(r"[\u0600-\u06FF]")

_LATIN = re.compile(r"[A-Za-z]")


def normalize_text(text: str) -> str:
    """
    Conservative normalization used by M5.

    The original legal text must remain unchanged and should be
    preserved separately as evidence.
    """

    if not text:
        return ""

    value = unicodedata.normalize(
        "NFKC",
        text,
    )

    # Remove Arabic tashkeel/diacritics.
    value = _ARABIC_DIACRITICS.sub(
        "",
        value,
    )

    # Remove Arabic tatweel.
    value = value.replace(
        "\u0640",
        "",
    )

    # Normalize whitespace.
    value = _WHITESPACE.sub(
        " ",
        value,
    ).strip()

    return value


def detect_language(text: str) -> str:
    """
    Detect the script category used by the text.

    Returns:
        ar
        en
        ar-en
        unknown
    """

    if not text or not text.strip():
        return "unknown"

    arabic_count = len(
        _ARABIC.findall(text)
    )

    latin_count = len(
        _LATIN.findall(text)
    )

    if arabic_count and latin_count:
        return "ar-en"

    if arabic_count:
        return "ar"

    if latin_count:
        return "en"

    return "unknown"


def normalize_for_match(text: str) -> str:
    """
    Create a normalized representation for matching and comparison.

    This output must NOT replace the original legal text.

    Legal identifiers, numbers, dots, and hyphens are preserved.
    """

    value = normalize_text(
        text
    ).lower()

    # Keep:
    #   - words
    #   - whitespace
    #   - Arabic characters
    #   - dots
    #   - hyphens
    #
    # Other punctuation is replaced with spaces.
    value = re.sub(
        r"[^\w\s\u0600-\u06FF.-]",
        " ",
        value,
    )

    return _WHITESPACE.sub(
        " ",
        value,
    ).strip()