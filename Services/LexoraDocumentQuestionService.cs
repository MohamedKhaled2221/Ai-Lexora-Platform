using System.Net.Http.Json;
using System.Text.Json;
using LegalAssistant.Api.Repositories;

namespace LegalAssistant.Api.Services;

public sealed class LexoraDocumentQuestionService
    : ILexoraDocumentQuestionService
{
    private const int MaxQuestionLength = 4000;

    private static readonly JsonSerializerOptions JsonOptions =
        new(JsonSerializerDefaults.Web);

    private readonly HttpClient _httpClient;
    private readonly IDocumentRepository _documents;
    private readonly ILogger<LexoraDocumentQuestionService> _logger;
    private readonly IConfiguration _configuration;

    public LexoraDocumentQuestionService(
        HttpClient httpClient,
        IDocumentRepository documents,
        ILogger<LexoraDocumentQuestionService> logger,
        IConfiguration configuration)
    {
        _httpClient = httpClient;
        _documents = documents;
        _logger = logger;
        _configuration = configuration;
    }

    public async Task<DocumentQuestionResult> AskAsync(
        string question,
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

        var ownedDocuments =
            await _documents.GetAllOwnedAsync(
                userId,
                cancellationToken);

        if (ownedDocuments.Count == 0)
        {
            throw new KeyNotFoundException(
                "No documents are available for question answering.");
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
            using var httpRequest = new HttpRequestMessage(
                HttpMethod.Post,
                "/api/v1/rag/ask");

            var clientId =
                _configuration["AiService:ClientId"]
                ?? "client_test";

            var confidentialityCeiling =
                _configuration["AiService:ConfidentialityCeiling"]
                ?? "privileged";

            httpRequest.Headers.Add(
                "X-Client-Id",
                clientId);

            httpRequest.Headers.Add(
                "X-Confidentiality-Ceiling",
                confidentialityCeiling);

            httpRequest.Content = JsonContent.Create(
                request,
                options: JsonOptions);

            response = await _httpClient.SendAsync(
                httpRequest,
                cancellationToken);
        }
        catch (HttpRequestException exception)
        {
            _logger.LogWarning(
                exception,
                "AI RAG service could not be reached for an authorized-library request");

            throw new AiQuestionAnsweringException(
                "The AI question-answering service could not be reached.",
                StatusCodes.Status503ServiceUnavailable,
                exception);
        }
        catch (TaskCanceledException exception)
            when (!cancellationToken.IsCancellationRequested)
        {
            _logger.LogWarning(
                exception,
                "AI RAG service timed out for an authorized-library request");

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

                var errorBody = await response.Content.ReadAsStringAsync(
                    cancellationToken);

                _logger.LogWarning(
                    "AI RAG service returned status {StatusCode} "
                    + "for an authorized-library request. Response: {ResponseBody}",
                    upstreamStatus,
                    errorBody);

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
                _logger.LogWarning(
                    exception,
                    "AI RAG service returned an invalid JSON response");

                throw new AiQuestionAnsweringException(
                    "The AI service returned an invalid response.",
                    StatusCodes.Status502BadGateway,
                    exception);
            }
            catch (NotSupportedException exception)
            {
                _logger.LogWarning(
                    exception,
                    "AI RAG service returned an unsupported response format");

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
                "Authorized-library RAG request completed "
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