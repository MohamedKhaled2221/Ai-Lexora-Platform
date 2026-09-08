import re
import unicodedata
import uuid

from src.schemas import (
    IdentifierSet,
    ProcessedQuery,
)


class QueryProcessor:
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

    ARTICLE_RE = re.compile(
        r"\b(?:article|art\.?|المادة|مادة)"
        r"\s*[-:#]?\s*([0-9٠-٩]+)\b",
        re.IGNORECASE,
    )

    CASE_RE = re.compile(
        r"\b(?:case|case\s*no\.?|قضية|دعوى)"
        r"\s*[-:#]?\s*([A-Za-z0-9٠-٩/-]+)",
        re.IGNORECASE,
    )

    DATE_RE = re.compile(
        r"\b(?:"
        r"\d{1,4}[/-]\d{1,2}[/-]\d{1,4}"
        r"|"
        r"\d{1,2}\s+"
        r"(?:Jan|January|Feb|February|"
        r"Mar|March|Apr|April|May|Jun|June|"
        r"Jul|July|Aug|August|Sep|September|"
        r"Oct|October|Nov|November|Dec|December)"
        r"\s+\d{2,4}"
        r")\b",
        re.IGNORECASE,
    )

    MONEY_RE = re.compile(
        r"(?:"
        r"[$€£]\s?[\d,]+(?:\.\d+)?"
        r"|"
        r"[\d,]+(?:\.\d+)?"
        r"\s?(?:EGP|USD|EUR|GBP|جنيه|دولار|يورو)"
        r")",
        re.IGNORECASE,
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
        Extract legal identifiers that must survive preprocessing.

        More complete identifier extraction, including party names
        and named legal terms, is implemented in M2.3.
        """

        articles = [
            match.group(1)
            for match
            in self.ARTICLE_RE.finditer(
                text
            )
        ]

        cases = [
            match.group(1)
            for match
            in self.CASE_RE.finditer(
                text
            )
        ]

        dates = [
            match.group(0)
            for match
            in self.DATE_RE.finditer(
                text
            )
        ]

        money = [
            match.group(0)
            for match
            in self.MONEY_RE.finditer(
                text
            )
        ]

        return IdentifierSet(
            article_numbers=articles,
            case_numbers=cases,
            dates=dates,
            monetary_values=money,
            party_names=[],
            named_legal_terms=[],
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