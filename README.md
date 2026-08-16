# Member 2 — Embedding & Multilingual Retrieval

## Project

**Legal Intelligence Assistant — Member 2**

This repository implements only the responsibilities assigned to **M2: Embedding & Multilingual Retrieval Engineer**.

According to the team allocation:
- Main technology: **BGE-M3**
- Scope: Shared Embedding Infrastructure, primarily Package 1
- Responsibilities: legal document embeddings, user-query embeddings, Arabic/English/mixed-language handling, lightweight Arabic normalization, legal identifier preservation, Egyptian Arabic and practical Arabizi support, multilingual evaluation
- Handoff to M3: **ProcessedQuery + Embedding**

## What this module does

```text
DocumentChunk
    |
    v
BGE-M3
    |
    v
Document Embedding
```

```text
User Query
    |
    v
Language Detection
    |
    v
Lightweight Normalization
    |
    v
Identifier Preservation
    |
    v
ProcessedQuery
    |
    v
BGE-M3
    |
    v
Query Embedding
    |
    v
M3: Qdrant / Retrieval / Reranking
```

## Explicitly out of scope

M2 does **not** own:
- Qdrant collections
- Hybrid search
- Reranking
- Retrieval orchestration
- RAG generation
- Ollama / LLM prompting
- Grounding
- Citation generation
- PDF/OCR processing
- Contract risk analysis
- Frontend/API ownership

Those are handled by other team members.

## Repository structure

```text
member2-embedding/
├── README.md
├── HANDOFF.md
├── requirements.txt
├── .env.example
├── src/
│   ├── __init__.py
│   ├── config.py
│   ├── schemas.py
│   ├── query_processor.py
│   ├── embedding_service.py
│   └── utils.py
├── evaluation/
│   ├── dataset.json
│   ├── metrics.py
│   └── benchmark.py
├── tests/
│   ├── test_query_processor.py
│   ├── test_schemas.py
│   └── test_metrics.py
└── docs/
    └── doc.md
```

## Installation

```bash
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

Linux/macOS:

```bash
source .venv/bin/activate
```

Install:

```bash
pip install -r requirements.txt
```

## Configuration

Copy:

```bash
copy .env.example .env
```

or on Linux/macOS:

```bash
cp .env.example .env
```

Default:

```env
EMBEDDING_MODEL=BAAI/bge-m3
USE_FP16=true
BATCH_SIZE=8
MAX_LENGTH=512
```

## Basic usage

```python
from src.embedding_service import EmbeddingService
from src.query_processor import QueryProcessor

processor = QueryProcessor()
embedding_service = EmbeddingService()

processed = processor.process(
    "ايه شروط termination في Article 69؟"
)

vector = embedding_service.embed_query(processed.normalized_text)

print(processed)
print(len(vector))
```

For document chunks:

```python
texts = [
    "Termination may occur after written notice.",
    "يجوز إنهاء العقد بعد إخطار كتابي."
]

vectors = embedding_service.embed_documents(texts)
```

## Important implementation rule

The query processor is intentionally lightweight. It does **not** translate the legal query into another language by default.

Reason:
- translation can alter legal identifiers;
- the project requires preservation of article numbers, case numbers, dates, party names, monetary values, and legal terminology;
- BGE-M3 is being used specifically for multilingual/cross-language retrieval.

## Evaluation

The evaluation package supports:
- Arabic retrieval quality
- English retrieval quality
- cross-language retrieval
- mixed Arabic-English retrieval
- Arabizi coverage
- identifier preservation
- embedding latency
- memory measurement hooks

Run the benchmark after installing BGE-M3:

```bash
python -m evaluation.benchmark
```

The included dataset is a **small development dataset**, not the final approved legal benchmark. The final benchmark must be prepared and approved by the team using representative legal documents.

## Tests

```bash
pytest -q
```

Tests that do not require loading BGE-M3 are intentionally isolated from model execution.

## Documentation PDF

Convert the documentation to HTML:

```bash
pandoc docs/doc.md -s -o docs/doc.html
```

Then open it in Chrome/Edge:

**Print → Save as PDF**

Or, if your Pandoc/LaTeX installation supports Arabic correctly:

```bash
pandoc docs/doc.md -o docs/doc.pdf
```
