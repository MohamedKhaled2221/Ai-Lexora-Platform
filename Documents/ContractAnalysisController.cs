using System.Security.Claims;
using LegalAssistant.Api.Data;
using LegalAssistant.Api.Repositories;
using LegalAssistant.Api.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace LegalAssistant.Api.Documents;

[ApiController]
[Authorize]
[Route("api/documents/{documentId:int}/analysis")]
public class ContractAnalysisController : ControllerBase
{
    private readonly IDocumentRepository _documents;
    private readonly IAnalysisRepository _analyses;
    private readonly IDocumentService _documentService;
    private readonly IContractAnalysisService _analysisService;
    private readonly IAnalysisWorkQueue _workQueue;
    private readonly ILogger<ContractAnalysisController> _logger;

    public ContractAnalysisController(
        IDocumentRepository documents,
        IAnalysisRepository analyses,
        IDocumentService documentService,
        IContractAnalysisService analysisService,
        IAnalysisWorkQueue workQueue,
        ILogger<ContractAnalysisController> logger)
    {
        _documents = documents;
        _analyses = analyses;
        _documentService = documentService;
        _analysisService = analysisService;
        _workQueue = workQueue;
        _logger = logger;
    }

    /// <summary>
    /// Queues contract analysis for this document and returns immediately.
    /// The actual work (text extraction + analysis) happens in the
    /// background — poll GET to see progress and the final result.
    /// </summary>
    [HttpPost]
    public Task<ActionResult<ContractAnalysisResponse>> Analyze(int documentId) => EnqueueAnalysisAsync(documentId);

    /// <summary>Alias of POST — kept for clients already using the explicit "start" action name.</summary>
    [HttpPost("start")]
    public Task<ActionResult<ContractAnalysisResponse>> Start(int documentId) => EnqueueAnalysisAsync(documentId);

    [HttpGet]
    public async Task<ActionResult<ContractAnalysisResponse>> Get(int documentId)
    {
        var document = await FindOwnedDocument(documentId);
        if (document is null) return NotFound(new { message = "Document not found." });

        var analysis = await _analyses.GetByDocumentIdAsync(documentId);

        return analysis is null
            ? NotFound(new { message = "This document has not been analyzed yet." })
            : Ok(ToResponse(analysis));
    }

    [HttpPost("complete")]
    [Authorize(Roles = AppRoles.Admin)]
    public async Task<ActionResult<ContractAnalysisResponse>> Complete(int documentId, CompleteAnalysisRequest request)
    {
        if (request.RiskScore is < 0 or > 100)
            return BadRequest(new { message = "Risk score must be between 0 and 100." });
        if (string.IsNullOrWhiteSpace(request.Summary) || request.Summary.Length > 2000)
            return BadRequest(new { message = "A summary of 2,000 characters or fewer is required." });

        var documentExists = await _analyses.DocumentExistsAsync(documentId);
        if (!documentExists) return NotFound(new { message = "Document not found." });

        var analysis = await GetOrCreateAnalysis(documentId);
        analysis.Status = AnalysisStatuses.Completed;
        analysis.StartedAt ??= DateTime.UtcNow;
        analysis.CompletedAt = DateTime.UtcNow;
        analysis.ErrorMessage = null;
        analysis.RiskScore = request.RiskScore;
        analysis.Summary = request.Summary.Trim();
        analysis.AnalyzedAt = DateTime.UtcNow;
        analysis.RiskyClauses.Clear();
        foreach (var clause in request.RiskyClauses ?? Array.Empty<CreateRiskyClauseRequest>())
        {
            if (string.IsNullOrWhiteSpace(clause.ClauseText) || clause.ClauseText.Length > 2000 ||
                string.IsNullOrWhiteSpace(clause.RiskType) || clause.RiskType.Length > 50 ||
                string.IsNullOrWhiteSpace(clause.Explanation) || clause.Explanation.Length > 1000)
                return BadRequest(new { message = "One or more risky clauses are invalid." });

            analysis.RiskyClauses.Add(new RiskyClause
            {
                ClauseText = clause.ClauseText.Trim(),
                RiskType = clause.RiskType.Trim(),
                Explanation = clause.Explanation.Trim(),
                Severity = clause.Severity?.Trim(),
                SeverityColor = clause.SeverityColor?.Trim()
            });
        }

        await _analyses.SaveChangesAsync();
        _logger.LogInformation("Analysis completed for document {DocumentId}", documentId);
        return Ok(ToResponse(analysis));
    }

    [HttpPost("fail")]
    [Authorize(Roles = AppRoles.Admin)]
    public async Task<ActionResult<ContractAnalysisResponse>> Fail(int documentId, FailAnalysisRequest request)
    {
        if (string.IsNullOrWhiteSpace(request.ErrorMessage) || request.ErrorMessage.Length > 2000)
            return BadRequest(new { message = "An error message of 2,000 characters or fewer is required." });

        var documentExists = await _analyses.DocumentExistsAsync(documentId);
        if (!documentExists) return NotFound(new { message = "Document not found." });

        var analysis = await GetOrCreateAnalysis(documentId);
        analysis.Status = AnalysisStatuses.Failed;
        analysis.StartedAt ??= DateTime.UtcNow;
        analysis.CompletedAt = DateTime.UtcNow;
        analysis.ErrorMessage = request.ErrorMessage.Trim();
        analysis.AnalyzedAt = DateTime.UtcNow;
        await _analyses.SaveChangesAsync();

        _logger.LogWarning("Analysis failed for document {DocumentId}: {ErrorMessage}", documentId, analysis.ErrorMessage);
        return Ok(ToResponse(analysis));
    }

    private async Task<ActionResult<ContractAnalysisResponse>> EnqueueAnalysisAsync(int documentId)
    {
        var document = await FindOwnedDocument(documentId);
        if (document is null) return NotFound(new { message = "Document not found." });

        var fullPath = _documentService.GetFilePath(document);
        if (!System.IO.File.Exists(fullPath))
            return NotFound(new { message = "The stored file no longer exists." });

        var extension = Path.GetExtension(document.FileName);
        if (!_analysisService.SupportedFileExtensions.Contains(extension, StringComparer.OrdinalIgnoreCase))
        {
            var supported = string.Join(", ", _analysisService.SupportedFileExtensions);
            return BadRequest(new
            {
                message = $"Files of type '{extension}' are not supported yet. Supported types: {supported}."
            });
        }

        var analysis = await GetOrCreateAnalysis(documentId);
        if (analysis.Status == AnalysisStatuses.Processing)
            return Conflict(new { message = "Analysis is already processing." });

        analysis.Status = AnalysisStatuses.Processing;
        analysis.StartedAt = DateTime.UtcNow;
        analysis.CompletedAt = null;
        analysis.ErrorMessage = null;
        analysis.RiskScore = 0;
        analysis.Summary = "Analysis is processing.";
        analysis.AnalyzedAt = DateTime.UtcNow;
        analysis.RiskyClauses.Clear();
        await _analyses.SaveChangesAsync();

        // Hand off to the background worker and return immediately — the
        // actual (potentially slow, eventually AI-backed) work happens
        // outside this request. Client polls GET for the result.
        await _workQueue.QueueAsync(documentId, HttpContext.RequestAborted);

        _logger.LogInformation("Analysis queued for document {DocumentId}", documentId);
        return AcceptedAtAction(nameof(Get), new { documentId }, ToResponse(analysis));
    }

    private async Task<Document?> FindOwnedDocument(int documentId)
    {
        var userId = User.FindFirstValue(ClaimTypes.NameIdentifier) ?? User.FindFirstValue("sub");
        return userId is null ? null : await _documents.GetOwnedAsync(documentId, userId);
    }

    private async Task<ContractAnalysis> GetOrCreateAnalysis(int documentId)
    {
        var analysis = await _analyses.GetByDocumentIdAsync(documentId);
        if (analysis is not null) return analysis;

        analysis = new ContractAnalysis { DocumentId = documentId, Status = AnalysisStatuses.Pending };
        _analyses.Add(analysis);
        return analysis;
    }

    private static ContractAnalysisResponse ToResponse(ContractAnalysis analysis) => new(
        analysis.Id,
        analysis.DocumentId,
        analysis.RiskScore,
        analysis.Summary,
        analysis.Status,
        analysis.StartedAt,
        analysis.CompletedAt,
        analysis.ErrorMessage,
        analysis.AnalyzedAt,
        analysis.RiskyClauses.Select(c => new RiskyClauseResponse(
            c.Id, c.ClauseText, c.RiskType, c.Explanation, c.Severity, c.SeverityColor)).ToList());
}