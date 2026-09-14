using System.Security.Claims;
using LegalAssistant.Api.Data;
using LegalAssistant.Api.Repositories;
using LegalAssistant.Api.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace LegalAssistant.Api.Generator;

[ApiController]
[Authorize]
[Route("api/document-generator")]
public class DocumentGeneratorController : ControllerBase
{
    private readonly IDocumentGenerationService _generationService;
    private readonly IGeneratedDocumentRepository _history;
    private readonly ILogger<DocumentGeneratorController> _logger;

    public DocumentGeneratorController(
        IDocumentGenerationService generationService,
        IGeneratedDocumentRepository history,
        ILogger<DocumentGeneratorController> logger)
    {
        _generationService = generationService;
        _history = history;
        _logger = logger;
    }

    [HttpGet("templates")]
    public ActionResult<IReadOnlyCollection<TemplateInfoResponse>> GetTemplates()
    {
        var templates = _generationService.GetAvailableTemplates()
            .Select(t => new TemplateInfoResponse(t.Key, t.Name, t.Description, t.RequiredFields))
            .ToList();
        return Ok(templates);
    }

    [HttpPost("generate")]
    public async Task<IActionResult> Generate(GenerateDocumentRequest request)
    {
        if (string.IsNullOrWhiteSpace(request.TemplateKey))
            return BadRequest(new { message = "templateKey is required." });

        var userId = User.FindFirstValue(ClaimTypes.NameIdentifier) ?? User.FindFirstValue("sub");
        if (userId is null) return Unauthorized();

        GeneratedDocument document;
        try
        {
            document = await _generationService.GenerateAsync(
                request.TemplateKey,
                request.Fields ?? new Dictionary<string, string>(),
                HttpContext.RequestAborted);
        }
        catch (UnknownTemplateException ex)
        {
            return BadRequest(new { message = ex.Message });
        }
        catch (MissingTemplateFieldsException ex)
        {
            return BadRequest(new { message = ex.Message, missingFields = ex.MissingFields });
        }

        await _history.AddAsync(new GeneratedDocumentRecord
        {
            UserId = userId,
            TemplateKey = request.TemplateKey,
            FileName = document.FileName,
            GeneratedAt = DateTime.UtcNow
        });
        await _history.SaveChangesAsync();

        _logger.LogInformation("Document generated from template {TemplateKey} for user {UserId}", request.TemplateKey, userId);
        return File(document.Content, document.ContentType, document.FileName);
    }
}