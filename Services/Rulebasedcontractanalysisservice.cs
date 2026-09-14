using System.Text.RegularExpressions;

namespace LegalAssistant.Api.Services;

/// <summary>
/// Temporary placeholder implementation of <see cref="IContractAnalysisService"/>.
/// Uses fixed keyword/regex patterns instead of real AI, so it is fast and
/// dependency-free — useful until a real LLM-backed service is wired in.
/// Not legal advice; intended purely as a stand-in during development.
/// </summary>
public sealed class RuleBasedContractAnalysisService : IContractAnalysisService
{
    // This implementation only ever looks at contractText (already extracted
    // by IDocumentTextExtractor), so it can't support anything that
    // extractor doesn't.
    public IReadOnlyCollection<string> SupportedFileExtensions { get; } = new[] { ".txt", ".pdf" };

    private static readonly RiskPattern[] Patterns =
    {
        new(@"\b(unlimited liability|liable for all damages|مسؤولية غير محدودة)\b", "High", 35,
            "Unlimited liability can expose a party to unbounded financial loss."),
        new(@"\b(terminate immediately|termination without notice|إنهاء فوري|إنهاء دون إخطار)\b", "High", 25,
            "The termination language may allow the agreement to end without adequate notice."),
        new(@"\b(exclusive|exclusivity|حصري|حصرية)\b", "Medium", 15,
            "Exclusivity may restrict the ability to work with other parties."),
        new(@"\b(automatic renewal|automatically renew|تجديد تلقائي)\b", "Medium", 15,
            "Automatic renewal can extend the contract unless notice is given in time."),
        new(@"\b(penalty|liquidated damages|غرامة|شرط جزائي)\b", "Medium", 15,
            "A penalty or liquidated-damages clause should be reviewed for proportionality."),
        new(@"\b(confidentiality|non-disclosure|سرية|عدم إفصاح)\b", "Low", 5,
            "Confidentiality obligations should define scope, duration, and permitted disclosures.")
    };

    public Task<ContractAnalysisResult> AnalyzeAsync(
        string contractText,
        string filePath,
        string fileName,
        CancellationToken cancellationToken = default)
    {
        var findings = FindRisks(contractText);
        var riskScore = Math.Min(100, findings.Sum(f => f.Score));
        var summary = CreateSummary(findings);

        var riskyClauses = findings
            .Select(f => new RiskyClauseResult(
                f.ClauseText,
                f.RiskType,
                f.Explanation,
                Severity: f.RiskType.ToLowerInvariant(),
                SeverityColor: f.RiskType.ToLowerInvariant() switch
                {
                    "high" => "red",
                    "medium" => "yellow",
                    "low" => "green",
                    _ => "gray"
                }))
            .ToList();

        return Task.FromResult(new ContractAnalysisResult(riskScore, summary, riskyClauses));
    }

    private static List<RiskFinding> FindRisks(string text)
    {
        var findings = new List<RiskFinding>();
        foreach (var pattern in Patterns)
        {
            var match = Regex.Match(text, pattern.Expression, RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);
            if (match.Success)
            {
                findings.Add(new RiskFinding(
                    ExtractClause(text, match.Index, match.Length),
                    pattern.RiskType,
                    pattern.Score,
                    pattern.Explanation));
            }
        }

        return findings;
    }

    private static string ExtractClause(string text, int index, int length)
    {
        const int contextLength = 400;
        var start = Math.Max(0, index - contextLength / 2);
        var end = Math.Min(text.Length, index + length + contextLength / 2);
        return text[start..end].Trim();
    }

    private static string CreateSummary(IReadOnlyCollection<RiskFinding> findings)
    {
        if (findings.Count == 0)
            return "No predefined risk patterns were found. This is a rule-based preliminary result, not legal advice.";

        var highCount = findings.Count(f => f.RiskType == "High");
        return $"Preliminary rule-based analysis found {findings.Count} potential risk clause(s), including {highCount} high-risk clause(s).";
    }

    private sealed record RiskPattern(string Expression, string RiskType, int Score, string Explanation);
    private sealed record RiskFinding(string ClauseText, string RiskType, int Score, string Explanation);
}