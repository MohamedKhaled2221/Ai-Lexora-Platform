from __future__ import annotations

from typing import Any, List, Optional

from .adapters import m1_payload_to_sections
from .classifier import ClauseClassifier
from .comparator import ClauseComparator
from .config import settings
from .entities import EntityExtractor
from .normalizer import detect_language
from .schemas import (
    ContractClause,
    Language,
    ReferenceClause,
    SourceLocation,
)
from .segmenter import ClauseSegmenter
from .similarity import SimilarityEngine


class ClauseIntelligencePipeline:
    """
    End-to-end M5 pipeline.

    M1 payload
        -> adapter
        -> segmentation
        -> classification
        -> entity extraction
        -> reference comparison
        -> ContractClause
    """

    def __init__(self):
        self.segmenter = ClauseSegmenter()

        self.classifier = ClauseClassifier(
            settings.classification_threshold,
            english_model=settings.english_classifier_model,
            arabic_model=settings.arabic_classifier_model,
            use_transformers=settings.use_transformers,
        )

        self.entity_extractor = EntityExtractor()

        self.similarity = SimilarityEngine(
            settings.similarity_model,
            settings.use_sentence_transformers,
        )

        self.comparator = ClauseComparator(
            self.similarity,
            settings.similarity_threshold,
        )

    def analyze(
        self,
        m1_payload: Any,
        reference_clauses: Optional[
            List[ReferenceClause]
        ] = None,
    ) -> List[ContractClause]:

        # ---------------------------------------------------------
        # 1. Convert actual M1 output into M5 internal sections.
        # ---------------------------------------------------------

        sections = m1_payload_to_sections(
            m1_payload
        )

        # ---------------------------------------------------------
        # 2. Segment sections into clause-like records.
        # ---------------------------------------------------------

        segmented = self.segmenter.segment(
            sections
        )

        references = (
            reference_clauses or []
        )

        results: List[ContractClause] = []

        # ---------------------------------------------------------
        # 3. Process each clause.
        # ---------------------------------------------------------

        for index, item in enumerate(
            segmented,
            start=1,
        ):

            # Preserve the complete legal text.
            original_text = item["text"]

            # Use the configured limit only for analysis components
            # that may need bounded input.
            analysis_text = (
                original_text[
                    : settings.max_text_chars
                ]
            )

            # -----------------------------------------------------
            # Language
            # -----------------------------------------------------

            language_value = (
                item.get("language")
                or detect_language(
                    original_text
                )
            )

            if (
                language_value
                in Language._value2member_map_
            ):
                language = Language(
                    language_value
                )
            else:
                language = Language.UNKNOWN

            # -----------------------------------------------------
            # Clause classification
            # -----------------------------------------------------

            clause_type, confidence, classification_meta = (
                self.classifier.classify(
                    analysis_text,
                    item.get("title"),
                    language.value,
                )
            )

            # -----------------------------------------------------
            # Entity extraction
            # -----------------------------------------------------

            entities = (
                self.entity_extractor.extract(
                    analysis_text
                )
            )

            # -----------------------------------------------------
            # Source metadata
            # -----------------------------------------------------

            metadata = dict(
                item.get("metadata") or {}
            )

            # -----------------------------------------------------
            # Build stable clause ID.
            # -----------------------------------------------------

            contract_clause_id = self._make_id(
                document_id=item[
                    "document_id"
                ],
                section_id=item.get(
                    "source_section_id"
                ),
                clause_number=item.get(
                    "clause_number"
                ),
                source_clause_id=metadata.get(
                    "source_clause_id"
                ),
                index=index,
            )

            # -----------------------------------------------------
            # Build M5 -> M6 contract.
            # -----------------------------------------------------

            clause = ContractClause(
                contract_clause_id=(
                    contract_clause_id
                ),

                document_id=item[
                    "document_id"
                ],

                source_section_id=item.get(
                    "source_section_id"
                ),

                clause_number=item.get(
                    "clause_number"
                ),

                title=item.get(
                    "title"
                ),

                # IMPORTANT:
                # Keep the complete original legal text.
                text=original_text,

                language=language,

                clause_type=clause_type,

                classification_confidence=round(
                    confidence,
                    6,
                ),

                entities=entities,

                source_location=SourceLocation(
                    page_start=item.get(
                        "page_start"
                    ),
                    page_end=item.get(
                        "page_end"
                    ),
                    section=item.get(
                        "section"
                    ),
                    clause_number=item.get(
                        "clause_number"
                    ),
                ),

                metadata=metadata,

                processing={
                    "pipeline": (
                        "m5_clause_intelligence"
                    ),
                    "classification": (
                        classification_meta
                    ),
                },
            )

            # -----------------------------------------------------
            # Reference comparison.
            # -----------------------------------------------------

            if references:

                clause.reference_match = (
                    self.comparator.compare(
                        clause,
                        references,
                    )
                )

            results.append(
                clause
            )

        return results

    @staticmethod
    def _make_id(
        document_id: str,
        section_id: str | None,
        clause_number: str | None,
        source_clause_id: str | None,
        index: int,
    ) -> str:

        parts = [
            document_id or "doc",
            section_id or "section",
            source_clause_id
            or clause_number
            or str(index),
        ]

        safe = "-".join(
            str(part)
            .strip()
            .replace(" ", "_")
            .replace("/", "-")
            for part in parts
        )

        return f"{safe}-clause"