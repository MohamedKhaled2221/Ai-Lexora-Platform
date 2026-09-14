namespace LegalAssistant.Api.Services;

/// <summary>
/// Abstraction over "analyze this contract and return risk findings".
/// The controller only depends on this interface, never on how the analysis
/// is actually produced. Today <see cref="RuleBasedContractAnalysisService"/>
/// implements it with regex/keyword matching as a placeholder;
/// <see cref="LexoraContractAnalysisService"/> implements it against the
/// real AI-Lexora M1→M5→M6 pipeline. Swapping which one is active is a
/// one-line change in Program.cs — ContractAnalysisController does not change.
/// </summary>
public interface IContractAnalysisService
{
    /// <summary>
    /// File extensions (lowercase, with the dot, e.g. ".pdf") this
    /// implementation can analyze. The controller uses this — not
    /// <see cref="IDocumentTextExtractor"/>'s supported formats — to decide
    /// whether to accept an upload, since an implementation may work
    /// directly from the original file (e.g. via OCR) rather than needing
    /// our own plain-text extraction to succeed first.
    /// </summary>
    IReadOnlyCollection<string> SupportedFileExtensions { get; }

    /// <summary>
    /// Analyzes a contract and returns a risk assessment.
    /// <paramref name="contractText"/> is the already-extracted plain text
    /// (from <see cref="IDocumentTextExtractor"/>) for implementations that
    /// only need text. <paramref name="filePath"/>/<paramref name="fileName"/>
    /// point at the original stored file, for implementations (like the real
    /// AI-Lexora pipeline) that need the source file itself — e.g. for
    /// OCR-aware, page-structure-aware clause segmentation that plain text
    /// alone would lose.
    /// </summary>
    Task<ContractAnalysisResult> AnalyzeAsync(
        string contractText,
        string filePath,
        string fileName,
        CancellationToken cancellationToken = default);
}

/// <summary>
/// Plain result of an analysis, independent of the EF Core entities
/// (ContractAnalysis / RiskyClause) so the AI-facing contract doesn't leak
/// persistence concerns and doesn't change if the DB schema changes.
/// </summary>
public sealed record ContractAnalysisResult(
    int RiskScore,
    string Summary,
    IReadOnlyCollection<RiskyClauseResult> RiskyClauses);

public sealed record RiskyClauseResult(
    string ClauseText,
    string RiskType,
    string Explanation,
    string? Severity = null,
    string? SeverityColor = null);