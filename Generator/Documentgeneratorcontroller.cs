using System.Security.Claims;
using LegalAssistant.Api.Data;
using LegalAssistant.Api.Repositories;
using LegalAssistant.Api.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace LegalAssistant.Api.Generator;

// Request/response DTOs (TemplateInfoResponse, TemplateFieldResponse,
// GenerateDocumentRequest, DraftSectionResponse, GenerateDocumentResponse)
// now live in DocumentGeneratorDtos.cs — same namespace, no using needed.

[ApiController]
[Authorize]
[Route("api/document-generator")]
public class DocumentGeneratorController : ControllerBase
{
    private readonly IPackage3DocumentGenerationService _p3Service;
    private readonly IAiCallerIdentityProvider _identityProvider;
    private readonly IGeneratedDocumentRepository _history;
    private readonly ILogger<DocumentGeneratorController> _logger;

    public DocumentGeneratorController(
        IPackage3DocumentGenerationService p3Service,
        IAiCallerIdentityProvider identityProvider,
        IGeneratedDocumentRepository history,
        ILogger<DocumentGeneratorController> logger)
    {
        _p3Service = p3Service;
        _identityProvider = identityProvider;
        _history = history;
        _logger = logger;
    }

    [HttpGet("templates")]
    public async Task<ActionResult<IReadOnlyCollection<TemplateInfoResponse>>> GetTemplates()
    {
        if (!TryResolveIdentity(out var identity, out var forbidden))
            return forbidden;

        IReadOnlyCollection<LexoraP3TemplateSummary> templates;
        try
        {
            templates = await _p3Service.GetTemplatesAsync(identity, HttpContext.RequestAborted);
        }
        catch (AiServiceUnavailableException ex)
        {
            return UpstreamUnavailable(ex, "list P3 templates");
        }

        var response = templates
            .Select(t => new TemplateInfoResponse(
                t.TemplateId,
                t.Version,
                t.DocumentType,
                t.Jurisdiction,
                t.Language,
                t.Fields.Select(f => new TemplateFieldResponse(f.Name, f.Label, f.Required)).ToList()))
            .ToList();

        return Ok(response);
    }

    /// <summary>Runs the M1 -&gt; M5 -&gt; M4 pipeline and returns the draft +
    /// validation status only. Never returns a file — see DownloadExport.</summary>
    [HttpPost("generate")]
    public async Task<ActionResult<GenerateDocumentResponse>> Generate(GenerateDocumentRequest request)
    {
        if (string.IsNullOrWhiteSpace(request.DocumentType))
            return BadRequest(new { message = "documentType is required." });
        if (string.IsNullOrWhiteSpace(request.Jurisdiction))
            return BadRequest(new { message = "jurisdiction is required." });

        var userId = CurrentUserId();
        if (userId is null) return Unauthorized();

        // Scope is derived from the authenticated user on the server; nothing from the request body is trusted.
        AiCallerIdentity identity;
        try { identity = _identityProvider.Resolve(User, request.MatterId); }
        catch (InvalidOperationException ex)
        {
            _logger.LogWarning(ex, "No AI scope for user {UserId}", userId);
            return StatusCode(StatusCodes.Status403Forbidden, new { message = "Your account has no access scope for the legal assistant." });
        }

        var generateRequest = new LexoraP3GenerateRequest
        {
            Request = new LexoraGuidedDocumentRequest
            {
                RequestId = Guid.NewGuid().ToString("N"),
                DocumentType = request.DocumentType,
                Jurisdiction = request.Jurisdiction,
                Fields = request.Fields,
                RequestedClauseIds = request.RequestedClauseIds ?? new List<string>(),
                SpecialConditions = request.SpecialConditions ?? new List<string>()
            },
            ClauseLanguage = string.IsNullOrWhiteSpace(request.ClauseLanguage) ? "en" : request.ClauseLanguage!,
            // Still ask the AI service to export: when export_allowed ends up
            // true we want docx_file_name already sitting there so the
            // frontend's later Download click is a plain GET, not a second
            // generation. When export isn't allowed, the AI side simply
            // reports docx_generated = false and we pass that through.
            ExportDocx = true
        };

        LexoraP3GenerateResponse result;
        try
        {
            result = await _p3Service.GenerateAsync(generateRequest, identity, HttpContext.RequestAborted);
        }
        catch (DocumentGenerationRejectedException ex)
        {
            return BadRequest(new { message = ex.Message, requestId = ex.RequestId });
        }
        catch (DocumentGenerationNotFoundException ex)
        {
            return NotFound(new { message = ex.Message, requestId = ex.RequestId });
        }
        catch (AiServiceUnavailableException ex)
        {
            return UpstreamUnavailable(ex, "generate document");
        }

        var draft = result.ValidatedDraft.Draft;
        var validation = result.ValidatedDraft.Validation;

        // Log the generation itself (an AI-resourced event) regardless of
        // whether the user goes on to click Download; TemplateKey records
        // what was generated even if the export is never fetched.
        await _history.AddAsync(new GeneratedDocumentRecord
        {
            UserId = userId,
            TemplateKey = request.DocumentType,
            FileName = result.DocxFileName ?? string.Empty,
            GeneratedAt = DateTime.UtcNow
        });
        await _history.SaveChangesAsync();

        _logger.LogInformation(
            "Document draft generated ({DocumentType}/{Jurisdiction}) for user {UserId} (exportAllowed={ExportAllowed}, requiresLawyerReview={RequiresLawyerReview})",
            request.DocumentType, request.Jurisdiction, userId, result.ExportAllowed, result.ValidatedDraft.RequiresLawyerReview);

        return Ok(new GenerateDocumentResponse(
            DraftId: draft.DraftId,
            DocumentType: draft.DocumentType,
            TemplateId: draft.TemplateId,
            TemplateVersion: draft.TemplateVersion,
            Sections: draft.Sections.Select(s => new DraftSectionResponse(s.SectionId, s.Title, s.Text)).ToList(),
            SelectedClauseIds: result.SelectedClauseIds,
            ExportAllowed: result.ExportAllowed,
            RequiresLawyerReview: result.ValidatedDraft.RequiresLawyerReview,
            DocxGenerated: result.DocxGenerated,
            DocxFileName: result.DocxFileName,
            ValidationErrors: validation.Errors,
            ValidationWarnings: validation.Warnings));
    }

    /// <summary>Separate download step: the frontend only calls this after
    /// showing the draft + validation from Generate() and the user confirms,
    /// with fileName taken from GenerateDocumentResponse.DocxFileName.</summary>
    [HttpGet("exports/{fileName}")]
    public async Task<IActionResult> DownloadExport(string fileName)
    {
        if (!TryResolveIdentity(out var identity, out var forbidden))
            return forbidden;

        GeneratedDocument document;
        try
        {
            document = await _p3Service.DownloadExportAsync(fileName, identity, HttpContext.RequestAborted);
        }
        catch (DocumentGenerationNotFoundException ex)
        {
            return NotFound(new { message = ex.Message, requestId = ex.RequestId });
        }
        catch (AiServiceUnavailableException ex)
        {
            return UpstreamUnavailable(ex, "download export");
        }

        return File(document.Content, document.ContentType, document.FileName);
    }

    private bool TryResolveIdentity(
        [System.Diagnostics.CodeAnalysis.NotNullWhen(true)] out AiCallerIdentity? identity,
        [System.Diagnostics.CodeAnalysis.NotNullWhen(false)] out ObjectResult? forbidden)
    {
        try
        {
            identity = _identityProvider.Resolve(User);
            forbidden = null;
            return true;
        }
        catch (InvalidOperationException ex)
        {
            _logger.LogWarning(ex, "No AI scope for user {UserId}", CurrentUserId());
            identity = null;
            forbidden = StatusCode(StatusCodes.Status403Forbidden, new { message = "Your account has no access scope for the legal assistant." });
            return false;
        }
    }

    private ObjectResult UpstreamUnavailable(AiServiceUnavailableException ex, string stage)
    {
        _logger.LogError(ex, "P3 {Stage} failed (ai request_id={RequestId})", stage, ex.RequestId);
        var status = ex.UpstreamStatus is 503 or 504 ? StatusCodes.Status503ServiceUnavailable : StatusCodes.Status502BadGateway;
        return StatusCode(status, new { message = ex.Message, requestId = ex.RequestId });
    }

    private string? CurrentUserId() => User.FindFirstValue(ClaimTypes.NameIdentifier) ?? User.FindFirstValue("sub");
}