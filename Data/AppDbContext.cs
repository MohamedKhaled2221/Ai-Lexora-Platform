using Microsoft.AspNetCore.Identity.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore;

namespace LegalAssistant.Api.Data;

// IdentityDbContext already brings AspNetUsers, AspNetRoles, AspNetUserRoles, etc.
// We add our own tables (Documents, ContractAnalyses, RiskyClauses) on top of it.
public class AppDbContext : IdentityDbContext<ApplicationUser>
{
    public AppDbContext(DbContextOptions<AppDbContext> options) : base(options) { }

    public DbSet<Document> Documents => Set<Document>();
    public DbSet<ContractAnalysis> ContractAnalyses => Set<ContractAnalysis>();
    public DbSet<RiskyClause> RiskyClauses => Set<RiskyClause>();
    public DbSet<RefreshToken> RefreshTokens => Set<RefreshToken>();
    public DbSet<GeneratedDocumentRecord> GeneratedDocuments => Set<GeneratedDocumentRecord>();
    public DbSet<ChatConversation> ChatConversations => Set<ChatConversation>();
    public DbSet<ChatMessage> ChatMessages => Set<ChatMessage>();

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        base.OnModelCreating(modelBuilder); // required so Identity tables get configured correctly

        modelBuilder.Entity<Document>()
            .HasOne<ApplicationUser>()
            .WithMany()
            .HasForeignKey(d => d.OwnerId)
            .OnDelete(DeleteBehavior.Restrict); // don't cascade-delete a lawyer's documents if their account is removed

        modelBuilder.Entity<Document>()
            .HasIndex(d => d.OwnerId);

        modelBuilder.Entity<Document>(entity =>
        {
            entity.Property(d => d.FileName).HasMaxLength(260);
            entity.Property(d => d.FilePath).HasMaxLength(1000);
            entity.Property(d => d.Type).HasMaxLength(50);
        });

        modelBuilder.Entity<ContractAnalysis>(entity =>
        {
            entity.Property(a => a.Summary).HasMaxLength(2000);
            entity.Property(a => a.Status).HasMaxLength(20);
            entity.Property(a => a.ErrorMessage).HasMaxLength(2000);
        });

        modelBuilder.Entity<RiskyClause>(entity =>
        {
            entity.Property(c => c.ClauseText).HasMaxLength(2000);
            entity.Property(c => c.RiskType).HasMaxLength(50);
            entity.Property(c => c.Explanation).HasMaxLength(1000);
        });

        modelBuilder.Entity<RefreshToken>(entity =>
        {
            entity.Property(t => t.TokenHash).HasMaxLength(64);
            entity.HasIndex(t => t.TokenHash).IsUnique();
            entity.HasIndex(t => t.UserId);
            entity.HasOne(t => t.User)
                .WithMany()
                .HasForeignKey(t => t.UserId)
                .OnDelete(DeleteBehavior.Cascade);
        });

        modelBuilder.Entity<ContractAnalysis>()
            .HasOne(a => a.Document)
            .WithOne(d => d.Analysis)
            .HasForeignKey<ContractAnalysis>(a => a.DocumentId);

        modelBuilder.Entity<RiskyClause>()
            .HasOne(c => c.ContractAnalysis)
            .WithMany(a => a.RiskyClauses)
            .HasForeignKey(c => c.ContractAnalysisId);

        modelBuilder.Entity<GeneratedDocumentRecord>(entity =>
        {
            entity.Property(r => r.UserId).HasMaxLength(450);
            entity.Property(r => r.TemplateKey).HasMaxLength(100);
            entity.Property(r => r.FileName).HasMaxLength(260);
            entity.HasIndex(r => r.UserId);
        });

        modelBuilder.Entity<ChatConversation>(entity =>
        {
            entity.Property(c => c.UserId).HasMaxLength(450);
            entity.HasIndex(c => c.UserId);
        });

        modelBuilder.Entity<ChatMessage>(entity =>
        {
            entity.Property(m => m.Role).HasMaxLength(20);
            entity.Property(m => m.Content).HasMaxLength(4000);
            entity.HasOne(m => m.Conversation)
                .WithMany(c => c.Messages)
                .HasForeignKey(m => m.ConversationId)
                .OnDelete(DeleteBehavior.Cascade);
            entity.HasIndex(m => m.ConversationId);
        });
    }
}

public class Document
{
    public int Id { get; set; }
    public string FileName { get; set; } = string.Empty;
    public string FilePath { get; set; } = string.Empty;
    public string OwnerId { get; set; } = string.Empty;
    public DateTime UploadedAt { get; set; } = DateTime.UtcNow;
    public string Type { get; set; } = "Contract";

    public ContractAnalysis? Analysis { get; set; }
}

public class ContractAnalysis
{
    public int Id { get; set; }
    public int DocumentId { get; set; }
    public Document Document { get; set; } = null!;

    public int RiskScore { get; set; }
    public string Summary { get; set; } = string.Empty;
    public string Status { get; set; } = AnalysisStatuses.Pending;
    public DateTime? StartedAt { get; set; }
    public DateTime? CompletedAt { get; set; }
    public string? ErrorMessage { get; set; }
    public DateTime AnalyzedAt { get; set; } = DateTime.UtcNow;

    public ICollection<RiskyClause> RiskyClauses { get; set; } = new List<RiskyClause>();
}

public static class AnalysisStatuses
{
    public const string Pending = "Pending";
    public const string Processing = "Processing";
    public const string Completed = "Completed";
    public const string Failed = "Failed";
}

public class RiskyClause
{
    public int Id { get; set; }
    public int ContractAnalysisId { get; set; }
    public ContractAnalysis ContractAnalysis { get; set; } = null!;

    public string ClauseText { get; set; } = string.Empty;
    public string RiskType { get; set; } = string.Empty; // Missing, Ambiguous, Unusual
    public string Explanation { get; set; } = string.Empty;
}

public class RefreshToken
{
    public int Id { get; set; }
    public string UserId { get; set; } = string.Empty;
    public ApplicationUser User { get; set; } = null!;
    public string TokenHash { get; set; } = string.Empty;
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
    public DateTime ExpiresAt { get; set; }
    public DateTime? RevokedAt { get; set; }
}

/// <summary>Lightweight audit trail of documents produced by the Document Generator.</summary>
public class GeneratedDocumentRecord
{
    public int Id { get; set; }
    public string UserId { get; set; } = string.Empty;
    public string TemplateKey { get; set; } = string.Empty;
    public string FileName { get; set; } = string.Empty;
    public DateTime GeneratedAt { get; set; } = DateTime.UtcNow;
}

public class ChatConversation
{
    public int Id { get; set; }
    public string UserId { get; set; } = string.Empty;
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;

    public ICollection<ChatMessage> Messages { get; set; } = new List<ChatMessage>();
}

public class ChatMessage
{
    public int Id { get; set; }
    public int ConversationId { get; set; }
    public ChatConversation Conversation { get; set; } = null!;

    public string Role { get; set; } = ChatMessageRoles.User;
    public string Content { get; set; } = string.Empty;
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
}

public static class ChatMessageRoles
{
    public const string User = "User";
    public const string Assistant = "Assistant";
}