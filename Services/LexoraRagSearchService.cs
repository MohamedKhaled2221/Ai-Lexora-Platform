using System.Net.Http.Json;
using System.Text.Json;
using LegalAssistant.Api.Repositories;

namespace LegalAssistant.Api.Services;

/// <summary>
/// Real <see cref="ISearchService"/>: calls the AI-Lexora Python RAG service's
/// ranked search endpoint (POST /api/v1/rag/search), which runs the actual
/// M2 (query processing/embedding) -> M3 (Qdrant vector retrieval) pipeline.
/// Replaces <see cref="KeywordSearchService"/> behind the same interface —
/// SearchController does not change.
///
/// Every request is scoped to the caller's own documents (same pattern as
/// <see cref="LexoraDocumentQuestionService"/>): we look up the user's owned
/// documents, send only their AI-side document IDs as a filter, and reject
/// any hit that comes back for a document outside that set rather than
/// silently dropping it — a mismatch there means the scoping is broken and
/// should fail loudly, not leak.
/// </summary>
public sealed class LexoraRagSearchService : ISearchService
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);

    private readonly HttpClient _httpClient;
    private readonly IDocumentRepository _documents;
    private readonly ILogger<LexoraRagSearchService> _logger;

    public LexoraRagSearchService(
        HttpClient httpClient,
        IDocumentRepository documents,
        ILogger<LexoraRagSearchService> logger)
    {
        _httpClient = httpClient;
        _documents = documents;
        _logger = logger;
    }

    public async Task<SearchResult> SearchAsync(
        string query,
        string userId,
        int page,
        int pageSize,
        CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(query))
            return new SearchResult(Array.Empty<SearchHit>(), 0);

        var ownedDocuments = await _documents.GetAllOwnedAsync(userId, cancellationToken);
        if (ownedDocuments.Count == 0)
            return new SearchResult(Array.Empty<SearchHit>(), 0);

        var documentsByAiId = ownedDocuments.ToDictionary(
            document => LexoraDocumentIds.FromBackendId(document.Id),
            StringComparer.Ordinal);

        var request = new LexoraSearchRequest
        {
            Query = query,
            Filters = new LexoraQueryFilters
            {
                DocumentIds = documentsByAiId.Keys.ToList()
            },
            Page = page,
            PageSize = pageSize
        };

        HttpResponseMessage response;
        try
        {
            response = await _httpClient.PostAsJsonAsync("/api/v1/rag/search", request, JsonOptions, cancellationToken);
        }
        catch (HttpRequestException exception)
        {
            _logger.LogWarning(exception, "AI RAG search service could not be reached");
            throw new AiSearchException(
                "The AI search service could not be reached.",
                StatusCodes.Status503ServiceUnavailable,
                exception);
        }
        catch (TaskCanceledException exception) when (!cancellationToken.IsCancellationRequested)
        {
            _logger.LogWarning(exception, "AI RAG search service timed out");
            throw new AiSearchException(
                "The AI search service timed out.",
                StatusCodes.Status503ServiceUnavailable,
                exception);
        }

        using (response)
        {
            if (!response.IsSuccessStatusCode)
            {
                var upstreamStatus = (int)response.StatusCode;
                var responseBody = await response.Content.ReadAsStringAsync(cancellationToken);

                _logger.LogWarning(
                    "AI RAG search service returned status {StatusCode}. Response: {ResponseBody}",
                    upstreamStatus,
                    responseBody);

                var downstreamStatus = upstreamStatus is 400 or 503
                    ? upstreamStatus
                    : StatusCodes.Status502BadGateway;

                throw new AiSearchException(
                    "The AI service failed to search the document library.",
                    downstreamStatus);
            }

            LexoraSearchResponse? result;
            try
            {
                result = await response.Content.ReadFromJsonAsync<LexoraSearchResponse>(JsonOptions, cancellationToken);
            }
            catch (JsonException exception)
            {
                throw new AiSearchException(
                    "The AI service returned an invalid search response.",
                    StatusCodes.Status502BadGateway,
                    exception);
            }

            if (result is null)
            {
                throw new AiSearchException(
                    "The AI service returned an empty search response.",
                    StatusCodes.Status502BadGateway);
            }

            var hits = new List<SearchHit>(result.Hits.Count);
            foreach (var hit in result.Hits)
            {
                if (!documentsByAiId.TryGetValue(hit.DocumentId, out var document))
                {
                    _logger.LogWarning(
                        "AI RAG search response contained a hit outside the authorized document scope");

                    throw new AiSearchException(
                        "The AI service returned a result outside the authorized document library.",
                        StatusCodes.Status502BadGateway);
                }

                hits.Add(new SearchHit(document.Id, document.FileName, hit.Snippet, hit.Score));
            }

            _logger.LogInformation(
                "RAG search completed with {HitCount} hits (total {Total})",
                hits.Count,
                result.Total);

            return new SearchResult(hits, result.Total);
        }
    }
}

/// <summary>Thrown when the external AI-Lexora search endpoint is unreachable or fails.</summary>
public sealed class AiSearchException : Exception
{
    public AiSearchException(string message, int responseStatusCode, Exception? innerException = null)
        : base(message, innerException)
    {
        ResponseStatusCode = responseStatusCode;
    }

    public int ResponseStatusCode { get; }
}
