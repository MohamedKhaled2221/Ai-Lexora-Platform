using LegalAssistant.Api.Repositories;

namespace LegalAssistant.Api.Services;

/// <summary>
/// Placeholder <see cref="ISearchService"/>: scans the requesting user's own
/// documents and does case-insensitive substring matching against extracted
/// text. No index, no semantic ranking — this exists purely so the Search
/// API shape is usable end-to-end before embeddings + a vector database are
/// wired in behind the same interface. Scores are just match counts.
/// </summary>
public sealed class KeywordSearchService : ISearchService
{
    // Guardrail while there is no index: cap how many of the user's
    // documents get scanned per request so a large library can't make a
    // single search request scan everything synchronously.
    private const int MaxDocumentsScanned = 200;

    private readonly IDocumentRepository _documents;
    private readonly IDocumentService _documentService;
    private readonly IDocumentTextExtractor _textExtractor;
    private readonly ILogger<KeywordSearchService> _logger;

    public KeywordSearchService(
        IDocumentRepository documents,
        IDocumentService documentService,
        IDocumentTextExtractor textExtractor,
        ILogger<KeywordSearchService> logger)
    {
        _documents = documents;
        _documentService = documentService;
        _textExtractor = textExtractor;
        _logger = logger;
    }

    public async Task<SearchResult> SearchAsync(string query, string userId, int page, int pageSize, CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(query))
            return new SearchResult(Array.Empty<SearchHit>(), 0);

        var owned = await _documents.GetPagedOwnedAsync(userId, page: 1, pageSize: MaxDocumentsScanned, search: null, type: null);

        var hits = new List<SearchHit>();
        foreach (var document in owned.Items)
        {
            cancellationToken.ThrowIfCancellationRequested();
            if (!_textExtractor.CanExtract(document.FileName)) continue;

            string text;
            try
            {
                var fullPath = _documentService.GetFilePath(document);
                if (!File.Exists(fullPath)) continue;
                text = await _textExtractor.ExtractTextAsync(fullPath, document.FileName, cancellationToken);
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "Could not extract text for document {DocumentId} during search", document.Id);
                continue;
            }

            var matchIndex = text.IndexOf(query, StringComparison.OrdinalIgnoreCase);
            if (matchIndex < 0) continue;

            hits.Add(new SearchHit(document.Id, document.FileName, BuildSnippet(text, matchIndex, query.Length), CountOccurrences(text, query)));
        }

        var ordered = hits.OrderByDescending(h => h.Score).ToList();
        var pageItems = ordered.Skip((page - 1) * pageSize).Take(pageSize).ToList();
        return new SearchResult(pageItems, ordered.Count);
    }

    private static int CountOccurrences(string text, string query)
    {
        var count = 0;
        var index = 0;
        while ((index = text.IndexOf(query, index, StringComparison.OrdinalIgnoreCase)) >= 0)
        {
            count++;
            index += query.Length;
        }
        return count;
    }

    private static string BuildSnippet(string text, int matchIndex, int matchLength)
    {
        const int context = 120;
        var start = Math.Max(0, matchIndex - context);
        var end = Math.Min(text.Length, matchIndex + matchLength + context);
        return text[start..end].Trim();
    }
}