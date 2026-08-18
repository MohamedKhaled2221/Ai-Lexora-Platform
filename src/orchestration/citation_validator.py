import re

from src.schemas.m4_contract import Citation, EvidenceItem, M4ModelOutput


_VALID_CITATION_PATTERN = re.compile(
    r"\[(E[1-9][0-9]*)\]"
)

_CITATION_LIKE_PATTERN = re.compile(
    r"\[([Ee][^\[\]]*)\]"
)


class CitationValidationError(ValueError):
    """
    Raised when LLM-generated citation references fail M4 validation.
    """


class CitationValidator:
    """
    Validates LLM citation references and resolves them to trusted
    source metadata.

    The LLM may reference only evidence aliases such as E1 or E2.
    Document IDs, chunk IDs, pages, and sections are always copied
    from the trusted evidence map constructed before generation.
    """

    def validate(
        self,
        model_output: M4ModelOutput,
        evidence_by_id: dict[str, EvidenceItem],
    ) -> list[Citation]:
        self._validate_evidence_map(
            evidence_by_id
        )

        answer_citation_ids = self._extract_answer_citations(
            model_output.answer
        )

        self._validate_declared_citations(
            declared_citation_ids=model_output.citation_ids,
            answer_citation_ids=answer_citation_ids,
            evidence_by_id=evidence_by_id,
        )

        return [
            self._build_trusted_citation(
                evidence_id=evidence_id,
                evidence=evidence_by_id[evidence_id],
            )
            for evidence_id in model_output.citation_ids
        ]

    def _validate_evidence_map(
        self,
        evidence_by_id: dict[str, EvidenceItem],
    ) -> None:
        for evidence_id in evidence_by_id:
            if not re.fullmatch(
                r"E[1-9][0-9]*",
                evidence_id,
            ):
                raise CitationValidationError(
                    f"Invalid trusted evidence alias: {evidence_id}"
                )

    def _extract_answer_citations(
        self,
        answer: str,
    ) -> list[str]:
        self._reject_malformed_citation_markers(
            answer
        )

        matches = _VALID_CITATION_PATTERN.findall(
            answer
        )

        # Preserve first-appearance order while allowing the same
        # evidence source to support multiple claims in the answer.
        return list(
            dict.fromkeys(matches)
        )

    def _reject_malformed_citation_markers(
        self,
        answer: str,
    ) -> None:
        citation_like_tokens = (
            _CITATION_LIKE_PATTERN.findall(answer)
        )

        for token in citation_like_tokens:
            if not re.fullmatch(
                r"E[1-9][0-9]*",
                token,
            ):
                raise CitationValidationError(
                    f"Malformed citation marker: [{token}]"
                )

    def _validate_declared_citations(
    self,
    *,
    declared_citation_ids: list[str],
    answer_citation_ids: list[str],
    evidence_by_id: dict[str, EvidenceItem],
    ) -> None:
        unknown_declared = [
            evidence_id
            for evidence_id in declared_citation_ids
            if evidence_id not in evidence_by_id
        ]

        if unknown_declared:
            raise CitationValidationError(
              "Model referenced evidence that was not supplied: "
                + ", ".join(unknown_declared)
            )

        unknown_in_answer = [
         evidence_id
         for evidence_id in answer_citation_ids
         if evidence_id not in evidence_by_id
        ]

        if unknown_in_answer:
           raise CitationValidationError(
              "Answer contains citations that were not supplied: "
              + ", ".join(unknown_in_answer)
          )

        undeclared_inline = [
          evidence_id
          for evidence_id in answer_citation_ids
          if evidence_id not in declared_citation_ids
        ]

        if undeclared_inline:
         raise CitationValidationError(
             "Answer contains citation markers that are missing "
             "from citation_ids: "
             + ", ".join(undeclared_inline)
         )
        
        
    def _build_trusted_citation(
        self,
        *,
        evidence_id: str,
        evidence: EvidenceItem,
    ) -> Citation:
        return Citation(
            evidence_id=evidence_id,
            document_id=evidence.document_id,
            chunk_id=evidence.chunk_id,
            page=evidence.page,
            section=evidence.section,
        )
