using LegalAssistant.Api.Data;

namespace LegalAssistant.Api.Repositories;

public interface IDocumentRepository
{
    Task<Document?> GetOwnedAsync(
        int id,
        string ownerId);

    Task<Document?> GetByIdAsync(int id);

    Task<PagedResult<Document>> GetPagedOwnedAsync(
        string ownerId,
        int page,
        int pageSize,
        string? search,
        string? type);

    Task<IReadOnlyCollection<Document>> GetOwnedByIdsAsync(
        IReadOnlyCollection<int> ids,
        string ownerId,
        CancellationToken cancellationToken = default);

    Task AddAsync(Document document);

    Task SaveChangesAsync();

    void Remove(Document document);
}

public record PagedResult<T>(
    IReadOnlyCollection<T> Items,
    int TotalCount);