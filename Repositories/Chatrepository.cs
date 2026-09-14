using LegalAssistant.Api.Data;
using Microsoft.EntityFrameworkCore;

namespace LegalAssistant.Api.Repositories;

public class ChatRepository : IChatRepository
{
    private readonly AppDbContext _db;

    public ChatRepository(AppDbContext db) => _db = db;

    public async Task<ChatConversation> CreateConversationAsync(string userId)
    {
        var conversation = new ChatConversation { UserId = userId };
        _db.ChatConversations.Add(conversation);
        await _db.SaveChangesAsync();
        return conversation;
    }

    public Task<ChatConversation?> GetOwnedConversationAsync(int conversationId, string userId) =>
        _db.ChatConversations
            .Include(c => c.Messages.OrderBy(m => m.CreatedAt))
            .SingleOrDefaultAsync(c => c.Id == conversationId && c.UserId == userId);

    public Task<List<ChatConversation>> GetOwnedConversationsAsync(string userId) =>
        _db.ChatConversations
            .Where(c => c.UserId == userId)
            .OrderByDescending(c => c.CreatedAt)
            .ToListAsync();

    public void AddMessage(ChatMessage message) => _db.ChatMessages.Add(message);

    public Task SaveChangesAsync() => _db.SaveChangesAsync();
}