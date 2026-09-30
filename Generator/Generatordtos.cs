namespace LegalAssistant.Api.Generator;

// =========================================================
// Request/response shapes for DocumentGeneratorController's
// own routes. (Distinct from the Lexora* wire DTOs in
// Services/LexoraP3Contracts.cs, which mirror the AI service's
// Pydantic schemas 1:1 — these are what the frontend actually
// sends/receives.)
// =========================================================

/// <summary>One available document type/jurisdiction template, with the
/// guided-input fields the frontend must collect before generating.</summary>
public sealed record TemplateInfoResponse(
    string TemplateId,
    string Version,
    string DocumentType,
    string Jurisdiction,
    string Language,
    IReadOnlyCollection<TemplateFieldResponse> Fields);

public sealed record TemplateFieldResponse(string Name, string Label, bool Required);

/// <summary>What the frontend sends to generate a document.</summary>
public sealed class GenerateDocumentRequest
{
    public string DocumentType { get; set; } = string.Empty;
    public string Jurisdiction { get; set; } = string.Empty;

    /// <summary>Guided-input values keyed by field name (see TemplateFieldResponse.Name).</summary>
    public Dictionary<string, object?> Fields { get; set; } = new();

    public List<string>? RequestedClauseIds { get; set; }
    public List<string>? SpecialConditions { get; set; }

    /// <summary>"ar" or "en". Defaults to "en" if omitted.</summary>
    public string? ClauseLanguage { get; set; }

    /// <summary>Optional matter/case scope, forwarded to the AI service as X-Matter-Id.</summary>
    public string? MatterId { get; set; }
}

/// <summary>One assembled section of the draft, for the frontend to render for review.</summary>
public sealed record DraftSectionResponse(string SectionId, string Title, string Text);

/// <summary>Option 1 shape: POST /generate returns the draft + M4 validation
/// status only. No file. The frontend decides whether to show a Download
/// button based on ExportAllowed, and should surface RequiresLawyerReview /
/// ValidationWarnings to the user before they download anything.</summary>
public sealed record GenerateDocumentResponse(
    string DraftId,
    string DocumentType,
    string TemplateId,
    string TemplateVersion,
    IReadOnlyCollection<DraftSectionResponse> Sections,
    IReadOnlyCollection<string> SelectedClauseIds,
    bool ExportAllowed,
    bool RequiresLawyerReview,
    bool DocxGenerated,
    string? DocxFileName,
    IReadOnlyCollection<string> ValidationErrors,
    IReadOnlyCollection<string> ValidationWarnings);