using LegalAssistant.Api.Data;

namespace LegalAssistant.Api.Repositories;

public class GeneratedDocumentRepository : IGeneratedDocumentRepository
{
    private readonly AppDbContext _db;

    public GeneratedDocumentRepository(AppDbContext db) => _db = db;

    public Task AddAsync(GeneratedDocumentRecord record)
    {
        _db.GeneratedDocuments.Add(record);
        return Task.CompletedTask;
    }

    public Task SaveChangesAsync() => _db.SaveChangesAsync();
}