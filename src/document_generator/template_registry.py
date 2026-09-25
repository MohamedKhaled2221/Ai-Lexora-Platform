from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .errors import TemplateNotFoundError
from .schemas import TemplateDefinition


class TemplateRegistry:
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

    @classmethod
    def from_json(
        cls,
        file_path: str | Path,
    ) -> "TemplateRegistry":
        """
        Load template definitions from M5's
        template_requirements.json.
        """

        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(
                f"Template requirements file not found: {path}"
            )

        with path.open(
            "r",
            encoding="utf-8",
        ) as file:
            data = json.load(file)

        templates_data = data.get("templates", [])

        templates: List[TemplateDefinition] = []

        for template_data in templates_data:
            template = TemplateDefinition(
                template_id=template_data["template_id"],
                document_type=template_data["document_type"],
                jurisdiction=template_data["jurisdiction"],
                file_path=template_data.get("file_path"),
                version=template_data.get(
                    "version",
                    data.get("version", "1.0.0"),
                ),
                active=template_data.get(
                    "active",
                    True,
                ),
                fields=template_data.get(
                    "fields",
                    [],
                ),
                required_clauses=template_data.get(
                    "required_clauses",
                    [],
                ),
                optional_clauses=template_data.get(
                    "optional_clauses",
                    [],
                ),
                prohibited_clauses=template_data.get(
                    "prohibited_clauses",
                    [],
                ),
                conditional_clauses=template_data.get(
                    "conditional_clauses",
                    [],
                ),
                section_placeholders=template_data.get(
                    "section_placeholders",
                    {},
                ),
                template_structure=template_data.get(
                    "template_structure",
                ),
            )

            templates.append(template)

        return cls(templates)

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
