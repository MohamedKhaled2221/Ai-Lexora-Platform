namespace LegalAssistant.Api.Common;

public record ApiErrorResponse(
    int Status,
    string Title,
    string? Detail,
    string TraceId,
    IReadOnlyDictionary<string, string[]>? Errors = null);
