"""
M5 Clause Engine — مكتبة البنود القانونية المعتمدة وقواعد التوليد.
"""

from .approval_workflow import (
    ApprovalWorkflow,
    ApprovalWorkflowError,
    InvalidTransitionError,
)
from .clause_library import (
    ClauseLibrary,
    ClauseLibraryError,
    ClauseNotFoundError,
    DuplicateClauseError,
)
from .compatibility_engine import CompatibilityEngine
from .required_clause_rules import RequiredClauseEngine
from .service import M5ClauseService
from .special_condition_resolver import (
    SpecialConditionResolver,
)
from .traceability import ClauseTraceability
from .versioning import ClauseVersionManager, VersioningError


__all__ = [
    # Service
    "M5ClauseService",
    # Clause Library
    "ClauseLibrary",
    "ClauseLibraryError",
    "ClauseNotFoundError",
    "DuplicateClauseError",
    # Compatibility
    "CompatibilityEngine",
    # Required Rules
    "RequiredClauseEngine",
    # Approval
    "ApprovalWorkflow",
    "ApprovalWorkflowError",
    "InvalidTransitionError",
    # Versioning
    "ClauseVersionManager",
    "VersioningError",
    # Special Conditions
    "SpecialConditionResolver",
    # Traceability
    "ClauseTraceability",
]
