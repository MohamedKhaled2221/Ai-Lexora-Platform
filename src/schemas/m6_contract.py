from typing import Optional, Dict, Any

from pydantic import BaseModel, computed_field


class ContractClause(BaseModel):
    """
    Input contract received from M5 and consumed by M6.
    """

    clause_id: str

    type: str

    text: str

    entities: Dict[str, Any] = {}

    page: int

    similarity_score: float

    is_modified: bool

    confidence: float


class ContractRisk(BaseModel):
    """
    Risk result produced by M6.
    """

    risk: str

    severity: str

    @computed_field
    @property
    def severity_color(self) -> str:
        severity_colors = {
            "low": "green",
            "medium": "yellow",
            "high": "red",
            "critical": "dark_red",
        }

        return severity_colors.get(
            self.severity.strip().lower(),
            "gray",
        )

    explanation: str

    evidence: str

    page: int

    clause: str

    confidence: float

    review_status: str

    # Rule provenance
    rule_id: str

    rule_type: str

    legal_reference: Optional[dict] = None