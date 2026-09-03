"""M5 - Contract Clause Intelligence.

Transforms M1 contract sections/clauses into structured ContractClause objects
for M6's Contract Risk Engine.
"""

from .pipeline import ClauseIntelligencePipeline
from .schemas import ContractClause, M1ContractSection, ReferenceClause

__all__ = [
    "ClauseIntelligencePipeline",
    "ContractClause",
    "M1ContractSection",
    "ReferenceClause",
]
