"""
Controlled multilingual query variants for M2.

This module does not translate complete legal questions.

It adds tightly controlled cross-language equivalents for known
legal concepts while preserving exact identifiers extracted from
the original query.

The original user query remains separately available through
ProcessedQuery.text_original.
"""

from __future__ import annotations

import re
import unicodedata

from src.schemas.m2_contract import (
    IdentifierSet,
)


class QueryVariantBuilder:
    """
    Build deterministic search variants for Arabic, English,
    and Arabic-English mixed legal queries.

    Arabizi processing is intentionally outside the current scope.
    """

    # -----------------------------------------------------
    # Controlled bilingual legal concept catalogue
    # -----------------------------------------------------

    LEGAL_CONCEPTS = (
        {
            "english": (
                "termination",
                "termination of contract",
            ),
            "arabic": (
                "إنهاء العقد",
                "انهاء العقد",
                "فسخ العقد",
            ),
        },
        {
            "english": (
                "force majeure",
            ),
            "arabic": (
                "القوة القاهرة",
            ),
        },
        {
            "english": (
                "governing law",
            ),
            "arabic": (
                "القانون الحاكم",
            ),
        },
        {
            "english": (
                "confidentiality",
            ),
            "arabic": (
                "السرية",
            ),
        },
        {
            "english": (
                "non-disclosure agreement",
            ),
            "arabic": (
                "اتفاقية عدم الإفصاح",
                "اتفاقية عدم الافصاح",
            ),
        },
        {
            "english": (
                "breach of contract",
            ),
            "arabic": (
                "الإخلال بالعقد",
                "الاخلال بالعقد",
            ),
        },
        {
            "english": (
                "liquidated damages",
            ),
            "arabic": (
                "الشرط الجزائي",
            ),
        },
        {
            "english": (
                "limitation of liability",
            ),
            "arabic": (
                "تحديد المسؤولية",
            ),
        },
        {
            "english": (
                "intellectual property",
            ),
            "arabic": (
                "الملكية الفكرية",
            ),
        },
        {
            "english": (
                "indemnity",
            ),
            "arabic": (
                "التعويض",
            ),
        },
        {
            "english": (
                "arbitration",
            ),
            "arabic": (
                "التحكيم",
            ),
        },
        {
            "english": (
                "jurisdiction",
            ),
            "arabic": (
                "الاختصاص القضائي",
            ),
        },
    )

    ARABIC_DIACRITICS_RE = re.compile(
        r"[\u0610-\u061A"
        r"\u064B-\u065F"
        r"\u0670"
        r"\u06D6-\u06ED]"
    )

    def build(
        self,
        *,
        normalized_text: str,
        language: str,
        identifiers: IdentifierSet,
    ) -> list[str]:
        """
        Build ordered, deduplicated query variants.

        Rules:
        1. normalized_text is always the first search variant;
        2. exact legal identifiers are restored if normalization
           changed them;
        3. known legal concepts may receive one controlled
           cross-language equivalent;
        4. complete-sentence machine translation is never performed.
        """

        if not normalized_text.strip():
            return []

        base_variant = (
            self._restore_exact_identifiers(
                normalized_text,
                identifiers,
            )
        )

        variants = [
            base_variant
        ]

        cross_language_terms = (
            self._cross_language_terms(
                base_variant=base_variant,
                language=language,
                identifiers=identifiers,
            )
        )

        if cross_language_terms:
            expanded = " ".join(
                [
                    base_variant,
                    *cross_language_terms,
                ]
            )

            variants.append(
                expanded
            )

        return self._deduplicate(
            variants
        )

    # -----------------------------------------------------
    # Cross-language legal concept expansion
    # -----------------------------------------------------

    def _cross_language_terms(
        self,
        *,
        base_variant: str,
        language: str,
        identifiers: IdentifierSet,
    ) -> list[str]:
        additions: list[str] = []

        for extracted_term in (
            identifiers.named_legal_terms
        ):
            concept = self._find_concept(
                extracted_term
            )

            if concept is None:
                continue

            candidates: list[str] = []

            if language == "en":
                candidates.append(
                    concept["arabic"][0]
                )

            elif language == "ar":
                candidates.append(
                    concept["english"][0]
                )

            elif language == "ar-en":
                candidates.extend(
                    [
                        concept["english"][0],
                        concept["arabic"][0],
                    ]
                )

            else:
                # Unknown language:
                # don't guess a translation direction.
                continue

            for candidate in candidates:
                if self._contains_equivalent(
                    base_variant,
                    candidate,
                ):
                    continue

                if any(
                    self._contains_equivalent(
                        existing,
                        candidate,
                    )
                    for existing in additions
                ):
                    continue

                additions.append(
                    candidate
                )

        return additions

    def _find_concept(
        self,
        term: str,
    ):
        term_key = self._comparison_key(
            term
        )

        for concept in self.LEGAL_CONCEPTS:
            all_terms = (
                *concept["english"],
                *concept["arabic"],
            )

            if any(
                self._comparison_key(
                    candidate
                )
                == term_key
                for candidate in all_terms
            ):
                return concept

        return None

    # -----------------------------------------------------
    # Exact identifier preservation
    # -----------------------------------------------------

    def _restore_exact_identifiers(
        self,
        text: str,
        identifiers: IdentifierSet,
    ) -> str:
        """
        Ensure exact values extracted from the original query remain
        available in every search variant.

        This is especially relevant where Arabic normalization may
        alter alef forms inside a party name or legal term.
        """

        additions: list[str] = []

        exact_values = (
            *identifiers.article_numbers,
            *identifiers.case_numbers,
            *identifiers.dates,
            *identifiers.monetary_values,
            *identifiers.party_names,
            *identifiers.named_legal_terms,
        )

        current = text.casefold()

        for value in exact_values:
            cleaned = value.strip()

            if not cleaned:
                continue

            if cleaned.casefold() in current:
                continue

            if any(
                cleaned.casefold()
                == existing.casefold()
                for existing in additions
            ):
                continue

            additions.append(
                cleaned
            )

        if not additions:
            return text

        return " ".join(
            [
                text,
                *additions,
            ]
        )

    # -----------------------------------------------------
    # Comparison helpers
    # -----------------------------------------------------

    def _contains_equivalent(
        self,
        text: str,
        term: str,
    ) -> bool:
        text_key = self._comparison_key(
            text
        )

        term_key = self._comparison_key(
            term
        )

        return term_key in text_key

    def _comparison_key(
        self,
        text: str,
    ) -> str:
        """
        Normalize only for internal comparison.

        This value is never returned to the caller and therefore
        cannot alter the user's legal query.
        """

        value = unicodedata.normalize(
            "NFC",
            text,
        )

        value = value.replace(
            "\u0640",
            "",
        )

        value = (
            self.ARABIC_DIACRITICS_RE.sub(
                "",
                value,
            )
        )

        value = (
            value
            .replace("أ", "ا")
            .replace("إ", "ا")
            .replace("آ", "ا")
        )

        value = re.sub(
            r"\s+",
            " ",
            value,
        )

        return (
            value.strip().casefold()
        )

    @staticmethod
    def _deduplicate(
        values,
    ) -> list[str]:
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
