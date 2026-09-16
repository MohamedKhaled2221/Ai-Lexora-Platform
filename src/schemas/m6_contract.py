from typing import Optional, Dict, Any, List

from pydantic import BaseModel, Field, computed_field


class ContractClause(BaseModel):
    """
    Input contract received from M5 and consumed by M6.
    """

    clause_id: str

    type: str

    text: str

    entities: Dict[str, Any] = Field(default_factory=dict)

    page: int

    similarity_score: float

    is_modified: bool

    confidence: float

    # Frontend location metadata
    source_section_id: Optional[str] = None

    source_chunk_id: Optional[str] = None

    page_start: Optional[int] = None

    page_end: Optional[int] = None

    # Bounding box as received from M5
    bbox: Optional[Dict[str, Any]] = None

    # Multiple bounding boxes as received from M5
    bboxes: Optional[List[Dict[str, Any]]] = None


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

    @computed_field
    @property
    def color_code(self) -> str:
        """
        Frontend-friendly alias for severity_color.

        This keeps severity_color available for backward compatibility
        while also returning color_code for the frontend.
        """
        return self.severity_color

    explanation: str

    evidence: str

    page: int

    clause: str

    confidence: float

    review_status: str

    # Frontend location metadata
    source_section_id: Optional[str] = None

    source_chunk_id: Optional[str] = None

    page_start: Optional[int] = None

    page_end: Optional[int] = None

    # Bounding box as received from M5
    bbox: Optional[Dict[str, Any]] = None

    # Multiple bounding boxes as received from M5
    bboxes: Optional[List[Dict[str, Any]]] = None

    # Rule provenance
    rule_id: str

    rule_type: str

    legal_reference: Optional[dict] = None