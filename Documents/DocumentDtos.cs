namespace LegalAssistant.Api.Documents;

public record DocumentResponse(
    int Id,
    string FileName,
    string Type,
    long SizeBytes,
    DateTime UploadedAt,
    string DownloadUrl);

public record PagedDocumentsResponse(
    IReadOnlyCollection<DocumentResponse> Items,
    int Page,
    int PageSize,
    int TotalCount,
    int TotalPages);

public record UpdateDocumentRequest(string? FileName, string? Type);
