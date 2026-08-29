from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from .normalizer import detect_language
from .schemas import M1ContractSection


CLAUSE_NUMBER_RE = re.compile(
    r"(?im)^\s*"
    r"(?:clause\s+)?"
    r"(\d+(?:\.\d+)*|[A-Z]\.\d+|\([a-z]\))"
    r"[).:\-]?\s+"
)


class ClauseSegmenter:
    """
    Segment M5 input into clause-like records.

    Priority:
        1. M1 structural clause
        2. M1 structural article/section
        3. Explicit clauses supplied by M1
        4. Numbered clause detection
        5. Paragraph fallback
        6. Whole-section fallback

    M1 remains the primary source of document structure.
    """

    def segment(
        self,
        sections: List[M1ContractSection],
    ) -> List[Dict[str, Any]]:

        output: List[Dict[str, Any]] = []

        for section in sections:

            metadata = section.metadata or {}

            structure = metadata.get(
                "m1_structure"
            )

            if not isinstance(structure, dict):
                structure = {}

            m1_unit_type = metadata.get(
                "m1_unit_type",
                "unstructured",
            )

            # ---------------------------------------------------------
            # 1. M1 explicitly identified a clause.
            # ---------------------------------------------------------

            m1_clause = structure.get(
                "clause"
            )

            if m1_clause is not None:

                output.append(
                    self._build_record(
                        section=section,
                        text=section.text.strip(),
                        index=1,
                        clause_number=str(
                            m1_clause
                        ),
                        source_clause_id=structure.get(
                            "clause_id"
                        ),
                    )
                )

                continue

            # ---------------------------------------------------------
            # 2. M1 explicitly identified an article or section.
            #
            # Important:
            # Do NOT split an M1 structural article/section into
            # paragraphs. M1 already decided this is one structural unit.
            # ---------------------------------------------------------

            if m1_unit_type in {
                "article",
                "section",
            }:

                output.append(
                    self._build_record(
                        section=section,
                        text=section.text.strip(),
                        index=1,
                        source_clause_id=structure.get(
                            "clause_id"
                        ),
                    )
                )

                continue

            # ---------------------------------------------------------
            # 3. Use explicit clauses supplied by M1.
            # ---------------------------------------------------------

            if section.clauses:

                section_records: List[
                    Dict[str, Any]
                ] = []

                for index, raw in enumerate(
                    section.clauses,
                    start=1,
                ):

                    if not isinstance(raw, dict):
                        continue

                    text = str(
                        raw.get("text")
                        or raw.get("content")
                        or ""
                    ).strip()

                    if not text:
                        continue

                    raw_structure = raw.get(
                        "structure"
                    )

                    if not isinstance(
                        raw_structure,
                        dict,
                    ):
                        raw_structure = {}

                    clause_number = (
                        raw.get("clause_number")
                        or raw.get("number")
                        or raw_structure.get("clause")
                    )

                    source_clause_id = (
                        raw.get("clause_id")
                        or raw_structure.get("clause_id")
                    )

                    section_records.append(
                        self._build_record(
                            section=section,
                            text=text,
                            index=index,
                            raw=raw,
                            clause_number=(
                                str(clause_number)
                                if clause_number is not None
                                else None
                            ),
                            source_clause_id=(
                                str(source_clause_id)
                                if source_clause_id is not None
                                else None
                            ),
                        )
                    )

                if section_records:

                    output.extend(
                        section_records
                    )

                    continue

            # ---------------------------------------------------------
            # 4. Regex fallback for numbered clauses.
            #
            # Used only when M1 did not provide structural information.
            # ---------------------------------------------------------

            text = section.text.strip()

            if not text:
                continue

            numbered = list(
                CLAUSE_NUMBER_RE.finditer(
                    text
                )
            )

            if len(numbered) >= 2:

                for index, match in enumerate(
                    numbered
                ):

                    start = match.start()

                    end = (
                        numbered[index + 1].start()
                        if index + 1 < len(numbered)
                        else len(text)
                    )

                    clause_text = text[
                        start:end
                    ].strip()

                    if not clause_text:
                        continue

                    output.append(
                        self._build_record(
                            section=section,
                            text=clause_text,
                            index=index + 1,
                            clause_number=match.group(1),
                        )
                    )

                continue

            # ---------------------------------------------------------
            # 5. Paragraph fallback.
            #
            # Only used when M1 has not already identified a structural
            # article/section/clause.
            # ---------------------------------------------------------

            paragraphs = [
                paragraph.strip()
                for paragraph in re.split(
                    r"\n{2,}",
                    text,
                )
                if paragraph.strip()
            ]

            if len(paragraphs) > 1:

                for index, paragraph in enumerate(
                    paragraphs,
                    start=1,
                ):

                    output.append(
                        self._build_record(
                            section=section,
                            text=paragraph,
                            index=index,
                        )
                    )

                continue

            # ---------------------------------------------------------
            # 6. Whole-section fallback.
            # ---------------------------------------------------------

            output.append(
                self._build_record(
                    section=section,
                    text=text,
                    index=1,
                )
            )

        return output

    def _build_record(
        self,
        section: M1ContractSection,
        text: str,
        index: int,
        raw: Optional[Dict[str, Any]] = None,
        clause_number: Optional[str] = None,
        source_clause_id: Optional[str] = None,
    ) -> Dict[str, Any]:

        raw = raw or {}

        metadata = dict(
            section.metadata or {}
        )

        # ---------------------------------------------------------
        # Merge clause-level metadata.
        # ---------------------------------------------------------

        raw_metadata = raw.get(
            "metadata"
        )

        if isinstance(
            raw_metadata,
            dict,
        ):
            metadata.update(
                raw_metadata
            )

        # ---------------------------------------------------------
        # Preserve source chunk ID.
        # ---------------------------------------------------------

        source_chunk_id = metadata.get(
            "source_chunk_id"
        )

        if source_chunk_id is not None:
            metadata[
                "source_chunk_id"
            ] = str(
                source_chunk_id
            )

        # ---------------------------------------------------------
        # Preserve source clause ID.
        # ---------------------------------------------------------

        if source_clause_id is not None:

            metadata[
                "source_clause_id"
            ] = str(
                source_clause_id
            )

        # ---------------------------------------------------------
        # M1 structure.
        # ---------------------------------------------------------

        structure = metadata.get(
            "m1_structure"
        )

        if not isinstance(
            structure,
            dict,
        ):
            structure = {}

        # ---------------------------------------------------------
        # Do not invent a clause number.
        # ---------------------------------------------------------

        number = (
            clause_number
            or raw.get("clause_number")
            or raw.get("number")
        )

        if number is not None:
            number = str(number)

        # ---------------------------------------------------------
        # Language.
        # ---------------------------------------------------------

        language = (
            raw.get("language")
            or section.language.value
        )

        language = str(
            language
        ).lower()

        if language not in {
            "ar",
            "en",
            "ar-en",
            "unknown",
        }:

            language = detect_language(
                text
            )

        if language == "mixed":
            language = "ar-en"

        # ---------------------------------------------------------
        # Section / article context.
        # ---------------------------------------------------------

        section_name = (
            raw.get("section")
            or structure.get("section")
            or structure.get("article")
            or section.section
            or section.title
        )

        # ---------------------------------------------------------
        # Title.
        # ---------------------------------------------------------

        title = (
            raw.get("title")
            or structure.get("title")
            or section.title
        )

        # ---------------------------------------------------------
        # Page provenance.
        # ---------------------------------------------------------

        page_start = raw.get(
            "page_start",
            section.page_start,
        )

        page_end = raw.get(
            "page_end",
            section.page_end,
        )

        return {
            "document_id": section.document_id,

            "source_section_id": (
                raw.get("section_id")
                or section.section_id
            ),

            "section": section_name,

            "title": title,

            "clause_number": number,

            # Preserve original legal text.
            "text": text,

            "language": language,

            "page_start": page_start,

            "page_end": page_end,

            "metadata": metadata,
        }