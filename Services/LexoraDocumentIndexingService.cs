using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;

namespace LegalAssistant.Api.Services;

public interface ILexoraDocumentIndexingService
{
    Task<LexoraDocumentIngestionResponse> IndexAsync(
        int backendDocumentId,
        string fileName,
        string fullPath,
        string? contentType,
        CancellationToken cancellationToken = default);
}

public static class LexoraDocumentIds
{
    public static string FromBackendId(int backendDocumentId)
    {
        if (backendDocumentId <= 0)
            throw new ArgumentOutOfRangeException(
                nameof(backendDocumentId),
                "Backend document ID must be positive.");

        return $"backend-doc-{backendDocumentId}";
    }
}

public sealed class LexoraDocumentIndexingService
    : ILexoraDocumentIndexingService
{
    private static readonly JsonSerializerOptions JsonOptions =
        new(JsonSerializerDefaults.Web);

    private readonly HttpClient _httpClient;
    private readonly ILogger<LexoraDocumentIndexingService> _logger;

    public LexoraDocumentIndexingService(
        HttpClient httpClient,
        ILogger<LexoraDocumentIndexingService> logger)
    {
        _httpClient = httpClient;
        _logger = logger;
    }

    public async Task<LexoraDocumentIngestionResponse> IndexAsync(
        int backendDocumentId,
        string fileName,
        string fullPath,
        string? contentType,
        CancellationToken cancellationToken = default)
    {
        var aiDocumentId =
            LexoraDocumentIds.FromBackendId(backendDocumentId);

        if (!File.Exists(fullPath))
        {
            throw new AiDocumentIndexingException(
                "The stored document file could not be found.",
                StatusCodes.Status500InternalServerError);
        }

        await using var fileStream = new FileStream(
            fullPath,
            FileMode.Open,
            FileAccess.Read,
            FileShare.Read,
            bufferSize: 81920,
            useAsync: true);

        using var fileContent =
            new StreamContent(fileStream);

        if (MediaTypeHeaderValue.TryParse(
                contentType,
                out var parsedContentType))
        {
            fileContent.Headers.ContentType =
                parsedContentType;
        }
        else
        {
            fileContent.Headers.ContentType =
                new MediaTypeHeaderValue(
                    "application/octet-stream");
        }

        using var form = new MultipartFormDataContent();

        form.Add(
            fileContent,
            "file",
            Path.GetFileName(fileName));

        var requestPath =
            "/api/v1/documents/ingest"
            + "?document_id="
            + Uri.EscapeDataString(aiDocumentId);

        HttpResponseMessage response;

        try
        {
            response = await _httpClient.PostAsync(
                requestPath,
                form,
                cancellationToken);
        }
        catch (HttpRequestException exception)
        {
            _logger.LogWarning(
                "AI document-ingestion service could not be reached "
                + "for backend document {DocumentId}",
                backendDocumentId);

            throw new AiDocumentIndexingException(
                "The AI document-ingestion service could not be reached.",
                StatusCodes.Status503ServiceUnavailable,
                exception);
        }
        catch (TaskCanceledException exception)
            when (!cancellationToken.IsCancellationRequested)
        {
            _logger.LogWarning(
                "AI document ingestion timed out "
                + "for backend document {DocumentId}",
                backendDocumentId);

            throw new AiDocumentIndexingException(
                "The AI document-ingestion service timed out.",
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
                    "AI document ingestion returned status {StatusCode} "
                    + "for backend document {DocumentId}",
                    upstreamStatus,
                    backendDocumentId);

                var downstreamStatus =
                    upstreamStatus is 400 or 413 or 415 or 422
                        ? upstreamStatus
                        : StatusCodes.Status502BadGateway;

                throw new AiDocumentIndexingException(
                    "The AI service rejected or failed to index the document.",
                    downstreamStatus);
            }

            LexoraDocumentIngestionResponse? result;

            try
            {
                result =
                    await response.Content
                        .ReadFromJsonAsync<LexoraDocumentIngestionResponse>(
                            JsonOptions,
                            cancellationToken);
            }
            catch (JsonException exception)
            {
                throw new AiDocumentIndexingException(
                    "The AI service returned an invalid ingestion response.",
                    StatusCodes.Status502BadGateway,
                    exception);
            }
            catch (NotSupportedException exception)
            {
                throw new AiDocumentIndexingException(
                    "The AI service returned an unsupported ingestion response.",
                    StatusCodes.Status502BadGateway,
                    exception);
            }

            if (result is null
                || !string.Equals(
                    result.DocumentId,
                    aiDocumentId,
                    StringComparison.Ordinal)
                || !string.Equals(
                    result.Status,
                    "indexed",
                    StringComparison.OrdinalIgnoreCase)
                || result.ChunksIndexed < 1)
            {
                throw new AiDocumentIndexingException(
                    "The AI service returned an invalid ingestion result.",
                    StatusCodes.Status502BadGateway);
            }

            _logger.LogInformation(
                "Backend document {DocumentId} indexed successfully "
                + "with {ChunkCount} chunks",
                backendDocumentId,
                result.ChunksIndexed);

            return result;
        }
    }
}

public sealed class AiDocumentIndexingException : Exception
{
    public AiDocumentIndexingException(
        string message,
        int responseStatusCode,
        Exception? innerException = null)
        : base(message, innerException)
    {
        ResponseStatusCode = responseStatusCode;
    }

    public int ResponseStatusCode { get; }
}
