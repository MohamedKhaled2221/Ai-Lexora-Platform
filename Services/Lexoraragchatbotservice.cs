using LegalAssistant.Api.Data;
using System.Net.Http.Json;
using System.Text.Json;

namespace LegalAssistant.Api.Services;

/// <summary>
/// Calls the AI-Lexora Python RAG service (POST /api/v1/rag/ask) to answer
/// the latest user message. Replaces <see cref="PlaceholderChatbotService"/>
/// behind the same <see cref="IChatbotService"/> interface — ChatbotController
/// does not change.
///
/// The AI service is a separate local process (FastAPI + Qdrant + Ollama).
/// If it isn't running, or returns an error, this throws — ChatbotController
/// already catches that and returns a 502 with a clear message rather than
/// crashing the request.
/// </summary>
public sealed class LexoraRagChatbotService : IChatbotService
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);

    private readonly HttpClient _httpClient;
    private readonly ILogger<LexoraRagChatbotService> _logger;

    public LexoraRagChatbotService(HttpClient httpClient, ILogger<LexoraRagChatbotService> logger)
    {
        _httpClient = httpClient;
        _logger = logger;
    }

    public async Task<string> ReplyAsync(IReadOnlyList<ChatTurn> history, CancellationToken cancellationToken = default)
    {
        var lastUserMessage = history.LastOrDefault(t => t.Role == ChatMessageRoles.User)?.Content;
        if (string.IsNullOrWhiteSpace(lastUserMessage))
            throw new InvalidOperationException("No user message to answer.");

        var requestBody = new LexoraAskRequest
        {
            Question = lastUserMessage,
            Filters = new LexoraQueryFilters()
        };

        HttpResponseMessage response;
        try
        {
            response = await _httpClient.PostAsJsonAsync("/api/v1/rag/ask", requestBody, JsonOptions, cancellationToken);
        }
        catch (HttpRequestException ex)
        {
            _logger.LogError(ex, "Could not reach the AI-Lexora RAG service");
            throw new AiServiceUnavailableException("The AI service could not be reached.", ex);
        }
        catch (TaskCanceledException ex) when (!cancellationToken.IsCancellationRequested)
        {
            _logger.LogError(ex, "AI-Lexora RAG service request timed out");
            throw new AiServiceUnavailableException("The AI service timed out.", ex);
        }

        if (!response.IsSuccessStatusCode)
        {
            var body = await response.Content.ReadAsStringAsync(cancellationToken);
            _logger.LogError("AI-Lexora RAG service returned {StatusCode}: {Body}", (int)response.StatusCode, body);
            throw new AiServiceUnavailableException($"The AI service returned status {(int)response.StatusCode}.");
        }

        var result = await response.Content.ReadFromJsonAsync<LexoraAiResponse>(JsonOptions, cancellationToken);
        if (result is null || string.IsNullOrWhiteSpace(result.Answer))
            throw new AiServiceUnavailableException("The AI service returned an empty answer.");

        return AppendSources(result);
    }

    private static string AppendSources(LexoraAiResponse result)
    {
        if (result.Citations.Count == 0)
            return result.Answer;

        var sources = result.Citations
            .Select(c => c.Section is { Length: > 0 } section ? $"{c.DocumentId} ({section})" : c.DocumentId)
            .Distinct();

        return $"{result.Answer}\n\nالمصادر: {string.Join("، ", sources)}";
    }
}

/// <summary>Thrown when the external AI-Lexora service is unreachable or fails.</summary>
public sealed class AiServiceUnavailableException : Exception
{
    public AiServiceUnavailableException(string message, Exception? innerException = null)
        : base(message, innerException)
    {
    }
}