namespace LegalAssistant.Api.Services;

/// <summary>
/// Dispatches to the correct <see cref="ITextExtractionStrategy"/> based on
/// file extension. Register new strategies (Word, OCR for images, etc.) in
/// Program.cs — this class never needs to change.
/// </summary>
public sealed class CompositeDocumentTextExtractor : IDocumentTextExtractor
{
    private readonly Dictionary<string, ITextExtractionStrategy> _strategiesByExtension;

    public CompositeDocumentTextExtractor(IEnumerable<ITextExtractionStrategy> strategies)
    {
        _strategiesByExtension = new Dictionary<string, ITextExtractionStrategy>(StringComparer.OrdinalIgnoreCase);
        foreach (var strategy in strategies)
        {
            foreach (var extension in strategy.SupportedExtensions)
            {
                _strategiesByExtension[extension] = strategy;
            }
        }
    }

    public bool CanExtract(string fileName)
        => _strategiesByExtension.ContainsKey(Path.GetExtension(fileName));

    public Task<string> ExtractTextAsync(string fullFilePath, string fileName, CancellationToken cancellationToken = default)
    {
        var extension = Path.GetExtension(fileName);
        if (!_strategiesByExtension.TryGetValue(extension, out var strategy))
            throw new UnsupportedFileTypeException(extension);

        return strategy.ExtractAsync(fullFilePath, cancellationToken);
    }
}