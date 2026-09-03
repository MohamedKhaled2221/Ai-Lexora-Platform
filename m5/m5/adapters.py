from __future__ import annotations

from typing import Any, Dict, List, Optional

from .normalizer import detect_language
from .schemas import Language, M1ContractSection


def _first(
    data: Dict[str, Any],
    *keys: str,
    default: Any = None,
) -> Any:
    """Return the first non-None value for the given keys."""

    for key in keys:
        if key in data and data[key] is not None:
            return data[key]

    return default


def _get_structure(
    item: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Extract M1 structural metadata.

    Preferred location:
        metadata.structure

    Fallback:
        top-level structure
    """

    metadata = item.get("metadata")

    if isinstance(metadata, dict):
        structure = metadata.get("structure")

        if isinstance(structure, dict):
            return structure

    structure = item.get("structure")

    if isinstance(structure, dict):
        return structure

    return {}


def _get_m1_unit_type(
    structure: Dict[str, Any],
) -> str:
    """
    Identify the structural unit already detected by M1.

    Priority:
        clause
        article
        section
        unstructured
    """

    if structure.get("clause") is not None:
        return "clause"

    if structure.get("article") is not None:
        return "article"

    if structure.get("section") is not None:
        return "section"

    return "unstructured"


def _get_page_span(
    item: Dict[str, Any],
) -> tuple[Optional[int], Optional[int]]:
    """
    Extract page boundaries from M1.

    Preferred:
        metadata.page_span

    Fallback:
        page_start / page_end / page
    """

    metadata = item.get("metadata")

    page_span = None

    if isinstance(metadata, dict):
        page_span = metadata.get("page_span")

    if isinstance(page_span, list) and page_span:
        pages = [
            int(page)
            for page in page_span
            if isinstance(page, (int, float))
            and not isinstance(page, bool)
        ]

        if pages:
            return min(pages), max(pages)

    page_start = _first(
        item,
        "page_start",
        "page",
    )

    page_end = _first(
        item,
        "page_end",
        "page",
        default=page_start,
    )

    return (
        int(page_start)
        if page_start is not None
        else None,
        int(page_end)
        if page_end is not None
        else None,
    )


def _get_char_span(
    item: Dict[str, Any],
) -> tuple[Optional[int], Optional[int]]:
    """
    Extract character offsets from M1.

    Preferred location:
        metadata.char_span
    """

    metadata = item.get("metadata")

    if not isinstance(metadata, dict):
        return None, None

    char_span = metadata.get("char_span")

    if not isinstance(char_span, list) or len(char_span) < 2:
        return None, None

    start, end = char_span[0], char_span[1]

    if (
        not isinstance(start, (int, float))
        or isinstance(start, bool)
    ):
        return None, None

    if (
        not isinstance(end, (int, float))
        or isinstance(end, bool)
    ):
        return None, None

    return int(start), int(end)


def _build_metadata(
    item: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Preserve M1 metadata and useful top-level provenance.
    """

    metadata = item.get("metadata")

    if isinstance(metadata, dict):
        result = dict(metadata)
    else:
        result = {}

    for key in (
        "document_type",
        "jurisdiction",
        "source_file",
        "source_engine",
    ):
        if key in item and key not in result:
            result[key] = item[key]

    return result


def _normalize_language(
    value: Any,
    text: str,
) -> Language:
    """
    Convert M1 language values to the M5 Language enum.

    Supported:
        ar
        en
        ar-en

    Unknown values fall back to language detection.
    """

    if isinstance(value, Language):
        return value

    raw = str(value or "").strip().lower()

    mapping = {
        "ar": Language.AR,
        "arabic": Language.AR,

        "en": Language.EN,
        "english": Language.EN,

        "ar-en": Language.AR_EN,
        "mixed": Language.AR_EN,

        "unknown": Language.UNKNOWN,
        "": Language.UNKNOWN,
    }

    if raw in mapping:
        return mapping[raw]

    detected = detect_language(text)

    if isinstance(detected, Language):
        return detected

    detected = str(detected).lower()

    if detected == "ar":
        return Language.AR

    if detected == "en":
        return Language.EN

    if detected in {"ar-en", "mixed"}:
        return Language.AR_EN

    return Language.UNKNOWN


def _extract_text(
    item: Dict[str, Any],
) -> Optional[str]:
    """
    Extract text from common M1 payload shapes.

    The current M1 output uses the top-level `text` field.
    """

    text = _first(
        item,
        "text",
        "content",
        "clause_text",
    )

    if text is not None:
        text = str(text).strip()

        if text:
            return text

    # Compatibility with older nested payloads.
    nested_section = item.get("section")

    if isinstance(nested_section, dict):
        nested_text = _first(
            nested_section,
            "text",
            "content",
        )

        if nested_text is not None:
            nested_text = str(
                nested_text
            ).strip()

            if nested_text:
                return nested_text

    return None


def _extract_section(
    item: Dict[str, Any],
    structure: Dict[str, Any],
) -> Optional[str]:
    """
    Extract article/section context.

    Article information belongs here,
    not in clause_number.
    """

    return _first(
        structure,
        "section",
        "article",
        default=_first(
            item,
            "section_name",
            "section",
        ),
    )


def _extract_title(
    item: Dict[str, Any],
    structure: Dict[str, Any],
) -> Optional[str]:
    """Extract the structural title/heading."""

    return _first(
        structure,
        "title",
        default=_first(
            item,
            "title",
            "heading",
        ),
    )


def _extract_clause_number(
    item: Dict[str, Any],
    structure: Dict[str, Any],
) -> Optional[str]:
    """
    Extract an actual clause identifier.

    IMPORTANT:
    Article numbers are NOT treated as clause numbers.

    Priority:
        structure.clause
        top-level clause
        top-level clause_number
        top-level number
    """

    value = _first(
        structure,
        "clause",
        default=_first(
            item,
            "clause",
            "clause_number",
            "number",
        ),
    )

    if value is None:
        return None

    return str(value)


def _extract_section_id(
    item: Dict[str, Any],
) -> Optional[str]:
    """
    Extract the source section/chunk identifier.

    Clause IDs are preserved separately in metadata.
    """

    value = _first(
        item,
        "section_id",
        "chunk_id",
        "id",
    )

    if value is None:
        return None

    return str(value)


def _build_m5_section(
    item: Dict[str, Any],
) -> Optional[M1ContractSection]:
    """
    Convert one M1 DocumentChunk into the M5 internal model.
    """

    text = _extract_text(item)

    if not text:
        return None

    structure = _get_structure(item)

    page_start, page_end = _get_page_span(item)

    char_start, char_end = _get_char_span(item)

    language_value = _first(
        item,
        "language",
        default="unknown",
    )

    language = _normalize_language(
        language_value,
        text,
    )

    metadata = _build_metadata(item)

    # Preserve character provenance.
    if (
        char_start is not None
        and char_end is not None
    ):
        metadata["source_char_span"] = [
            char_start,
            char_end,
        ]

    # Preserve page provenance.
    if (
        page_start is not None
        and page_end is not None
    ):
        metadata["source_page_span"] = [
            page_start,
            page_end,
        ]

    # Preserve M1 structural information.
    if structure:
        metadata["m1_structure"] = structure

    # Identify the structural unit detected by M1.
    metadata["m1_unit_type"] = _get_m1_unit_type(
        structure
    )

    # Preserve M1 chunk identity.
    chunk_id = _first(
        item,
        "chunk_id",
    )

    if chunk_id is not None:
        metadata["source_chunk_id"] = str(
            chunk_id
        )

    # Preserve M1 clause identity separately.
    clause_id = _first(
        structure,
        "clause_id",
    )

    if clause_id is not None:
        metadata["source_clause_id"] = str(
            clause_id
        )

    return M1ContractSection(
        document_id=str(
            _first(
                item,
                "document_id",
                "doc_id",
                default="unknown_document",
            )
        ),

        section_id=_extract_section_id(
            item,
        ),

        section=_extract_section(
            item,
            structure,
        ),

        title=_extract_title(
            item,
            structure,
        ),

        text=text,

        page_start=page_start,
        page_end=page_end,

        language=language,

        clause_number=_extract_clause_number(
            item,
            structure,
        ),

        clauses=item.get("clauses"),

        metadata=metadata,
    )


def analyze_request_to_m1_payload(
    request: Any,
) -> Dict[str, Any]:
    """
    Adapt the public API request shape into the existing M1-to-M5 section model.

    This keeps the HTTP layer thin and preserves the current M5 business logic.
    """

    document_id = "unknown_document"
    clauses: List[Dict[str, Any]] = []

    if hasattr(request, "document_id"):
        document_id = str(request.document_id or "unknown_document")

    raw_clauses = getattr(request, "clauses", []) or []

    for item in raw_clauses:
        if hasattr(item, "model_dump"):
            clause = item.model_dump()
        elif isinstance(item, dict):
            clause = dict(item)
        else:
            continue

        text = str(clause.get("text") or "").strip()
        if not text:
            continue

        clause_id = clause.get("clause_id")
        page = clause.get("page")
        section = clause.get("section")
        language = clause.get("language")

        sections_item: Dict[str, Any] = {
            "document_id": document_id,
            "section_id": str(clause_id) if clause_id is not None else None,
            "section": section,
            "title": section,
            "text": text,
            "page_start": page,
            "page_end": page,
            "language": language,
            "metadata": {"source_clause_id": str(clause_id) if clause_id is not None else None},
        }

        if clause_id is None:
            sections_item["metadata"].pop("source_clause_id", None)

        clauses.append(sections_item)

    return {
        "document_id": document_id,
        "sections": clauses,
    }


def m1_payload_to_sections(
    payload: Any,
) -> List[M1ContractSection]:
    """
    Convert M1 output into the M5 internal input contract.

    Supported:

        {"chunks": [...]}

        {"sections": [...]}

        {"contract_sections": [...]}

        {"clauses": [...]}

        {
            "samples": [
                {
                    "chunks": [...]
                }
            ]
        }

        [...]

        single DocumentChunk object
    """

    if isinstance(payload, dict):

        # Normal/simple formats.
        items = (
            payload.get("chunks")
            or payload.get("sections")
            or payload.get("contract_sections")
            or payload.get("clauses")
            or payload.get("data")
        )

        # Actual M1 sample format:
        #
        # {
        #     "samples": [
        #         {
        #             "sample_group": "...",
        #             "chunks": [...]
        #         },
        #         {
        #             "sample_group": "...",
        #             "chunks": [...]
        #         }
        #     ]
        # }
        #
        # Flatten all chunks from all sample groups.
        if items is None and isinstance(
            payload.get("samples"),
            list,
        ):

            items = []

            for sample_group in payload["samples"]:

                if not isinstance(
                    sample_group,
                    dict,
                ):
                    continue

                sample_chunks = sample_group.get(
                    "chunks"
                )

                if isinstance(
                    sample_chunks,
                    list,
                ):
                    items.extend(
                        sample_chunks
                    )

        if items is None:
            items = [payload]

    elif isinstance(payload, list):

        items = payload

    else:

        raise TypeError(
            "M1 payload must be a dict or list"
        )

    # ---------------------------------------------------------
    # Validate the extracted collection.
    # ---------------------------------------------------------

    if not isinstance(items, list):

        raise TypeError(
            "M1 payload collection must be a list"
        )

    # ---------------------------------------------------------
    # Convert every M1 chunk into an M5 section.
    # ---------------------------------------------------------

    result: List[M1ContractSection] = []

    for index, item in enumerate(
        items,
        start=1,
    ):

        if not isinstance(
            item,
            dict,
        ):
            raise TypeError(
                f"M1 item {index} must be an object"
            )

        section = _build_m5_section(
            item
        )

        if section is None:
            continue

        result.append(
            section
        )

    # ---------------------------------------------------------
    # IMPORTANT:
    # Return the converted sections to the pipeline.
    # ---------------------------------------------------------

    return result