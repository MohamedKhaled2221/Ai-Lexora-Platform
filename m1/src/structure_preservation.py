"""Structure preservation: the intermediate representation + legal marker detection.

Two jobs:

1. **The IR.** Every extraction path (PyMuPDF/Docling, PaddleOCR, Tesseract,
   python-docx, plaintext) produces the *same* :class:`ExtractedDocument`. RTL
   repair, normalization, chunking and metadata extraction then operate on that
   one shape, so adding an extractor never touches downstream code.

2. **Legal structure detection.** Recognizing Arabic and English clause /
   article / section markers, so chunking can split on real legal boundaries
   rather than character counts (spec: "chunk by clause/section boundaries, not
   blind splitting").

The spec names page numbers, sections, headings, clauses, tables and bounding
boxes as elements that must survive extraction. Every one of them has a home on
:class:`TextBlock` / :class:`ExtractedPage` and is carried through to
``DocumentChunk.metadata``.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Iterable, Literal

from .document_chunk_schema import (
    BlockType,
    BoundingBox,
    DocumentType,
    Language,
    OCRConfidence,
    RTLFlag,
    SourceEngine,
    StructuralRef,
)

# ---------------------------------------------------------------------------
# Character classes
# ---------------------------------------------------------------------------

ARABIC_INDIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
EXTENDED_ARABIC_INDIC_DIGITS = "۰۱۲۳۴۵۶۷۸۹"  # Persian/Urdu forms, seen in scans
WESTERN_DIGITS = "0123456789"

_DIGIT_MAP = {
    **{ord(a): w for a, w in zip(ARABIC_INDIC_DIGITS, WESTERN_DIGITS)},
    **{ord(a): w for a, w in zip(EXTENDED_ARABIC_INDIC_DIGITS, WESTERN_DIGITS)},
}

# Any digit, either script -- used inside marker patterns.
ANY_DIGIT = f"0-9{ARABIC_INDIC_DIGITS}{EXTENDED_ARABIC_INDIC_DIGITS}"

_ARABIC_RANGES = (
    (0x0600, 0x06FF),  # Arabic
    (0x0750, 0x077F),  # Arabic Supplement
    (0x08A0, 0x08FF),  # Arabic Extended-A
    (0xFB50, 0xFDFF),  # Presentation Forms-A
    (0xFE70, 0xFEFF),  # Presentation Forms-B
)


def to_western_digits(s: str) -> str:
    """Fold Arabic-Indic and extended Arabic-Indic digits to 0-9."""
    return s.translate(_DIGIT_MAP)


def is_arabic_char(ch: str) -> bool:
    cp = ord(ch)
    return any(lo <= cp <= hi for lo, hi in _ARABIC_RANGES)


def is_latin_char(ch: str) -> bool:
    return ("a" <= ch <= "z") or ("A" <= ch <= "Z") or (
        0x00C0 <= ord(ch) <= 0x024F
    )


def script_profile(text: str) -> dict[str, int]:
    """Count characters by script. Basis for language detection and for the
    mixed-direction heuristics in :mod:`src.rtl_fix`."""
    counts = {"arabic": 0, "latin": 0, "digit": 0, "other": 0, "total": 0}
    for ch in text:
        if ch.isspace():
            continue
        counts["total"] += 1
        if is_arabic_char(ch):
            counts["arabic"] += 1
        elif is_latin_char(ch):
            counts["latin"] += 1
        elif ch.isdigit() or ch in ARABIC_INDIC_DIGITS or ch in EXTENDED_ARABIC_INDIC_DIGITS:
            counts["digit"] += 1
        else:
            counts["other"] += 1
    return counts


def detect_language(text: str, mixed_threshold: float = 0.15) -> Language:
    """Classify a span as ``ar`` / ``en`` / ``ar-en`` / ``unknown``.

    ``ar-en`` requires the minority script to hold at least ``mixed_threshold``
    of the *letter* mass -- a single English defined term inside an Arabic
    clause should stay ``ar``, but a genuinely bilingual clause becomes
    ``ar-en``. Digits and punctuation are excluded from the denominator because
    Egyptian legal text is dense with numbers in both scripts.

    ``mixed_threshold`` keeps its name: it is the script-mixing *ratio* that
    decides the call, not the label that comes out of it.
    """
    p = script_profile(text)
    letters = p["arabic"] + p["latin"]
    if letters < 3:
        return Language.UNKNOWN
    ar_ratio = p["arabic"] / letters
    if ar_ratio >= 1 - mixed_threshold:
        return Language.AR
    if ar_ratio <= mixed_threshold:
        return Language.EN
    return Language.AR_EN


# ---------------------------------------------------------------------------
# Legal structural markers
# ---------------------------------------------------------------------------


class StructLevel(IntEnum):
    """Hierarchy depth. Lower number = more senior heading.

    Egyptian statutes nest كتاب > باب > فصل > مادة > بند. Contracts usually
    only use section > clause > sub-clause. Both map onto this ladder so one
    chunker handles both.
    """

    BOOK = 1        # الكتاب / الباب  |  Part / Book
    CHAPTER = 2     # الفصل           |  Chapter
    SECTION = 3     # القسم / heading |  Section / Schedule / Annex
    ARTICLE = 4     # المادة          |  Article
    CLAUSE = 5      # البند / 1.1     |  Clause
    SUBCLAUSE = 6   # (أ) / (a) / (i) |  Sub-clause
    PARAGRAPH = 9   # no marker


@dataclass
class StructuralMarker:
    """A detected legal boundary at the head of a line."""

    level: StructLevel
    kind: str                     # "article" | "clause" | "section" | ...
    label: str                    # human label, e.g. "المادة 12" / "Article 12"
    number: str | None            # normalized number, e.g. "12" / "12.3" / "a"
    language: Literal["ar", "en"]
    raw: str                      # the matched marker text as it appeared
    match_end: int                # offset in the line where the marker ends
    title: str | None = None      # trailing title on the same line, if any

    # --- tolerant matching provenance (see src/fuzzy_markers.py) -------------
    fuzzy: bool = False
    """True when the exact patterns missed and tolerant matching recovered this
    marker. Surfaced on the chunk so a fuzzy match is monitorable rather than
    silently equivalent to a clean one."""
    match_confidence: float = 1.0
    """1.0 for an exact match; lower when the marker word or its digits had to
    be repaired."""
    match_evidence: str | None = None
    """What the tolerant matcher had to do, in words, for spot-checking."""


# Arabic ordinal words used instead of digits: "الباب الأول", "أولاً".
_AR_ORDINALS = {
    "الأول": "1", "الاول": "1", "أولا": "1", "أولاً": "1", "اولا": "1", "اولاً": "1",
    "الثاني": "2", "ثانيا": "2", "ثانياً": "2",
    "الثالث": "3", "ثالثا": "3", "ثالثاً": "3",
    "الرابع": "4", "رابعا": "4", "رابعاً": "4",
    "الخامس": "5", "خامسا": "5", "خامساً": "5",
    "السادس": "6", "سادسا": "6", "سادساً": "6",
    "السابع": "7", "سابعا": "7", "سابعاً": "7",
    "الثامن": "8", "ثامنا": "8", "ثامناً": "8",
    "التاسع": "9", "تاسعا": "9", "تاسعاً": "9",
    "العاشر": "10", "عاشرا": "10", "عاشراً": "10",
    "الحادي عشر": "11", "الثاني عشر": "12", "الثالث عشر": "13",
    "الرابع عشر": "14", "الخامس عشر": "15",
}
_AR_ORD_ALT = "|".join(sorted(map(re.escape, _AR_ORDINALS), key=len, reverse=True))

# Arabic letter enumerators used for sub-clauses: (أ) (ب) (ج) (د) (هـ) (و) (ز)
_AR_LETTERS = "أابتثجحخدذرزسشصضطظعغفقكلمنهوي" + "ـ"

_NUM = f"[{ANY_DIGIT}]+(?:\\s*[-/.]\\s*[{ANY_DIGIT}]+)*"

# Each entry: (compiled regex, level, kind, language). Anchored at line start.
# Order matters -- more specific patterns first.
_MARKER_PATTERNS: list[tuple[re.Pattern, StructLevel, str, str]] = [
    # ---------------- Arabic ----------------
    (re.compile(rf"^\s*(?:ال)?كتاب\s+(?P<num>{_AR_ORD_ALT}|{_NUM})\b[\s:\-–—]*(?P<title>.*)$"),
     StructLevel.BOOK, "book", "ar"),
    (re.compile(rf"^\s*(?:ال)?باب\s+(?:ال)?(?P<num>{_AR_ORD_ALT}|{_NUM})\b[\s:\-–—]*(?P<title>.*)$"),
     StructLevel.BOOK, "book", "ar"),
    (re.compile(rf"^\s*(?:ال)?فصل\s+(?:ال)?(?P<num>{_AR_ORD_ALT}|{_NUM})\b[\s:\-–—]*(?P<title>.*)$"),
     StructLevel.CHAPTER, "chapter", "ar"),
    (re.compile(rf"^\s*(?:ال)?قسم\s+(?:ال)?(?P<num>{_AR_ORD_ALT}|{_NUM})\b[\s:\-–—]*(?P<title>.*)$"),
     StructLevel.SECTION, "section", "ar"),
    # المادة (12) / المادة ١٢ / مادة 12 مكرر
    (re.compile(
        rf"^\s*(?:ال)?ماد(?:ة|ه)\s*[\(\[]?\s*(?P<num>{_NUM}|{_AR_ORD_ALT})\s*[\)\]]?"
        rf"\s*(?P<bis>مكرر[\sاً]*(?:[{ANY_DIGIT}]+)?)?[\s:\-–—.]*(?P<title>.*)$"),
     StructLevel.ARTICLE, "article", "ar"),
    (re.compile(rf"^\s*(?:ال)?بند\s*[\(\[]?\s*(?P<num>{_NUM}|{_AR_ORD_ALT})\s*[\)\]]?[\s:\-–—.]*(?P<title>.*)$"),
     StructLevel.CLAUSE, "clause", "ar"),
    (re.compile(rf"^\s*(?:ال)?فقر(?:ة|ه)\s*[\(\[]?\s*(?P<num>{_NUM}|{_AR_ORD_ALT})\s*[\)\]]?[\s:\-–—.]*(?P<title>.*)$"),
     StructLevel.CLAUSE, "clause", "ar"),
    # Standalone ordinal enumerator: "أولاً:" / "ثانيا -"
    (re.compile(rf"^\s*(?P<num>{_AR_ORD_ALT})\s*[:：\-–—.]\s*(?P<title>.*)$"),
     StructLevel.CLAUSE, "clause", "ar"),
    # Arabic letter sub-clause: (أ) / أ-
    (re.compile(rf"^\s*[\(\[]\s*(?P<num>[{_AR_LETTERS}]{{1,2}})\s*[\)\]][\s:\-–—.]*(?P<title>.*)$"),
     StructLevel.SUBCLAUSE, "subclause", "ar"),

    # ---------------- English ----------------
    (re.compile(r"^\s*(?:PART|Part|BOOK|Book)\s+(?P<num>[IVXLC]+|\d+|[A-Z])\b[\s:\-–—]*(?P<title>.*)$"),
     StructLevel.BOOK, "book", "en"),
    (re.compile(r"^\s*(?:CHAPTER|Chapter)\s+(?P<num>[IVXLC]+|\d+)\b[\s:\-–—]*(?P<title>.*)$"),
     StructLevel.CHAPTER, "chapter", "en"),
    (re.compile(r"^\s*(?:SCHEDULE|Schedule|ANNEX|Annex|APPENDIX|Appendix|EXHIBIT|Exhibit)"
                r"\s+(?P<num>[IVXLC]+|\d+|[A-Z])\b[\s:\-–—]*(?P<title>.*)$"),
     StructLevel.SECTION, "annex", "en"),
    (re.compile(r"^\s*(?:SECTION|Section)\s+(?P<num>\d+(?:\.\d+)*|[IVXLC]+)\b[\s:\-–—.]*(?P<title>.*)$"),
     StructLevel.SECTION, "section", "en"),
    (re.compile(r"^\s*(?:ARTICLE|Article|ART\.)\s+(?P<num>\d+(?:\.\d+)*|[IVXLC]+)\b[\s:\-–—.]*(?P<title>.*)$"),
     StructLevel.ARTICLE, "article", "en"),
    (re.compile(r"^\s*(?:CLAUSE|Clause)\s+(?P<num>\d+(?:\.\d+)*)\b[\s:\-–—.]*(?P<title>.*)$"),
     StructLevel.CLAUSE, "clause", "en"),
    # Decimal outline: "12.3 Termination." -- 2+ components so a sentence
    # starting "1. " is not mistaken for a clause when it is a list item.
    #
    # The trailing alphabetic components cover the deep style Egyptian
    # commercial drafting uses once a clause has sub-sub-obligations:
    # "5.2.1.a", "5.2.1.b.ii". Without them the numeric prefix still matched but
    # the letter suffix was read as the start of the *title*, so every sibling
    # of 5.2.1 collapsed onto the same clause id and the sub-levels vanished.
    # Lowercase only, so "1.2.Section" stays unmatched.
    (re.compile(r"^\s*(?P<num>\d+(?:\.\d+){1,3}(?:\.[a-z]{1,4}){0,2})\.?\s+(?P<title>\S.*)$"),
     StructLevel.CLAUSE, "clause", "en"),
    # Top-level numbered clause: "12. Termination"
    (re.compile(r"^\s*(?P<num>\d{1,3})[\.\)]\s+(?P<title>\S.*)$"),
     StructLevel.CLAUSE, "clause", "en"),
    # "(a)" / "(iv)"
    (re.compile(r"^\s*\(\s*(?P<num>[a-z]{1,2}|[ivxlc]{1,4})\s*\)[\s:\-–—.]*(?P<title>.*)$"),
     StructLevel.SUBCLAUSE, "subclause", "en"),
]

# Headings that carry no number at all but are unmistakably structural.
_UNNUMBERED_HEADINGS = {
    "en": [
        "recitals", "definitions", "interpretation", "whereas",
        "termination", "governing law", "dispute resolution", "confidentiality",
        "force majeure", "indemnity", "indemnification", "warranties",
        "representations", "notices", "assignment", "entire agreement",
        "severability", "counterparts", "signatures", "preamble", "witnesseth",
    ],
    "ar": [
        "تمهيد", "ديباجة", "التعريفات", "تعريفات", "مقدمة",
        "الإنهاء", "انهاء العقد", "إنهاء العقد", "القانون الواجب التطبيق",
        "تسوية المنازعات", "فض المنازعات", "السرية", "القوة القاهرة",
        "التعويض", "الضمانات", "الإقرارات", "الإخطارات", "التنازل",
        "الاتفاق الكامل", "قابلية الفصل", "التوقيعات", "الشروط العامة",
        "حيثيات", "الحيثيات", "منطوق الحكم", "المنطوق", "الوقائع", "الأسباب",
    ],
}


def _normalize_number(num: str | None, language: str) -> str | None:
    if not num:
        return None
    num = num.strip()
    if language == "ar" and num in _AR_ORDINALS:
        return _AR_ORDINALS[num]
    num = to_western_digits(num)
    return re.sub(r"\s*([-/.])\s*", r"\1", num).strip(" .:-")


def detect_marker(line: str, allow_fuzzy: bool = True) -> StructuralMarker | None:
    """Detect a legal structural marker at the start of ``line``.

    Returns ``None`` for ordinary prose. Only the *head* of the line is
    considered: an "Article 5" reference buried mid-sentence is a cross
    reference, not a boundary, and must not trigger a split.

    Exact patterns run first and unchanged. Only when every one of them has
    missed does :mod:`src.fuzzy_markers` get a turn, rewriting a damaged marker
    word or a split number back into canonical form and re-running the same
    patterns over the result. A clean document therefore never touches the
    tolerant path at all, and there is still exactly one definition of what a
    marker is.

    ``allow_fuzzy=False`` gives the strict behaviour, which the tolerant layer's
    own tests use as their baseline.
    """
    marker = _detect_exact(line)
    if not allow_fuzzy:
        return marker

    from .fuzzy_markers import repair_marker_line

    hit = repair_marker_line(line)
    if hit is None:
        return marker

    repaired = _detect_exact(hit.repaired_line)
    if repaired is None:
        return marker

    if marker is not None:
        # The strict patterns already matched. The tolerant layer only wins here
        # when the number was split -- "المادة 1 2" matches strictly and yields
        # article *1*, quietly dropping the second digit and folding article
        # 12's text into article 1's chunk. A longer number from the repaired
        # line is that case; anything else, the strict reading stands.
        strict_num = marker.number or ""
        if not (hit.digits_joined and len(repaired.number or "") > len(strict_num)):
            return marker

    repaired.fuzzy = True
    repaired.match_confidence = hit.confidence
    repaired.match_evidence = hit.describe()
    # ``raw`` keeps what was actually on the page rather than what it was
    # matched to, so the flag can be checked against the source without
    # re-running anything.
    repaired.raw = line.strip()[: len(repaired.raw) + 4].strip()
    return repaired


def _detect_exact(line: str) -> StructuralMarker | None:
    """The strict, regex-only marker detector. Unchanged behaviour."""
    stripped = line.strip()
    if not stripped or len(stripped) > 300:
        # Very long lines are body text; a heading that long is not a heading.
        return None

    for pattern, level, kind, lang in _MARKER_PATTERNS:
        m = pattern.match(stripped)
        if not m:
            continue
        raw = m.group(0)[: m.end("num")] if "num" in m.groupdict() else m.group(0)
        number = _normalize_number(m.groupdict().get("num"), lang)
        title = (m.groupdict().get("title") or "").strip() or None
        bis = (m.groupdict().get("bis") or "").strip()

        # ``label`` is the *identifier only* ("المادة 12", "Clause 1.2"). The
        # heading text lives in ``title``. Keeping them apart matters because
        # the label is what a lawyer cites and what chunk grouping keys on,
        # while the title is what makes a chunk human-readable -- and a label
        # with a whole sentence glued to it is useless for both.
        label = _build_label(kind, number, lang, bis)
        if bis:
            number = f"{number} مكرر" if number else number
        return StructuralMarker(
            level=level,
            kind=kind,
            label=label,
            number=number,
            language=lang,  # type: ignore[arg-type]
            raw=raw.strip(),
            match_end=m.end("num") if "num" in m.groupdict() else m.end(),
            title=title,
        )

    # Unnumbered but well-known headings.
    probe = stripped.lower().strip(" :.-–—،")
    for lang, names in _UNNUMBERED_HEADINGS.items():
        if probe in names and len(stripped) <= 80:
            return StructuralMarker(
                level=StructLevel.SECTION,
                kind="section",
                label=stripped.strip(" :.-–—،"),
                number=None,
                language=lang,  # type: ignore[arg-type]
                raw=stripped,
                match_end=len(stripped),
                title=stripped.strip(" :.-–—،"),
            )
    return None


def _build_label(kind: str, number: str | None, lang: str, bis: str = "") -> str:
    ar_names = {
        "book": "الباب", "chapter": "الفصل", "section": "القسم",
        "article": "المادة", "clause": "البند", "subclause": "بند فرعي",
    }
    en_names = {
        "book": "Part", "chapter": "Chapter", "section": "Section",
        "article": "Article", "clause": "Clause", "subclause": "Sub-clause",
        "annex": "Annex",
    }
    name = (ar_names if lang == "ar" else en_names).get(kind, kind.title())
    label = f"{name} {number}".strip() if number else name
    return f"{label} {bis}".strip() if bis else label


def looks_like_heading(text: str, bbox: BoundingBox | None = None,
                       font_size: float | None = None,
                       body_font_size: float | None = None,
                       is_bold: bool = False) -> bool:
    """Typographic heading heuristic, used when no textual marker matched.

    Combines shortness with visual prominence (larger or bold font). Kept
    separate from :func:`detect_marker` because it is much less reliable --
    chunking treats a typographic heading as a weaker boundary than a numbered
    article.
    """
    t = text.strip()
    if not t or len(t) > 120 or "\n" in t:
        return False
    if t.endswith((".", "،", "؛", ";")):
        return False
    # Wholly bracketed lines are editorial notes, watermarks and "[DRAFT]"
    # stamps, not headings. Without this, a centred bold note becomes a section
    # and every following chunk inherits it as its section label.
    if (t.startswith("[") and t.endswith("]")) or (t.startswith("(") and t.endswith(")")):
        return False
    bigger = (
        font_size is not None
        and body_font_size is not None
        and font_size >= body_font_size * 1.15
    )
    if bigger or is_bold:
        return True
    # ALL CAPS short line, Latin only.
    letters = [c for c in t if c.isalpha()]
    if letters and all(is_latin_char(c) for c in letters) and t.upper() == t and len(t) < 80:
        return True
    return False


# ---------------------------------------------------------------------------
# Document-level inference
# ---------------------------------------------------------------------------

_DOC_TYPE_CUES: list[tuple[DocumentType, list[str], int]] = [
    # NOTE: "باسم الشعب" is deliberately absent -- Egyptian *statutes* and
    # *judgments* both open with it, so it discriminates nothing and previously
    # pulled statutes into COURT_RULING.
    (DocumentType.COURT_RULING,
     ["محكمة النقض", "محكمة الاستئناف", "المحكمة الابتدائية",
      "حكم المحكمة", "منطوق الحكم", "حيثيات الحكم", "الدائرة المدنية",
      "بعد سماع المرافعة", "المحكمة بعد الاطلاع على الأوراق",
      "judgment of the court", "the court hereby rules", "cassation"], 3),
    (DocumentType.LAW,
     ["الجريدة الرسمية", "قرار رئيس الجمهورية", "قانون رقم", "لائحة تنفيذية",
      "مرسوم بقانون", "بعد الاطلاع على الدستور", "أصدرنا القانون الآتي نصه",
      "قرر مجلس النواب", "يعمل بأحكام القانون المرفق", "الباب الأول",
      # Constitutions are statutory instruments for our purposes -- they are
      # cited by article like any other law, and M2/M3 route them the same way.
      "دستور", "الدستور", "الجمهورية العربية", "نظام الحكم",
      "official gazette", "law no.", "decree",
      "constitution", "constitutional declaration"], 3),
    (DocumentType.CORRESPONDENCE,
     ["مذكرة داخلية", "إلى:", "من:", "الموضوع:", "نوصي بـ", "نوصي ب",
      "internal memorandum", "memorandum to", "we recommend", "re:", "subject:"], 2),
    (DocumentType.POWER_OF_ATTORNEY,
     ["توكيل رسمي", "توكيل عام", "توكيل خاص", "وكل الموكل",
      "power of attorney", "hereby appoints as attorney"], 3),
    (DocumentType.PLEADING,
     ["مذكرة دفاع", "صحيفة دعوى", "لائحة اعتراض", "الطاعن", "المطعون ضده",
      "statement of claim", "memorandum of defence"], 2),
    (DocumentType.CONTRACT,
     ["عقد", "اتفاقية", "الطرف الأول", "الطرف الثاني", "الفريق الأول",
      "أبرم هذا العقد", "بنود العقد", "agreement", "contract", "this agreement",
      "party of the first part", "the parties hereto", "whereas"], 1),
]

_JURISDICTION_CUES: list[tuple[str, list[str]]] = [
    ("Egypt",
     ["جمهورية مصر العربية", "مصر", "القاهرة", "طنطا", "الإسكندرية",
      "محكمة النقض المصرية", "القانون المدني المصري", "الجريدة الرسمية",
      "egypt", "egyptian", "cairo", "tanta", "alexandria", "arab republic of egypt"]),
    ("Saudi Arabia", ["المملكة العربية السعودية", "الرياض", "saudi arabia", "riyadh"]),
    ("UAE", ["الإمارات العربية المتحدة", "دبي", "أبوظبي", "united arab emirates", "dubai"]),
]


def infer_document_type(text: str) -> tuple[DocumentType, float]:
    """Heuristic document classification from lexical cues.

    Returns ``(type, confidence)`` where confidence is a crude 0-1 score.

    CAVEAT: tuned on public Egyptian legal documents and synthetic fixtures
    only. It has never seen a document from the firm. Expect to retune the cue
    lists once real samples arrive -- that is the intended change, not a rewrite.
    """
    probe = text[:6000].lower()
    # Also match against a space-stripped copy. Arabic PDFs routinely extract
    # with spurious intra-word spacing ("دس تور" for "دستور", "ا ن ش اء" for
    # "انشاء") when the producer positioned glyphs individually. A cue list
    # matched only against the spaced text misses those documents entirely --
    # which is how a national constitution was classifying as `unknown`.
    squeezed = re.sub(r"\s+", "", probe)

    scores: dict[DocumentType, int] = {}
    for dtype, cues, weight in _DOC_TYPE_CUES:
        hits = 0
        for cue in cues:
            low = cue.lower()
            if low in probe or re.sub(r"\s+", "", low) in squeezed:
                hits += 1
        if hits:
            scores[dtype] = scores.get(dtype, 0) + hits * weight
    if not scores:
        return DocumentType.UNKNOWN, 0.0
    best = max(scores, key=lambda k: scores[k])
    total = sum(scores.values())
    return best, round(scores[best] / total, 3)


def infer_jurisdiction(text: str, default: str | None = None) -> str | None:
    probe = text[:8000].lower()
    squeezed = re.sub(r"\s+", "", probe)   # see infer_document_type
    for name, cues in _JURISDICTION_CUES:
        for cue in cues:
            low = cue.lower()
            if low in probe or re.sub(r"\s+", "", low) in squeezed:
                return name
    return default


# ---------------------------------------------------------------------------
# Intermediate representation
# ---------------------------------------------------------------------------


@dataclass
class TextBlock:
    """One layout block: a paragraph, heading, list item, or table cell run.

    Carries everything the spec requires to survive extraction: page number,
    bounding box, block type, and (once :func:`annotate_structure` has run) the
    structural marker that governs it.
    """

    text: str
    page: int | None = None
    bbox: BoundingBox | None = None
    block_type: BlockType = BlockType.PARAGRAPH
    source_engine: SourceEngine = SourceEngine.UNKNOWN

    font_size: float | None = None
    is_bold: bool = False
    order: int = 0
    """Reading-order index assigned by the extractor. For RTL pages this is
    already right-to-left column order, not raw PDF stream order."""

    # OCR provenance (None for text-layer blocks)
    confidence: float | None = None
    n_boxes: int | None = None

    # filled in by annotate_structure()
    marker: StructuralMarker | None = None
    struct: StructuralRef = field(default_factory=StructuralRef)

    # filled in by rtl_fix / normalize
    raw_text: str | None = None
    display_text: str | None = None
    rtl_flags: list[RTLFlag] = field(default_factory=list)
    normalization_applied: list[str] = field(default_factory=list)

    # filled in by the PDF extractor; consumed by src.visual_order
    geometric_text: str | None = None
    """The same block read from glyph x-positions instead of the content
    stream, for PDF text layers only. Candidate reading, not yet chosen -- see
    :func:`src.extract_pymupdf_docling._resolve_reading_order`."""
    reading_order_repaired: bool = False
    """True when this block's text was reordered from visual to logical order.
    Surfaced on the chunk as ``metadata.reading_order_repaired`` so the repair
    stays auditable rather than silent."""

    def is_empty(self) -> bool:
        return not self.text or not self.text.strip()


@dataclass
class ExtractedTable:
    """A table, preserved as structured rows *and* as a markdown rendering.

    Two representations on purpose: ``rows`` for M5's programmatic use (payment
    schedules, party tables), ``markdown`` so the table can be embedded as chunk
    text without losing its grid.
    """

    rows: list[list[str]]
    page: int | None = None
    bbox: BoundingBox | None = None
    caption: str | None = None
    source_engine: SourceEngine = SourceEngine.UNKNOWN
    order: int = 0

    @property
    def shape(self) -> tuple[int, int]:
        return (len(self.rows), max((len(r) for r in self.rows), default=0))

    def to_markdown(self) -> str:
        if not self.rows:
            return ""
        ncols = self.shape[1]
        norm = [list(r) + [""] * (ncols - len(r)) for r in self.rows]
        def esc(c: str) -> str:
            return (c or "").replace("|", "\\|").replace("\n", " ").strip()
        head = "| " + " | ".join(esc(c) for c in norm[0]) + " |"
        rule = "| " + " | ".join(["---"] * ncols) + " |"
        body = ["| " + " | ".join(esc(c) for c in row) + " |" for row in norm[1:]]
        return "\n".join([head, rule, *body])


@dataclass
class ExtractedPage:
    """One page of the source document."""

    page_number: int
    blocks: list[TextBlock] = field(default_factory=list)
    tables: list[ExtractedTable] = field(default_factory=list)
    width: float | None = None
    height: float | None = None
    source_engine: SourceEngine = SourceEngine.UNKNOWN
    ocr: OCRConfidence | None = None
    is_blank: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(b.text for b in self.blocks if not b.is_empty())

    @property
    def char_count(self) -> int:
        return sum(len(b.text) for b in self.blocks)


@dataclass
class ExtractedDocument:
    """The full IR handed from any extractor to the rest of the pipeline."""

    document_id: str
    source_path: str
    file_type: str
    pages: list[ExtractedPage] = field(default_factory=list)
    pdf_kind: str | None = None
    document_type: DocumentType = DocumentType.UNKNOWN
    doc_type_confidence: float = 0.0
    language: Language = Language.UNKNOWN
    jurisdiction: str | None = None
    engine_log: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    timings_ms: dict[str, float] = field(default_factory=dict)

    @property
    def full_text(self) -> str:
        return "\n\n".join(p.text for p in self.pages if p.text.strip())

    @property
    def n_pages(self) -> int:
        return len(self.pages)

    def all_blocks(self) -> Iterable[TextBlock]:
        for page in self.pages:
            yield from page.blocks

    def all_tables(self) -> Iterable[ExtractedTable]:
        for page in self.pages:
            yield from page.tables

    def log_engine(self, page: int | None, engine: str, **detail) -> None:
        """Record which engine handled a page and why (spec requirement)."""
        self.engine_log.append({"page": page, "engine": engine, **detail})


# ---------------------------------------------------------------------------
# Structure annotation pass
# ---------------------------------------------------------------------------


def mark_running_headers(
    doc: ExtractedDocument,
    min_pages: int = 3,
    min_repeat_fraction: float = 0.5,
    margin_fraction: float = 0.15,
) -> int:
    """Label repeating page headers and footers as ``BlockType.HEADER_FOOTER``.

    Running boilerplate -- firm letterhead, a court's name, a source URL, "Page
    3 of 40" -- repeats on nearly every page in the top or bottom margin. Left
    unlabelled it does real damage:

      * it is short, prominent and non-terminated, so the typographic heading
        heuristic promotes it to a **section**, and every following chunk then
        inherits a meaningless section label;
      * it lands in chunk text on every page, adding noise to every embedding.

    Docling labels these when it runs, but Docling is skipped on long documents
    (``docling_max_pages``) -- and long documents are exactly where running
    headers repeat most. So this geometric fallback is needed independently.

    A block is boilerplate when its normalized text repeats on at least
    ``min_repeat_fraction`` of pages **and** sits within ``margin_fraction`` of
    the top or bottom edge. Both conditions are required: a clause that happens
    to recur is not a header, and a one-off title in the top margin is not
    boilerplate.

    Returns the number of blocks marked. Requires bounding boxes, so it is a
    no-op for TXT and for DOCX extracted without geometry.
    """
    pages = [p for p in doc.pages if p.blocks]
    if len(pages) < min_pages:
        return 0

    def key(block: TextBlock) -> str:
        # Digits are wildcarded so "Page 3 of 40" and "Page 4 of 40" collapse
        # to the same key -- otherwise page numbers defeat the repeat test.
        flat = " ".join(block.text.split())[:80]
        return re.sub(rf"[{ANY_DIGIT}]+", "#", flat)

    counts: dict[str, set[int]] = {}
    for page in pages:
        for block in page.blocks:
            if block.is_empty() or block.bbox is None or not page.height:
                continue
            top = block.bbox.y0 / page.height
            bottom = block.bbox.y1 / page.height
            in_margin = top <= margin_fraction or bottom >= (1 - margin_fraction)
            if in_margin:
                counts.setdefault(key(block), set()).add(page.page_number)

    threshold = max(2, int(len(pages) * min_repeat_fraction))
    repeating = {k for k, seen in counts.items() if len(seen) >= threshold}
    if not repeating:
        return 0

    marked = 0
    for page in pages:
        for block in page.blocks:
            if block.is_empty() or block.bbox is None or not page.height:
                continue
            top = block.bbox.y0 / page.height
            bottom = block.bbox.y1 / page.height
            if (top <= margin_fraction or bottom >= (1 - margin_fraction)) and key(block) in repeating:
                block.block_type = BlockType.HEADER_FOOTER
                marked += 1

    if marked:
        doc.log_engine(None, "structure", running_headers_marked=marked,
                       distinct_patterns=len(repeating))
    return marked


# How many lines into a block to look for its marker. Two, not one, and not
# many: see :func:`_leading_marker`.
MARKER_SEARCH_LINES = 2


def _leading_marker(block: TextBlock):
    """The block's opening line and the marker that governs it.

    Normally that is the first line. Bilingual documents break this, and they
    are the norm in Egyptian practice: a clause is written once in Arabic and
    once in English, and the two sit in the same block. When the Arabic comes
    first *and* the source stored it in visual order, its marker has been pushed
    to the end of the line by the bidi reordering --

        '. يلتزم المستشار بأداء الخدمات وفقا للأصول المهنية المتعارف عليها5.1'
        '5.1 The Consultant shall perform the Services ...'

    -- so a first-line-only search finds nothing, and the whole document falls
    back to paragraph chunking with no clause identity at all. That is what
    ``stress_nested_clauses_ar.pdf`` did: 2 chunks and 0 clause ids for a page
    carrying fourteen numbered clauses.

    So the second line is searched too, and its marker adopted if the first line
    has none. The line kept as the block's opening text is still the first one,
    because that is what the heading heuristics and the section label want.

    Deliberately capped at two lines. A block's third line and beyond is body
    text, and "1." at the start of a sentence three lines down is far more
    likely to be an enumeration inside a paragraph than the clause the block
    belongs to. The failure this fixes is specifically the two-language pair.
    """
    text = block.text.strip()
    if not text:
        return "", None
    lines = text.splitlines()
    first_line = lines[0]
    for line in lines[:MARKER_SEARCH_LINES]:
        marker = detect_marker(line)
        if marker is not None:
            return first_line, marker
    return first_line, None


def annotate_structure(doc: ExtractedDocument) -> ExtractedDocument:
    """Walk the document in reading order and attach a :class:`StructuralRef`
    to every block, maintaining an open heading stack.

    This is what makes chunking *legal-aware*: after this pass, every block
    knows which article and clause governs it, so a chunker can cut on those
    boundaries and every emitted chunk can name its own section.

    Rules:
      * A block whose first line matches a marker opens a new unit at that
        level and closes every open unit at the same or deeper level.
      * Blocks with no marker inherit the currently open stack.
      * A typographic heading (no marker) opens a SECTION-level unit only when
        nothing deeper is already open, so a bold line inside a clause does not
        break the clause.
    """
    # Boilerplate must be identified BEFORE headings are inferred: a running
    # header is short, prominent and unterminated, so the typographic heuristic
    # would otherwise promote it to a section and every subsequent chunk would
    # inherit it as its section label.
    mark_running_headers(doc)

    stack: dict[StructLevel, StructuralMarker] = {}
    body_font = _estimate_body_font_size(doc)

    for page in doc.pages:
        for block in sorted(page.blocks, key=lambda b: b.order):
            if block.is_empty() or block.block_type is BlockType.HEADER_FOOTER:
                continue
            first_line, marker = _leading_marker(block)

            if marker is None and looks_like_heading(
                first_line, block.bbox, block.font_size, body_font, block.is_bold
            ):
                deepest = max(stack) if stack else None
                if deepest is None or deepest <= StructLevel.SECTION:
                    marker = StructuralMarker(
                        level=StructLevel.SECTION,
                        kind="section",
                        label=first_line.strip(),
                        number=None,
                        language="ar" if detect_language(first_line) == Language.AR else "en",
                        raw=first_line.strip(),
                        match_end=len(first_line),
                        title=first_line.strip(),
                    )
                    block.block_type = BlockType.HEADING

            if marker is not None:
                for lvl in [l for l in stack if l >= marker.level]:
                    stack.pop(lvl, None)
                stack[marker.level] = marker
                block.marker = marker
                if block.block_type == BlockType.PARAGRAPH and marker.level <= StructLevel.SECTION:
                    block.block_type = BlockType.HEADING

            block.struct = _ref_from_stack(stack)

    _report_structure_detection(doc)
    return doc


# Below this many blocks a document is a note or a cover page, and having no
# structure is the correct answer rather than a failure worth reporting.
_MIN_BLOCKS_TO_EXPECT_STRUCTURE = 4


def _report_structure_detection(doc: ExtractedDocument) -> None:
    """Record what marker detection actually achieved, including nothing.

    The failure mode this exists for: a regex misses on a mangled marker, the
    document has no structure, chunking silently degrades to paragraph mode, and
    **the output looks exactly like a document that genuinely has no clauses**.
    The quality loss is large, invisible, and indistinguishable from correct
    behaviour on an unstructured file.

    So both outcomes are now stated. A document that found markers reports how
    many, and how many of those needed tolerant matching -- that count is the
    thing to watch, because a rising fuzzy share means OCR quality is drifting.
    A document that found none raises ``structure_detection_failed`` as a
    warning, so QA has something to search for rather than an absence to notice.
    """
    blocks = [b for b in doc.all_blocks()
              if not b.is_empty() and b.block_type is not BlockType.HEADER_FOOTER]
    if not blocks:
        return

    markers = [b.marker for b in blocks if b.marker is not None]
    fuzzy = [m for m in markers if m.fuzzy]

    if markers:
        doc.log_engine(None, "structure", markers=len(markers),
                       fuzzy_markers=len(fuzzy),
                       kinds=sorted({m.kind for m in markers}))
        if fuzzy:
            doc.warnings.append(
                f"{len(fuzzy)} of {len(markers)} structural marker(s) were "
                f"recovered by OCR-tolerant matching rather than an exact match "
                f"(lowest confidence {min(m.match_confidence for m in fuzzy):.2f}). "
                f"Examples: "
                + "; ".join(
                    f"{m.raw!r} -> {m.label} ({m.match_evidence})" for m in fuzzy[:3]
                )
                + ". Spot-check these against the source."
            )
        return

    if len(blocks) < _MIN_BLOCKS_TO_EXPECT_STRUCTURE:
        return

    doc.log_engine(None, "structure", status="structure_detection_failed",
                   blocks_examined=len(blocks), markers=0)
    doc.warnings.append(
        f"structure_detection_failed: no legal structure marker was found in "
        f"{len(blocks)} block(s), after exact and OCR-tolerant matching. This "
        f"document will be chunked by paragraph rather than by clause, so its "
        f"chunks carry no clause identity and will not appear in the M1->M5 "
        f"clause view. If the source visibly has articles or numbered clauses, "
        f"its markers were destroyed before this stage -- check reading order "
        f"and OCR quality for it."
    )


def _ref_from_stack(stack: dict[StructLevel, StructuralMarker]) -> StructuralRef:
    get = lambda lvl: stack.get(lvl)  # noqa: E731
    book, chapter, section = get(StructLevel.BOOK), get(StructLevel.CHAPTER), get(StructLevel.SECTION)
    article, clause, sub = get(StructLevel.ARTICLE), get(StructLevel.CLAUSE), get(StructLevel.SUBCLAUSE)

    deepest = stack[max(stack)] if stack else None
    parts = []
    if article and article.number:
        parts.append(f"art_{article.number}")
    if clause and clause.number:
        parts.append(f"cl_{clause.number}")
    if sub and sub.number:
        parts.append(f"sub_{sub.number}")
    if not parts and section:
        parts.append("sec_" + re.sub(r"\s+", "_", (section.number or section.label))[:40])

    # Title of the deepest unit that has one -- walk outwards until we find a
    # heading with actual text, so a numbered sub-clause with no title still
    # reports the article title that governs it.
    title = None
    for lvl in sorted(stack, reverse=True):
        if stack[lvl].title:
            title = stack[lvl].title
            break

    return StructuralRef(
        book=book.label if book else None,
        chapter=chapter.label if chapter else None,
        section=(section.label if section else (article.label if article else None)),
        article=article.label if article else None,
        clause=(clause.label if clause else (sub.label if sub else None)),
        clause_id=".".join(parts) or None,
        title=title,
        heading_path=[
            f"{stack[l].label}: {stack[l].title}" if stack[l].title and
            stack[l].title != stack[l].label else stack[l].label
            for l in sorted(stack)
        ],
        heading_level=int(max(stack)) if stack else None,
        marker_language=deepest.language if deepest else None,
        # Tolerant-matching provenance for the deepest open unit. Rides along on
        # StructuralRef (which allows extra fields) so a consumer can filter for
        # clauses whose identity was reconstructed rather than read cleanly.
        marker_fuzzy=bool(deepest and deepest.fuzzy),
        marker_confidence=(deepest.match_confidence if deepest else 1.0),
        marker_evidence=(deepest.match_evidence if deepest and deepest.fuzzy else None),
    )


def _estimate_body_font_size(doc: ExtractedDocument) -> float | None:
    """Modal font size across the document -- the baseline "body text" size."""
    sizes: dict[float, int] = {}
    for b in doc.all_blocks():
        if b.font_size:
            key = round(b.font_size, 1)
            sizes[key] = sizes.get(key, 0) + max(len(b.text), 1)
    if not sizes:
        return None
    return max(sizes, key=lambda k: sizes[k])


def clean_control_chars(text: str) -> str:
    """Drop Unicode control/format chars that break downstream tokenizers,
    keeping newline, tab, and the bidi marks (which :mod:`src.rtl_fix` needs)."""
    keep = {"\n", "\t", "\u200e", "\u200f", "\u202a", "\u202b", "\u202c", "\u202d", "\u202e"}
    return "".join(
        ch for ch in text
        if ch in keep or unicodedata.category(ch) not in ("Cc", "Cf", "Co", "Cs")
    )
