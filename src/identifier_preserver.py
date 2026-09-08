"""
Deterministic legal identifier preservation for M2.

The preserver extracts exact legal identifiers from the original
user query without translating, normalizing, or rewriting their text.

M2 extracts and preserves the identifiers.
M3 decides how to use them during retrieval.
"""

from __future__ import annotations

import re

from src.schemas.m2_contract import (
    IdentifierSet,
)


class IdentifierPreserver:
    """
    Extract exact legal identifiers from multilingual queries.

    Supported categories:
    - article numbers;
    - case numbers;
    - dates;
    - monetary values;
    - party names;
    - named legal terms.

    Extraction always operates on the original user query.
    """

    DIGIT = r"0-9٠-٩"

    NUMBER = (
        rf"[{DIGIT}]"
        rf"[{DIGIT},٬]*"
        rf"(?:[.\u066B][{DIGIT}]+)?"
    )

    ARTICLE_RE = re.compile(
        r"\b(?:"
        r"article|art\.?|"
        r"المادة|"
        r"مادة|"
        r"للمادة|"
        r"بالمادة|"
        r"فالمادة|"
        r"والمادة"
        r")"
        r"\s*"
        r"(?:(?:no\.?|number|رقم)\s*)?"
        r"[-:#]?\s*"
        r"([0-9٠-٩]+(?:[/-][0-9٠-٩]+)?)",
        re.IGNORECASE,
    )

    CASE_RE = re.compile(
        r"\b(?:"
        r"case(?:\s*(?:no\.?|number))?|"
        r"lawsuit|claim|"
        r"قضية|القضية|دعوى|الدعوى"
        r")"
        r"\s*"
        r"(?:(?:no\.?|number|رقم)\s*)?"
        r"[-:#]?\s*"
        r"("
        r"[A-Za-z0-9٠-٩]+"
        r"(?:[/-][A-Za-z0-9٠-٩]+)*"
        r")",
        re.IGNORECASE,
    )

    NUMERIC_DATE_RE = re.compile(
        r"\b"
        r"[0-9٠-٩]{1,4}"
        r"[/-]"
        r"[0-9٠-٩]{1,2}"
        r"[/-]"
        r"[0-9٠-٩]{1,4}"
        r"\b"
    )

    ENGLISH_DATE_RE = re.compile(
        r"\b"
        r"[0-9]{1,2}\s+"
        r"(?:"
        r"Jan(?:uary)?|"
        r"Feb(?:ruary)?|"
        r"Mar(?:ch)?|"
        r"Apr(?:il)?|"
        r"May|"
        r"Jun(?:e)?|"
        r"Jul(?:y)?|"
        r"Aug(?:ust)?|"
        r"Sep(?:tember)?|"
        r"Oct(?:ober)?|"
        r"Nov(?:ember)?|"
        r"Dec(?:ember)?"
        r")"
        r"\s+[0-9]{2,4}"
        r"\b",
        re.IGNORECASE,
    )

    ENGLISH_DATE_MONTH_FIRST_RE = re.compile(
        r"\b"
        r"(?:"
        r"Jan(?:uary)?|"
        r"Feb(?:ruary)?|"
        r"Mar(?:ch)?|"
        r"Apr(?:il)?|"
        r"May|"
        r"Jun(?:e)?|"
        r"Jul(?:y)?|"
        r"Aug(?:ust)?|"
        r"Sep(?:tember)?|"
        r"Oct(?:ober)?|"
        r"Nov(?:ember)?|"
        r"Dec(?:ember)?"
        r")"
        r"\s+[0-9]{1,2},?"
        r"\s+[0-9]{4}"
        r"\b",
        re.IGNORECASE,
    )

    ARABIC_DATE_RE = re.compile(
        r"\b"
        r"[0-9٠-٩]{1,2}\s+"
        r"(?:"
        r"يناير|فبراير|مارس|أبريل|ابريل|"
        r"مايو|يونيو|يوليو|أغسطس|اغسطس|"
        r"سبتمبر|أكتوبر|اكتوبر|نوفمبر|ديسمبر"
        r")"
        r"\s+[0-9٠-٩]{2,4}"
        r"\b"
    )

    MONEY_RE = re.compile(
        rf"(?:"
        rf"(?:EGP|USD|EUR|GBP|AED|SAR|[$€£])"
        rf"\s*{NUMBER}"
        rf"|"
        rf"{NUMBER}\s*"
        rf"(?:"
        rf"EGP|USD|EUR|GBP|AED|SAR|"
        rf"جنيه(?:\s+مصري)?|"
        rf"دولار(?:\s+أمريكي)?|"
        rf"يورو|"
        rf"ريال(?:\s+سعودي)?|"
        rf"درهم(?:\s+إماراتي)?"
        rf")"
        rf")",
        re.IGNORECASE,
    )

    LATIN_ORGANIZATION_RE = re.compile(
        r"\b"
        r"[A-Z][A-Za-z0-9&.'-]*"
        r"(?:\s+[A-Z][A-Za-z0-9&.'-]*){0,6}"
        r"\s+"
        r"(?:"
        r"LLC|"
        r"L\.L\.C\.|"
        r"Ltd\.?|"
        r"Limited|"
        r"Inc\.?|"
        r"Corporation|"
        r"Corp\.?|"
        r"PLC|"
        r"S\.A\.E\.|"
        r"SAE"
        r")"
        r"(?=$|[\s,.;:!?()])"
    )

    ENGLISH_PERSON_ROLE_RE = re.compile(
        r"\b(?i:"
        r"plaintiff|"
        r"defendant|"
        r"claimant|"
        r"respondent|"
        r"mr\.?|"
        r"mrs\.?|"
        r"ms\.?|"
        r"dr\.?"
        r")"
        r"\s+"
        r"("
        r"[A-Z][A-Za-z.'-]+"
        r"(?:\s+[A-Z][A-Za-z.'-]+){1,3}"
        r")"
    )
    ARABIC_ORGANIZATION_PREFIX_RE = re.compile(
        r"\b(?:شركة|مؤسسة)\b"
    )

    ARABIC_PERSON_ROLE_RE = re.compile(
        r"\b(?:"
        r"المدعي|"
        r"المدعى\s+عليه|"
        r"السيد|"
        r"السيدة"
        r")\b"
    )

    ARABIC_NAME_STOPWORDS = {
        "في",
        "ضد",
        "عن",
        "حول",
        "على",
        "من",
        "إلى",
        "الى",
        "لدى",
        "بموجب",
        "بخصوص",
        "رقم",
        "المادة",
        "مادة",
        "قضية",
        "القضية",
        "دعوى",
        "الدعوى",
        "بشأن",
        "بشان",
        "مع",
    }

    LEGAL_TERMS = (
        # English
        "force majeure",
        "governing law",
        "confidentiality",
        "non-disclosure agreement",
        "breach of contract",
        "liquidated damages",
        "limitation of liability",
        "intellectual property",
        "indemnity",
        "arbitration",
        "jurisdiction",
        "termination",

        # Arabic
        "القوة القاهرة",
        "القانون الحاكم",
        "السرية",
        "اتفاقية عدم الإفصاح",
        "اتفاقية عدم الافصاح",
        "الإخلال بالعقد",
        "الاخلال بالعقد",
        "الشرط الجزائي",
        "تحديد المسؤولية",
        "الملكية الفكرية",
        "التعويض",
        "التحكيم",
        "الاختصاص القضائي",
        "إنهاء العقد",
        "انهاء العقد",
        "فسخ العقد",
    )

    LEGAL_TERM_PATTERNS = tuple(
        re.compile(
            rf"(?<!\w){re.escape(term)}(?!\w)",
            re.IGNORECASE,
        )
        for term in sorted(
            LEGAL_TERMS,
            key=len,
            reverse=True,
        )
    )

    def extract(
        self,
        text: str,
    ) -> IdentifierSet:
        """
        Extract all supported identifiers from original query text.
        """

        if not text:
            return IdentifierSet()

        return IdentifierSet(
            article_numbers=(
                self.extract_articles(text)
            ),
            case_numbers=(
                self.extract_cases(text)
            ),
            dates=(
                self.extract_dates(text)
            ),
            monetary_values=(
                self.extract_money(text)
            ),
            party_names=(
                self.extract_party_names(text)
            ),
            named_legal_terms=(
                self.extract_legal_terms(text)
            ),
        )

    def extract_articles(
        self,
        text: str,
    ) -> list[str]:
        return self._deduplicate(
            match.group(1)
            for match in self.ARTICLE_RE.finditer(
                text
            )
        )

    def extract_cases(
        self,
        text: str,
    ) -> list[str]:
        return self._deduplicate(
            match.group(1)
            for match in self.CASE_RE.finditer(
                text
            )
        )

    def extract_dates(
        self,
        text: str,
    ) -> list[str]:
        matches: list[
            tuple[int, str]
        ] = []

        patterns = (
            self.NUMERIC_DATE_RE,
            self.ENGLISH_DATE_RE,
            self.ENGLISH_DATE_MONTH_FIRST_RE,
            self.ARABIC_DATE_RE,
        )

        for pattern in patterns:
            for match in pattern.finditer(
                text
            ):
                matches.append(
                    (
                        match.start(),
                        match.group(0),
                    )
                )

        matches.sort(
            key=lambda item: item[0]
        )

        return self._deduplicate(
            value
            for _, value in matches
        )

    def extract_money(
        self,
        text: str,
    ) -> list[str]:
        return self._deduplicate(
            match.group(0)
            for match in self.MONEY_RE.finditer(
                text
            )
        )

    def extract_party_names(
        self,
        text: str,
    ) -> list[str]:
        matches: list[
            tuple[int, str]
        ] = []

        for match in (
            self.LATIN_ORGANIZATION_RE
            .finditer(text)
        ):
            matches.append(
                (
                    match.start(),
                    match.group(0),
                )
            )

        for match in (
            self.ENGLISH_PERSON_ROLE_RE
            .finditer(text)
        ):
            matches.append(
                (
                    match.start(1),
                    match.group(1),
                )
            )

        for match in (
            self.ARABIC_ORGANIZATION_PREFIX_RE
            .finditer(text)
        ):
            value = (
                self._extract_arabic_name_after_marker(
                    text=text,
                    marker_start=match.start(),
                    marker_end=match.end(),
                    include_marker=True,
                    max_words=6,
                )
            )

            if value:
                matches.append(
                    (
                        match.start(),
                        value,
                    )
                )

        for match in (
            self.ARABIC_PERSON_ROLE_RE
            .finditer(text)
        ):
            value = (
                self._extract_arabic_name_after_marker(
                    text=text,
                    marker_start=match.start(),
                    marker_end=match.end(),
                    include_marker=False,
                    max_words=4,
                )
            )

            if value:
                matches.append(
                    (
                        match.end(),
                        value,
                    )
                )

        matches.sort(
            key=lambda item: item[0]
        )

        return self._deduplicate(
            value
            for _, value in matches
        )

    def extract_legal_terms(
        self,
        text: str,
    ) -> list[str]:
        matches: list[
            tuple[int, str]
        ] = []

        for pattern in (
            self.LEGAL_TERM_PATTERNS
        ):
            for match in pattern.finditer(
                text
            ):
                matches.append(
                    (
                        match.start(),
                        match.group(0),
                    )
                )

        matches.sort(
            key=lambda item: item[0]
        )

        return self._deduplicate(
            value
            for _, value in matches
        )

    def _extract_arabic_name_after_marker(
        self,
        *,
        text: str,
        marker_start: int,
        marker_end: int,
        include_marker: bool,
        max_words: int,
    ) -> str | None:
        """
        Conservatively collect Arabic name tokens after a known marker.

        This deliberately stops at common legal/query connector words
        instead of trying to perform general-purpose Arabic NER.
        """

        remainder = text[
            marker_end:
        ]

        token_matches = list(
            re.finditer(
                r"\S+",
                remainder,
            )
        )

        if not token_matches:
            return None

        collected = []

        for token_match in token_matches:
            token = token_match.group(0)

            cleaned = token.strip(
                "،,.;:!?؟()[]{}\"'"
            )

            if not cleaned:
                continue

            if (
                cleaned
                in self.ARABIC_NAME_STOPWORDS
            ):
                break

            if not any(
                "\u0600" <= character <= "\u06FF"
                for character in cleaned
            ):
                break

            collected.append(
                token_match
            )

            if (
                len(collected)
                >= max_words
            ):
                break

        if not collected:
            return None

        final_relative_end = (
            collected[-1].end()
        )

        if include_marker:
            result = text[
                marker_start:
                marker_end
                + final_relative_end
            ]
        else:
            result = remainder[
                collected[0].start():
                final_relative_end
            ]

        return result.strip().rstrip(
            "،,.;:!?؟"
        )

    @staticmethod
    def _deduplicate(
        values,
    ) -> list[str]:
        """
        Deduplicate while preserving original order and spelling.
        """

        result: list[str] = []
        seen: set[str] = set()

        for value in values:
            cleaned = value.strip()

            if not cleaned:
                continue

            key = cleaned.casefold()

            if key in seen:
                continue

            seen.add(
                key
            )

            result.append(
                cleaned
            )

        return result
