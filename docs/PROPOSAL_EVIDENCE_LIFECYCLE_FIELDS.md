# Proposal: lifecycle fields on `EvidenceItem`

**From:** M3 · **Needs sign-off from:** M4 (contract owner), M6 (field semantics)
**Status:** proposal, no contract change made

## Problem

`EvidenceItem` (`src/schemas/m4_contract.py`) has 7 fields: document, chunk, text, page, section, language, score. It says nothing about whether the source is still valid law. M4 therefore cannot tell a current article from a superseded one, and cannot say "this was replaced by…" in an answer.

M6 now defines the source of truth for these fields (`src/schemas/m6_knowledge.py`: `validity_status`, `effective_from`/`effective_to`, `superseded_by_record_id`). M3's index sync (`src/indexing/index_sync.py`) already writes them onto Qdrant points as `record_id`, `record_version`, `validity_status`, `effective_from`, `effective_to`, `supersedes_record_id`, `superseded_by_record_id`.

## Proposed fields (all optional, backward compatible)

```python
class EvidenceItem(BaseModel):
    ...existing 7 fields unchanged...

    record_id: Optional[str] = None
    validity_status: Optional[Literal["current", "superseded", "review_required"]] = None
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    superseded_by_record_id: Optional[str] = None
```

| Field | Source | `None` means |
|---|---|---|
| `record_id` | M6 canonical record | chunk came from the document pipeline, not M6 |
| `validity_status` | M6 `ValidityStatus` | status unknown (all 1,945 current points) |
| `effective_from` / `effective_to` | M6 record | no dates recorded |
| `superseded_by_record_id` | M6 record | not superseded, or unknown |

Deliberately **not** proposed:
- **Approval status.** Only M6 records reach the index approved (`KnowledgeIngestionService` rejects unapproved M1 records), so every indexed chunk would read "approved". The field would carry no information.
- **ACL fields.** Enforcement happens in the Qdrant filter and in M3's post-retrieval check. M4 must not become a second place where access is decided.

## Decisions needed

1. **M4:** how should `None` status be treated? Options:
   - (a) treat as current. This is today's behaviour.
   - (b) add a caveat to the answer.
   - (c) abstain.

   M3 recommends **(a)** until the corpus is re-indexed through M6 sync. Otherwise every answer today would carry a caveat or abstain.
2. **M4:** should `superseded` evidence ever be cited? M6's `ConversationPolicyService` currently allows generation with a reason string only. M3 recommends that it can be cited only alongside the superseding record, and the answer must say it's superseded.
3. **M6:** confirm the field names and `ValidityStatus` values are final.

## M3 work once agreed (small)

Carry the payload keys through `QdrantVectorStore._project` and `M3RetrievalPipeline.run` into `EvidenceItem`. The retrieval side already supports restricting by status (`RAG_VALIDITY_STATUS_FILTER`, off by default), so M4 can choose between filtering superseded evidence out and receiving it with a label.
