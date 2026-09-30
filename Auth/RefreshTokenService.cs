using System.Security.Cryptography;
using System.Text;
using LegalAssistant.Api.Data;
using Microsoft.EntityFrameworkCore;

namespace LegalAssistant.Api.Auth;

public class RefreshTokenService
{
    private const int RefreshTokenLifetimeDays = 7;
    private readonly AppDbContext _db;

    public RefreshTokenService(AppDbContext db) => _db = db;

    public async Task<RefreshTokenResult> CreateAsync(ApplicationUser user)
    {
        var rawToken = Convert.ToBase64String(RandomNumberGenerator.GetBytes(64));
        var expiresAt = DateTime.UtcNow.AddDays(RefreshTokenLifetimeDays);
        _db.RefreshTokens.Add(new RefreshToken
        {
            UserId = user.Id,
            TokenHash = Hash(rawToken),
            CreatedAt = DateTime.UtcNow,
            ExpiresAt = expiresAt
        });
        await _db.SaveChangesAsync();
        return new RefreshTokenResult(rawToken, expiresAt);
    }

    public async Task<(ApplicationUser User, RefreshTokenResult Token)?> RotateAsync(string rawToken)
    {
        var token = await _db.RefreshTokens
            .Include(t => t.User)
            .SingleOrDefaultAsync(t => t.TokenHash == Hash(rawToken));

        if (token is null || token.RevokedAt is not null || token.ExpiresAt <= DateTime.UtcNow)
            return null;

        token.RevokedAt = DateTime.UtcNow;
        var replacement = await CreateAsync(token.User);
        return (token.User, replacement);
    }

    public async Task RevokeAsync(string rawToken, string userId)
    {
        var token = await _db.RefreshTokens.SingleOrDefaultAsync(t => t.TokenHash == Hash(rawToken) && t.UserId == userId);
        if (token is null || token.RevokedAt is not null) return;

        token.RevokedAt = DateTime.UtcNow;
        await _db.SaveChangesAsync();
    }

    public async Task RevokeAllAsync(string userId)
    {
        var activeTokens = await _db.RefreshTokens
            .Where(t => t.UserId == userId && t.RevokedAt == null && t.ExpiresAt > DateTime.UtcNow)
            .ToListAsync();
        foreach (var token in activeTokens) token.RevokedAt = DateTime.UtcNow;
        if (activeTokens.Count > 0) await _db.SaveChangesAsync();
    }

    private static string Hash(string token) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(token)));
}

public record RefreshTokenResult(string Token, DateTime ExpiresAt);