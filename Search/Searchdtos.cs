namespace LegalAssistant.Api.Search;

public record SearchResponse(IReadOnlyCollection<SearchHitResponse> Results, int TotalCount, int Page, int PageSize);

public record SearchHitResponse(int DocumentId, string FileName, string Snippet, double Score);