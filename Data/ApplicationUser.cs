using System.ComponentModel.DataAnnotations;
using Microsoft.AspNetCore.Identity;

namespace LegalAssistant.Api.Data;

// IdentityUser already gives us: Id, Email, UserName, PasswordHash, PhoneNumber...
// We just add the fields specific to our legal platform.
public class ApplicationUser : IdentityUser
{
    public string FullName { get; set; } = string.Empty;
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;

    // AI access scope. Copied into the JWT (client_id / confidentiality_ceiling) and forwarded to the
    // AI service as X-Client-Id / X-Confidentiality-Ceiling. Null = no scope assigned yet.
    // Values must match what the AI team stamped on the documents at ingestion time.
    [MaxLength(100)] public string? ClientId { get; set; }
    [MaxLength(50)] public string? ConfidentialityCeiling { get; set; }
}

// Two roles for now: Admin manages the knowledge base, Lawyer uses the modules.
public static class AppRoles
{
    public const string Admin = "Admin";
    public const string Lawyer = "Lawyer";
}