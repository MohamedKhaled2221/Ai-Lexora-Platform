from __future__ import annotations

import re

from typing import List

from .schemas import LegalEntity


MONEY_RE = re.compile(
    r"(?i)(?:USD|EUR|GBP|EGP|\$|€|£|جنيه|دولار)"
    r"\s*[\d,]+(?:\.\d+)?"
)

PERCENT_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s*%"
)

DURATION_RE = re.compile(
    r"(?i)"
    r"\b\d+(?:\.\d+)?\s*(?:days?|weeks?|months?|years?)\b"
    r"|"
    r"(?:\d+)\s*(?:يوم|أيام|أسبوع|أسابيع|شهر|أشهر|سنة|سنوات)"
)

NOTICE_RE = re.compile(
    r"(?i)\b(?:written\s+notice|notice)\b"
    r"|(?:إخطار|إشعار)"
)

DATE_RE = re.compile(
    r"\b"
    r"(?:"
    r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"
    r"|"
    r"\d{4}[/-]\d{1,2}[/-]\d{1,2}"
    r")"
    r"\b"
)

ARTICLE_RE = re.compile(
    r"(?i)\b"
    r"(?:article|clause|section|المادة|البند)"
    r"\s*[\w.-]+"
    r"\b"
)


class EntityExtractor:
    """
    Lightweight rule-based legal entity extraction.

    This is a baseline extractor, not a full legal NER model.

    Extracted entities are high-value structured terms that can
    support downstream comparison and risk analysis.
    """

    def extract(
        self,
        text: str,
    ) -> List[LegalEntity]:

        if not text:
            return []

        entities: List[LegalEntity] = []

        patterns = [
            ("money", MONEY_RE),
            ("percentage", PERCENT_RE),
            ("duration", DURATION_RE),
            ("notice", NOTICE_RE),
            ("date", DATE_RE),
            ("legal_reference", ARTICLE_RE),
        ]

        for entity_type, pattern in patterns:

            for match in pattern.finditer(text):

                value = match.group(0).strip()

                if not value:
                    continue

                entities.append(
                    LegalEntity(
                        entity_type=entity_type,
                        value=value,
                        normalized_value=value.lower(),
                        start=match.start(),
                        end=match.end(),
                        # Heuristic confidence only.
                        confidence=0.90,
                    )
                )

        # Remove exact duplicate entities.
        unique = {}

        for entity in entities:

            key = (
                entity.entity_type,
                entity.start,
                entity.end,
                entity.value,
            )

            unique[key] = entity

        return list(unique.values())