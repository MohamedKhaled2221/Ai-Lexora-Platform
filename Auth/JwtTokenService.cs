using System.IdentityModel.Tokens.Jwt;
using System.Security.Claims;
using System.Text;
using LegalAssistant.Api.Data;
using LegalAssistant.Api.Services;
using Microsoft.IdentityModel.Tokens;

namespace LegalAssistant.Api.Auth;

public class JwtTokenService
{
    private readonly IConfiguration _config;

    public JwtTokenService(IConfiguration config)
    {
        _config = config;
    }

    public (string Token, DateTime ExpiresAt) GenerateToken(ApplicationUser user, string role)
    {
        var key = _config["Jwt:Key"]!;
        var issuer = _config["Jwt:Issuer"];
        var audience = _config["Jwt:Audience"];
        var expiresAt = DateTime.UtcNow.AddHours(8); // token valid for 8 hours

        var claims = new List<Claim>
        {
            new(JwtRegisteredClaimNames.Sub, user.Id),
            new(JwtRegisteredClaimNames.Email, user.Email ?? string.Empty),
            new(ClaimTypes.Name, user.FullName),
            new(ClaimTypes.Role, role),
            new(JwtRegisteredClaimNames.Jti, Guid.NewGuid().ToString())
        };

        // AI access scope: only added when assigned, so a user without a scope carries NO claim
        // (and gets refused by ClaimsAiCallerIdentityProvider once AllowSharedIdentity=false).
        if (!string.IsNullOrWhiteSpace(user.ClientId))
            claims.Add(new Claim(ClaimsAiCallerIdentityProvider.ClientIdClaim, user.ClientId.Trim()));
        if (!string.IsNullOrWhiteSpace(user.ConfidentialityCeiling))
            claims.Add(new Claim(ClaimsAiCallerIdentityProvider.CeilingClaim, user.ConfidentialityCeiling.Trim()));

        var credentials = new SigningCredentials(
            new SymmetricSecurityKey(Encoding.UTF8.GetBytes(key)),
            SecurityAlgorithms.HmacSha256);

        var token = new JwtSecurityToken(
            issuer: issuer,
            audience: audience,
            claims: claims,
            expires: expiresAt,
            signingCredentials: credentials);

        return (new JwtSecurityTokenHandler().WriteToken(token), expiresAt);
    }
}