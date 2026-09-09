namespace LegalAssistant.Api.Services;

/// <summary>
/// Abstraction over "find documents matching this query for this user".
/// The placeholder implementation (<see cref="KeywordSearchService"/>) does
/// in-memory substring matching over extracted text. A real implementation
/// (embeddings + vector database + RAG) can replace it later — SearchController
/// only depends on this interface and does not change.
/// </summary>
public interface ISearchService
{
    Task<SearchResult> SearchAsync(string query, string userId, int page, int pageSize, CancellationToken cancellationToken = default);
}

public sealed record SearchResult(IReadOnlyCollection<SearchHit> Hits, int TotalCount);

public sealed record SearchHit(int DocumentId, string FileName, string Snippet, double Score);