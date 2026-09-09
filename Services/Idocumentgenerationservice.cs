namespace LegalAssistant.Api.Services;

/// <summary>
/// Abstraction over "fill a template with fields and produce a document".
/// The placeholder implementation does simple {{token}} substitution on one
/// built-in template and returns plain text. A real implementation (proper
/// Word/PDF templating, or LLM-assisted drafting) can replace it later —
/// DocumentGeneratorController only depends on this interface.
/// </summary>
public interface IDocumentGenerationService
{
    IReadOnlyCollection<DocumentTemplateInfo> GetAvailableTemplates();

    Task<GeneratedDocument> GenerateAsync(
        string templateKey,
        IReadOnlyDictionary<string, string> fields,
        CancellationToken cancellationToken = default);
}

public sealed record DocumentTemplateInfo(string Key, string Name, string Description, IReadOnlyCollection<string> RequiredFields);

public sealed record GeneratedDocument(string FileName, string ContentType, byte[] Content);

public sealed class UnknownTemplateException : Exception
{
    public UnknownTemplateException(string templateKey) : base($"No template registered with key '{templateKey}'.")
        => TemplateKey = templateKey;

    public string TemplateKey { get; }
}

public sealed class MissingTemplateFieldsException : Exception
{
    public MissingTemplateFieldsException(IReadOnlyCollection<string> missingFields)
        : base($"Missing required field(s): {string.Join(", ", missingFields)}")
    {
        MissingFields = missingFields;
    }

    public IReadOnlyCollection<string> MissingFields { get; }
}