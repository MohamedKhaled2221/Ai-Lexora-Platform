# Packages 3 & 4 Shared Contracts

## Purpose

This document freezes the integration boundaries used by the six-member
Legal Intelligence Assistant team for Packages 3 and 4.

The goal is to allow members to develop independently while avoiding
duplicate schemas and incompatible handoffs.

---

# Package 3 — Legal Document Generator

## Main flow

User Guided Input

→ M1 template selection and field validation

→ M5 approved clause decisions

→ M1 deterministic document assembly

→ M1 GenerationManifest

→ M4 grounding, provenance and structural validation

→ lawyer review

→ M1 DOCX/PDF export

## M1 → M4

M1 provides:

- `AssembledDraft`
- `GenerationManifest`

M4 must not assume that incoming data is valid.

An `AssembledDraft` can contain missing provenance so that M4 can
detect and report the problem.

## Trusted Package 3 source types

A legal draft section may originate only from:

- `template`
- `approved_clause`
- `user_input`
- `lawyer_approved_edit`

AI output is not itself a trusted legal source.

If AI transforms text, the transformation must remain grounded in
one or more approved source IDs and must record:

- model tag
- prompt version
- target section
- source IDs
- timestamp

## M4 → downstream

M4 returns:

- `ValidatedDraft`

The object contains:

- original `AssembledDraft`
- original `GenerationManifest`
- `DraftValidationResult`
- validator version
- model/prompt metadata when applicable
- lawyer-review flag

---

# Package 4 — Legal Knowledge Base & Chatbot

## Main flow

User question

→ M6 conversation policy

→ M2 multilingual query processing

→ M3 retrieval

→ M6 evidence sufficiency and response-language plan

→ M4 grounded Qwen generation

→ M4 grounding and citation validation

→ final structured response

## M3 evidence contract

The existing shared model remains:

- `RetrievedEvidence`

The evidence contains trusted document/chunk metadata supplied by
retrieval.

## M6 → M4

M6 sends:

- `AnswerGenerationRequest`

The request contains:

- request ID
- query ID
- original query
- selected response language
- trusted `RetrievedEvidence`
- evidence sufficiency decision
- insufficiency reason when applicable
- safe conversation context
- response-policy instructions

Authorization and confidentiality filtering must happen before this
request reaches M4.

## Safe conversation context

`SafeContextTurn` may help M4 understand a follow-up question.

It is NOT legal evidence.

Previous chatbot/model answers must never become trusted evidence.

Only `RetrievedEvidence` can support legal claims.

## M4 → backend

M4 returns:

- `ValidatedAIResponse`

The response records:

- request ID
- query ID
- grounded answer
- trusted citations
- confidence
- insufficient-evidence state
- grounding-validation result
- citation-validation result
- structured-output-validation result
- unsupported claims
- validation errors
- model tag
- prompt version
- timestamp

Citation metadata must always be resolved from trusted evidence in
Python. The model must not invent document IDs, chunk IDs, pages or
source metadata.

---

# Compatibility Rule

The existing Packages 1 and 2 contracts remain available:

- `EvidenceItem`
- `RetrievedEvidence`
- `M4ModelOutput`
- `Citation`
- `AIResponse`

They must not be renamed or removed until all dependent API/backend
code has been migrated.

`ValidatedAIResponse` is the new Package 4 contract.

---

# Ownership

## Package 3

M5 → M1:
- approved clauses
- compatibility decisions
- required-clause decisions

M1 → M4:
- `AssembledDraft`
- `GenerationManifest`

M5 → M4:
- provenance/status rules

M4 → downstream:
- `ValidatedDraft`

## Package 4

M2 → M3:
- `ProcessedQuery`

M6 → M3:
- knowledge/status/access information

M3 → M6:
- `RetrievedEvidence`

M6 → M4:
- `AnswerGenerationRequest`

M4 → backend:
- `ValidatedAIResponse`

---

# M4 Hard Rules

1. Reuse the existing local Qwen + Ollama + LangChain stack.
2. No unsourced legal clause may be introduced in Package 3.
3. Package 4 answers may use only `RetrievedEvidence` as legal evidence.
4. Conversation history is context, not evidence.
5. Citation metadata is resolved from trusted evidence in code.
6. Prompt and model versions must be recorded.
7. Insufficient evidence must produce an abstention-style response.
8. Existing Packages 1 and 2 interfaces must remain backward compatible
   until integration migration is complete.

---

# M4 Delivery API

## Package 3

POST `/api/v1/m4/p3/validate`

Input:

- AssembledDraft
- GenerationManifest
- P3GroundingContext

Output:

- ValidatedDraft

Behavior:

- structural contract mismatch -> HTTP 400
- local AI unavailable -> HTTP 503
- local AI validation failure -> HTTP 502
- legal/provenance validation failure -> HTTP 200 with
  `is_valid=false` and `requires_lawyer_review=true`

## Package 4

POST `/api/v1/m4/p4/answer`

Input:

- AnswerGenerationRequest

Output:

- ValidatedAIResponse

Behavior:

- insufficient trusted evidence -> deterministic abstention
- Ollama unavailable -> HTTP 503
- invalid structured generation -> HTTP 502
- invalid citations -> HTTP 502
- semantic grounding failure -> HTTP 502

The existing Packages 1 and 2 endpoints remain available during
migration.

M4 API logging records safe operational metadata and runtime resource
metrics only. Legal question text, retrieved legal passages, generated
legal text, credentials, and confidential document content must not
be written to application logs.