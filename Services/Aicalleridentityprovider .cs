using System.Security.Claims;

namespace LegalAssistant.Api.Services;

/// <summary>Access scope sent to the AI service as X-Client-Id / X-Matter-Id / X-Confidentiality-Ceiling.</summary>
public sealed record AiCallerIdentity(string ClientId, string? MatterId, string ConfidentialityCeiling);

/// <summary>
/// Single place that decides which AI access scope a signed-in user gets.
/// The scope must come from the authenticated identity on the server — never from the request body.
/// </summary>
public interface IAiCallerIdentityProvider
{
    /// <exception cref="InvalidOperationException">No scope can be derived for this user.</exception>
    AiCallerIdentity Resolve(ClaimsPrincipal user, string? matterId = null);
}

/// <summary>
/// Reads client_id / confidentiality_ceiling from the user's JWT claims.
/// While AiService:AllowSharedIdentity=true (dev only) it falls back to the shared values in appsettings.
/// In production set it to false: a user with no scope is then refused instead of inheriting one.
/// </summary>
public sealed class ClaimsAiCallerIdentityProvider : IAiCallerIdentityProvider
{
    public const string ClientIdClaim = "client_id";
    public const string CeilingClaim = "confidentiality_ceiling";

    private readonly IConfiguration _config;
    public ClaimsAiCallerIdentityProvider(IConfiguration config) => _config = config;

    public AiCallerIdentity Resolve(ClaimsPrincipal user, string? matterId = null)
    {
        var clientId = user.FindFirstValue(ClientIdClaim);
        var ceiling = user.FindFirstValue(CeilingClaim);

        if (string.IsNullOrWhiteSpace(clientId) || string.IsNullOrWhiteSpace(ceiling))
        {
            if (!_config.GetValue("AiService:AllowSharedIdentity", true))
                throw new InvalidOperationException("No AI access scope is assigned to this user.");

            clientId = string.IsNullOrWhiteSpace(clientId) ? _config["AiService:ClientId"]?.Trim() : clientId;
            ceiling = string.IsNullOrWhiteSpace(ceiling) ? _config["AiService:ConfidentialityCeiling"]?.Trim() : ceiling;
        }

        if (string.IsNullOrWhiteSpace(clientId) || string.IsNullOrWhiteSpace(ceiling))
            throw new InvalidOperationException("AiService identity is not configured.");

        return new AiCallerIdentity(clientId!, string.IsNullOrWhiteSpace(matterId) ? null : matterId, ceiling!);
    }
}