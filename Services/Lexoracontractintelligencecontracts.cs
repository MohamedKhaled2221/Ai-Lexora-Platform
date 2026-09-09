using System.Text.Json.Serialization;

namespace LegalAssistant.Api.Services;

/// <summary>
/// Wire-format DTOs for the AI-Lexora Module 2 pipeline: M1 (document/clause
/// extraction), M5 (clause classification/comparison), and M6 (risk
/// scoring). Field names use snake_case to match each service's Pydantic
/// models exactly. See:
/// - m1/src/api.py (ClauseResponse / ClauseItem — the M1 -> M5 contract)
/// - m5/main.py (AnalyzeRequest / AnalyzeResponse — the M5 -> M6 contract)
/// - src/api/schemas.py + src/schemas/m6_contract.py (M6RiskRequest/Response)
/// </summary>

// ---- M1: POST /clauses (multipart file upload) -> ClauseResponse ----

public sealed class M1ClauseResponse
{
    [JsonPropertyName("document_id")]
    public string DocumentId { get; set; } = string.Empty;

    [JsonPropertyName("document_type")]
    public string DocumentType { get; set; } = string.Empty;

    [JsonPropertyName("language")]
    public string Language { get; set; } = string.Empty;

    [JsonPropertyName("n_clauses")]
    public int ClauseCount { get; set; }

    [JsonPropertyName("n_chunks_total")]
    public int TotalChunkCount { get; set; }

    [JsonPropertyName("clauses")]
    public List<M1ClauseItem> Clauses { get; set; } = new();

    [JsonPropertyName("warnings")]
    public List<string> Warnings { get; set; } = new();
}

public sealed class M1ClauseItem
{
    [JsonPropertyName("chunk_id")]
    public string ChunkId { get; set; } = string.Empty;

    [JsonPropertyName("clause_id")]
    public string? ClauseId { get; set; }

    [JsonPropertyName("section")]
    public string? Section { get; set; }

    [JsonPropertyName("page")]
    public int? Page { get; set; }

    [JsonPropertyName("language")]
    public string Language { get; set; } = string.Empty;

    [JsonPropertyName("text")]
    public string Text { get; set; } = string.Empty;
}

// ---- M5: POST /clauses/analyze -> AnalyzeResponse ----

public sealed class M5AnalyzeRequest
{
    [JsonPropertyName("document_id")]
    public string DocumentId { get; set; } = string.Empty;

    [JsonPropertyName("clauses")]
    public List<M5ClauseInput> Clauses { get; set; } = new();
}

public sealed class M5ClauseInput
{
    [JsonPropertyName("clause_id")]
    public string ClauseId { get; set; } = string.Empty;

    [JsonPropertyName("text")]
    public string Text { get; set; } = string.Empty;

    [JsonPropertyName("page")]
    public int? Page { get; set; }

    [JsonPropertyName("section")]
    public string? Section { get; set; }

    [JsonPropertyName("language")]
    public string? Language { get; set; }
}

public sealed class M5AnalyzeResponse
{
    [JsonPropertyName("document_id")]
    public string DocumentId { get; set; } = string.Empty;

    [JsonPropertyName("clauses")]
    public List<M6ClauseInput> Clauses { get; set; } = new();
}

// ---- M6: POST /api/v1/risk/analyze -> M6RiskResponse ----
// M6ClauseInput is both M5's output shape and (unchanged) M6's expected
// input shape, so the same DTO is forwarded directly as the "clauses" field
// of the M6 request.

public sealed class M6ClauseInput
{
    [JsonPropertyName("clause_id")]
    public string ClauseId { get; set; } = string.Empty;

    [JsonPropertyName("type")]
    public string Type { get; set; } = string.Empty;

    [JsonPropertyName("text")]
    public string Text { get; set; } = string.Empty;

    [JsonPropertyName("entities")]
    public Dictionary<string, object> Entities { get; set; } = new();

    [JsonPropertyName("page")]
    public int? Page { get; set; }

    [JsonPropertyName("similarity_score")]
    public double SimilarityScore { get; set; }

    [JsonPropertyName("is_modified")]
    public bool IsModified { get; set; }

    [JsonPropertyName("confidence")]
    public double Confidence { get; set; }
}

public sealed class M6RiskRequest
{
    [JsonPropertyName("clauses")]
    public List<M6ClauseInput> Clauses { get; set; } = new();
}

public sealed class M6RiskResponse
{
    [JsonPropertyName("risks")]
    public List<M6ContractRisk> Risks { get; set; } = new();
}

public sealed class M6ContractRisk
{
    [JsonPropertyName("risk")]
    public string Risk { get; set; } = string.Empty;

    [JsonPropertyName("severity")]
    public string Severity { get; set; } = string.Empty;

    [JsonPropertyName("explanation")]
    public string Explanation { get; set; } = string.Empty;

    [JsonPropertyName("evidence")]
    public string Evidence { get; set; } = string.Empty;

    [JsonPropertyName("page")]
    public int Page { get; set; }

    [JsonPropertyName("clause")]
    public string Clause { get; set; } = string.Empty;

    [JsonPropertyName("confidence")]
    public double Confidence { get; set; }

    [JsonPropertyName("rule_id")]
    public string RuleId { get; set; } = string.Empty;

    [JsonPropertyName("rule_type")]
    public string RuleType { get; set; } = string.Empty;
}