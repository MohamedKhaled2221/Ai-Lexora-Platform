using System.Net.Http.Json;
using System.Text.Json;
using LegalAssistant.Api.Repositories;

namespace LegalAssistant.Api.Services;

public sealed class LexoraDocumentQuestionService
    : ILexoraDocumentQuestionService
{
    private const int MaxSelectedDocuments = 50;
    private const int MaxQuestionLength = 4000;

    private static readonly JsonSerializerOptions JsonOptions =
        new(JsonSerializerDefaults.Web);

    private readonly HttpClient _httpClient;
    private readonly IDocumentRepository _documents;
    private readonly ILogger<LexoraDocumentQuestionService> _logger;

    public LexoraDocumentQuestionService(
        HttpClient httpClient,
        IDocumentRepository documents,
        ILogger<LexoraDocumentQuestionService> logger)
    {
        _httpClient = httpClient;
        _documents = documents;
        _logger = logger;
    }

    public async Task<DocumentQuestionResult> AskAsync(
        string question,
        IReadOnlyCollection<int> documentIds,
        string userId,
        CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(question))
        {
            throw new ArgumentException(
                "A question is required.",
                nameof(question));
        }

        var normalizedQuestion = question.Trim();

        if (normalizedQuestion.Length > MaxQuestionLength)
        {
            throw new ArgumentException(
                $"Question must be {MaxQuestionLength} characters or fewer.",
                nameof(question));
        }

        if (documentIds is null || documentIds.Count == 0)
        {
            throw new ArgumentException(
                "At least one document must be selected.",
                nameof(documentIds));
        }

        if (documentIds.Count > MaxSelectedDocuments)
        {
            throw new ArgumentException(
                $"No more than {MaxSelectedDocuments} documents may be selected.",
                nameof(documentIds));
        }

        if (documentIds.Any(id => id <= 0))
        {
            throw new ArgumentException(
                "Document IDs must be positive integers.",
                nameof(documentIds));
        }

        var distinctDocumentIds = documentIds
            .Distinct()
            .ToArray();

        var ownedDocuments =
            await _documents.GetOwnedByIdsAsync(
                distinctDocumentIds,
                userId,
                cancellationToken);

        if (ownedDocuments.Count != distinctDocumentIds.Length)
        {
            throw new KeyNotFoundException(
                "One or more selected documents were not found.");
        }

        var documentsByAiId = ownedDocuments.ToDictionary(
            document => LexoraDocumentIds.FromBackendId(document.Id),
            StringComparer.Ordinal);

        var request = new LexoraAskRequest
        {
            Question = normalizedQuestion,
            Filters = new LexoraQueryFilters
            {
                DocumentIds = documentsByAiId.Keys.ToList()
            }
        };

        HttpResponseMessage response;

        try
        {
            response = await _httpClient.PostAsJsonAsync(
                "/api/v1/rag/ask",
                request,
                JsonOptions,
                cancellationToken);
        }
        catch (HttpRequestException exception)
        {
            _logger.LogWarning(
                "AI RAG service could not be reached for a document-scoped request");

            throw new AiQuestionAnsweringException(
                "The AI question-answering service could not be reached.",
                StatusCodes.Status503ServiceUnavailable,
                exception);
        }
        catch (TaskCanceledException exception)
            when (!cancellationToken.IsCancellationRequested)
        {
            _logger.LogWarning(
                "AI RAG service timed out for a document-scoped request");

            throw new AiQuestionAnsweringException(
                "The AI question-answering service timed out.",
                StatusCodes.Status503ServiceUnavailable,
                exception);
        }

        using (response)
        {
            if (!response.IsSuccessStatusCode)
            {
                var upstreamStatus =
                    (int)response.StatusCode;

                _logger.LogWarning(
                    "AI RAG service returned status {StatusCode} "
                    + "for a document-scoped request",
                    upstreamStatus);

                var downstreamStatus =
                    upstreamStatus == StatusCodes.Status503ServiceUnavailable
                        ? StatusCodes.Status503ServiceUnavailable
                        : StatusCodes.Status502BadGateway;

                throw new AiQuestionAnsweringException(
                    "The AI service failed to answer the question.",
                    downstreamStatus);
            }

            LexoraAiResponse? result;

            try
            {
                result = await response.Content
                    .ReadFromJsonAsync<LexoraAiResponse>(
                        JsonOptions,
                        cancellationToken);
            }
            catch (JsonException exception)
            {
                throw new AiQuestionAnsweringException(
                    "The AI service returned an invalid response.",
                    StatusCodes.Status502BadGateway,
                    exception);
            }
            catch (NotSupportedException exception)
            {
                throw new AiQuestionAnsweringException(
                    "The AI service returned an unsupported response.",
                    StatusCodes.Status502BadGateway,
                    exception);
            }

            if (result is null
                || string.IsNullOrWhiteSpace(result.QueryId)
                || string.IsNullOrWhiteSpace(result.Answer)
                || result.Confidence is < 0 or > 1)
            {
                throw new AiQuestionAnsweringException(
                    "The AI service returned an invalid answer.",
                    StatusCodes.Status502BadGateway);
            }

            var citations =
                new List<DocumentQuestionCitation>();

            foreach (var citation in result.Citations)
            {
                if (!documentsByAiId.TryGetValue(
                        citation.DocumentId,
                        out var document))
                {
                    _logger.LogWarning(
                        "AI RAG response contained a citation "
                        + "outside the authorized document scope");

                    throw new AiQuestionAnsweringException(
                        "The AI service returned an invalid citation.",
                        StatusCodes.Status502BadGateway);
                }

                if (string.IsNullOrWhiteSpace(
                        citation.EvidenceId)
                    || string.IsNullOrWhiteSpace(
                        citation.ChunkId))
                {
                    throw new AiQuestionAnsweringException(
                        "The AI service returned an invalid citation.",
                        StatusCodes.Status502BadGateway);
                }

                citations.Add(
                    new DocumentQuestionCitation(
                        citation.EvidenceId,
                        document.Id,
                        document.FileName,
                        citation.ChunkId,
                        citation.Page,
                        citation.Section));
            }

            _logger.LogInformation(
                "Document-scoped RAG request completed "
                + "with {CitationCount} citations",
                citations.Count);

            return new DocumentQuestionResult(
                result.QueryId,
                result.Answer,
                result.Confidence,
                citations);
        }
    }
}

public sealed class AiQuestionAnsweringException : Exception
{
    public AiQuestionAnsweringException(
        string message,
        int responseStatusCode,
        Exception? innerException = null)
        : base(message, innerException)
    {
        ResponseStatusCode = responseStatusCode;
    }

    public int ResponseStatusCode { get; }
}
