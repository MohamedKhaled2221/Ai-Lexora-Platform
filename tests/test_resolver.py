from src.m1.template_registry import TemplateRegistry
from src.m1.template_selector import TemplateSelector
from src.m1.clause_library import ClauseLibrary
from src.m1.template_clause_resolver import TemplateClauseResolver
from src.m1.schemas import GuidedDocumentRequest


template_registry = TemplateRegistry.from_json(
    "data/template_requirements.json"
)

clause_library = ClauseLibrary.from_json(
    "data/clause_library.json"
)

selector = TemplateSelector(template_registry)

request = GuidedDocumentRequest(
    request_id="REQ-001",
    document_type="nda",
    jurisdiction="EG",
)

template = selector.select(request)

resolver = TemplateClauseResolver(
    clause_library
)

required_clauses = resolver.resolve_required(
    template
)

print("Template:")
print(template.template_id)

print()
print("Resolved Required Clauses:")

for clause in required_clauses:
    print(
        "-",
        clause.clause_id,
        "|",
        clause.type,
        "|",
        clause.jurisdiction,
    )

print()
print("Decisions:")

decisions = resolver.build_decisions(template)

for decision in decisions:
    print(
        "-",
        decision.clause_id,
        "|",
        decision.decision,
        "|",
        decision.reason,
    )