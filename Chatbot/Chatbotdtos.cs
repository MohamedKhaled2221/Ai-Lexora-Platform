using LegalAssistant.Api.Services;

namespace LegalAssistant.Api.Chatbot;

public record ChatConversationResponse(int Id, DateTime CreatedAt);

// New trailing members are optional so existing callers/tests keep compiling.
public record ChatMessageResponse(
    int Id,
    string Role,
    string Content,
    DateTime CreatedAt,
    IReadOnlyList<ChatCitation>? Citations = null,
    bool InsufficientEvidence = false,
    string? RequestId = null);

public record SendMessageRequest(string Content);