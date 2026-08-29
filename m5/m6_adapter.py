from __future__ import annotations

from typing import Any, Dict, List

from .schemas import ContractClause


def contract_clause_to_m6(
    clause: ContractClause,
) -> Dict[str, Any]:
    """
    Convert one internal M5 ContractClause
    into the exact payload expected by M6.
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
    # Exact M6 contract
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
    }


def contracts_to_m6(
    clauses: List[ContractClause],
) -> List[Dict[str, Any]]:
    """
    Convert all M5 ContractClause objects
    into M6-compatible objects.
    """

    return [
        contract_clause_to_m6(clause)
        for clause in clauses
    ]