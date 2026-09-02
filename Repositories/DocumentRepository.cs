using LegalAssistant.Api.Data;
using Microsoft.EntityFrameworkCore;

namespace LegalAssistant.Api.Repositories;

public class DocumentRepository : IDocumentRepository
{
    private readonly AppDbContext _db;

    public DocumentRepository(AppDbContext db) => _db = db;

    public Task<Document?> GetOwnedAsync(
        int id,
        string ownerId) =>
        _db.Documents.SingleOrDefaultAsync(
            d => d.Id == id && d.OwnerId == ownerId);

    public Task<Document?> GetByIdAsync(int id) =>
        _db.Documents.SingleOrDefaultAsync(
            d => d.Id == id);

    public async Task<PagedResult<Document>> GetPagedOwnedAsync(
        string ownerId,
        int page,
        int pageSize,
        string? search,
        string? type)
    {
        var query =
            _db.Documents.Where(
                d => d.OwnerId == ownerId);

        if (!string.IsNullOrWhiteSpace(search))
        {
            var searchTerm = search.Trim();

            query = query.Where(
                d => d.FileName.Contains(searchTerm));
        }

        if (!string.IsNullOrWhiteSpace(type))
        {
            var documentType = type.Trim();

            query = query.Where(
                d => d.Type == documentType);
        }

        var totalCount =
            await query.CountAsync();

        var documents =
            await query
                .OrderByDescending(
                    d => d.UploadedAt)
                .Skip((page - 1) * pageSize)
                .Take(pageSize)
                .ToListAsync();

        return new PagedResult<Document>(
            documents,
            totalCount);
    }

    public async Task<IReadOnlyCollection<Document>>
        GetOwnedByIdsAsync(
            IReadOnlyCollection<int> ids,
            string ownerId,
            CancellationToken cancellationToken = default)
    {
        var distinctIds =
            ids.Distinct().ToArray();

        return await _db.Documents
            .Where(
                document =>
                    document.OwnerId == ownerId
                    && distinctIds.Contains(
                        document.Id))
            .ToListAsync(cancellationToken);
    }

    public async Task AddAsync(
        Document document)
    {
        _db.Documents.Add(document);

        await _db.SaveChangesAsync();
    }

    public Task SaveChangesAsync() =>
        _db.SaveChangesAsync();

    public void Remove(
        Document document) =>
        _db.Documents.Remove(document);
}