using System.Security.Claims;
using System.Text.Json;
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
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);

    private readonly IChatbotService _chatbotService;
    private readonly IAiCallerIdentityProvider _identityProvider;
    private readonly ILogger<ChatbotController> _logger;

    public ChatbotController(
        IChatRepository chats, IChatbotService chatbotService,
        IAiCallerIdentityProvider identityProvider, ILogger<ChatbotController> logger)
    {
        _chats = chats;
        _chatbotService = chatbotService;
        _identityProvider = identityProvider;
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

        // Scope is derived from the authenticated user on the server; nothing from the request body is trusted.
        AiCallerIdentity identity;
        try { identity = _identityProvider.Resolve(User); }
        catch (InvalidOperationException ex)
        {
            _logger.LogWarning(ex, "No AI scope for user {UserId}", userId);
            return StatusCode(StatusCodes.Status403Forbidden, new { message = "Your account has no access scope for the legal assistant." });
        }

        ChatReply reply;
        try
        {
            reply = await _chatbotService.AskAsync(history, identity, HttpContext.RequestAborted);
        }
        catch (ChatbotRejectedException ex)
        {
            return BadRequest(new { message = ex.Message, requestId = ex.RequestId });
        }
        catch (AiServiceUnavailableException ex)
        {
            _logger.LogError(ex, "Chatbot reply failed for conversation {ConversationId} (ai request_id={RequestId})", conversationId, ex.RequestId);
            var status = ex.UpstreamStatus is 503 or 504 ? StatusCodes.Status503ServiceUnavailable : StatusCodes.Status502BadGateway;
            return StatusCode(status, new { message = ex.Message, requestId = ex.RequestId });
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
            Content = reply.Content,
            InsufficientEvidence = reply.InsufficientEvidence,
            CitationsJson = reply.Citations is { Count: > 0 } ? JsonSerializer.Serialize(reply.Citations, JsonOptions) : null,
            AiRequestId = reply.RequestId,
            ModelTag = reply.ModelTag
        };
        _chats.AddMessage(assistantMessage);
        await _chats.SaveChangesAsync();

        _logger.LogInformation("Chatbot replied in conversation {ConversationId}", conversationId);
        return Ok(ToResponse(assistantMessage));
    }

    private string? CurrentUserId() => User.FindFirstValue(ClaimTypes.NameIdentifier) ?? User.FindFirstValue("sub");

    private static ChatMessageResponse ToResponse(ChatMessage message) =>
        new(message.Id, message.Role, message.Content, message.CreatedAt,
            ParseCitations(message.CitationsJson), message.InsufficientEvidence, message.AiRequestId);

    private static IReadOnlyList<ChatCitation>? ParseCitations(string? json)
    {
        if (string.IsNullOrWhiteSpace(json)) return null;
        try { return JsonSerializer.Deserialize<List<ChatCitation>>(json, JsonOptions); }
        catch (JsonException) { return null; }
    }
}