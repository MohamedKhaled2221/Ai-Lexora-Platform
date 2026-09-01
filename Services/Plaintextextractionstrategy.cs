namespace LegalAssistant.Api.Services;

public sealed class PlainTextExtractionStrategy : ITextExtractionStrategy
{
    public IReadOnlyCollection<string> SupportedExtensions { get; } = new[] { ".txt" };

    public async Task<string> ExtractAsync(string fullFilePath, CancellationToken cancellationToken = default)
        => await File.ReadAllTextAsync(fullFilePath, cancellationToken);
}