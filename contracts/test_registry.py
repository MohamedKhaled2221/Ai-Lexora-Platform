from m1.template_registry import TemplateRegistry


registry = TemplateRegistry.from_json(
    "data/template_requirements.json"
)

templates = registry.list_active()

print(f"Active templates: {len(templates)}")

for template in templates:
    print()
    print("Template ID:", template.template_id)
    print("Document Type:", template.document_type)
    print("Jurisdiction:", template.jurisdiction)
    print("Required:", template.required_clauses)
    print("Optional:", template.optional_clauses)
    print("Prohibited:", template.prohibited_clauses)
    print("Conditional:", template.conditional_clauses)