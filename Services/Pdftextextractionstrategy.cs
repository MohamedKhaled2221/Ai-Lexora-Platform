using System.Text;
using UglyToad.PdfPig;

namespace LegalAssistant.Api.Services;

/// <summary>
/// Extracts text from PDFs that have an embedded text layer (the vast
/// majority of contracts drafted digitally). Scanned/image-only PDFs will
/// yield little or no text here — that's expected until an OCR strategy is
/// added; callers already treat empty extracted text as "unreadable" and
/// surface a clear error rather than silently analyzing nothing.
/// </summary>
public sealed class PdfTextExtractionStrategy : ITextExtractionStrategy
{
    public IReadOnlyCollection<string> SupportedExtensions { get; } = new[] { ".pdf" };

    public Task<string> ExtractAsync(string fullFilePath, CancellationToken cancellationToken = default)
    {
        // PdfPig is synchronous; run it on a background thread so it doesn't
        // block the request thread for large documents.
        return Task.Run(() =>
        {
            var builder = new StringBuilder();
            using var document = PdfDocument.Open(fullFilePath);
            foreach (var page in document.GetPages())
            {
                cancellationToken.ThrowIfCancellationRequested();
                builder.AppendLine(page.Text);
            }

            return builder.ToString();
        }, cancellationToken);
    }
}