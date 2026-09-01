namespace LegalAssistant.Api.Users;

public record ProfileResponse(string Id, string Email, string FullName, DateTime CreatedAt, IReadOnlyCollection<string> Roles);

public record UpdateProfileRequest(string FullName);

public record ChangePasswordRequest(string CurrentPassword, string NewPassword);
