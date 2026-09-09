using System.Security.Claims;
using LegalAssistant.Api.Auth;
using LegalAssistant.Api.Data;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Identity;
using Microsoft.AspNetCore.Mvc;

namespace LegalAssistant.Api.Users;

[ApiController]
[Authorize]
[Route("api/profile")]
public class ProfileController : ControllerBase
{
    private readonly UserManager<ApplicationUser> _userManager;
    private readonly ILogger<ProfileController> _logger;
    private readonly RefreshTokenService _refreshTokenService;

    public ProfileController(
        UserManager<ApplicationUser> userManager,
        ILogger<ProfileController> logger,
        RefreshTokenService refreshTokenService)
    {
        _userManager = userManager;
        _logger = logger;
        _refreshTokenService = refreshTokenService;
    }

    [HttpGet]
    public async Task<ActionResult<ProfileResponse>> Get()
    {
        var user = await GetCurrentUser();
        return user is null ? Unauthorized() : Ok(await ToResponse(user));
    }

    [HttpPut]
    public async Task<ActionResult<ProfileResponse>> Update(UpdateProfileRequest request)
    {
        if (string.IsNullOrWhiteSpace(request.FullName) || request.FullName.Trim().Length > 150)
            return BadRequest(new { message = "Full name is required and must be 150 characters or fewer." });

        var user = await GetCurrentUser();
        if (user is null) return Unauthorized();

        user.FullName = request.FullName.Trim();
        var result = await _userManager.UpdateAsync(user);
        if (!result.Succeeded)
            return BadRequest(new { message = "Could not update profile.", errors = result.Errors.Select(e => e.Description) });

        _logger.LogInformation("Profile updated for user {UserId}", user.Id);
        return Ok(await ToResponse(user));
    }

    [HttpPut("password")]
    public async Task<IActionResult> ChangePassword(ChangePasswordRequest request)
    {
        if (string.IsNullOrWhiteSpace(request.CurrentPassword) || string.IsNullOrWhiteSpace(request.NewPassword))
            return BadRequest(new { message = "Current password and new password are required." });

        var user = await GetCurrentUser();
        if (user is null) return Unauthorized();

        var result = await _userManager.ChangePasswordAsync(user, request.CurrentPassword, request.NewPassword);
        if (!result.Succeeded)
            return BadRequest(new { message = "Could not change password.", errors = result.Errors.Select(e => e.Description) });

        await _refreshTokenService.RevokeAllAsync(user.Id);
        _logger.LogInformation("Password changed for user {UserId}", user.Id);
        return NoContent();
    }

    private async Task<ApplicationUser?> GetCurrentUser()
    {
        var userId = User.FindFirstValue(ClaimTypes.NameIdentifier) ?? User.FindFirstValue("sub");
        return userId is null ? null : await _userManager.FindByIdAsync(userId);
    }

    private async Task<ProfileResponse> ToResponse(ApplicationUser user) => new(
        user.Id,
        user.Email ?? string.Empty,
        user.FullName,
        user.CreatedAt,
        (await _userManager.GetRolesAsync(user)).ToArray());
}
