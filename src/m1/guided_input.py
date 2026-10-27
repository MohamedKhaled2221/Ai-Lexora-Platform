from __future__ import annotations

from typing import Any, Dict, List
from .errors import ValidationError
from .schemas import GuidedDocumentRequest, TemplateDefinition


def validate_guided_input(request: GuidedDocumentRequest, template: TemplateDefinition) -> None:
    if request.document_type != template.document_type:
        raise ValidationError("Document type mismatch")
    if request.jurisdiction != template.jurisdiction:
        raise ValidationError("Jurisdiction mismatch")

    missing: List[str] = []
    for field in template.fields:
        if field.required:
            value = request.fields.get(field.name)
            if value is None or (isinstance(value, str) and not value.strip()):
                missing.append(field.name)

    if missing:
        raise ValidationError("Missing required fields: " + ", ".join(missing))


def validate_field_types(request: GuidedDocumentRequest, template: TemplateDefinition) -> None:
    definitions: Dict[str, Any] = {f.name: f for f in template.fields}

    for name, value in request.fields.items():
        definition = definitions.get(name)
        if not definition:
            raise ValidationError(f"Unknown input field: {name}")

        if definition.field_type == "boolean" and not isinstance(value, bool):
            raise ValidationError(f"Field {name} must be boolean")

        if definition.field_type in {"number", "currency"}:
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ValidationError(f"Field {name} must be numeric")

        if definition.field_type == "select" and value not in definition.options:
            raise ValidationError(f"Field {name} has an invalid option")
