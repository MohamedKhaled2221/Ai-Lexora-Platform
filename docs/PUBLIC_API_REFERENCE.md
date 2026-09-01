# M5 Contract Clause Intelligence — Public API Reference

## Responsibility

M5 receives clause-level contract data from M1, analyzes each clause, and
returns structured clause intelligence for M6.

## Endpoints

### POST /clauses/analyze

**Content-Type:** `application/json`

Request:
```json
{
  "document_id": "doc_001",
  "clauses": [
    {
      "clause_id": "clause_001",
      "text": "يلتزم الطرف الثاني بسداد قيمة الخدمات خلال ثلاثين يوماً.",
      "page": 5,
      "section": "Payment",
      "language": "ar"
    }
  ]
}
```

Response — HTTP 200:
```json
{
  "document_id": "doc_001",
  "clauses": [
    {
      "clause_id": "clause_001",
      "type": "payment",
      "text": "يلتزم الطرف الثاني بسداد قيمة الخدمات خلال ثلاثين يوماً.",
      "entities": {},
      "page": 5,
      "similarity_score": 0.91,
      "is_modified": false,
      "confidence": 0.94
    }
  ]
}
```

### GET /health

Response:
```json
{
  "status": "ok",
  "service": "m5-contract-clause-intelligence"
}
```

## Endpoint ownership

M1:
- POST /ingest
- POST /clauses

M5:
- POST /clauses/analyze
- GET /health

## M5 → M6 fields

| Field | Type | Meaning |
|---|---|---|
| clause_id | string | Clause identifier |
| type | string | M5 ClauseType |
| text | string | Original clause text |
| entities | object | Extracted legal entities |
| page | integer/null | Source page |
| similarity_score | float | Reference similarity when available |
| is_modified | boolean | Derived from reference comparison |
| confidence | float | Classification confidence |

## Clause types

termination, liability, payment, confidentiality, renewal, penalty,
governing_law, dispute_resolution, indemnity, intellectual_property,
force_majeure, term, notice, assignment, representations, warranties,
data_protection, other, unknown.

## Flow

M1 → POST /clauses → M5 → POST /clauses/analyze → M6

The LLM/Qwen/M4 classification path is not part of this M5 API contract.
