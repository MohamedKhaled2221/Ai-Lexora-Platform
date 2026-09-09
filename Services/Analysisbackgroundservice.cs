using LegalAssistant.Api.Data;
using LegalAssistant.Api.Repositories;

namespace LegalAssistant.Api.Services;

/// <summary>
/// Consumes <see cref="IAnalysisWorkQueue"/> and runs the actual analysis
/// pipeline (text extraction -> IContractAnalysisService -> save result) in
/// the background. This is where an LLM-backed IContractAnalysisService will
/// actually be called once it's ready — this class does not need to change
/// when that happens, since it only depends on the interface.
/// </summary>
public sealed class AnalysisBackgroundService : BackgroundService
{
    private readonly IAnalysisWorkQueue _queue;
    private readonly IServiceScopeFactory _scopeFactory;
    private readonly ILogger<AnalysisBackgroundService> _logger;

    public AnalysisBackgroundService(
        IAnalysisWorkQueue queue,
        IServiceScopeFactory scopeFactory,
        ILogger<AnalysisBackgroundService> logger)
    {
        _queue = queue;
        _scopeFactory = scopeFactory;
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        // If the app restarted while analyses were in flight, they'll never
        // be dequeued again on their own (the in-memory queue is empty after
        // a restart) — re-queue them so they run again instead of being
        // silently stuck in "Processing" forever.
        await RequeueInterruptedAnalysesAsync(stoppingToken);

        while (!stoppingToken.IsCancellationRequested)
        {
            int documentId;
            try
            {
                documentId = await _queue.DequeueAsync(stoppingToken);
            }
            catch (OperationCanceledException)
            {
                break;
            }

            try
            {
                await ProcessAsync(documentId, stoppingToken);
            }
            catch (Exception ex)
            {
                // Defensive: ProcessAsync already catches and records
                // analysis-specific failures. This only guards against
                // something unexpected (e.g. a DB outage) so one bad item
                // never kills the whole background loop.
                _logger.LogError(ex, "Unhandled error processing queued analysis for document {DocumentId}", documentId);
            }
        }
    }

    private async Task RequeueInterruptedAnalysesAsync(CancellationToken cancellationToken)
    {
        using var scope = _scopeFactory.CreateScope();
        var analyses = scope.ServiceProvider.GetRequiredService<IAnalysisRepository>();
        var stuckDocumentIds = await analyses.GetDocumentIdsByStatusAsync(AnalysisStatuses.Processing);
        foreach (var documentId in stuckDocumentIds)
        {
            _logger.LogWarning("Re-queuing analysis for document {DocumentId} interrupted by a previous restart", documentId);
            await _queue.QueueAsync(documentId, cancellationToken);
        }
    }

    private async Task ProcessAsync(int documentId, CancellationToken cancellationToken)
    {
        using var scope = _scopeFactory.CreateScope();
        var services = scope.ServiceProvider;
        var documents = services.GetRequiredService<IDocumentRepository>();
        var analyses = services.GetRequiredService<IAnalysisRepository>();
        var documentService = services.GetRequiredService<IDocumentService>();
        var textExtractor = services.GetRequiredService<IDocumentTextExtractor>();
        var analysisService = services.GetRequiredService<IContractAnalysisService>();

        var document = await documents.GetByIdAsync(documentId);
        var analysis = await analyses.GetByDocumentIdAsync(documentId);
        if (document is null || analysis is null)
        {
            _logger.LogWarning("Queued analysis for document {DocumentId} skipped: document or analysis record no longer exists", documentId);
            return;
        }

        try
        {
            var fullPath = documentService.GetFilePath(document);

            string text;
            try
            {
                text = await textExtractor.ExtractTextAsync(fullPath, document.FileName, cancellationToken);
            }
            catch (UnsupportedFileTypeException)
            {
                // No extractor at all for this file type — nothing downstream
                // can work with it (not even an implementation that reads the
                // raw file itself), so this is a genuine hard stop.
                await MarkFailedAsync(analyses, analysis,
                    "This file type isn't supported yet.");
                return;
            }

            // Note: text may be empty here (e.g. a scanned PDF our own
            // extractor can't read). We still call the analysis service
            // with the file path — a real implementation may do its own
            // OCR-aware extraction from the original file and succeed where
            // our plain-text extractor couldn't.
            var result = await analysisService.AnalyzeAsync(text, fullPath, document.FileName, cancellationToken);

            analysis.RiskScore = result.RiskScore;
            analysis.Summary = result.Summary;
            analysis.Status = AnalysisStatuses.Completed;
            analysis.CompletedAt = DateTime.UtcNow;
            analysis.ErrorMessage = null;
            analysis.AnalyzedAt = DateTime.UtcNow;
            analysis.RiskyClauses.Clear();
            foreach (var clause in result.RiskyClauses)
            {
                analysis.RiskyClauses.Add(new RiskyClause
                {
                    ClauseText = clause.ClauseText,
                    RiskType = clause.RiskType,
                    Explanation = clause.Explanation
                });
            }

            await analyses.SaveChangesAsync();
            _logger.LogInformation("Document {DocumentId} analyzed in background; {RiskCount} findings", documentId, result.RiskyClauses.Count);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Analysis failed for document {DocumentId}", documentId);
            await MarkFailedAsync(analyses, analysis, "Analysis failed. Please try again.");
        }
    }

    private static async Task MarkFailedAsync(IAnalysisRepository analyses, ContractAnalysis analysis, string message)
    {
        analysis.Status = AnalysisStatuses.Failed;
        analysis.CompletedAt = DateTime.UtcNow;
        analysis.ErrorMessage = message;
        analysis.AnalyzedAt = DateTime.UtcNow;
        await analyses.SaveChangesAsync();
    }
}