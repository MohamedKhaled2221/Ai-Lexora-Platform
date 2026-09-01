namespace LegalAssistant.Api.Users;

public record AdminUserResponse(
    string Id,
    string Email,
    string FullName,
    DateTime CreatedAt,
    IReadOnlyCollection<string> Roles,
    bool IsActive);

public record PagedUsersResponse(
    IReadOnlyCollection<AdminUserResponse> Items,
    int Page,
    int PageSize,
    int TotalCount,
    int TotalPages);

public record UpdateUserRoleRequest(string Role);

public record UpdateUserStatusRequest(bool IsActive);
