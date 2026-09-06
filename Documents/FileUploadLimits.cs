namespace LegalAssistant.Api.Documents;

/// <summary>
/// [RequestSizeLimit] needs a compile-time constant, so it can't read
/// FileStorage:MaxFileSizeBytes from appsettings.json directly. Keep this
/// value equal to (or greater than) FileStorage:MaxFileSizeBytes, or valid
/// uploads will get rejected by Kestrel/MVC before DocumentService's own
/// config-driven size check ever runs.
///
/// Current appsettings.json value: 52428800 bytes (50 MB), matching the AI
/// service's 50MB cap. If that changes, update MaxSingleFileBytes below too.
/// </summary>
public static class FileUploadLimits
{
    public const long MaxSingleFileBytes = 50 * 1024 * 1024; // 50 MB - keep in sync with FileStorage:MaxFileSizeBytes

    // Batch endpoint accepts multiple files in one request; this is a total
    // request-body ceiling, not a per-file one (each file is still checked
    // against FileStorage:MaxFileSizeBytes individually in DocumentService).
    public const long MaxBatchTotalBytes = 10 * MaxSingleFileBytes; // 500 MB total per batch request
}