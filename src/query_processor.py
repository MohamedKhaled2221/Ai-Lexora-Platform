import re
import unicodedata
import uuid
from src.identifier_preserver import (
    IdentifierPreserver,
)

from src.schemas import (
    IdentifierSet,
    ProcessedQuery,
)


class QueryProcessor:
    def __init__(
        self,
        identifier_preserver: (
            IdentifierPreserver | None
        ) = None,
    ) -> None:
        self.identifier_preserver = (
            identifier_preserver
            or IdentifierPreserver()
        )
    """
    Processes multilingual legal queries before BGE-M3 embedding.

    Supported query forms:
    - English;
    - Arabic;
    - Egyptian Arabic written in Arabic script;
    - Arabic-English mixed text.

    Arabizi processing is intentionally deferred until the team
    decides whether it belongs in the supported scope.

    The processor never translates the user query. Translation or
    aggressive rewriting can alter legal meaning or damage exact
    identifiers.
    """

    # Arabic Unicode blocks commonly encountered in legal/user text.
    ARABIC_RE = re.compile(
        r"["
        r"\u0600-\u06FF"
        r"\u0750-\u077F"
        r"\u08A0-\u08FF"
        r"\uFB50-\uFDFF"
        r"\uFE70-\uFEFF"
        r"]"
    )

    LATIN_RE = re.compile(
        r"[A-Za-z]"
    )

    # Arabic combining marks / diacritics.
    ARABIC_DIACRITICS_RE = re.compile(
        r"[\u0610-\u061A"
        r"\u064B-\u065F"
        r"\u0670"
        r"\u06D6-\u06ED]"
    )
    def detect_language(
        self,
        text: str,
    ) -> str:
        """
        Detect the alphabetic script composition of a legal query.

        Returns:
            ar:
                Arabic-script letters with no Latin letters.

            en:
                Latin-script letters with no Arabic letters.

            ar-en:
                Query contains both Arabic and Latin letters.

            unknown:
                No Arabic or Latin alphabetic content.

        Arabic-Indic digits do not make a query Arabic or mixed.
        Egyptian Arabic written using Arabic script is classified
        as ``ar``.

        This is intentionally script-level detection rather than
        dialect classification.
        """

        if not text:
            return "unknown"

        has_arabic = False
        has_latin = False

        for character in text:
            # Ignore digits, punctuation, whitespace,
            # currency symbols, and other non-letter characters.
            if not character.isalpha():
                continue

            unicode_name = unicodedata.name(
                character,
                "",
            )

            if "ARABIC" in unicode_name:
                has_arabic = True

            elif "LATIN" in unicode_name:
                has_latin = True

            if has_arabic and has_latin:
                return "ar-en"

        if has_arabic:
            return "ar"

        if has_latin:
            return "en"

        return "unknown"

    def normalize(
        self,
        text: str,
    ) -> str:
        """
        Apply conservative multilingual normalization.

        The original query is never modified in ProcessedQuery.
        This method produces a separate normalized representation.

        Normalization intentionally performs only low-risk operations:
        - Unicode NFC normalization;
        - trim surrounding whitespace;
        - collapse repeated whitespace;
        - remove Arabic tatweel;
        - remove Arabic diacritics;
        - normalize common Arabic alef variants.

        It does NOT:
        - translate;
        - stem;
        - lowercase all text;
        - remove punctuation;
        - rewrite Arabic/Latin digits;
        - alter identifiers such as case/article numbers.
        """

        if not text:
            return ""

        normalized = unicodedata.normalize(
            "NFC",
            text,
        )

        # Remove Arabic tatweel/kashida.
        normalized = normalized.replace(
            "\u0640",
            "",
        )

        # Remove optional Arabic vowel/recitation marks.
        normalized = (
            self.ARABIC_DIACRITICS_RE.sub(
                "",
                normalized,
            )
        )

        # Conservative Arabic alef normalization.
        normalized = (
            normalized
            .replace("أ", "ا")
            .replace("إ", "ا")
            .replace("آ", "ا")
        )

        # Do not normalize ي/ى or ة/ه because these may alter
        # names and legal terminology.
        normalized = re.sub(
            r"\s+",
            " ",
            normalized,
        )

        return normalized.strip()

    def extract_identifiers(
        self,
        text: str,
    ) -> IdentifierSet:
        """
        Extract exact legal identifiers from the original query.

        Delegated to IdentifierPreserver so extraction logic remains
        independent from language detection and normalization.
        """

        return (
            self.identifier_preserver
            .extract(text)
        )
    def build_variants(
        self,
        normalized_text: str,
        language: str,
    ) -> list[str]:
        """
        Return the current conservative query representation.

        Controlled query expansion is intentionally deferred to M2.4.
        """

        del language

        return [
            normalized_text
        ]

    def process(
        self,
        text: str,
    ) -> ProcessedQuery:
        """
        Run the complete deterministic M2 query-processing stage.

        The query is not embedded here. Embedding remains the
        responsibility of M2QueryPipeline / EmbeddingService.
        """

        if (
            not text
            or not text.strip()
        ):
            raise ValueError(
                "query must not be empty"
            )

        language = self.detect_language(
            text
        )

        normalized = self.normalize(
            text
        )

        identifiers = (
            self.extract_identifiers(
                text
            )
        )

        variants = self.build_variants(
            normalized,
            language,
        )

        return ProcessedQuery(
            query_id=(
                f"q_{uuid.uuid4().hex[:8]}"
            ),
            text_original=text,
            normalized_text=normalized,
            language=language,
            query_variants=variants,
            identifiers=identifiers,
            embedding=[],
        )