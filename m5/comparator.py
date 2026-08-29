from __future__ import annotations

from typing import List, Optional

from .schemas import (
    ContractClause,
    DeviationType,
    ReferenceClause,
    ReferenceMatch,
)
from .similarity import SimilarityEngine


class ClauseComparator:
    """
    Compare a contract clause against approved/reference clauses.

    M5 provides comparison evidence only.
    Final legal risk/severity belongs to M6.
    """

    def __init__(
        self,
        similarity: SimilarityEngine,
        threshold: float = 0.70,
    ):
        self.similarity = similarity
        self.threshold = threshold

    def compare(
        self,
        clause: ContractClause,
        references: List[ReferenceClause],
    ) -> Optional[ReferenceMatch]:

        # No reference available.
        # The caller can handle this as "no reference".
        if not references:
            return None

        # Prefer references with the same clause type.
        candidates = [
            reference
            for reference in references
            if (
                reference.clause_type is None
                or reference.clause_type
                == clause.clause_type
            )
        ]

        # If no type-compatible references exist,
        # fall back to the complete reference set.
        if not candidates:
            candidates = references

        best_ref: Optional[ReferenceClause] = None
        best_score = -1.0

        for reference in candidates:

            score = self.similarity.score(
                clause.text,
                reference.text,
            )

            if score > best_score:
                best_score = score
                best_ref = reference

        if best_ref is None:
            return None

        reasons: List[str] = []

        # Reference and contract clause types differ.
        if (
            best_ref.clause_type is not None
            and best_ref.clause_type
            != clause.clause_type
        ):
            reasons.append(
                "reference clause type differs"
            )

        # Compare semantic similarity against the
        # configured baseline threshold.
        if best_score >= self.threshold:

            deviation = DeviationType.MATCHED

        else:

            deviation = DeviationType.MODIFIED

            reasons.append(
                "semantic similarity is below "
                "configured match threshold"
            )

        # A prohibited/rejected/revoked reference
        # overrides similarity classification.
        approval_status = (
            best_ref.approval_status or ""
        ).strip().lower()

        if approval_status in {
            "prohibited",
            "rejected",
            "revoked",
        }:

            deviation = DeviationType.PROHIBITED

            reasons.append(
                "reference clause is marked "
                "prohibited/rejected/revoked"
            )

        # This is a heuristic comparison confidence,
        # not a calibrated probability.
        confidence = max(
            0.20,
            min(
                0.99,
                best_score,
            ),
        )

        return ReferenceMatch(
            reference_clause_id=(
                best_ref.reference_clause_id
            ),
            similarity_score=round(
                best_score,
                6,
            ),
            deviation=deviation,
            comparison_confidence=round(
                confidence,
                6,
            ),
            reasons=reasons,
        )