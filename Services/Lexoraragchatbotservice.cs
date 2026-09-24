using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;
using LegalAssistant.Api.Data;

namespace LegalAssistant.Api.Services;

/// <summary>Wire format of POST /api/v1/p4/chat response (snake_case = Pydantic ValidatedAIResponse).</summary>
public sealed class LexoraP4ChatResponse
{
    [JsonPropertyName("request_id")] public string? RequestId { get; set; }
    [JsonPropertyName("query_id")] public string? QueryId { get; set; }
    [JsonPropertyName("answer")] public string Answer { get; set; } = string.Empty;
    [JsonPropertyName("citations")] public List<LexoraCitation> Citations { get; set; } = new();
    [JsonPropertyName("confidence")] public double Confidence { get; set; }
    [JsonPropertyName("insufficient_evidence")] public bool InsufficientEvidence { get; set; }
    [JsonPropertyName("grounding_valid")] public bool GroundingValid { get; set; }
    [JsonPropertyName("citations_valid")] public bool CitationsValid { get; set; }
    [JsonPropertyName("structured_output_valid")] public bool StructuredOutputValid { get; set; }
    [JsonPropertyName("model_tag")] public string? ModelTag { get; set; }
}

/// <summary>
/// Calls the AI-Lexora Package 4 grounded chatbot (POST /api/v1/p4/chat).
/// It only transports: no answer/citation is built here, and an answer that the AI service did
/// not mark grounded + citation-valid is refused (fail closed) rather than shown.
/// </summary>
public sealed class LexoraRagChatbotService : IChatbotService
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);
    // Older messages had "\n\nالمصادر: ..." appended to Content; never feed that back as assistant context.
    private static readonly Regex LegacySources = new(@"\s*\n\nالمصادر:.*$", RegexOptions.Singleline | RegexOptions.Compiled);

    private readonly HttpClient _httpClient;
    private readonly ILogger<LexoraRagChatbotService> _logger;
    private readonly AiCallerIdentity _fallbackIdentity;

    public LexoraRagChatbotService(HttpClient httpClient, ILogger<LexoraRagChatbotService> logger, IConfiguration configuration)
    {
        _httpClient = httpClient;
        _logger = logger;
        _fallbackIdentity = new AiCallerIdentity(
            configuration["AiService:ClientId"]?.Trim()
                ?? throw new InvalidOperationException("AiService:ClientId is not configured."),
            null,
            configuration["AiService:ConfidentialityCeiling"]?.Trim()
                ?? throw new InvalidOperationException("AiService:ConfidentialityCeiling is not configured."));
    }

    // Legacy entry point. Prefer AskAsync with a per-user identity.
    public async Task<string> ReplyAsync(IReadOnlyList<ChatTurn> history, CancellationToken cancellationToken = default)
        => (await AskAsync(history, _fallbackIdentity, cancellationToken)).Content;

    public async Task<ChatReply> AskAsync(
        IReadOnlyList<ChatTurn> history, AiCallerIdentity identity, CancellationToken cancellationToken = default)
    {
        var lastUserMessage = history.LastOrDefault(t => t.Role == ChatMessageRoles.User)?.Content;
        if (string.IsNullOrWhiteSpace(lastUserMessage))
            throw new InvalidOperationException("No user message to answer.");

        var requestBody = new LexoraP4ChatRequest
        {
            Question = lastUserMessage,
            Filters = new LexoraQueryFilters(),   // relevance filters only; ACL is derived by the AI service from the headers
            SafeContext = history
                .Take(Math.Max(0, history.Count - 1))
                .Where(t => !string.IsNullOrWhiteSpace(t.Content)
                            && (t.Role == ChatMessageRoles.User || t.Role == ChatMessageRoles.Assistant))
                .TakeLast(12)
                .Select(t => new LexoraSafeContextTurn
                {
                    Role = t.Role == ChatMessageRoles.User ? "user" : "assistant",
                    Text = LegacySources.Replace(t.Content, string.Empty)
                })
                .ToList()
        };

        HttpResponseMessage response;
        try
        {
            using var httpRequest = new HttpRequestMessage(HttpMethod.Post, "/api/v1/p4/chat")
            {
                Content = JsonContent.Create(requestBody, options: JsonOptions)
            };
            httpRequest.Headers.Add("X-Client-Id", identity.ClientId);
            if (!string.IsNullOrWhiteSpace(identity.MatterId))
                httpRequest.Headers.Add("X-Matter-Id", identity.MatterId);
            httpRequest.Headers.Add("X-Confidentiality-Ceiling", identity.ConfidentialityCeiling);
            response = await _httpClient.SendAsync(httpRequest, cancellationToken);
        }
        catch (HttpRequestException ex)
        {
            _logger.LogError(ex, "Could not reach the AI-Lexora P4 service");
            throw new AiServiceUnavailableException("The AI service could not be reached.", ex) { UpstreamStatus = 503 };
        }
        catch (TaskCanceledException ex) when (!cancellationToken.IsCancellationRequested)
        {
            _logger.LogError(ex, "AI-Lexora P4 request timed out");
            throw new AiServiceUnavailableException("The AI service timed out.", ex) { UpstreamStatus = 504 };
        }

        if (!response.IsSuccessStatusCode)
        {
            var requestId = await ReadErrorRequestIdAsync(response, cancellationToken);
            _logger.LogWarning("P4 chat returned {Status} (ai request_id={RequestId})", (int)response.StatusCode, requestId);

            if (response.StatusCode == HttpStatusCode.BadRequest || response.StatusCode == HttpStatusCode.UnprocessableEntity)
                throw new ChatbotRejectedException("The question could not be processed. Please rephrase it.", requestId);

            throw new AiServiceUnavailableException(
                response.StatusCode == HttpStatusCode.ServiceUnavailable
                    ? "The AI service is temporarily unavailable."
                    : "The AI service could not produce a verified answer.")
            { UpstreamStatus = (int)response.StatusCode, RequestId = requestId };
        }

        var result = await response.Content.ReadFromJsonAsync<LexoraP4ChatResponse>(JsonOptions, cancellationToken);
        if (result is null || string.IsNullOrWhiteSpace(result.Answer))
            throw new AiServiceUnavailableException("The AI service returned an empty answer.") { UpstreamStatus = 502 };

        // Abstention is a valid, expected outcome: pass it through, flagged, with no citations.
        if (result.InsufficientEvidence)
            return new ChatReply(result.Answer, Array.Empty<ChatCitation>(), true, result.RequestId, result.ModelTag);

        // Fail closed: never show an answer the AI service did not certify.
        if (!result.GroundingValid || !result.CitationsValid || !result.StructuredOutputValid)
        {
            _logger.LogWarning("P4 answer rejected: grounding={G} citations={C} structured={S} (ai request_id={R})",
                result.GroundingValid, result.CitationsValid, result.StructuredOutputValid, result.RequestId);
            throw new AiServiceUnavailableException("The AI service could not produce a verified answer.")
            { UpstreamStatus = 502, RequestId = result.RequestId };
        }

        var citations = result.Citations
            .Select(c => new ChatCitation(c.EvidenceId, c.DocumentId, c.ChunkId, c.Page, c.Section))
            .ToList();

        return new ChatReply(result.Answer, citations, false, result.RequestId, result.ModelTag);
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

/// <summary>Thrown when the external AI-Lexora service is unreachable or fails.</summary>
public sealed class AiServiceUnavailableException : Exception
{
    public AiServiceUnavailableException(string message, Exception? innerException = null) : base(message, innerException) { }

    /// <summary>HTTP status the AI service returned (or 503/504 for transport failures). Null if unknown.</summary>
    public int? UpstreamStatus { get; init; }

    /// <summary>The AI service's request_id, for support / trace correlation.</summary>
    public string? RequestId { get; init; }
}

/// <summary>The AI service rejected the question itself (400/422). Safe to show to the user.</summary>
public sealed class ChatbotRejectedException : Exception
{
    public ChatbotRejectedException(string message, string? requestId = null) : base(message) => RequestId = requestId;
    public string? RequestId { get; }
}