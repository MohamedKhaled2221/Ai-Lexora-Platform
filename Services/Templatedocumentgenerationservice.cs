using System.Text;

namespace LegalAssistant.Api.Services;

/// <summary>
/// Placeholder <see cref="IDocumentGenerationService"/>: fills one built-in
/// NDA template with simple {{Token}} substitution and returns plain text.
/// Proves the generate -&gt; download flow end-to-end before real Word/PDF
/// templating (or LLM-assisted drafting) is wired in behind the same interface.
/// </summary>
public sealed class TemplateDocumentGenerationService : IDocumentGenerationService
{
    private static readonly IReadOnlyDictionary<string, Template> Templates = new Dictionary<string, Template>(StringComparer.OrdinalIgnoreCase)
    {
        ["nda"] = new Template(
            Name: "Non-Disclosure Agreement",
            Description: "A simple mutual NDA template.",
            RequiredFields: new[] { "PartyAName", "PartyBName", "EffectiveDate", "DurationYears" },
            Body: NdaTemplateBody)
    };

    public IReadOnlyCollection<DocumentTemplateInfo> GetAvailableTemplates() =>
        Templates.Select(kv => new DocumentTemplateInfo(kv.Key, kv.Value.Name, kv.Value.Description, kv.Value.RequiredFields)).ToList();

    public Task<GeneratedDocument> GenerateAsync(
        string templateKey,
        IReadOnlyDictionary<string, string> fields,
        CancellationToken cancellationToken = default)
    {
        if (!Templates.TryGetValue(templateKey, out var template))
            throw new UnknownTemplateException(templateKey);

        var missing = template.RequiredFields
            .Where(f => !fields.TryGetValue(f, out var value) || string.IsNullOrWhiteSpace(value))
            .ToList();
        if (missing.Count > 0)
            throw new MissingTemplateFieldsException(missing);

        var body = template.Body;
        foreach (var field in fields)
            body = body.Replace($"{{{{{field.Key}}}}}", field.Value);

        var content = Encoding.UTF8.GetBytes(body);
        var fileName = $"{templateKey}-{DateTime.UtcNow:yyyyMMddHHmmss}.txt";
        return Task.FromResult(new GeneratedDocument(fileName, "text/plain", content));
    }

    private sealed record Template(string Name, string Description, IReadOnlyCollection<string> RequiredFields, string Body);

    private const string NdaTemplateBody = """
        NON-DISCLOSURE AGREEMENT

        This Non-Disclosure Agreement ("Agreement") is entered into as of {{EffectiveDate}}
        between {{PartyAName}} ("Party A") and {{PartyBName}} ("Party B").

        1. Each party may disclose confidential information to the other in connection
           with their business relationship.
        2. Each party agrees to protect the other's confidential information with the
           same degree of care it uses for its own confidential information.
        3. This Agreement shall remain in effect for {{DurationYears}} year(s) from the
           Effective Date.

        This is a placeholder template for demonstration purposes and is not legal advice.

        Party A: ______________________   Party B: ______________________
        """;
}