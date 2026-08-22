import re
import uuid

from src.schemas import IdentifierSet, ProcessedQuery


class QueryProcessor:
    """Processes multilingual legal queries before BGE-M3 embedding.

    The implementation is intentionally lightweight. It does not perform
    machine translation because translation can change legal identifiers or
    terminology. BGE-M3 is expected to provide the multilingual embedding
    space.
    """

    ARABIC_RE = re.compile(r"[\u0600-\u06FF]")
    LATIN_RE = re.compile(r"[A-Za-z]")
    ARABIZI_HINTS = {
        "el", "al", "ana", "enta", "enti", "eh", "eih", "fe", "fi",
        "law", "contract", "clause", "termination", "article", "case",
    }

    ARTICLE_RE = re.compile(
        r"\b(?:article|art\.?|المادة|مادة)\s*[-:#]?\s*([0-9٠-٩]+)\b",
        re.IGNORECASE,
    )
    CASE_RE = re.compile(
        r"\b(?:case|case\s*no\.?|قضية|دعوى)\s*[-:#]?\s*([A-Za-z0-9٠-٩/-]+)",
        re.IGNORECASE,
    )
    DATE_RE = re.compile(
        r"\b(?:\d{1,4}[/-]\d{1,2}[/-]\d{1,4}|"
        r"\d{1,2}\s+(?:Jan|January|Feb|February|Mar|March|Apr|April|"
        r"May|Jun|June|Jul|July|Aug|August|Sep|September|Oct|October|"
        r"Nov|November|Dec|December)\s+\d{2,4})\b",
        re.IGNORECASE,
    )
    MONEY_RE = re.compile(
        r"(?:[$€£]\s?[\d,]+(?:\.\d+)?|"
        r"[\d,]+(?:\.\d+)?\s?(?:EGP|USD|EUR|GBP|جنيه|دولار|يورو))",
        re.IGNORECASE,
    )

    def detect_language(self, text: str) -> str:
        """Classify a query as Arabic, English, mixed, or unknown.

        Input:
            text: Original user query.

        Output:
            One of ar, en, ar-en, unknown.

        Side effects:
            None.

        Edge cases:
            Digits-only or punctuation-only input becomes unknown.
        """
        has_ar = bool(self.ARABIC_RE.search(text))
        has_latin = bool(self.LATIN_RE.search(text))

        if has_ar and has_latin:
            return "ar-en"
        if has_ar:
            return "ar"
        if has_latin:
            return "en"
        return "unknown"

    def normalize(self, text: str) -> str:
        """Apply conservative normalization without translating legal text.

        Input:
            Original query.

        Output:
            Whitespace-normalized query with common Arabic presentation
            variants reduced.

        Side effects:
            None.

        Important constraint:
            The method avoids aggressive stemming or deletion because legal
            terminology and identifiers must remain intact.
        """
        text = text.strip()
        text = text.replace("\u0640", "")
        text = re.sub(r"\s+", " ", text)

        # Normalize Arabic alef variants conservatively.
        text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")

        # Keep Arabic Yeh and Teh Marbuta intact; legal text should not be
        # aggressively rewritten.
        return text.strip()

    def extract_identifiers(self, text: str) -> IdentifierSet:
        """Extract legal identifiers that must survive preprocessing.

        Input:
            Query text.

        Output:
            IdentifierSet containing article/case/date/money values.

        Side effects:
            None.

        Edge cases:
            Missing categories are returned as empty lists.
        """
        articles = [match.group(1) for match in self.ARTICLE_RE.finditer(text)]
        cases = [match.group(1) for match in self.CASE_RE.finditer(text)]
        dates = [match.group(0) for match in self.DATE_RE.finditer(text)]
        money = [match.group(0) for match in self.MONEY_RE.finditer(text)]

        return IdentifierSet(
            article_numbers=articles,
            case_numbers=cases,
            dates=dates,
            monetary_values=money,
            party_names=[],
        )

    def detect_arabizi(self, text: str) -> bool:
        """Provide a lightweight Arabizi coverage signal.

        This is not a full Arabizi NLP model. It only detects whether the
        query contains Latin-script words commonly seen in Egyptian Arabic
        code-switching.

        Input:
            Query text.

        Output:
            Boolean indicator.

        Side effects:
            None.
        """
        tokens = set(re.findall(r"[A-Za-z]+", text.lower()))
        return bool(tokens & self.ARABIZI_HINTS)

    def build_variants(self, normalized_text: str, language: str) -> list[str]:
        """Create conservative query variants.

        The current MVP returns the normalized query and avoids speculative
        translations. A future version may add controlled query expansion
        after evaluation.

        Input:
            normalized query and language label.

        Output:
            Ordered list of variants.

        Side effects:
            None.
        """
        return [normalized_text]

    def process(self, text: str) -> ProcessedQuery:
        """Run the complete query-processing pipeline.

        Input:
            Raw Arabic, English, or mixed legal query.

        Output:
            ProcessedQuery ready for BGE-M3 embedding and M3 handoff.

        Side effects:
            None.

        Edge cases:
            Empty input raises ValueError.
        """
        if not text or not text.strip():
            raise ValueError("query must not be empty")

        language = self.detect_language(text)
        normalized = self.normalize(text)
        identifiers = self.extract_identifiers(text)
        variants = self.build_variants(normalized, language)

        return ProcessedQuery(
            query_id=f"q_{uuid.uuid4().hex[:8]}",
            text_original=text,
            normalized_text=normalized,
            language=language,
            query_variants=variants,
            identifiers=identifiers,
            embedding=[],
        )
