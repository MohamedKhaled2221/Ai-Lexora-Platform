using System.Security.Claims;
using LegalAssistant.Api.Data;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Identity;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace LegalAssistant.Api.Users;

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

    private string? GetCurrentUserId() => User.FindFirstValue(ClaimTypes.NameIdentifier) ?? User.FindFirstValue("sub");

    private async Task<AdminUserResponse> ToResponse(ApplicationUser user) => new(
        user.Id,
        user.Email ?? string.Empty,
        user.FullName,
        user.CreatedAt,
        (await _userManager.GetRolesAsync(user)).ToArray(),
        !user.LockoutEnd.HasValue || user.LockoutEnd <= DateTimeOffset.UtcNow);
}
