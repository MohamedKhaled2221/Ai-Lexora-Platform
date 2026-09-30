using LegalAssistant.Api.Data;
using LegalAssistant.Api.Email;
using Microsoft.AspNetCore.Identity;
using Microsoft.AspNetCore.Identity.Data;
using Microsoft.AspNetCore.Mvc;

namespace LegalAssistant.Api.Auth;

[ApiController]
[Route("api/auth")]
public class AuthController : ControllerBase
{
    private readonly UserManager<ApplicationUser> _userManager;
    private readonly RoleManager<IdentityRole> _roleManager;
    private readonly JwtTokenService _jwtTokenService;
    private readonly RefreshTokenService _refreshTokenService;
    private readonly IEmailService _emailService;
    private readonly IConfiguration _configuration;
    private readonly ILogger<AuthController> _logger;

    public AuthController(
        UserManager<ApplicationUser> userManager,
        RoleManager<IdentityRole> roleManager,
        JwtTokenService jwtTokenService,
        RefreshTokenService refreshTokenService,
        IEmailService emailService,
        IConfiguration configuration,
        ILogger<AuthController> logger)
    {
        _userManager = userManager;
        _roleManager = roleManager;
        _jwtTokenService = jwtTokenService;
        _refreshTokenService = refreshTokenService;
        _emailService = emailService;
        _configuration = configuration;
        _logger = logger;
    }

    [HttpPost("register")]
    public async Task<ActionResult<AuthResponse>> Register(RegisterRequest request)
    {
        if (string.IsNullOrWhiteSpace(request.Email) || string.IsNullOrWhiteSpace(request.Password))
            return BadRequest(new { message = "Email and password are required." });

        var existing = await _userManager.FindByEmailAsync(request.Email);
        if (existing is not null)
            return Conflict(new { message = "An account with this email already exists." });

        var user = new ApplicationUser
        {
            UserName = request.Email,
            Email = request.Email,
            FullName = request.FullName,
            CreatedAt = DateTime.UtcNow
        };

        var result = await _userManager.CreateAsync(user, request.Password);
        if (!result.Succeeded)
        {
            var errors = result.Errors.Select(e => e.Description);
            return BadRequest(new { message = "Could not create account.", errors });
        }

        // Every new signup defaults to the Lawyer role; an Admin can be promoted manually later.
        await EnsureRoleExists(AppRoles.Lawyer);
        await _userManager.AddToRoleAsync(user, AppRoles.Lawyer);

        await SendEmailConfirmationAsync(user);

        _logger.LogInformation("New user registered: {Email}", user.Email);

        return Ok(await CreateAuthResponse(user, AppRoles.Lawyer));
    }

    [HttpPost("login")]
    public async Task<ActionResult<AuthResponse>> Login(LoginRequest request)
    {
        var user = await _userManager.FindByEmailAsync(request.Email);
        if (user is null)
            return Unauthorized(new { message = "Invalid email or password." });

        var passwordValid = await _userManager.CheckPasswordAsync(user, request.Password);
        if (!passwordValid)
        {
            _logger.LogWarning("Failed login attempt for {Email}", request.Email);
            return Unauthorized(new { message = "Invalid email or password." });
        }

        var roles = await _userManager.GetRolesAsync(user);
        var role = roles.FirstOrDefault() ?? AppRoles.Lawyer;

        _logger.LogInformation("User logged in: {Email}", user.Email);

        return Ok(await CreateAuthResponse(user, role));
    }

    [HttpPost("forgot-password")]
    public async Task<IActionResult> ForgotPassword(ForgotPasswordRequest request)
    {
        // The same response is returned whether the account exists or not, to avoid email enumeration.
        var user = await _userManager.FindByEmailAsync(request.Email);
        if (user is not null)
        {
            var token = await _userManager.GeneratePasswordResetTokenAsync(user);
            var link = BuildLink("reset-password", new Dictionary<string, string>
            {
                ["email"] = user.Email!,
                ["token"] = token
            });
            await _emailService.SendAsync(user.Email!, "Reset your Legal Assistant password",
                $"<p>Use this link to reset your password:</p><p><a href=\"{link}\">Reset password</a></p>");
        }
        return Ok(new { message = "If an account exists for this email, a password-reset message has been sent." });
    }

    [HttpPost("reset-password")]
    public async Task<IActionResult> ResetPassword(ResetPasswordRequest request)
    {
        var user = await _userManager.FindByEmailAsync(request.Email);
        if (user is null) return BadRequest(new { message = "Invalid password reset request." });

        var result = await _userManager.ResetPasswordAsync(user, request.Token, request.NewPassword);
        if (!result.Succeeded)
            return BadRequest(new { message = "Could not reset password.", errors = result.Errors.Select(e => e.Description) });

        await _refreshTokenService.RevokeAllAsync(user.Id);
        return NoContent();
    }

    [HttpPost("confirm-email")]
    public async Task<IActionResult> ConfirmEmail(ConfirmEmailRequest request)
    {
        var user = await _userManager.FindByIdAsync(request.UserId);
        if (user is null) return BadRequest(new { message = "Invalid email confirmation request." });

        var result = await _userManager.ConfirmEmailAsync(user, request.Token);
        if (!result.Succeeded)
            return BadRequest(new { message = "Could not confirm email.", errors = result.Errors.Select(e => e.Description) });

        return NoContent();
    }

    [HttpPost("resend-confirmation")]
    public async Task<IActionResult> ResendConfirmation(ForgotPasswordRequest request)
    {
        var user = await _userManager.FindByEmailAsync(request.Email);
        if (user is not null && !user.EmailConfirmed)
            await SendEmailConfirmationAsync(user);
        return Ok(new { message = "If the account requires confirmation, a confirmation message has been sent." });
    }

    [HttpPost("change-email")]
    [Microsoft.AspNetCore.Authorization.Authorize]
    public async Task<IActionResult> ChangeEmail(ChangeEmailRequest request)
    {
        if (string.IsNullOrWhiteSpace(request.NewEmail) || string.IsNullOrWhiteSpace(request.Password))
            return BadRequest(new { message = "New email and password are required." });

        var user = await GetCurrentUser();
        if (user is null) return Unauthorized();
        if (!await _userManager.CheckPasswordAsync(user, request.Password))
            return BadRequest(new { message = "Password is incorrect." });
        if (await _userManager.FindByEmailAsync(request.NewEmail) is not null)
            return Conflict(new { message = "An account with this email already exists." });

        var newEmail = request.NewEmail.Trim();
        var token = await _userManager.GenerateChangeEmailTokenAsync(user, newEmail);
        var link = BuildLink("confirm-email-change", new Dictionary<string, string>
        {
            ["userId"] = user.Id,
            ["newEmail"] = newEmail,
            ["token"] = token
        });
        await _emailService.SendAsync(newEmail, "Confirm your new Legal Assistant email",
            $"<p>Use this link to confirm your new email address:</p><p><a href=\"{link}\">Confirm new email</a></p>");
        return Accepted(new { message = "A confirmation message was sent to the new email address." });
    }

    [HttpPost("confirm-email-change")]
    public async Task<IActionResult> ConfirmEmailChange(ConfirmEmailChangeRequest request)
    {
        var user = await _userManager.FindByIdAsync(request.UserId);
        if (user is null) return BadRequest(new { message = "Invalid email change request." });

        var result = await _userManager.ChangeEmailAsync(user, request.NewEmail, request.Token);
        if (!result.Succeeded)
            return BadRequest(new { message = "Could not change email.", errors = result.Errors.Select(e => e.Description) });

        var userNameResult = await _userManager.SetUserNameAsync(user, request.NewEmail);
        if (!userNameResult.Succeeded)
            return BadRequest(new { message = "Email changed but username could not be updated.", errors = userNameResult.Errors.Select(e => e.Description) });

        await _refreshTokenService.RevokeAllAsync(user.Id);
        return NoContent();
    }

    [HttpPost("refresh")]
    public async Task<ActionResult<AuthResponse>> Refresh(RefreshRequest request)
    {
        if (string.IsNullOrWhiteSpace(request.RefreshToken))
            return BadRequest(new { message = "Refresh token is required." });

        var result = await _refreshTokenService.RotateAsync(request.RefreshToken);
        if (result is null)
            return Unauthorized(new { message = "Invalid or expired refresh token." });

        var roles = await _userManager.GetRolesAsync(result.Value.User);
        var role = roles.FirstOrDefault() ?? AppRoles.Lawyer;
        var (accessToken, accessExpiresAt) = _jwtTokenService.GenerateToken(result.Value.User, role);
        return Ok(new AuthResponse(
            accessToken,
            accessExpiresAt,
            result.Value.Token.Token,
            result.Value.Token.ExpiresAt,
            result.Value.User.Email!,
            result.Value.User.FullName,
            role));
    }

    [HttpPost("logout")]
    [Microsoft.AspNetCore.Authorization.Authorize]
    public async Task<IActionResult> Logout(RefreshRequest request)
    {
        var userId = User.FindFirst(System.Security.Claims.ClaimTypes.NameIdentifier)?.Value ?? User.FindFirst("sub")?.Value;
        if (userId is null) return Unauthorized();
        if (!string.IsNullOrWhiteSpace(request.RefreshToken))
            await _refreshTokenService.RevokeAsync(request.RefreshToken, userId);
        return NoContent();
    }

    [HttpPost("promote-to-admin")]
    [Microsoft.AspNetCore.Authorization.Authorize(Roles = AppRoles.Admin)]
    public async Task<IActionResult> PromoteToAdmin([FromBody] PromoteRequest request)
    {
        var user = await _userManager.FindByEmailAsync(request.Email);
        if (user is null)
            return NotFound(new { message = "No user found with this email." });

        if (await _userManager.IsInRoleAsync(user, AppRoles.Admin))
            return Ok(new { message = "User is already an Admin." });

        await _userManager.AddToRoleAsync(user, AppRoles.Admin);
        _logger.LogInformation("User {Email} promoted to Admin", user.Email);

        return Ok(new { message = $"{user.Email} is now an Admin." });
    }

    private async Task EnsureRoleExists(string roleName)
    {
        if (!await _roleManager.RoleExistsAsync(roleName))
            await _roleManager.CreateAsync(new IdentityRole(roleName));
    }

    private async Task<AuthResponse> CreateAuthResponse(ApplicationUser user, string role)
    {
        var (accessToken, accessExpiresAt) = _jwtTokenService.GenerateToken(user, role);
        var refreshToken = await _refreshTokenService.CreateAsync(user);
        return new AuthResponse(
            accessToken,
            accessExpiresAt,
            refreshToken.Token,
            refreshToken.ExpiresAt,
            user.Email!,
            user.FullName,
            role);
    }

    private async Task SendEmailConfirmationAsync(ApplicationUser user)
    {
        var token = await _userManager.GenerateEmailConfirmationTokenAsync(user);
        var link = BuildLink("confirm-email", new Dictionary<string, string>
        {
            ["userId"] = user.Id,
            ["token"] = token
        });
        await _emailService.SendAsync(user.Email!, "Confirm your Legal Assistant email",
            $"<p>Welcome to Legal Assistant.</p><p><a href=\"{link}\">Confirm email</a></p>");
    }

    private string BuildLink(string path, IReadOnlyDictionary<string, string> query)
    {
        var baseUrl = _configuration["Email:FrontendBaseUrl"]?.TrimEnd('/') ?? "http://localhost:3000";
        var queryString = string.Join("&", query.Select(item => $"{Uri.EscapeDataString(item.Key)}={Uri.EscapeDataString(item.Value)}"));
        return $"{baseUrl}/{path}?{queryString}";
    }

    private async Task<ApplicationUser?> GetCurrentUser()
    {
        var userId = User.FindFirst(System.Security.Claims.ClaimTypes.NameIdentifier)?.Value ?? User.FindFirst("sub")?.Value;
        return userId is null ? null : await _userManager.FindByIdAsync(userId);
    }
}