from src.schemas.m6_contract import ContractClause

TYPE_MAPPING = {
    "termination": "Termination",
    "liability": "Liability",
    "payment": "Payment",
    "confidentiality": "Confidentiality",
    "renewal": "Renewal",
    "penalty": "Penalty",
    "governing_law": "Governing Law",
    "dispute_resolution": "Dispute Resolution",
}


def normalize_clause_type(clause_type: str) -> str:
    """
    Convert M5 clause type into the standardized
    M6 clause type used by the Legal Playbook.
    """

    if not clause_type:
        return "Unknown"

    normalized = clause_type.strip().lower()

    return TYPE_MAPPING.get(
        normalized,
        "Unknown"
    )


def convert_m5_clause(data: dict) -> ContractClause:
    """
    Convert one M5 clause into an M6 ContractClause.
    """

    return ContractClause(
        clause_id=data["clause_id"],

        type=normalize_clause_type(
            data.get("type", "unknown")
        ),

        text=data["text"],

        entities=data.get(
            "entities",
            {}
        ),

        page=data.get(
            "page",
            0
        ),

        similarity_score=data.get(
            "similarity_score",
            1.0
        ),

        is_modified=data.get(
            "is_modified",
            False
        ),

        confidence=data.get(
            "confidence",
            0.0
        ),
    )


def convert_m5_payload(
    data: dict
) -> list[ContractClause]:
    """
    Convert the complete M5 output into
    a list of M6 ContractClause objects.
    """

    clauses = data.get(
        "clauses",
        []
    )

    if not isinstance(clauses, list):
        raise ValueError(
            "M5 payload 'clauses' must be a list."
        )

    return [
        convert_m5_clause(clause)
        for clause in clauses
    ]