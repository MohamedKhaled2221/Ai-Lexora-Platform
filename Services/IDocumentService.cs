using LegalAssistant.Api.Data;
using LegalAssistant.Api.Repositories;
using Microsoft.AspNetCore.Http;

namespace LegalAssistant.Api.Services;

public interface IDocumentService
{
    Task<StoredDocument> UploadAsync(IFormFile file, string? type, string userId);
    Task<IReadOnlyCollection<StoredDocument>> UploadBatchAsync(IFormFileCollection files, string? type, string userId);
    Task<PagedResult<Document>> GetPagedAsync(string userId, int page, int pageSize, string? search, string? type);
    Task<Document?> GetOwnedAsync(int id, string userId);
    Task<Document?> UpdateAsync(int id, string userId, string? fileName, string? type);
    Task<bool> DeleteAsync(int id, string userId);
    string GetFilePath(Document document);
    long GetFileSize(Document document);
}

public record StoredDocument(Document Document, long SizeBytes);
