namespace LegalAssistant.Api.Services;

/// <summary>
/// Abstraction over "given a conversation, produce a reply to the latest user message".
/// ReplyAsync is the legacy plain-text contract (kept so PlaceholderChatbotService still compiles).
/// AskAsync is the Package 4 contract: it carries the caller's server-derived AI scope in,
/// and returns the validated answer + trusted citations + abstention flag out.
/// </summary>
public interface IChatbotService
{
    Task<string> ReplyAsync(IReadOnlyList<ChatTurn> history, CancellationToken cancellationToken = default);

    // Default implementation keeps non-P4 implementations (the placeholder) working unchanged.
    async Task<ChatReply> AskAsync(
        IReadOnlyList<ChatTurn> history, AiCallerIdentity identity, CancellationToken cancellationToken = default)
    {
        var text = await ReplyAsync(history, cancellationToken);
        return new ChatReply(text);
    }
}

public sealed record ChatTurn(string Role, string Content);

/// <summary>Trusted citation, resolved by the Python P4 service from retrieved evidence (never built by the UI or LLM).</summary>
public sealed record ChatCitation(string EvidenceId, string DocumentId, string ChunkId, int? Page, string? Section);

/// <summary>Validated P4 answer. InsufficientEvidence=true is a normal abstention, not an error.</summary>
public sealed record ChatReply(
    string Content,
    IReadOnlyList<ChatCitation>? Citations = null,
    bool InsufficientEvidence = false,
    string? RequestId = null,
    string? ModelTag = null);