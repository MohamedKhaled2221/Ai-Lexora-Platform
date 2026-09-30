using System.Security.Claims;
using System.Text.RegularExpressions;
using LegalAssistant.Api.Data;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Identity;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace LegalAssistant.Api.Users;

// =========================================================
// AI-scope request/validator, moved here from the old
// LegalAssistant.Api.Auth.AdminUsersController (that file's
// controller class is gone — merged into this one).
// =========================================================

public record SetAiScopeRequest(string ClientId, string ConfidentialityCeiling);

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

[ApiController]
[Authorize(Roles = AppRoles.Admin)]
[Route("api/admin/users")]
public class AdminUsersController : ControllerBase
{
    private readonly UserManager<ApplicationUser> _userManager;
    private readonly ILogger<AdminUsersController> _logger;

    public AdminUsersController(UserManager<ApplicationUser> userManager, ILogger<AdminUsersController> logger)
    {
        _userManager = userManager;
        _logger = logger;
    }

    /// <summary>Paged, searchable user list. Now also carries each user's AI
    /// scope (ClientId / ConfidentialityCeiling) — see the note below on
    /// AdminUserResponse — so you can spot who has none from the same list.</summary>
    [HttpGet]
    public async Task<ActionResult<PagedUsersResponse>> List(
        [FromQuery] int page = 1,
        [FromQuery] int pageSize = 20,
        [FromQuery] string? search = null)
    {
        if (page < 1) return BadRequest(new { message = "Page must be at least 1." });
        if (pageSize is < 1 or > 100) return BadRequest(new { message = "Page size must be between 1 and 100." });

        var query = _userManager.Users.AsNoTracking();
        if (!string.IsNullOrWhiteSpace(search))
        {
            var searchTerm = search.Trim();
            query = query.Where(u => u.Email!.Contains(searchTerm) || u.FullName.Contains(searchTerm));
        }

        var totalCount = await query.CountAsync();
        var users = await query
            .OrderByDescending(u => u.CreatedAt)
            .Skip((page - 1) * pageSize)
            .Take(pageSize)
            .ToListAsync();

        var responses = await Task.WhenAll(users.Select(ToResponse));
        return Ok(new PagedUsersResponse(responses, page, pageSize, totalCount, (int)Math.Ceiling(totalCount / (double)pageSize)));
    }

    [HttpPut("{id}/role")]
    public async Task<ActionResult<AdminUserResponse>> UpdateRole(string id, UpdateUserRoleRequest request)
    {
        if (GetCurrentUserId() == id)
            return BadRequest(new { message = "You cannot change your own role." });
        if (request.Role is not (AppRoles.Admin or AppRoles.Lawyer))
            return BadRequest(new { message = "Role must be Admin or Lawyer." });

        var user = await _userManager.FindByIdAsync(id);
        if (user is null) return NotFound(new { message = "User not found." });

        var currentRoles = await _userManager.GetRolesAsync(user);
        if (!currentRoles.Contains(request.Role))
        {
            var addResult = await _userManager.AddToRoleAsync(user, request.Role);
            if (!addResult.Succeeded)
                return BadRequest(new { message = "Could not update user role.", errors = addResult.Errors.Select(e => e.Description) });
        }

        var rolesToRemove = currentRoles.Where(role => role != request.Role).ToArray();
        if (rolesToRemove.Length > 0)
        {
            var removeResult = await _userManager.RemoveFromRolesAsync(user, rolesToRemove);
            if (!removeResult.Succeeded)
                return BadRequest(new { message = "Could not update user role.", errors = removeResult.Errors.Select(e => e.Description) });
        }

        _logger.LogInformation("Admin updated role for user {UserId} to {Role}", id, request.Role);
        return Ok(await ToResponse(user));
    }

    [HttpPut("{id}/status")]
    public async Task<ActionResult<AdminUserResponse>> UpdateStatus(string id, UpdateUserStatusRequest request)
    {
        if (GetCurrentUserId() == id)
            return BadRequest(new { message = "You cannot change your own account status." });

        var user = await _userManager.FindByIdAsync(id);
        if (user is null) return NotFound(new { message = "User not found." });

        user.LockoutEnabled = true;
        user.LockoutEnd = request.IsActive ? null : DateTimeOffset.MaxValue;
        var result = await _userManager.UpdateAsync(user);
        if (!result.Succeeded)
            return BadRequest(new { message = "Could not update account status.", errors = result.Errors.Select(e => e.Description) });

        _logger.LogInformation("Admin set user {UserId} active status to {IsActive}", id, request.IsActive);
        return Ok(await ToResponse(user));
    }

    /// <summary>Assign (or change) the user's AI client and confidentiality
    /// ceiling. Merged in from the old Auth.AdminUsersController.</summary>
    [HttpPut("{userId}/ai-scope")]
    public async Task<ActionResult<AdminUserResponse>> SetAiScope(string userId, [FromBody] SetAiScopeRequest request)
    {
        var (clientId, ceiling, error) = AiScopeValidator.Validate(request.ClientId, request.ConfidentialityCeiling);
        if (error is not null) return BadRequest(new { message = error });

        var user = await _userManager.FindByIdAsync(userId);
        if (user is null) return NotFound(new { message = "User not found." });

        user.ClientId = clientId;
        user.ConfidentialityCeiling = ceiling;
        return await SaveAiScopeAsync(user, "set");
    }

    /// <summary>Remove the user's AI scope. Once AllowSharedIdentity=false the user can no longer query the AI.</summary>
    [HttpDelete("{userId}/ai-scope")]
    public async Task<ActionResult<AdminUserResponse>> ClearAiScope(string userId)
    {
        var user = await _userManager.FindByIdAsync(userId);
        if (user is null) return NotFound(new { message = "User not found." });

        user.ClientId = null;
        user.ConfidentialityCeiling = null;
        return await SaveAiScopeAsync(user, "cleared");
    }

    private async Task<ActionResult<AdminUserResponse>> SaveAiScopeAsync(ApplicationUser user, string action)
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
        return Ok(await ToResponse(user));
    }

    private string? GetCurrentUserId() => User.FindFirstValue(ClaimTypes.NameIdentifier) ?? User.FindFirstValue("sub");

    private async Task<AdminUserResponse> ToResponse(ApplicationUser user) => new(
        user.Id,
        user.Email ?? string.Empty,
        user.FullName,
        user.CreatedAt,
        (await _userManager.GetRolesAsync(user)).ToArray(),
        !user.LockoutEnd.HasValue || user.LockoutEnd <= DateTimeOffset.UtcNow,
        user.ClientId,
        user.ConfidentialityCeiling);
}