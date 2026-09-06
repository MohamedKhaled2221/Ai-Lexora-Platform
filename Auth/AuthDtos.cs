namespace LegalAssistant.Api.Auth;

public record RegisterRequest(string FullName, string Email, string Password);

public record LoginRequest(string Email, string Password);

public record AuthResponse(
    string Token,
    DateTime ExpiresAt,
    string RefreshToken,
    DateTime RefreshTokenExpiresAt,
    string Email,
    string FullName,
    string Role);

public record PromoteRequest(string Email);

public record RefreshRequest(string RefreshToken);

public record ForgotPasswordRequest(string Email);

public record ResetPasswordRequest(string Email, string Token, string NewPassword);

public record ConfirmEmailRequest(string UserId, string Token);

public record ChangeEmailRequest(string NewEmail, string Password);

public record ConfirmEmailChangeRequest(string UserId, string NewEmail, string Token);
