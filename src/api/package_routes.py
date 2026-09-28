from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    status,
)
from fastapi.responses import FileResponse

from src.api.dependencies import (
    get_p3_generation_runtime,
    get_p4_chat_service,
)
from src.api.identity import (
    CallerIdentityDependency,
    apply_access_scope,
    reject_client_supplied_access,
)
from src.api.package_runtime import (
    P3APIRuntime,
)
from src.api.schemas import (
    P3GenerateRequest,
    P3GenerateResponse,
    P3TemplateFieldResponse,
    P3TemplateSummary,
    P3TemplatesResponse,
    P4ChatRequest,
)
from src.document_generator.errors import (
    TemplateNotFoundError,
    ValidationError as M1ValidationError,
)
from src.orchestration import (
    CitationValidationError,
    M2EmbeddingContractError,
    M2QueryRuntimeError,
    M2QueryValidationError,
    M4LLMConnectionError,
    M4LLMInvocationError,
)
from src.orchestration.m5_grounding_adapter import (
    M5GroundingAdapterError,
)
from src.orchestration.p3_generation_service import (
    P3GenerationIntegrationError,
)
from src.orchestration.p3_orchestrator import (
    P3ValidationContractError,
)
from src.orchestration.p4_chat_service import (
    P4ChatService,
    P4RetrievalContractError,
    P4RetrievalPolicyError,
)
from src.orchestration.p4_orchestrator import (
    P4GroundingValidationError,
)
from src.retrieval.reranker import (
    RerankerUnavailable,
)
from src.schemas.p4_chat_contract import (
    ValidatedAIResponse,
)


logger = logging.getLogger(
    "src.api.package_routes"
)


router = APIRouter(
    prefix="/api/v1",
)


P3Dependency = Annotated[
    P3APIRuntime,
    Depends(
        get_p3_generation_runtime
    ),
]


P4Dependency = Annotated[
    P4ChatService,
    Depends(
        get_p4_chat_service
    ),
]


# =========================================================
# Package 3 - Available Templates
# =========================================================


@router.get(
    "/p3/templates",
    response_model=P3TemplatesResponse,
    tags=["Package 3"],
)
async def list_package3_templates(
    runtime: P3Dependency,
    identity: CallerIdentityDependency,
) -> P3TemplatesResponse:
    """
    Return the enabled Package 3 templates
    and their guided-input fields.

    Template definitions are loaded once by the
    P3 runtime from the configured M1 template registry.
    """

    # Require the same caller-identity boundary
    # used by Package 3 generation.
    _ = identity

    return P3TemplatesResponse(
        templates=[
            P3TemplateSummary(
                template_id=template.template_id,
                document_type=template.document_type,
                jurisdiction=template.jurisdiction,
                fields=[
                    P3TemplateFieldResponse(
                        name=field.name,
                        label=field.label,
                        field_type=field.field_type,
                        required=field.required,
                    )
                    for field in template.fields
                ],
            )
            for template in runtime.templates
        ]
    )


# =========================================================
# Package 3 - Document Generation
# =========================================================


@router.post(
    "/p3/generate",
    response_model=P3GenerateResponse,
    tags=["Package 3"],
)
async def generate_package3(
    request_body: P3GenerateRequest,
    request: Request,
    runtime: P3Dependency,
    identity: CallerIdentityDependency,
) -> P3GenerateResponse:

    # Identity dependency is deliberate even though
    # Package 3 does not use retrieval ACLs.
    _ = identity

    docx_path = None
    file_name = None

    if request_body.export_docx:
        file_name = (
            f"{uuid.uuid4().hex}.docx"
        )

        docx_path = str(
            runtime.export_dir
            / file_name
        )

    try:
        result = await asyncio.to_thread(
            runtime.service.generate,
            request=request_body.request,
            clause_language=(
                request_body.clause_language
            ),
            active_conditions=(
                request_body
                .request
                .special_conditions
            ),
            optional_clause_ids=(
                request_body
                .request
                .requested_clause_ids
            ),
            docx_path=docx_path,
        )

    except (
        P3GenerationIntegrationError,
        P3ValidationContractError,
        TemplateNotFoundError,
        M1ValidationError,
        ValueError,
    ) as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_400_BAD_REQUEST
            ),
            detail=(
                "Package 3 generation request "
                "is invalid."
            ),
        ) from exc

    except M5GroundingAdapterError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_422_UNPROCESSABLE_ENTITY
            ),
            detail=(
                "Package 3 references an "
                "unavailable or unusable "
                "approved clause."
            ),
        ) from exc

    except M4LLMConnectionError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail=(
                "The local Package 3 AI "
                "validation runtime is unavailable."
            ),
        ) from exc

    except M4LLMInvocationError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_502_BAD_GATEWAY
            ),
            detail=(
                "Package 3 AI validation failed."
            ),
        ) from exc

    docx_generated = bool(
        result.docx_result
        and result.docx_result.success
    )

    logger.info(
        "p3_generation_completed",
        extra={
            "request_id": getattr(
                request.state,
                "request_id",
                "unknown",
            ),
            "draft_id": (
                result
                .validated_draft
                .draft
                .draft_id
            ),
            "valid": (
                result
                .validated_draft
                .validation
                .is_valid
            ),
            "export_allowed": (
                result.export_allowed
            ),
            "docx_generated": (
                docx_generated
            ),
        },
    )

    return P3GenerateResponse(
        validated_draft=(
            result.validated_draft
        ),
        selected_clause_ids=list(
            result.selected_clause_ids
        ),
        export_allowed=(
            result.export_allowed
        ),
        m5_resolved_clause_count=(
            result.m5_resolved_clause_count
        ),
        docx_generated=(
            docx_generated
        ),
        docx_file_name=(
            file_name
            if docx_generated
            else None
        ),
    )


# =========================================================
# Package 3 - Generated Document Download
# =========================================================


@router.get(
    "/p3/exports/{file_name}",
    response_class=FileResponse,
    tags=["Package 3"],
)
async def download_package3_export(
    file_name: str,
    runtime: P3Dependency,
    identity: CallerIdentityDependency,
) -> FileResponse:
    """
    Download a generated Package 3 DOCX.

    Files are served only from the configured
    Package 3 export directory.
    """

    # Require the same caller-identity boundary
    # used by Package 3 generation.
    _ = identity

    if (
        not file_name
        or file_name in {".", ".."}
        or "/" in file_name
        or "\\" in file_name
        or not file_name.casefold().endswith(
            ".docx"
        )
    ):
        raise HTTPException(
            status_code=(
                status.HTTP_404_NOT_FOUND
            ),
            detail=(
                "Package 3 export was not found."
            ),
        )

    export_root = (
        runtime.export_dir.resolve()
    )

    export_path = (
        export_root / file_name
    ).resolve(
        strict=False
    )

    # Generated exports are direct children of
    # P3_EXPORT_DIR. Resolving the path also prevents
    # symlink/path-traversal escapes.
    if (
        export_path.parent != export_root
        or not export_path.is_file()
    ):
        raise HTTPException(
            status_code=(
                status.HTTP_404_NOT_FOUND
            ),
            detail=(
                "Package 3 export was not found."
            ),
        )

    return FileResponse(
        path=str(export_path),
        media_type=(
            "application/"
            "vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        ),
        filename=file_name,
    )


# =========================================================
# Package 4 - Legal Knowledge Chat
# =========================================================


@router.post(
    "/p4/chat",
    response_model=ValidatedAIResponse,
    tags=["Package 4"],
)
async def chat_package4(
    request_body: P4ChatRequest,
    request: Request,
    service: P4Dependency,
    identity: CallerIdentityDependency,
) -> ValidatedAIResponse:

    reject_client_supplied_access(
        request_body.filters,
        request,
        field_path="filters.access",
    )

    scoped_filters = apply_access_scope(
        request_body.filters,
        identity,
    )

    try:
        result = await service.aanswer(
            question=request_body.question,
            filters=scoped_filters,
            request_id=getattr(
                request.state,
                "request_id",
                None,
            ),
            response_language=(
                request_body
                .response_language
            ),
            safe_context=(
                request_body.safe_context
            ),
            response_instructions=(),
        )

    except M2QueryValidationError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_400_BAD_REQUEST
            ),
            detail=(
                "The Package 4 question "
                "is invalid."
            ),
        ) from exc

    except (
        M2EmbeddingContractError,
        P4RetrievalContractError,
    ) as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_502_BAD_GATEWAY
            ),
            detail=(
                "The Package 4 retrieval "
                "contract failed."
            ),
        ) from exc

    except (
        M2QueryRuntimeError,
        RerankerUnavailable,
        M4LLMConnectionError,
        P4RetrievalPolicyError,
    ) as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail=(
                "The local Package 4 runtime "
                "is unavailable."
            ),
        ) from exc

    except (
        M4LLMInvocationError,
        CitationValidationError,
        P4GroundingValidationError,
    ) as exc:
        logger.exception(
            "p4_grounded_response_failed",
            extra={
                "request_id": getattr(
                    request.state,
                    "request_id",
                    "unknown",
                ),
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
            },
        )

        raise HTTPException(
            status_code=(
                status.HTTP_502_BAD_GATEWAY
            ),
            detail=(
                "Package 4 could not produce "
                "a valid grounded response."
            ),
        ) from exc

    logger.info(
        "p4_chat_completed",
        extra={
            "request_id": getattr(
                request.state,
                "request_id",
                "unknown",
            ),
            "query_id": (
                result.response.query_id
            ),
            "insufficient_evidence": (
                result
                .response
                .insufficient_evidence
            ),
            "evidence_count": (
                result
                .metrics
                .evidence_count
            ),
            "citation_count": (
                result
                .metrics
                .citation_count
            ),
            "generation_invoked": (
                result
                .metrics
                .generation_invoked
            ),
        },
    )

    return result.response
