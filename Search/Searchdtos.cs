namespace LegalAssistant.Api.Search;

public record SearchResponse(IReadOnlyCollection<SearchHitResponse> Results, int TotalCount, int Page, int PageSize);

public record SearchHitResponse(int DocumentId, string FileName, string Snippet, double Score);

public sealed record AskDocumentsRequest(
    string Question,
    IReadOnlyCollection<int> DocumentIds);

public sealed record AskDocumentsResponse(
    string QueryId,
    string Answer,
    double Confidence,
    IReadOnlyCollection<SearchCitationResponse> Citations);

public sealed record SearchCitationResponse(
    string EvidenceId,
    int DocumentId,
    string FileName,
    string ChunkId,
    int? Page,
    string? Section);