namespace LegalAssistant.Api.Documents;

public record RiskyClauseResponse(
    int Id,
    string ClauseText,
    string RiskType,
    string Explanation,
    string? Severity,
    string? SeverityColor);

public record ContractAnalysisResponse(
    int Id,
    int DocumentId,
    int RiskScore,
    string Summary,
    string Status,
    DateTime? StartedAt,
    DateTime? CompletedAt,
    string? ErrorMessage,
    DateTime AnalyzedAt,
    IReadOnlyCollection<RiskyClauseResponse> RiskyClauses);

public record CompleteAnalysisRequest(
    int RiskScore,
    string Summary,
    IReadOnlyCollection<CreateRiskyClauseRequest>? RiskyClauses);

public record CreateRiskyClauseRequest(
    string ClauseText,
    string RiskType,
    string Explanation,
    string? Severity = null,
    string? SeverityColor = null);

public record FailAnalysisRequest(string ErrorMessage);