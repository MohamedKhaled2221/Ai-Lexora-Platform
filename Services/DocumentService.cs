using LegalAssistant.Api.Data;
using LegalAssistant.Api.Repositories;

namespace LegalAssistant.Api.Services;

public class DocumentService : IDocumentService
{
    private readonly IDocumentRepository _documents;
    private readonly IConfiguration _configuration;
    private readonly IWebHostEnvironment _environment;
    private readonly ILexoraDocumentIndexingService _documentIndexer;

    public DocumentService(
      IDocumentRepository documents,
      IConfiguration configuration,
      IWebHostEnvironment environment,
      ILexoraDocumentIndexingService documentIndexer)
  {
      _documents = documents;
      _configuration = configuration;
      _environment = environment;
      _documentIndexer = documentIndexer;
  }

    public Task<PagedResult<Document>> GetPagedAsync(string userId, int page, int pageSize, string? search, string? type) =>
        _documents.GetPagedOwnedAsync(userId, page, pageSize, search, type);

    public Task<Document?> GetOwnedAsync(int id, string userId) => _documents.GetOwnedAsync(id, userId);

    public async Task<StoredDocument> UploadAsync(
        IFormFile file,
        string? type,
        string userId)
    {
        ValidateUpload(file, type);

        var stored =
            await StoreAsync(
                file,
                type,
                userId);

        var fullPath =
            GetFilePath(stored.Document);

        try
        {
            await _documentIndexer.IndexAsync(
                stored.Document.Id,
                stored.Document.FileName,
                fullPath,
                file.ContentType);
        }
        catch
        {
            // A successful backend upload must also be RAG-ready.
            // Roll back the SQL row and stored file if AI indexing
            // fails, so the user never sees an unusable document.
            _documents.Remove(stored.Document);
            await _documents.SaveChangesAsync();

            DeleteStoredFile(stored.Document);

            throw;
        }

        return stored;
    }

    public async Task<IReadOnlyCollection<StoredDocument>> UploadBatchAsync(IFormFileCollection files, string? type, string userId)
    {
        if (files.Count is < 1 or > 5)
            throw new ArgumentException("Upload between 1 and 5 files at once.");
        foreach (var file in files) ValidateUpload(file, type);

        var stored = new List<StoredDocument>();
        try
        {
            foreach (var file in files) stored.Add(await StoreAsync(file, type, userId));
            return stored;
        }
        catch
        {
            foreach (var item in stored)
            {
                _documents.Remove(item.Document);
                DeleteStoredFile(item.Document);
            }
            if (stored.Count > 0) await _documents.SaveChangesAsync();
            throw;
        }
    }

    public async Task<Document?> UpdateAsync(int id, string userId, string? fileName, string? type)
    {
        if (fileName is null && type is null)
            throw new ArgumentException("File name or document type is required.");

        var document = await _documents.GetOwnedAsync(id, userId);
        if (document is null) return null;

        if (fileName is not null)
        {
            var safeFileName = Path.GetFileName(fileName.Trim());
            if (string.IsNullOrWhiteSpace(safeFileName) || safeFileName.Length > 260)
                throw new ArgumentException("File name must be between 1 and 260 characters.");
            document.FileName = safeFileName;
        }
        if (type is not null)
        {
            var documentType = type.Trim();
            if (string.IsNullOrWhiteSpace(documentType) || documentType.Length > 50)
                throw new ArgumentException("Document type must be between 1 and 50 characters.");
            document.Type = documentType;
        }
        await _documents.SaveChangesAsync();
        return document;
    }

    public async Task<bool> DeleteAsync(int id, string userId)
    {
        var document = await _documents.GetOwnedAsync(id, userId);
        if (document is null) return false;

        _documents.Remove(document);
        await _documents.SaveChangesAsync();
        DeleteStoredFile(document);
        return true;
    }

    public string GetFilePath(Document document)
    {
        var root = GetStorageRoot();
        var fullPath = Path.GetFullPath(Path.Combine(root, document.FilePath));
        if (!fullPath.StartsWith(root + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("Invalid stored file path.");
        return fullPath;
    }

    public long GetFileSize(Document document)
    {
        var file = new FileInfo(GetFilePath(document));
        return file.Exists ? file.Length : 0;
    }

    private async Task<StoredDocument> StoreAsync(IFormFile file, string? type, string userId)
    {
        var originalFileName = Path.GetFileName(file.FileName);
        var storedFileName = $"{Guid.NewGuid():N}{Path.GetExtension(originalFileName).ToLowerInvariant()}";
        var userFolder = Path.Combine(GetStorageRoot(), userId);
        Directory.CreateDirectory(userFolder);
        var fullPath = Path.Combine(userFolder, storedFileName);
        await using (var stream = System.IO.File.Create(fullPath))
        {
            await file.CopyToAsync(stream);
        }

        var document = new Document
        {
            FileName = originalFileName,
            FilePath = Path.Combine(userId, storedFileName),
            OwnerId = userId,
            Type = string.IsNullOrWhiteSpace(type) ? "Contract" : type.Trim(),
            UploadedAt = DateTime.UtcNow
        };

        try
        {
            await _documents.AddAsync(document);
            return new StoredDocument(document, file.Length);
        }
        catch
        {
            System.IO.File.Delete(fullPath);
            throw;
        }
    }

    private void ValidateUpload(IFormFile file, string? type)
    {
        if (file.Length == 0) throw new ArgumentException("File must not be empty.");
        var maxSize = _configuration.GetValue<long>("FileStorage:MaxFileSizeBytes", 20 * 1024 * 1024);
        if (file.Length > maxSize) throw new ArgumentException($"File exceeds the {maxSize / 1024 / 1024} MB limit.");

        var originalFileName = Path.GetFileName(file.FileName);
        if (string.IsNullOrWhiteSpace(originalFileName) || originalFileName.Length > 260)
            throw new ArgumentException("File name is invalid or too long.");
        var extension = Path.GetExtension(originalFileName);
        var allowed = _configuration.GetSection("FileStorage:AllowedExtensions").Get<string[]>() ?? Array.Empty<string>();
        if (string.IsNullOrWhiteSpace(extension) || !allowed.Contains(extension, StringComparer.OrdinalIgnoreCase))
            throw new ArgumentException("Unsupported file type.");
        if (!string.IsNullOrWhiteSpace(type) && type.Trim().Length > 50)
            throw new ArgumentException("Document type must be 50 characters or fewer.");
    }

    private void DeleteStoredFile(Document document)
    {
        var path = GetFilePath(document);
        if (System.IO.File.Exists(path)) System.IO.File.Delete(path);
    }

    private string GetStorageRoot()
    {
        var configuredPath = _configuration["FileStorage:RootPath"] ?? "App_Data/uploads";
        return Path.GetFullPath(Path.Combine(_environment.ContentRootPath, configuredPath));
    }
}
