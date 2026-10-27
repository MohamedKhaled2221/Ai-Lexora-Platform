# M1 — Legal Document Generator & Knowledge Ingestion

Implementation aligned with the project Member Split:
- Package 3: Legal Document Generator
- Reusable ingestion support for Package 4

M1 deliverables:
template_registry, guided_input_schema, template_selector, document_assembler,
placeholder_validator, docx_exporter, pdf_exporter, generation_manifest,
knowledge_ingestion_adapter.

Package 3 flow:
GuidedDocumentRequest -> Template Selection + Field Validation
-> M5 ApprovedClause[] / ClauseDecision[]
-> Deterministic Controlled Assembly -> GenerationManifest
-> M4 validation -> Lawyer Review -> DOCX/PDF export.

Hard rule:
No generated legal clause may appear unless traceable to an approved template/clause,
an explicit user field, or a lawyer-approved edit. Unsupported special conditions
must be routed to lawyer review.

Package 4:
Reuse the existing document-processing/OCR pipeline and adapt its output into
normalized approved records/passages for M6. This package deliberately does not
build a second parser/OCR stack.

M1 does NOT own:
BGE-M3, Qdrant, retrieval/reranking, canonical knowledge DB, approved clause library,
legal compatibility policy, Qwen/Ollama inference, or M4 grounding validation.

Install:
    pip install -e ".[dev]"
Run tests:
    pytest -q
Run demo:
    python -m m1.demo

PDF export:
Use local LibreOffice/soffice for DOCX -> PDF. No cloud conversion service is used.

The demo contains explicitly NON-LEGAL sample text only to exercise the pipeline.
Replace it with real approved templates/clauses from the team before integration.
