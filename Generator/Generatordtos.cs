namespace LegalAssistant.Api.Generator;

public record TemplateInfoResponse(string Key, string Name, string Description, IReadOnlyCollection<string> RequiredFields);

public record GenerateDocumentRequest(string TemplateKey, Dictionary<string, string>? Fields);