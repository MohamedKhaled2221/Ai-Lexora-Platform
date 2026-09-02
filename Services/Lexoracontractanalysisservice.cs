using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;

namespace LegalAssistant.Api.Services;

/// <summary>
/// Calls the AI-Lexora Module 2 pipeline end to end:
///   1. M1  POST /clauses        — original file in, clause-level text out
///   2. M5  POST /clauses/analyze — classifies each clause, compares to baseline
///   3. M6  POST /api/v1/risk/analyze — scores risk per clause
/// Replaces <see cref="RuleBasedContractAnalysisService"/> behind the same
/// <see cref="IContractAnalysisService"/> interface — ContractAnalysisController
/// does not change.
///
/// Each stage is a separate local process. If any of them isn't running, or
/// returns an error, this throws — ContractAnalysisController's caller
/// (AnalysisBackgroundService) already catches that and marks the analysis
/// as Failed with a clear message rather than crashing.
/// </summary>
public sealed class LexoraContractAnalysisService : IContractAnalysisService
{
    // Matches M1's accepted extensions exactly (m1/src/api.py) — this
    // implementation sends the original file straight to M1, which does its
    // own OCR-aware extraction, so it can handle far more than plain text
    // extraction alone (e.g. scanned images, DOCX).
    public IReadOnlyCollection<string> SupportedFileExtensions { get; } = new[]
    {
        ".pdf", ".docx", ".txt", ".md",
        ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"
    };

    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);

    private static readonly Dictionary<string, string> SeverityLabelsArabic = new()
    {
        ["critical"] = "حرج",
        ["high"] = "مرتفع",
        ["medium"] = "متوسط",
        ["low"] = "منخفض"
    };

    private static readonly Dictionary<string, int> SeverityPoints = new()
    {
        ["critical"] = 40,
        ["high"] = 25,
        ["medium"] = 12,
        ["low"] = 5
    };

    private readonly IHttpClientFactory _httpClientFactory;
    private readonly ILogger<LexoraContractAnalysisService> _logger;

    public LexoraContractAnalysisService(IHttpClientFactory httpClientFactory, ILogger<LexoraContractAnalysisService> logger)
    {
        _httpClientFactory = httpClientFactory;
        _logger = logger;
    }

    public async Task<ContractAnalysisResult> AnalyzeAsync(
        string contractText,
        string filePath,
        string fileName,
        CancellationToken cancellationToken = default)
    {
        var documentId = Guid.NewGuid().ToString("N");

        var m1Result = await CallM1Async(filePath, fileName, documentId, cancellationToken);
        if (m1Result.Clauses.Count == 0)
        {
            // M1 ran but found no clause-structured content (e.g. the
            // document's structure wasn't detectable). Nothing to send
            // downstream — this is a legitimate "no findings" result, not
            // a pipeline failure.
            return new ContractAnalysisResult(
                0,
                "لم يتم العثور على بنود قابلة للتحليل في هذا المستند (قد يكون هيكل العقد غير واضح للنظام).",
                Array.Empty<RiskyClauseResult>());
        }

        var m5Result = await CallM5Async(m1Result, cancellationToken);
        var m6Result = await CallM6Async(m5Result.Clauses, cancellationToken);

        return BuildResult(m6Result.Risks);
    }

    private async Task<M1ClauseResponse> CallM1Async(string filePath, string fileName, string documentId, CancellationToken cancellationToken)
    {
        var client = _httpClientFactory.CreateClient("M1Service");

        using var content = new MultipartFormDataContent();
        await using var fileStream = File.OpenRead(filePath);
        using var streamContent = new StreamContent(fileStream);
        streamContent.Headers.ContentType = new MediaTypeHeaderValue("application/octet-stream");
        content.Add(streamContent, "file", fileName);

        var requestUri = $"/clauses?contracts_only=true&document_id={Uri.EscapeDataString(documentId)}";

        HttpResponseMessage response;
        try
        {
            response = await client.PostAsync(requestUri, content, cancellationToken);
        }
        catch (HttpRequestException ex)
        {
            _logger.LogError(ex, "Could not reach the M1 document-processing service");
            throw new AiServiceUnavailableException("The document-processing (M1) service could not be reached.", ex);
        }

        if (!response.IsSuccessStatusCode)
        {
            _logger.LogWarning(
                "M1 document-processing service returned status {StatusCode}",
                (int)response.StatusCode);

            throw new AiServiceUnavailableException(
                $"The document-processing (M1) service returned status {(int)response.StatusCode}.");
        }

        var result = await response.Content.ReadFromJsonAsync<M1ClauseResponse>(JsonOptions, cancellationToken);
        return result ?? throw new AiServiceUnavailableException("The M1 service returned an empty response.");
    }

    private async Task<M5AnalyzeResponse> CallM5Async(M1ClauseResponse m1Result, CancellationToken cancellationToken)
    {
        var client = _httpClientFactory.CreateClient("M5Service");

        var request = new M5AnalyzeRequest
        {
            DocumentId = m1Result.DocumentId,
            Clauses = m1Result.Clauses.Select(c => new M5ClauseInput
            {
                // M1's clause_id can be null for some clauses; chunk_id is
                // always present, so fall back to it to satisfy M5's
                // required, non-empty clause_id field.
                ClauseId = string.IsNullOrWhiteSpace(c.ClauseId) ? c.ChunkId : c.ClauseId,
                Text = c.Text,
                Page = c.Page,
                Section = c.Section,
                Language = c.Language
            }).ToList()
        };

        HttpResponseMessage response;
        try
        {
            response = await client.PostAsJsonAsync("/clauses/analyze", request, JsonOptions, cancellationToken);
        }
        catch (HttpRequestException ex)
        {
            _logger.LogError(ex, "Could not reach the M5 clause-analysis service");
            throw new AiServiceUnavailableException("The clause-analysis (M5) service could not be reached.", ex);
        }

        if (!response.IsSuccessStatusCode)
        {
            _logger.LogWarning(
                "M5 clause-analysis service returned status {StatusCode}",
                (int)response.StatusCode);

            throw new AiServiceUnavailableException(
                $"The clause-analysis (M5) service returned status {(int)response.StatusCode}.");
        }

        var result = await response.Content.ReadFromJsonAsync<M5AnalyzeResponse>(JsonOptions, cancellationToken);
        return result ?? throw new AiServiceUnavailableException("The M5 service returned an empty response.");
    }

    private async Task<M6RiskResponse> CallM6Async(List<M6ClauseInput> clauses, CancellationToken cancellationToken)
    {
        // M6's risk endpoint lives inside the main AI-Lexora app (the same
        // service the Chatbot talks to), so it shares that base URL.
        var client = _httpClientFactory.CreateClient("M6Service");
        var request = new M6RiskRequest { Clauses = clauses };

        HttpResponseMessage response;
        try
        {
            response = await client.PostAsJsonAsync("/api/v1/risk/analyze", request, JsonOptions, cancellationToken);
        }
        catch (HttpRequestException ex)
        {
            _logger.LogError(ex, "Could not reach the M6 risk-analysis service");
            throw new AiServiceUnavailableException("The risk-analysis (M6) service could not be reached.", ex);
        }

        if (!response.IsSuccessStatusCode)
        {
            _logger.LogWarning(
                "M6 risk-analysis service returned status {StatusCode}",
                (int)response.StatusCode);

            throw new AiServiceUnavailableException(
                $"The risk-analysis (M6) service returned status {(int)response.StatusCode}.");
        }

        var result = await response.Content.ReadFromJsonAsync<M6RiskResponse>(JsonOptions, cancellationToken);
        return result ?? throw new AiServiceUnavailableException("The M6 service returned an empty response.");
    }

    private static ContractAnalysisResult BuildResult(List<M6ContractRisk> risks)
    {
        if (risks.Count == 0)
        {
            return new ContractAnalysisResult(
                0,
                "لم يتم رصد أي مخاطر في هذا العقد وفق القواعد الحالية.",
                Array.Empty<RiskyClauseResult>());
        }

        var riskScore = Math.Min(100, risks.Sum(r => SeverityPoints.GetValueOrDefault(r.Severity.Trim().ToLowerInvariant(), 5)));

        var severityCounts = risks
            .GroupBy(r => r.Severity.Trim().ToLowerInvariant())
            .ToDictionary(g => g.Key, g => g.Count());

        var summaryParts = severityCounts
            .OrderByDescending(kv => SeverityPoints.GetValueOrDefault(kv.Key, 0))
            .Select(kv => $"{kv.Value} {SeverityLabelsArabic.GetValueOrDefault(kv.Key, kv.Key)}");

        var summary = $"تم رصد {risks.Count} مخاطرة محتملة: {string.Join("، ", summaryParts)}.";

        var riskyClauses = risks
            .Select(r => new RiskyClauseResult(
                ClauseText: r.Evidence,
                RiskType: SeverityLabelsArabic.GetValueOrDefault(r.Severity.Trim().ToLowerInvariant(), r.Severity),
                Explanation: r.Explanation))
            .ToList();

        return new ContractAnalysisResult(riskScore, summary, riskyClauses);
    }
}