namespace LegalAssistant.Api.Services;

/// <summary>
/// Knows how to extract text from one specific file format. Register one
/// implementation per format; <see cref="CompositeDocumentTextExtractor"/>
/// picks the right one by extension. Adding Word or OCR-for-images support
/// later means adding a new class here and one DI registration line — no
/// existing code changes.
/// </summary>
public interface ITextExtractionStrategy
{
    /// <summary>File extensions this strategy handles, e.g. ".pdf" (lowercase, with the dot).</summary>
    IReadOnlyCollection<string> SupportedExtensions { get; }

    Task<string> ExtractAsync(string fullFilePath, CancellationToken cancellationToken = default);
}