using Microsoft.AspNetCore.Identity;

namespace LegalAssistant.Api.Data;

// IdentityUser already gives us: Id, Email, UserName, PasswordHash, PhoneNumber...
// We just add the fields specific to our legal platform.
public class ApplicationUser : IdentityUser
{
    public string FullName { get; set; } = string.Empty;
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
}

// Two roles for now: Admin manages the knowledge base, Lawyer uses the modules.
public static class AppRoles
{
    public const string Admin = "Admin";
    public const string Lawyer = "Lawyer";
}
