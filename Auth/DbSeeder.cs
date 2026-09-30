using LegalAssistant.Api.Data;
using Microsoft.AspNetCore.Identity;

namespace LegalAssistant.Api.Auth;

public static class DbSeeder
{
    public static async Task SeedAsync(IServiceProvider services, IConfiguration config, ILogger logger)
    {
        var userManager = services.GetRequiredService<UserManager<ApplicationUser>>();
        var roleManager = services.GetRequiredService<RoleManager<IdentityRole>>();

        // 1) Make sure both roles exist.
        foreach (var role in new[] { AppRoles.Admin, AppRoles.Lawyer })
        {
            if (!await roleManager.RoleExistsAsync(role))
                await roleManager.CreateAsync(new IdentityRole(role));
        }

        // 2) Create the default admin if it doesn't exist yet (local/dev convenience).
        var adminEmail = config["AdminSeed:Email"];
        var adminPassword = config["AdminSeed:Password"];
        var adminFullName = config["AdminSeed:FullName"] ?? "Admin";

        if (string.IsNullOrWhiteSpace(adminEmail) || string.IsNullOrWhiteSpace(adminPassword))
        {
            logger.LogWarning("AdminSeed not configured — skipping default admin creation.");
            return;
        }

        var existingAdmin = await userManager.FindByEmailAsync(adminEmail);
        if (existingAdmin is not null)
        {
            // Already seeded — make sure it still has the Admin role (in case DB was tampered with).
            if (!await userManager.IsInRoleAsync(existingAdmin, AppRoles.Admin))
                await userManager.AddToRoleAsync(existingAdmin, AppRoles.Admin);
            return;
        }

        var admin = new ApplicationUser
        {
            UserName = adminEmail,
            Email = adminEmail,
            FullName = adminFullName,
            CreatedAt = DateTime.UtcNow,
            EmailConfirmed = true
        };

        var result = await userManager.CreateAsync(admin, adminPassword);
        if (result.Succeeded)
        {
            await userManager.AddToRoleAsync(admin, AppRoles.Admin);
            logger.LogInformation("Seeded default admin account: {Email}", adminEmail);
        }
        else
        {
            var errors = string.Join(", ", result.Errors.Select(e => e.Description));
            logger.LogError("Failed to seed default admin: {Errors}", errors);
        }
    }
}