"""Input type detection and routing.

Answers two questions before any extraction happens:

1. **What kind of file is this?** PDF / DOCX / TXT / image -- by magic bytes
   first, extension second, because scanned material routinely arrives with a
   wrong or missing extension.
2. **If PDF: is it scanned or text-based?** i.e. does it have a usable text
   layer, or must it go through OCR?

The scanned/text question is decided *per page*, not per document. Egyptian
legal bundles are routinely hybrid: a digitally-typed contract with a scanned
signature-and-stamp page appended, or a born-digital cover sheet on a scanned
court file. Treating such a file as wholly one or the other loses real content,
so :class:`PDFTypeReport` records a decision for every page and the document
verdict is a summary of those, not a substitute for them.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Literal

from .config import ExtractionConfig

logger = logging.getLogger(__name__)


class FileType(str, Enum):
    PDF = "pdf"
    DOCX = "docx"
    DOC = "doc"          # legacy binary Word -- not supported, detected to fail loudly
    TXT = "txt"
    IMAGE = "image"
    UNKNOWN = "unknown"


class ExtractionRoute(str, Enum):
    """Which pipeline path an input takes."""

    TEXT_LAYER = "text_layer"   # PyMuPDF + Docling
    OCR = "ocr"                 # PaddleOCR -> Tesseract
    HYBRID = "hybrid"           # per-page mix of the two
    DOCX = "docx"               # Docling, python-docx fallback
    PLAINTEXT = "plaintext"
    UNSUPPORTED = "unsupported"


# Magic-byte signatures. Checked before extension.
_MAGIC: list[tuple[bytes, FileType]] = [
    (b"%PDF-", FileType.PDF),
    (b"\x89PNG\r\n\x1a\n", FileType.IMAGE),
    (b"\xff\xd8\xff", FileType.IMAGE),           # JPEG
    (b"GIF87a", FileType.IMAGE),
    (b"GIF89a", FileType.IMAGE),
    (b"BM", FileType.IMAGE),                      # BMP
    (b"II*\x00", FileType.IMAGE),                 # TIFF LE
    (b"MM\x00*", FileType.IMAGE),                 # TIFF BE
    (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", FileType.DOC),  # OLE2 = legacy .doc
]

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp", ".gif"}
_TEXT_EXTS = {".txt", ".text", ".md"}


def text_layer_quality(text: str) -> tuple[float, str]:
    """Score how plausible an extracted text layer is as real language.

    Returns ``(alpha_ratio, diagnosis)`` where ``alpha_ratio`` is the share of
    non-whitespace characters that are letters or digits.

    **Why this exists.** "Has a text layer" and "has a *usable* text layer" are
    different questions, and only the second one matters. A PDF can carry a
    full text layer that decodes to nonsense when its embedded font uses a
    custom or broken encoding with no usable ToUnicode CMap -- common in older
    Arabic typesetting and in scanner software that burns in its own OCR. The
    text extracts happily and looks like this::

        ----------------- •• • • • • • • \\ '\\'\\A ;.;..J Yo (.J wj\\i ~JbJl.1

    That is 7,500 characters of "text" containing zero Arabic. Routing such a
    page to the text-layer path produces confident, well-structured garbage --
    far worse than routing it to OCR, which reads the rendered glyphs and
    recovers the real text.

    One of the interim corpus documents (``wipo_eg087ar_1.pdf``, a published
    Egyptian statute) is exactly this case, which is how the gap was found.

    Runs of a repeated punctuation character are collapsed first. Without that,
    a legitimate table-of-contents page scores as badly as mojibake: its dot
    leaders (``الفصل الأول .................. 12``) are 99% of its
    non-alphanumeric mass and would push it to OCR for nothing. Mojibake is
    distinguishable because its punctuation is *diverse* -- assorted symbols
    from arbitrary codepoints -- so collapsing repeats barely shrinks it.

    Measured across the whole interim corpus (per-document min / median)::

        eg_official_gazette_excerpt.pdf    0.97 / 0.98   text layer kept
        eg_constitution_2014_en.pdf        0.95 / 0.98   text layer kept
        wipo_eg088ar_1.pdf                 0.96 / 0.97   text layer kept
        constitute_egypt_2014_ar.pdf       0.87 / 0.96   text layer kept (TOC incl.)
        wipo_eg081ar_1.pdf                 0.88 / 0.97   text layer kept
        wipo_eg087ar_1.pdf                 0.32 / 0.33   REJECTED -> OCR

    Clean separation with no false positives: every genuine document scores
    above 0.87, the one with a broken font encoding scores 0.33.
    """
    import re

    # Collapse repeated punctuation, allowing whitespace between the repeats --
    # PDF extraction often returns dot leaders as ". . . . ." rather than
    # "......", and a naive same-character-adjacent rule misses them entirely.
    #
    # ``_`` is matched explicitly: it is a \w character to the regex engine but
    # not alphanumeric to str.isalnum(), so underscore leaders ("الاسم ______")
    # would otherwise count as junk and push every form contract to OCR.
    collapsed = re.sub(r"([^\w\s]|_)(?:[ \t]*\1)+", r"\1", text)
    stripped = [c for c in collapsed if not c.isspace()]
    if len(stripped) < 50:
        return 1.0, "too little text to judge"

    alpha_num = sum(1 for c in stripped if c.isalnum())
    ratio = alpha_num / len(stripped)

    if ratio < 0.50:
        return ratio, (
            f"only {ratio:.0%} of characters are letters or digits (after "
            "collapsing repeated punctuation) -- the text layer looks like "
            "mojibake from a broken font encoding, not language"
        )
    if ratio < 0.65:
        return ratio, f"{ratio:.0%} letters/digits -- text layer quality is marginal"
    return ratio, f"{ratio:.0%} letters/digits -- plausible text"


@dataclass
class PageTypeVerdict:
    """Per-page scanned/text decision with the evidence behind it."""

    page_number: int
    has_text_layer: bool
    char_count: int
    image_area_ratio: float
    """Fraction of the page area covered by raster images."""
    route: ExtractionRoute
    reason: str
    text_quality: float = 1.0
    """Share of non-space characters that are letters/digits. Below ~0.5 the
    text layer is mojibake -- see :func:`text_layer_quality`."""

    @property
    def is_scanned(self) -> bool:
        return self.route is ExtractionRoute.OCR


@dataclass
class PDFTypeReport:
    """Document-level verdict plus the per-page detail it was derived from."""

    kind: Literal["text", "scanned", "hybrid"]
    route: ExtractionRoute
    n_pages: int
    pages: list[PageTypeVerdict] = field(default_factory=list)
    total_chars: int = 0
    is_encrypted: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def scanned_pages(self) -> list[int]:
        return [p.page_number for p in self.pages if p.is_scanned]

    @property
    def text_pages(self) -> list[int]:
        return [p.page_number for p in self.pages if not p.is_scanned]


@dataclass
class DetectionResult:
    """What :func:`detect` returns for any input path."""

    path: str
    file_type: FileType
    route: ExtractionRoute
    pdf_report: PDFTypeReport | None = None
    detected_by: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def pdf_kind(self) -> str | None:
        if self.file_type is not FileType.PDF:
            return "n/a"
        return self.pdf_report.kind if self.pdf_report else None


# ---------------------------------------------------------------------------
# File type
# ---------------------------------------------------------------------------


def detect_file_type(path: str | Path) -> tuple[FileType, str]:
    """Identify a file by magic bytes, falling back to extension.

    Returns ``(file_type, how_it_was_detected)``.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)

    try:
        head = p.open("rb").read(8192)
    except OSError as exc:
        logger.warning("could not read header of %s: %s", p, exc)
        head = b""

    for sig, ftype in _MAGIC:
        if head.startswith(sig):
            if ftype is FileType.PDF:
                return FileType.PDF, "magic"
            if ftype is FileType.DOC:
                return FileType.DOC, "magic"
            return ftype, "magic"

    # OOXML (.docx) is a zip; disambiguate by looking for the word/ part.
    if head.startswith(b"PK\x03\x04"):
        if b"word/" in head or p.suffix.lower() == ".docx":
            return FileType.DOCX, "magic+zip"
        try:
            import zipfile

            with zipfile.ZipFile(p) as zf:
                names = zf.namelist()
            if any(n.startswith("word/") for n in names):
                return FileType.DOCX, "zip-listing"
        except Exception:  # noqa: BLE001 - corrupt zip is just "not a docx"
            pass

    ext = p.suffix.lower()
    if ext == ".pdf":
        return FileType.PDF, "extension"
    if ext == ".docx":
        return FileType.DOCX, "extension"
    if ext == ".doc":
        return FileType.DOC, "extension"
    if ext in _IMAGE_EXTS:
        return FileType.IMAGE, "extension"
    if ext in _TEXT_EXTS:
        return FileType.TXT, "extension"

    # Last resort: does it decode as text?
    if head and _looks_like_text(head):
        return FileType.TXT, "content-sniff"
    return FileType.UNKNOWN, "none"


def _looks_like_text(head: bytes) -> bool:
    for enc in ("utf-8", "utf-16", "cp1256"):  # cp1256 = legacy Windows Arabic
        try:
            decoded = head.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
        printable = sum(1 for c in decoded if c.isprintable() or c.isspace())
        if printable / max(len(decoded), 1) > 0.90:
            return True
    return False


# ---------------------------------------------------------------------------
# PDF: scanned vs text-based
# ---------------------------------------------------------------------------


def classify_pdf(
    path: str | Path,
    config: ExtractionConfig | None = None,
    *,
    hybrid_tolerance: float = 0.15,
) -> PDFTypeReport:
    """Decide, per page, whether a PDF has a usable text layer.

    A page routes to OCR when **either**:

      * it yields fewer than ``text_layer_min_chars_per_page`` characters, or
      * it yields *some* text but that text is dwarfed by a full-page raster
        image -- the classic "scanned page with a junk OCR layer already burned
        in by the scanner driver" case, which is common in Egyptian court
        bundles and is worse than no text layer at all.

    Document verdict:
      * ``text``    -- no page needs OCR
      * ``scanned`` -- every page needs OCR
      * ``hybrid``  -- a mix; ``hybrid_tolerance`` decides how small a minority
        can be before we still call the document homogeneous (a single scanned
        signature page in a 40-page contract is not worth calling the whole
        document hybrid, but it still gets OCR'd -- the per-page routes are
        authoritative either way).
    """
    import fitz  # PyMuPDF

    cfg = config or ExtractionConfig()
    min_chars = cfg.text_layer_min_chars_per_page
    report_notes: list[str] = []

    doc = fitz.open(str(path))
    try:
        encrypted = bool(doc.is_encrypted)
        if encrypted and not doc.authenticate(""):
            return PDFTypeReport(
                kind="scanned", route=ExtractionRoute.UNSUPPORTED, n_pages=doc.page_count,
                is_encrypted=True,
                notes=["PDF is password-protected; cannot inspect text layer"],
            )

        verdicts: list[PageTypeVerdict] = []
        for i, page in enumerate(doc, start=1):
            text = page.get_text("text") or ""
            n_chars = len(text.strip())
            page_area = abs(page.rect.get_area()) or 1.0

            image_area = 0.0
            try:
                for info in page.get_image_info():
                    bbox = info.get("bbox")
                    if bbox:
                        image_area += abs(fitz.Rect(bbox).get_area())
            except Exception as exc:  # noqa: BLE001
                report_notes.append(f"page {i}: image inspection failed ({exc})")
            ratio = min(image_area / page_area, 1.0)

            quality, quality_note = text_layer_quality(text)

            if n_chars >= min_chars and quality < cfg.min_text_layer_quality:
                # A text layer that decodes to nonsense is worse than none:
                # the text path would produce confident garbage. Send it to OCR,
                # which reads the rendered glyphs instead.
                route = ExtractionRoute.OCR
                reason = f"text layer present ({n_chars} chars) but unusable -- {quality_note}"
                report_notes.append(
                    f"page {i}: text layer rejected as garbled ({quality:.0%} "
                    "letters/digits); routed to OCR"
                )
            elif n_chars >= min_chars and ratio < 0.85:
                route, reason = ExtractionRoute.TEXT_LAYER, f"text layer has {n_chars} chars"
            elif n_chars >= min_chars and ratio >= 0.85:
                # Text present but a near-full-page image covers it.
                route = ExtractionRoute.TEXT_LAYER
                reason = (
                    f"text layer has {n_chars} chars but image covers {ratio:.0%} of page; "
                    "kept text layer, flagged for OCR comparison"
                )
                report_notes.append(f"page {i}: possible burned-in scanner OCR layer")
            elif ratio > 0.30:
                route, reason = ExtractionRoute.OCR, (
                    f"only {n_chars} chars of text, image covers {ratio:.0%} of page"
                )
            elif n_chars == 0:
                route, reason = ExtractionRoute.OCR, "no text layer and no detectable image (blank or vector-only)"
            else:
                route, reason = ExtractionRoute.OCR, f"only {n_chars} chars, below threshold {min_chars}"

            verdicts.append(
                PageTypeVerdict(
                    page_number=i,
                    has_text_layer=n_chars > 0,
                    char_count=n_chars,
                    image_area_ratio=round(ratio, 4),
                    route=route,
                    reason=reason,
                    text_quality=round(quality, 4),
                )
            )

        n = len(verdicts)
        n_ocr = sum(1 for v in verdicts if v.is_scanned)
        if n == 0:
            kind, route = "text", ExtractionRoute.TEXT_LAYER
            report_notes.append("PDF has zero pages")
        elif n_ocr == 0:
            kind, route = "text", ExtractionRoute.TEXT_LAYER
        elif n_ocr == n:
            kind, route = "scanned", ExtractionRoute.OCR
        else:
            frac = n_ocr / n
            route = ExtractionRoute.HYBRID
            if frac <= hybrid_tolerance:
                kind = "text"
                report_notes.append(
                    f"{n_ocr}/{n} pages need OCR (<= {hybrid_tolerance:.0%}); "
                    "document called 'text' but those pages still route to OCR"
                )
            elif frac >= 1 - hybrid_tolerance:
                kind = "scanned"
                report_notes.append(
                    f"{n - n_ocr}/{n} pages have a text layer; document called 'scanned' "
                    "but those pages still use the text layer"
                )
            else:
                kind = "hybrid"

        return PDFTypeReport(
            kind=kind,  # type: ignore[arg-type]
            route=route,
            n_pages=n,
            pages=verdicts,
            total_chars=sum(v.char_count for v in verdicts),
            is_encrypted=encrypted,
            notes=report_notes,
        )
    finally:
        doc.close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def detect(path: str | Path, config: ExtractionConfig | None = None) -> DetectionResult:
    """Full detection: file type, and for PDFs the scanned/text routing plan.

    >>> detect("contract.pdf").route          # doctest: +SKIP
    <ExtractionRoute.TEXT_LAYER: 'text_layer'>
    """
    p = Path(path)
    ftype, how = detect_file_type(p)
    notes: list[str] = []

    if ftype is FileType.PDF:
        report = classify_pdf(p, config)
        notes.extend(report.notes)
        return DetectionResult(
            path=str(p), file_type=ftype, route=report.route,
            pdf_report=report, detected_by=how, notes=notes,
        )

    route = {
        FileType.DOCX: ExtractionRoute.DOCX,
        FileType.TXT: ExtractionRoute.PLAINTEXT,
        FileType.IMAGE: ExtractionRoute.OCR,   # images go straight to OCR
        FileType.DOC: ExtractionRoute.UNSUPPORTED,
        FileType.UNKNOWN: ExtractionRoute.UNSUPPORTED,
    }[ftype]

    if ftype is FileType.DOC:
        notes.append(
            "legacy binary .doc is not supported; convert to .docx or PDF "
            "(LibreOffice: soffice --headless --convert-to docx)"
        )
    if ftype is FileType.UNKNOWN:
        notes.append("could not identify file type from magic bytes or extension")

    return DetectionResult(
        path=str(p), file_type=ftype, route=route, detected_by=how, notes=notes
    )
