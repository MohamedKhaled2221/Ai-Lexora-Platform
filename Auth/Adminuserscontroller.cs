using System.Security.Claims;
using System.Text.RegularExpressions;
using LegalAssistant.Api.Data;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Identity;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace LegalAssistant.Api.Auth;

public record SetAiScopeRequest(string ClientId, string ConfidentialityCeiling);

public record AiScopeResponse(string UserId, string Email, string FullName, string? ClientId, string? ConfidentialityCeiling);

/// <summary>
/// Validation for the AI access scope an Admin assigns to a user. Both values end up in HTTP headers sent
/// to the AI service (X-Client-Id / X-Confidentiality-Ceiling), so they are tightly restricted.
/// </summary>
public static class AiScopeValidator
{
    // Must match ConfidentialityLevel in the Python AI service (src/schemas/access_control.py).
    public static readonly IReadOnlyList<string> AllowedCeilings = new[] { "public", "internal", "privileged" };

    private static readonly Regex ClientIdPattern = new(@"^[A-Za-z0-9._:\-]{1,100}$", RegexOptions.Compiled);

    public static (string? ClientId, string? Ceiling, string? Error) Validate(string? clientId, string? ceiling)
    {
        var id = clientId?.Trim();
        if (string.IsNullOrEmpty(id) || !ClientIdPattern.IsMatch(id))
            return (null, null, "clientId is required: letters, digits and . _ : - only, max 100 characters.");

        var level = ceiling?.Trim().ToLowerInvariant();
        if (level is null || !AllowedCeilings.Contains(level))
            return (null, null, $"confidentialityCeiling must be one of: {string.Join(", ", AllowedCeilings)}.");

        return (id, level, null);
    }
}

/// <summary>Admin-only management of each user's AI access scope (one client per user, ceiling per user).</summary>
[ApiController]
[Authorize(Roles = AppRoles.Admin)]
[Route("api/admin/users")]
public sealed class AdminUsersController : ControllerBase
{
    private readonly UserManager<ApplicationUser> _userManager;
    private readonly ILogger<AdminUsersController> _logger;

    public AdminUsersController(UserManager<ApplicationUser> userManager, ILogger<AdminUsersController> logger)
    {
        _userManager = userManager;
        _logger = logger;
    }

    /// <summary>List users with their current AI scope, so you can spot who has none.</summary>
    [HttpGet]
    public async Task<ActionResult<IReadOnlyList<AiScopeResponse>>> List(CancellationToken ct)
    {
        var users = await _userManager.Users
            .OrderBy(u => u.Email)
            .Select(u => new AiScopeResponse(u.Id, u.Email ?? "", u.FullName, u.ClientId, u.ConfidentialityCeiling))
            .ToListAsync(ct);
        return Ok(users);
    }

    /// <summary>Assign (or change) the user's client and confidentiality ceiling.</summary>
    [HttpPut("{userId}/ai-scope")]
    public async Task<ActionResult<AiScopeResponse>> SetAiScope(string userId, [FromBody] SetAiScopeRequest request)
    {
        var (clientId, ceiling, error) = AiScopeValidator.Validate(request.ClientId, request.ConfidentialityCeiling);
        if (error is not null) return BadRequest(new { message = error });

        var user = await _userManager.FindByIdAsync(userId);
        if (user is null) return NotFound(new { message = "User not found." });

        user.ClientId = clientId;
        user.ConfidentialityCeiling = ceiling;
        return await SaveAsync(user, "set");
    }

    /// <summary>Remove the user's AI scope. Once AllowSharedIdentity=false the user can no longer query the AI.</summary>
    [HttpDelete("{userId}/ai-scope")]
    public async Task<ActionResult<AiScopeResponse>> ClearAiScope(string userId)
    {
        var user = await _userManager.FindByIdAsync(userId);
        if (user is null) return NotFound(new { message = "User not found." });

        user.ClientId = null;
        user.ConfidentialityCeiling = null;
        return await SaveAsync(user, "cleared");
    }

    private async Task<ActionResult<AiScopeResponse>> SaveAsync(ApplicationUser user, string action)
    {
        var result = await _userManager.UpdateAsync(user);
        if (!result.Succeeded)
        {
            _logger.LogError("Could not update AI scope for {UserId}: {Errors}", user.Id,
                string.Join("; ", result.Errors.Select(e => e.Description)));
            return StatusCode(StatusCodes.Status500InternalServerError, new { message = "Could not update the user." });
        }

        var admin = User.FindFirstValue(ClaimTypes.NameIdentifier) ?? User.FindFirstValue("sub");
        _logger.LogInformation("Admin {AdminId} {Action} AI scope for user {UserId}: client={ClientId} ceiling={Ceiling}",
            admin, action, user.Id, user.ClientId, user.ConfidentialityCeiling);

        // The scope is baked into the JWT, so it applies from the user's next login / token refresh.
        return Ok(new AiScopeResponse(user.Id, user.Email ?? "", user.FullName, user.ClientId, user.ConfidentialityCeiling));
    }
}