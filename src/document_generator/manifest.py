from __future__ import annotations

from typing import Any, Dict, Iterable, Optional
from uuid import uuid4

from .schemas import (
    AITransformation,
    ApprovedClause,
    AssembledDraft,
    GenerationManifest,
    GuidedDocumentRequest,
)


def build_generation_manifest(
    request: GuidedDocumentRequest,
    draft: AssembledDraft,
    clauses: Iterable[ApprovedClause],
    *,
    ai_transformation: Optional[AITransformation] = None,
    edits: Optional[list[Dict[str, Any]]] = None,
) -> GenerationManifest:
    return GenerationManifest.now(
        generation_id=str(uuid4()),
        draft_id=draft.draft_id,
        request_id=request.request_id,
        template_id=draft.template_id,
        template_version=draft.template_version,
        clause_refs=[
            {"clause_id": c.clause_id, "version": c.version}
            for c in clauses
        ],
        user_fields=request.fields,
        ai_transformation=ai_transformation or AITransformation(),
        edits=edits or [],
    )
