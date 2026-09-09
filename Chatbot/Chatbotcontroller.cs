using System.Security.Claims;
using LegalAssistant.Api.Data;
using LegalAssistant.Api.Repositories;
using LegalAssistant.Api.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace LegalAssistant.Api.Chatbot;

[ApiController]
[Authorize]
[Route("api/chatbot")]
public class ChatbotController : ControllerBase
{
    private readonly IChatRepository _chats;
    private readonly IChatbotService _chatbotService;
    private readonly ILogger<ChatbotController> _logger;

    public ChatbotController(IChatRepository chats, IChatbotService chatbotService, ILogger<ChatbotController> logger)
    {
        _chats = chats;
        _chatbotService = chatbotService;
        _logger = logger;
    }

    [HttpGet("conversations")]
    public async Task<ActionResult<IReadOnlyCollection<ChatConversationResponse>>> GetConversations()
    {
        var userId = CurrentUserId();
        if (userId is null) return Unauthorized();

        var conversations = await _chats.GetOwnedConversationsAsync(userId);
        return Ok(conversations.Select(c => new ChatConversationResponse(c.Id, c.CreatedAt)).ToList());
    }

    [HttpPost("conversations")]
    public async Task<ActionResult<ChatConversationResponse>> CreateConversation()
    {
        var userId = CurrentUserId();
        if (userId is null) return Unauthorized();

        var conversation = await _chats.CreateConversationAsync(userId);
        return CreatedAtAction(nameof(GetMessages), new { conversationId = conversation.Id },
            new ChatConversationResponse(conversation.Id, conversation.CreatedAt));
    }

    [HttpGet("conversations/{conversationId:int}/messages")]
    public async Task<ActionResult<IReadOnlyCollection<ChatMessageResponse>>> GetMessages(int conversationId)
    {
        var userId = CurrentUserId();
        if (userId is null) return Unauthorized();

        var conversation = await _chats.GetOwnedConversationAsync(conversationId, userId);
        if (conversation is null) return NotFound(new { message = "Conversation not found." });

        return Ok(conversation.Messages.Select(ToResponse).ToList());
    }

    [HttpPost("conversations/{conversationId:int}/messages")]
    public async Task<ActionResult<ChatMessageResponse>> SendMessage(int conversationId, SendMessageRequest request)
    {
        if (string.IsNullOrWhiteSpace(request.Content) || request.Content.Length > 4000)
            return BadRequest(new { message = "Message content is required and must be 4000 characters or fewer." });

        var userId = CurrentUserId();
        if (userId is null) return Unauthorized();

        var conversation = await _chats.GetOwnedConversationAsync(conversationId, userId);
        if (conversation is null) return NotFound(new { message = "Conversation not found." });

        var userMessage = new ChatMessage
        {
            ConversationId = conversationId,
            Role = ChatMessageRoles.User,
            Content = request.Content.Trim()
        };
        _chats.AddMessage(userMessage);
        await _chats.SaveChangesAsync();

        var history = conversation.Messages
            .Append(userMessage)
            .OrderBy(m => m.CreatedAt)
            .Select(m => new ChatTurn(m.Role, m.Content))
            .ToList();

        string replyContent;
        try
        {
            replyContent = await _chatbotService.ReplyAsync(history, HttpContext.RequestAborted);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Chatbot reply failed for conversation {ConversationId}", conversationId);
            return StatusCode(StatusCodes.Status502BadGateway, new { message = "The chatbot service failed to respond." });
        }

        var assistantMessage = new ChatMessage
        {
            ConversationId = conversationId,
            Role = ChatMessageRoles.Assistant,
            Content = replyContent
        };
        _chats.AddMessage(assistantMessage);
        await _chats.SaveChangesAsync();

        _logger.LogInformation("Chatbot replied in conversation {ConversationId}", conversationId);
        return Ok(ToResponse(assistantMessage));
    }

    private string? CurrentUserId() => User.FindFirstValue(ClaimTypes.NameIdentifier) ?? User.FindFirstValue("sub");

    private static ChatMessageResponse ToResponse(ChatMessage message) =>
        new(message.Id, message.Role, message.Content, message.CreatedAt);
}