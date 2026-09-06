using LegalAssistant.Api.Data;

namespace LegalAssistant.Api.Repositories;

public interface IChatRepository
{
    Task<ChatConversation> CreateConversationAsync(string userId);
    Task<ChatConversation?> GetOwnedConversationAsync(int conversationId, string userId);
    Task<List<ChatConversation>> GetOwnedConversationsAsync(string userId);
    void AddMessage(ChatMessage message);
    Task SaveChangesAsync();
}