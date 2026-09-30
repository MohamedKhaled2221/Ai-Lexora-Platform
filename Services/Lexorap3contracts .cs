using System.Text.Json.Serialization;

namespace LegalAssistant.Api.Services;

// =========================================================
// Outgoing: POST /api/v1/p3/generate  (request)
// Wire format matches src/api/schemas.py:P3GenerateRequest
// =========================================================

/// <summary>Wire format of the "request" field inside P3GenerateRequest
/// (src/document_generator/schemas.py:GuidedDocumentRequest).</summary>
public sealed class LexoraGuidedDocumentRequest
{
    [JsonPropertyName("request_id")] public string RequestId { get; set; } = string.Empty;
    [JsonPropertyName("document_type")] public string DocumentType { get; set; } = string.Empty;
    [JsonPropertyName("jurisdiction")] public string Jurisdiction { get; set; } = string.Empty;

    /// <summary>Guided-input field values keyed by the template's field name
    /// (see LexoraP3TemplateField.Name from GET /api/v1/p3/templates).</summary>
    [JsonPropertyName("fields")] public Dictionary<string, object?> Fields { get; set; } = new();

    [JsonPropertyName("requested_clause_ids")] public List<string> RequestedClauseIds { get; set; } = new();
    [JsonPropertyName("special_conditions")] public List<string> SpecialConditions { get; set; } = new();
}

/// <summary>Wire format of POST /api/v1/p3/generate request body
/// (src/api/schemas.py:P3GenerateRequest).</summary>
public sealed class LexoraP3GenerateRequest
{
    [JsonPropertyName("request")] public LexoraGuidedDocumentRequest Request { get; set; } = new();

    /// <summary>"ar" or "en". Defaults to "en" on the AI side if omitted.</summary>
    [JsonPropertyName("clause_language")] public string ClauseLanguage { get; set; } = "en";

    [JsonPropertyName("export_docx")] public bool ExportDocx { get; set; } = true;
}

// =========================================================
// Incoming: POST /api/v1/p3/generate  (response)
// Wire format matches src/api/schemas.py:P3GenerateResponse
// and src/schemas/p3_generation_contract.py
// =========================================================

/// <summary>One trusted source backing a draft section
/// (p3_generation_contract.py:SourceReference).</summary>
public sealed class LexoraP3SourceReference
{
    /// <summary>"template" | "approved_clause" | "user_input" | "lawyer_approved_edit".</summary>
    [JsonPropertyName("source_type")] public string SourceType { get; set; } = string.Empty;
    [JsonPropertyName("source_id")] public string SourceId { get; set; } = string.Empty;
    [JsonPropertyName("source_version")] public string? SourceVersion { get; set; }
}

/// <summary>One assembled section of the M1 draft
/// (p3_generation_contract.py:DraftSection).</summary>
public sealed class LexoraP3DraftSection
{
    [JsonPropertyName("section_id")] public string SectionId { get; set; } = string.Empty;
    [JsonPropertyName("title")] public string Title { get; set; } = string.Empty;
    [JsonPropertyName("text")] public string Text { get; set; } = string.Empty;
    [JsonPropertyName("source_references")] public List<LexoraP3SourceReference> SourceReferences { get; set; } = new();
}

/// <summary>Deterministically assembled draft produced by M1
/// (p3_generation_contract.py:AssembledDraft).</summary>
public sealed class LexoraP3AssembledDraft
{
    [JsonPropertyName("draft_id")] public string DraftId { get; set; } = string.Empty;
    [JsonPropertyName("document_type")] public string DocumentType { get; set; } = string.Empty;
    [JsonPropertyName("template_id")] public string TemplateId { get; set; } = string.Empty;
    [JsonPropertyName("template_version")] public string TemplateVersion { get; set; } = string.Empty;
    [JsonPropertyName("sections")] public List<LexoraP3DraftSection> Sections { get; set; } = new();
    [JsonPropertyName("created_at")] public DateTimeOffset CreatedAt { get; set; }
}

/// <summary>Approved M5 clause used during assembly (ClauseReference).</summary>
public sealed class LexoraP3ClauseReference
{
    [JsonPropertyName("clause_id")] public string ClauseId { get; set; } = string.Empty;
    [JsonPropertyName("clause_version")] public string ClauseVersion { get; set; } = string.Empty;
}

/// <summary>Reference to a lawyer-reviewed edit (LawyerEditReference).</summary>
public sealed class LexoraP3LawyerEditReference
{
    [JsonPropertyName("edit_id")] public string EditId { get; set; } = string.Empty;
    [JsonPropertyName("section_id")] public string SectionId { get; set; } = string.Empty;
    [JsonPropertyName("reviewer_id")] public string ReviewerId { get; set; } = string.Empty;
    [JsonPropertyName("approved_at")] public DateTimeOffset ApprovedAt { get; set; }
}

/// <summary>Audit record for an AI-assisted transformation (AITransformationRecord).</summary>
public sealed class LexoraP3AiTransformationRecord
{
    [JsonPropertyName("transformation_id")] public string TransformationId { get; set; } = string.Empty;
    [JsonPropertyName("target_section_id")] public string TargetSectionId { get; set; } = string.Empty;
    [JsonPropertyName("source_ids")] public List<string> SourceIds { get; set; } = new();
    [JsonPropertyName("model_tag")] public string ModelTag { get; set; } = string.Empty;
    [JsonPropertyName("prompt_version")] public string PromptVersion { get; set; } = string.Empty;
    [JsonPropertyName("transformed_at")] public DateTimeOffset TransformedAt { get; set; }
}

/// <summary>Full provenance manifest created by M1 (GenerationManifest).
/// Note: distinct shape from document_generator's own GenerationManifest —
/// this is the one actually returned inside ValidatedDraft.</summary>
public sealed class LexoraP3GenerationManifest
{
    [JsonPropertyName("manifest_id")] public string ManifestId { get; set; } = string.Empty;
    [JsonPropertyName("draft_id")] public string DraftId { get; set; } = string.Empty;
    [JsonPropertyName("template_id")] public string TemplateId { get; set; } = string.Empty;
    [JsonPropertyName("template_version")] public string TemplateVersion { get; set; } = string.Empty;
    [JsonPropertyName("clause_references")] public List<LexoraP3ClauseReference> ClauseReferences { get; set; } = new();
    [JsonPropertyName("user_fields")] public Dictionary<string, string> UserFields { get; set; } = new();
    [JsonPropertyName("lawyer_edit_references")] public List<LexoraP3LawyerEditReference> LawyerEditReferences { get; set; } = new();
    [JsonPropertyName("ai_transformations")] public List<LexoraP3AiTransformationRecord> AiTransformations { get; set; } = new();
    [JsonPropertyName("created_at")] public DateTimeOffset CreatedAt { get; set; }
}

/// <summary>M4's validation verdict on the draft (DraftValidationResult).</summary>
public sealed class LexoraP3DraftValidationResult
{
    [JsonPropertyName("is_valid")] public bool IsValid { get; set; }
    [JsonPropertyName("structure_valid")] public bool StructureValid { get; set; }
    [JsonPropertyName("provenance_valid")] public bool ProvenanceValid { get; set; }
    [JsonPropertyName("grounding_valid")] public bool GroundingValid { get; set; }
    [JsonPropertyName("unsourced_section_ids")] public List<string> UnsourcedSectionIds { get; set; } = new();
    [JsonPropertyName("errors")] public List<string> Errors { get; set; } = new();
    [JsonPropertyName("warnings")] public List<string> Warnings { get; set; } = new();
    [JsonPropertyName("validated_at")] public DateTimeOffset ValidatedAt { get; set; }
}

/// <summary>Final M4-validated Package 3 output (ValidatedDraft).</summary>
public sealed class LexoraP3ValidatedDraft
{
    [JsonPropertyName("draft")] public LexoraP3AssembledDraft Draft { get; set; } = new();
    [JsonPropertyName("manifest")] public LexoraP3GenerationManifest Manifest { get; set; } = new();
    [JsonPropertyName("validation")] public LexoraP3DraftValidationResult Validation { get; set; } = new();
    [JsonPropertyName("validator_version")] public string ValidatorVersion { get; set; } = "1.0.0";
    [JsonPropertyName("model_tag")] public string? ModelTag { get; set; }
    [JsonPropertyName("prompt_version")] public string? PromptVersion { get; set; }
    [JsonPropertyName("requires_lawyer_review")] public bool RequiresLawyerReview { get; set; }
    [JsonPropertyName("validated_at")] public DateTimeOffset ValidatedAt { get; set; }
}

/// <summary>Wire format of POST /api/v1/p3/generate response body
/// (src/api/schemas.py:P3GenerateResponse).</summary>
public sealed class LexoraP3GenerateResponse
{
    [JsonPropertyName("validated_draft")] public LexoraP3ValidatedDraft ValidatedDraft { get; set; } = new();
    [JsonPropertyName("selected_clause_ids")] public List<string> SelectedClauseIds { get; set; } = new();
    [JsonPropertyName("export_allowed")] public bool ExportAllowed { get; set; }
    [JsonPropertyName("m5_resolved_clause_count")] public int M5ResolvedClauseCount { get; set; }
    [JsonPropertyName("docx_generated")] public bool DocxGenerated { get; set; }
    [JsonPropertyName("docx_file_name")] public string? DocxFileName { get; set; }
}

// =========================================================
// Incoming: GET /api/v1/p3/templates  (response)
// Wire format matches src/api/schemas.py:
//   P3TemplateFieldResponse / P3TemplateSummary / P3TemplatesResponse
// =========================================================

/// <summary>One guided-input field a template requires
/// (P3TemplateFieldResponse). The real API does not return a
/// field_type — the frontend should treat every field as free text
/// unless/until the AI team adds typing.</summary>
public sealed class LexoraP3TemplateField
{
    [JsonPropertyName("name")] public string Name { get; set; } = string.Empty;
    [JsonPropertyName("label")] public string Label { get; set; } = string.Empty;
    [JsonPropertyName("required")] public bool Required { get; set; }
}

/// <summary>One available Package 3 template (P3TemplateSummary).</summary>
public sealed class LexoraP3TemplateSummary
{
    [JsonPropertyName("template_id")] public string TemplateId { get; set; } = string.Empty;
    [JsonPropertyName("version")] public string Version { get; set; } = string.Empty;
    [JsonPropertyName("document_type")] public string DocumentType { get; set; } = string.Empty;
    [JsonPropertyName("jurisdiction")] public string Jurisdiction { get; set; } = string.Empty;
    [JsonPropertyName("language")] public string Language { get; set; } = string.Empty;
    [JsonPropertyName("fields")] public List<LexoraP3TemplateField> Fields { get; set; } = new();
}

/// <summary>Wire format of GET /api/v1/p3/templates response body
/// (src/api/schemas.py:P3TemplatesResponse).</summary>
public sealed class LexoraP3TemplatesResponse
{
    [JsonPropertyName("templates")] public List<LexoraP3TemplateSummary> Templates { get; set; } = new();
}