from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from .errors import TemplateNotFoundError
from .schemas import TemplateDefinition


class TemplateRegistry:
    """
    Registry of M1-owned document templates only.

    M5 clause requirements are not loaded here. They arrive
    separately through TemplateClauseRequirement.
    """

    def __init__(
        self,
        templates: Iterable[TemplateDefinition] = (),
    ):
        self._templates: Dict[
            tuple[str, str],
            TemplateDefinition,
        ] = {}

        for template in templates:
            self.register(template)

    def register(
        self,
        template: TemplateDefinition,
    ) -> None:
        self._templates[
            (template.template_id, template.version)
        ] = template

    def get(
        self,
        template_id: str,
        version: Optional[str] = None,
    ) -> TemplateDefinition:

        matches = [
            template
            for (
                template_id_key,
                _,
            ), template in self._templates.items()
            if (
                template_id_key == template_id
                and template.active
            )
        ]

        if version is not None:
            for template in matches:
                if template.version == version:
                    return template

        if matches:
            return sorted(
                matches,
                key=lambda template: template.version,
            )[-1]

        raise TemplateNotFoundError(
            f"Template not found: {template_id}"
        )

    def list_active(
        self,
    ) -> List[TemplateDefinition]:

        return [
            template
            for template in self._templates.values()
            if template.active
        ]