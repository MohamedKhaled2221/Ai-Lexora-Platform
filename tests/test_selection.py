from src.m1.template_registry import TemplateRegistry
from src.m1.template_selector import TemplateSelector
from src.m1.schemas import GuidedDocumentRequest


registry = TemplateRegistry.from_json(
    "data/template_requirements.json"
)

selector = TemplateSelector(registry)

request = GuidedDocumentRequest(
    request_id="REQ-001",
    document_type="nda",
    jurisdiction="EG",
)

template = selector.select(request)

print("Selected Template:")
print("ID:", template.template_id)
print("Version:", template.version)
print("Document Type:", template.document_type)
print("Jurisdiction:", template.jurisdiction)

print()
print("Required Clauses:")
for clause_id in template.required_clauses:
    print("-", clause_id)

print()
print("Optional Clauses:")
for clause_id in template.optional_clauses:
    print("-", clause_id)

print()
print("Prohibited Clauses:")
for clause_id in template.prohibited_clauses:
    print("-", clause_id)

print()
print("Conditional Clauses:")
for condition in template.conditional_clauses:
    print(
        "-",
        condition.clause_id,
        "| condition:",
        condition.condition,
    )