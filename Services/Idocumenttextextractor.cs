namespace LegalAssistant.Api.Services;

/// <summary>
/// Extracts plain text from a stored document file. This is shared
/// infrastructure — Contract Analysis, Search, and the Chatbot's RAG
/// pipeline all need clean text as their input, regardless of whether the
/// source file is a .txt, .pdf, .docx, or a scanned image. This is plain
/// backend/infra work, not an AI concern, so it belongs behind its own
/// interface rather than living inside any single feature's controller.
/// </summary>
public interface IDocumentTextExtractor
{
    /// <summary>
    /// True if this extractor knows how to handle the given file name's extension.
    /// </summary>
    bool CanExtract(string fileName);

    /// <summary>
    /// Reads the file at <paramref name="fullFilePath"/> and returns its text content.
    /// Throws <see cref="UnsupportedFileTypeException"/> if the extension isn't supported.
    /// </summary>
    Task<string> ExtractTextAsync(string fullFilePath, string fileName, CancellationToken cancellationToken = default);
}

/// <summary>
/// Thrown when a document's file type has no registered extraction strategy yet
/// (e.g. scanned images before an OCR engine is wired in).
/// </summary>
public sealed class UnsupportedFileTypeException : Exception
{
    public UnsupportedFileTypeException(string extension)
        : base($"No text extractor is registered for '{extension}' files yet.")
    {
        Extension = extension;
    }

    public string Extension { get; }
}