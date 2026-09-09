# M2 Multilingual Query and Embedding Handoff

## Ownership

M2 owns multilingual legal-query processing and BGE-M3
embedding generation.

Supported query forms in the current implementation:

- English
- Arabic
- Egyptian Arabic written using Arabic script
- Arabic-English mixed queries

Arabizi is intentionally not included because support has not
yet been agreed by the team.

## M2 Query Output

The primary M2-to-M3 contract is `ProcessedQuery`.

It contains:

- `query_id`
- `text_original`
- `normalized_text`
- `language`
- `embedding`
- `sparse_embedding`
- `filters`
- `query_variants`
- `identifiers`

Canonical language values are:

- `en`
- `ar`
- `ar-en`
- `unknown`

## Original and Normalized Text

`text_original` preserves the user's query exactly.

`normalized_text` is a conservative search representation.

Normalization does not perform full translation, stemming, or
general-purpose rewriting.

Arabic normalization currently includes limited operations such
as removal of diacritics/tatweel and conservative alef
normalization.

The original query remains available separately and must not be
reconstructed from normalized text.

## Exact Legal Identifiers

`identifiers` contains:

- `article_numbers`
- `case_numbers`
- `dates`
- `monetary_values`
- `party_names`
- `named_legal_terms`

Identifier extraction is performed against the original user
query.

M2 preserves the original spelling/digit representation where
possible. Examples include:

- `Article 157`
- `المادة ١٥٧`
- `123/2025`
- `١٢٣/٢٠٢٥`
- `EGP 250,000`
- `٢٥٠٬٠٠٠ جنيه مصري`

M3 should consume these fields for exact-identifier and hybrid
retrieval rather than reimplementing identifier extraction.

## Query Variants

`query_variants` contains deterministic retrieval variants.

M2 does not perform unrestricted LLM query rewriting.

Current expansion is based on an approved internal bilingual
legal-term catalogue.

Examples include mappings such as:

- `force majeure` / `القوة القاهرة`
- `arbitration` / `التحكيم`
- `termination` / `إنهاء العقد`
- `governing law` / `القانون الحاكم`

Exact identifiers are preserved in generated variants.

M3 may use these variants for lexical, dense, hybrid, or fusion
retrieval as appropriate.

M3 remains responsible for deciding how variants affect ranking
and fusion.

## BGE-M3 Embeddings

Current embedding model:

`BAAI/bge-m3`

The deployment may configure this as a local filesystem path.

Current M2 dense-vector contract:

- dimension: `1024`
- dense output only
- optional explicit L2 normalization enabled by default
- CPU or CUDA runtime
- FP16 enabled only when CUDA is selected

M2 validates:

- output count
- numeric values
- finite values
- expected vector dimension
- non-zero vectors when normalization is enabled

Runtime metrics include:

- embedding latency
- process RSS before/after
- CUDA peak allocated memory when CUDA is used
- model/runtime metadata

## Passage Embeddings

M2 also provides BGE-M3 embeddings for trusted document
passages/chunks.

`EmbeddedDocumentChunk` preserves source metadata including:

- document ID
- chunk ID
- original chunk text
- page
- section
- clause
- language
- document type
- metadata
- embedding model
- embedding dimension

M2 does not own Qdrant storage or retrieval.

## M3 Integration Requirement

M3 should consume the M2 output rather than duplicate M2
processing.

The current required handoff is conceptually:

```text
ProcessedQuery
├── text_original
├── normalized_text
├── language
├── embedding
├── filters
├── query_variants
└── identifiers
