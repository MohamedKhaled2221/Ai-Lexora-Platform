using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;

namespace LegalAssistant.Api.Services;

/// <summary>
/// Abstraction over the AI-Lexora Package 3 controlled document generation
/// pipeline (M1 template selection -&gt; M5 approved clauses -&gt; M1 assembly
/// -&gt; M4 validation -&gt; export). Mirrors <see cref="IChatbotService"/>'s shape:
/// every call takes the caller's <see cref="AiCallerIdentity"/> explicitly,
/// resolved server-side by <see cref="IAiCallerIdentityProvider"/> — never
/// trusted from the request body.
/// </summary>
public interface IPackage3DocumentGenerationService
{
    /// <summary>GET /api/v1/p3/templates — the enabled templates and their
    /// guided-input fields (document_type, jurisdiction, required fields).</summary>
    Task<IReadOnlyCollection<LexoraP3TemplateSummary>> GetTemplatesAsync(
        AiCallerIdentity identity,
        CancellationToken cancellationToken = default);

    /// <summary>POST /api/v1/p3/generate — runs the full M1 -&gt; M5 -&gt; M4
    /// pipeline and returns the validated draft (plus the exported docx file
    /// name, when export_docx was requested and validation allowed export).</summary>
    Task<LexoraP3GenerateResponse> GenerateAsync(
        LexoraP3GenerateRequest request,
        AiCallerIdentity identity,
        CancellationToken cancellationToken = default);

    /// <summary>GET /api/v1/p3/exports/{fileName} — downloads a previously
    /// generated docx by the file name returned from <see cref="GenerateAsync"/>.</summary>
    Task<GeneratedDocument> DownloadExportAsync(
        string fileName,
        AiCallerIdentity identity,
        CancellationToken cancellationToken = default);
}

/// <summary>
/// Calls the AI-Lexora Package 3 endpoints (same host/port as Package 4 —
/// AiService:BaseUrl). Transport only: it does not reinterpret M4's
/// validation verdict (export_allowed, requires_lawyer_review, etc.) —
/// callers (the controller) decide what to do with those flags.
/// </summary>
public sealed class LexoraP3DocumentGenerationService : IPackage3DocumentGenerationService
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);

    private readonly HttpClient _httpClient;
    private readonly ILogger<LexoraP3DocumentGenerationService> _logger;

    public LexoraP3DocumentGenerationService(HttpClient httpClient, ILogger<LexoraP3DocumentGenerationService> logger)
    {
        _httpClient = httpClient;
        _logger = logger;
    }

    public async Task<IReadOnlyCollection<LexoraP3TemplateSummary>> GetTemplatesAsync(
        AiCallerIdentity identity, CancellationToken cancellationToken = default)
    {
        using var httpRequest = new HttpRequestMessage(HttpMethod.Get, "/api/v1/p3/templates");
        ApplyIdentityHeaders(httpRequest, identity);

        var response = await SendAsync(httpRequest, "templates", cancellationToken);

        var result = await response.Content.ReadFromJsonAsync<LexoraP3TemplatesResponse>(JsonOptions, cancellationToken);
        return result?.Templates ?? new List<LexoraP3TemplateSummary>();
    }

    public async Task<LexoraP3GenerateResponse> GenerateAsync(
        LexoraP3GenerateRequest request, AiCallerIdentity identity, CancellationToken cancellationToken = default)
    {
        using var httpRequest = new HttpRequestMessage(HttpMethod.Post, "/api/v1/p3/generate")
        {
            Content = JsonContent.Create(request, options: JsonOptions)
        };
        ApplyIdentityHeaders(httpRequest, identity);

        var response = await SendAsync(httpRequest, "generate", cancellationToken);

        var result = await response.Content.ReadFromJsonAsync<LexoraP3GenerateResponse>(JsonOptions, cancellationToken);
        return result ?? throw new AiServiceUnavailableException("The P3 service returned an empty response.") { UpstreamStatus = 502 };
    }

    public async Task<GeneratedDocument> DownloadExportAsync(
        string fileName, AiCallerIdentity identity, CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(fileName))
            throw new ArgumentException("fileName is required.", nameof(fileName));

        using var httpRequest = new HttpRequestMessage(HttpMethod.Get, $"/api/v1/p3/exports/{Uri.EscapeDataString(fileName)}");
        ApplyIdentityHeaders(httpRequest, identity);

        var response = await SendAsync(httpRequest, "exports", cancellationToken);

        var bytes = await response.Content.ReadAsByteArrayAsync(cancellationToken);
        var contentType = response.Content.Headers.ContentType?.ToString()
            ?? "application/vnd.openxmlformats-officedocument.wordprocessingml.document";

        return new GeneratedDocument(fileName, contentType, bytes);
    }

    private static void ApplyIdentityHeaders(HttpRequestMessage request, AiCallerIdentity identity)
    {
        request.Headers.Add("X-Client-Id", identity.ClientId);
        if (!string.IsNullOrWhiteSpace(identity.MatterId))
            request.Headers.Add("X-Matter-Id", identity.MatterId);
        request.Headers.Add("X-Confidentiality-Ceiling", identity.ConfidentialityCeiling);
    }

    /// <summary>
    /// Sends the request and turns transport failures / non-success statuses
    /// into the same exception vocabulary <see cref="LexoraRagChatbotService"/>
    /// uses for Package 4, so the controller layer can handle both the same way:
    ///   - unreachable / timeout           -&gt; AiServiceUnavailableException (503/504)
    ///   - 400 / 422 (bad request/fields)  -&gt; DocumentGenerationRejectedException
    ///   - 404 (unknown template/export)   -&gt; DocumentGenerationNotFoundException
    ///   - anything else non-success       -&gt; AiServiceUnavailableException
    /// </summary>
    private async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, string stage, CancellationToken cancellationToken)
    {
        HttpResponseMessage response;
        try
        {
            response = await _httpClient.SendAsync(request, cancellationToken);
        }
        catch (HttpRequestException ex)
        {
            _logger.LogError(ex, "Could not reach the AI-Lexora P3 service ({Stage})", stage);
            throw new AiServiceUnavailableException("The document-generation (P3) service could not be reached.", ex) { UpstreamStatus = 503 };
        }
        catch (TaskCanceledException ex) when (!cancellationToken.IsCancellationRequested)
        {
            _logger.LogError(ex, "AI-Lexora P3 request timed out ({Stage})", stage);
            throw new AiServiceUnavailableException("The document-generation (P3) service timed out.", ex) { UpstreamStatus = 504 };
        }

        if (response.IsSuccessStatusCode)
            return response;

        var requestId = await ReadErrorRequestIdAsync(response, cancellationToken);
        _logger.LogWarning("P3 {Stage} returned {Status} (ai request_id={RequestId})", stage, (int)response.StatusCode, requestId);

        switch (response.StatusCode)
        {
            case HttpStatusCode.BadRequest:
            case HttpStatusCode.UnprocessableEntity:
                throw new DocumentGenerationRejectedException(
                    "The document request was rejected. Check the required fields and clause selections.", requestId);

            case HttpStatusCode.NotFound:
                throw new DocumentGenerationNotFoundException(
                    stage == "exports" ? "The generated document was not found." : "The requested template was not found.", requestId);

            case HttpStatusCode.ServiceUnavailable:
                throw new AiServiceUnavailableException(
                    "The document-generation (P3) service is temporarily unavailable.")
                { UpstreamStatus = 503, RequestId = requestId };

            default:
                throw new AiServiceUnavailableException(
                    $"The document-generation (P3) service returned status {(int)response.StatusCode}.")
                { UpstreamStatus = (int)response.StatusCode, RequestId = requestId };
        }
    }

    private static async Task<string?> ReadErrorRequestIdAsync(HttpResponseMessage r, CancellationToken ct)
    {
        try
        {
            using var doc = await JsonDocument.ParseAsync(await r.Content.ReadAsStreamAsync(ct), cancellationToken: ct);
            return doc.RootElement.GetProperty("error").GetProperty("request_id").GetString();
        }
        catch { return null; }
    }
}

/// <summary>The P3 service rejected the request itself (400/422) — safe to show to the user.</summary>
public sealed class DocumentGenerationRejectedException : Exception
{
    public DocumentGenerationRejectedException(string message, string? requestId = null) : base(message) => RequestId = requestId;
    public string? RequestId { get; }
}

/// <summary>The requested template or generated export does not exist (404).</summary>
public sealed class DocumentGenerationNotFoundException : Exception
{
    public DocumentGenerationNotFoundException(string message, string? requestId = null) : base(message) => RequestId = requestId;
    public string? RequestId { get; }
}