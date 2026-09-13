from __future__ import annotations

from typing import Any, Dict, List

from .schemas import ContractClause


def contract_clause_to_m6(
    clause: ContractClause,
) -> Dict[str, Any]:
    """
    Convert one internal M5 ContractClause
    into an M6-compatible payload while preserving
    source and provenance information from M1.
    """

    # ---------------------------------------------------------
    # Convert M5 entities:
    #
    # List[LegalEntity]
    #
    # into:
    #
    # Dict[str, Any]
    # ---------------------------------------------------------

    entities: Dict[str, Any] = {}

    for entity in clause.entities:
        entities.setdefault(
            entity.entity_type,
            [],
        ).append(
            {
                "value": entity.value,
                "normalized_value": entity.normalized_value,
                "start": entity.start,
                "end": entity.end,
                "confidence": entity.confidence,
            }
        )

    # ---------------------------------------------------------
    # Reference comparison
    # ---------------------------------------------------------

    if clause.reference_match is not None:

        similarity_score = (
            clause.reference_match.similarity_score
        )

        is_modified = (
            clause.reference_match.deviation.value
            == "modified"
        )

        confidence = clause.classification_confidence

    else:

        similarity_score = 0.0
        is_modified = False

        confidence = (
            clause.classification_confidence
        )

    # ---------------------------------------------------------
    # Page
    # ---------------------------------------------------------

    page = clause.source_location.page_start

    if page is None:
        page = 0

    # ---------------------------------------------------------
    # Source / Provenance
    #
    # Preserve the information originally received from M1.
    # The metadata field contains M1-specific information such
    # as source_chunk_id, source_clause_id, bbox, structure,
    # page spans, character spans, etc.
    # ---------------------------------------------------------

    source: Dict[str, Any] = {
        "document_id": clause.document_id,
        "source_section_id": clause.source_section_id,
        "clause_number": clause.clause_number,
        "title": clause.title,
        "language": clause.language.value,

        "page_start": (
            clause.source_location.page_start
        ),
        "page_end": (
            clause.source_location.page_end
        ),
        "section": (
            clause.source_location.section
        ),

        "metadata": clause.metadata,
    }

    # ---------------------------------------------------------
    # M6 payload
    #
    # Keep the existing M6 fields unchanged and add the
    # preserved source/provenance information.
    # ---------------------------------------------------------

    return {
        "clause_id": clause.contract_clause_id,
        "type": clause.clause_type.value,
        "text": clause.text,
        "entities": entities,
        "page": page,
        "similarity_score": similarity_score,
        "is_modified": is_modified,
        "confidence": confidence,

        "source": source,
    }


def contracts_to_m6(
    clauses: List[ContractClause],
) -> List[Dict[str, Any]]:
    """
    Convert all M5 ContractClause objects
    into M6-compatible objects while preserving
    source and provenance information.
    """

    return [
        contract_clause_to_m6(clause)
        for clause in clauses
    ]
