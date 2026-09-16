using System.Text.Json.Serialization;

namespace LegalAssistant.Api.Services;

/// <summary>
/// Wire-format DTOs for the AI-Lexora Python RAG service
/// (POST /api/v1/rag/ask). Field names use snake_case to match the
/// service's Pydantic models exactly — see AI-Lexora-main/src/api/schemas.py
/// and src/schemas/m4_contract.py in the AI repo.
/// </summary>
public sealed class LexoraAskRequest
{
    [JsonPropertyName("question")]
    public string Question { get; set; } = string.Empty;

    [JsonPropertyName("filters")]
    public LexoraQueryFilters? Filters { get; set; }
}

public sealed class LexoraQueryFilters
{
    [JsonPropertyName("document_ids")]
    public List<string> DocumentIds { get; set; } = new();

    [JsonPropertyName("document_type")]
    public string? DocumentType { get; set; }

    [JsonPropertyName("jurisdiction")]
    public string? Jurisdiction { get; set; }

    [JsonPropertyName("language")]
    public string? Language { get; set; }
}

public sealed class LexoraAiResponse
{
    [JsonPropertyName("query_id")]
    public string QueryId { get; set; } = string.Empty;

    [JsonPropertyName("answer")]
    public string Answer { get; set; } = string.Empty;

    [JsonPropertyName("citations")]
    public List<LexoraCitation> Citations { get; set; } = new();

    [JsonPropertyName("confidence")]
    public double Confidence { get; set; }
}

public sealed class LexoraCitation
{
    [JsonPropertyName("evidence_id")]
    public string EvidenceId { get; set; } = string.Empty;

    [JsonPropertyName("document_id")]
    public string DocumentId { get; set; } = string.Empty;

    [JsonPropertyName("chunk_id")]
    public string ChunkId { get; set; } = string.Empty;

    [JsonPropertyName("page")]
    public int? Page { get; set; }

    [JsonPropertyName("section")]
    public string? Section { get; set; }
}
/// <summary>
/// Wire-format DTOs for the AI-Lexora Python ranked-search endpoint
/// (POST /api/v1/rag/search). Same filters shape as /ask, but no LLM call:
/// each hit is a document ranked by its best-matching chunk.
/// </summary>
public sealed class LexoraSearchRequest
{
    [JsonPropertyName("query")]
    public string Query { get; set; } = string.Empty;

    [JsonPropertyName("filters")]
    public LexoraQueryFilters? Filters { get; set; }

    [JsonPropertyName("page")]
    public int Page { get; set; } = 1;

    [JsonPropertyName("page_size")]
    public int PageSize { get; set; } = 10;
}

public sealed class LexoraSearchResponse
{
    [JsonPropertyName("query_id")]
    public string QueryId { get; set; } = string.Empty;

    [JsonPropertyName("hits")]
    public List<LexoraSearchHit> Hits { get; set; } = new();

    [JsonPropertyName("total")]
    public int Total { get; set; }

    [JsonPropertyName("page")]
    public int Page { get; set; }

    [JsonPropertyName("page_size")]
    public int PageSize { get; set; }
}

public sealed class LexoraSearchHit
{
    [JsonPropertyName("document_id")]
    public string DocumentId { get; set; } = string.Empty;

    [JsonPropertyName("score")]
    public double Score { get; set; }

    [JsonPropertyName("snippet")]
    public string Snippet { get; set; } = string.Empty;

    [JsonPropertyName("chunk_id")]
    public string ChunkId { get; set; } = string.Empty;

    [JsonPropertyName("page")]
    public int? Page { get; set; }

    [JsonPropertyName("section")]
    public string? Section { get; set; }

    [JsonPropertyName("matched_chunks")]
    public int MatchedChunks { get; set; }
}

public sealed class LexoraDocumentIngestionResponse
{
    [JsonPropertyName("document_id")]
    public string DocumentId { get; set; } = string.Empty;

    [JsonPropertyName("source_file")]
    public string SourceFile { get; set; } = string.Empty;

    [JsonPropertyName("file_type")]
    public string FileType { get; set; } = string.Empty;

    [JsonPropertyName("document_type")]
    public string DocumentType { get; set; } = string.Empty;

    [JsonPropertyName("language")]
    public string Language { get; set; } = string.Empty;

    [JsonPropertyName("pages")]
    public int Pages { get; set; }

    [JsonPropertyName("chunks_indexed")]
    public int ChunksIndexed { get; set; }

    [JsonPropertyName("embedding_model")]
    public string EmbeddingModel { get; set; } = string.Empty;

    [JsonPropertyName("embedding_dimension")]
    public int EmbeddingDimension { get; set; }

    [JsonPropertyName("status")]
    public string Status { get; set; } = string.Empty;
}
