using LegalAssistant.Api.Data;
using LegalAssistant.Api.Repositories;
using Microsoft.EntityFrameworkCore;

namespace LegalAssistant.Api.Tests.Repositories;

public sealed class DocumentRepositoryTests
{
    [Fact]
    public async Task GetAllOwnedAsync_ReturnsOnlyDocumentsOwnedByUser()
    {
        var options =
            new DbContextOptionsBuilder<AppDbContext>()
                .UseInMemoryDatabase(
                    $"documents-{Guid.NewGuid()}")
                .Options;

        await using var db =
            new AppDbContext(options);

        db.Documents.AddRange(
            new Document
            {
                Id = 1001,
                OwnerId = "user-a",
                FileName = "authorized-a.pdf",
                FilePath = "/test/authorized-a.pdf",
                Type = "law"
            },
            new Document
            {
                Id = 1002,
                OwnerId = "user-b",
                FileName = "other-user.pdf",
                FilePath = "/test/other-user.pdf",
                Type = "law"
            },
            new Document
            {
                Id = 1003,
                OwnerId = "user-a",
                FileName = "authorized-b.pdf",
                FilePath = "/test/authorized-b.pdf",
                Type = "contract"
            });

        await db.SaveChangesAsync();

        var repository =
            new DocumentRepository(db);

        var result =
            await repository.GetAllOwnedAsync(
                "user-a");

        var ids =
            result
                .Select(document => document.Id)
                .OrderBy(id => id)
                .ToArray();

        Assert.Equal(
            new[] { 1001, 1003 },
            ids);

        Assert.All(
            result,
            document =>
                Assert.Equal(
                    "user-a",
                    document.OwnerId));
    }
}
