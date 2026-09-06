namespace LegalAssistant.Api.Services;

/// <summary>
/// Abstraction over "given a conversation, produce a reply to the latest
/// user message". The placeholder implementation returns canned, keyword-
/// matched replies. A real LLM + RAG-backed implementation (optionally
/// consulting a knowledge graph) replaces it later — ChatbotController only
/// depends on this interface.
/// </summary>
public interface IChatbotService
{
    Task<string> ReplyAsync(IReadOnlyList<ChatTurn> history, CancellationToken cancellationToken = default);
}

public sealed record ChatTurn(string Role, string Content);