namespace LegalAssistant.Api.Chatbot;

public record ChatConversationResponse(int Id, DateTime CreatedAt);

public record ChatMessageResponse(int Id, string Role, string Content, DateTime CreatedAt);

public record SendMessageRequest(string Content);