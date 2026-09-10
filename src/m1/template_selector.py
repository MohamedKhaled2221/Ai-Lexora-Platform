from __future__ import annotations

from .errors import TemplateNotFoundError
from .schemas import GuidedDocumentRequest, TemplateDefinition
from .template_registry import TemplateRegistry


class TemplateSelector:
    def __init__(self, registry: TemplateRegistry):
        self.registry = registry

    def select(
        self,
        request: GuidedDocumentRequest,
    ) -> TemplateDefinition:

        candidates = [
            template
            for template in self.registry.list_active()
            if (
                template.document_type.lower()
                == request.document_type.lower()
                and template.jurisdiction.lower()
                == request.jurisdiction.lower()
            )
        ]

        if not candidates:
            raise TemplateNotFoundError(
                "No active template found for "
                f"{request.document_type}/{request.jurisdiction}"
            )

        # Select the latest template version.
        selected_template = sorted(
            candidates,
            key=lambda template: template.version,
        )[-1]

        return selected_template