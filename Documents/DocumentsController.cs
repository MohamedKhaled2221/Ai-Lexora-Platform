using System.Security.Claims;
using LegalAssistant.Api.Data;
using LegalAssistant.Api.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace LegalAssistant.Api.Documents;

[ApiController]
[Authorize]
[Route("api/documents")]
public class DocumentsController : ControllerBase
{
    private readonly IDocumentService _documents;
    private readonly ILogger<DocumentsController> _logger;

    public DocumentsController(IDocumentService documents, ILogger<DocumentsController> logger)
    {
        _documents = documents;
        _logger = logger;
    }

    [HttpPost]
    [RequestSizeLimit(20 * 1024 * 1024)]
    [Consumes("multipart/form-data")]
    public async Task<ActionResult<DocumentResponse>> Upload( IFormFile? file, [FromForm] string? type)
    {
        if (file is null) return BadRequest(new { message = "A file is required." });
        var userId = GetCurrentUserId();
        if (userId is null) return Unauthorized();

        try
        {
            var stored = await _documents.UploadAsync(file, type, userId);
            _logger.LogInformation("Document {DocumentId} uploaded by user {UserId}", stored.Document.Id, userId);
            return CreatedAtAction(nameof(Download), new { id = stored.Document.Id }, ToResponse(stored.Document, stored.SizeBytes));
        }
        catch (ArgumentException exception)
        {
            return BadRequest(new { message = exception.Message });
        }
    }

    [HttpPost("batch")]
    [RequestSizeLimit(100 * 1024 * 1024)]
    [Consumes("multipart/form-data")]
    public async Task<ActionResult<IReadOnlyCollection<DocumentResponse>>> UploadBatch([FromForm] IFormFileCollection? files, [FromForm] string? type)
    {
        if (files is null) return BadRequest(new { message = "At least one file is required." });
        var userId = GetCurrentUserId();
        if (userId is null) return Unauthorized();

        try
        {
            var stored = await _documents.UploadBatchAsync(files, type, userId);
            _logger.LogInformation("User {UserId} uploaded {FileCount} documents", userId, stored.Count);
            return Ok(stored.Select(item => ToResponse(item.Document, item.SizeBytes)).ToList());
        }
        catch (ArgumentException exception)
        {
            return BadRequest(new { message = exception.Message });
        }
    }

    [HttpGet]
    public async Task<ActionResult<PagedDocumentsResponse>> List([FromQuery] int page = 1, [FromQuery] int pageSize = 20, [FromQuery] string? search = null, [FromQuery] string? type = null)
    {
        if (page < 1 || pageSize is < 1 or > 100)
            return BadRequest(new { message = "Page must be at least 1 and page size must be between 1 and 100." });
        var userId = GetCurrentUserId();
        if (userId is null) return Unauthorized();

        var result = await _documents.GetPagedAsync(userId, page, pageSize, search, type);
        return Ok(new PagedDocumentsResponse(
            result.Items.Select(document => ToResponse(document, _documents.GetFileSize(document))).ToList(),
            page, pageSize, result.TotalCount, (int)Math.Ceiling(result.TotalCount / (double)pageSize)));
    }

    [HttpGet("{id:int}")]
    public async Task<ActionResult<DocumentResponse>> Get(int id)
    {
        var document = await FindOwnedDocument(id);
        return document is null ? NotFound(new { message = "Document not found." }) : Ok(ToResponse(document, _documents.GetFileSize(document)));
    }

    [HttpPut("{id:int}")]
    public async Task<ActionResult<DocumentResponse>> Update(int id, UpdateDocumentRequest request)
    {
        var userId = GetCurrentUserId();
        if (userId is null) return Unauthorized();
        try
        {
            var document = await _documents.UpdateAsync(id, userId, request.FileName, request.Type);
            if (document is null) return NotFound(new { message = "Document not found." });
            return Ok(ToResponse(document, _documents.GetFileSize(document)));
        }
        catch (ArgumentException exception)
        {
            return BadRequest(new { message = exception.Message });
        }
    }

    [HttpGet("{id:int}/download")]
    public async Task<IActionResult> Download(int id)
    {
        var document = await FindOwnedDocument(id);
        if (document is null) return NotFound();
        var path = _documents.GetFilePath(document);
        if (!System.IO.File.Exists(path)) return NotFound(new { message = "The stored file no longer exists." });
        return PhysicalFile(path, "application/octet-stream", document.FileName, enableRangeProcessing: true);
    }

    [HttpDelete("{id:int}")]
    public async Task<IActionResult> Delete(int id)
    {
        var userId = GetCurrentUserId();
        if (userId is null) return Unauthorized();
        return await _documents.DeleteAsync(id, userId) ? NoContent() : NotFound();
    }

    private async Task<Document?> FindOwnedDocument(int id)
    {
        var userId = GetCurrentUserId();
        return userId is null ? null : await _documents.GetOwnedAsync(id, userId);
    }

    private string? GetCurrentUserId() => User.FindFirstValue(ClaimTypes.NameIdentifier) ?? User.FindFirstValue("sub");

    private DocumentResponse ToResponse(Document document, long sizeBytes) => new(
        document.Id, document.FileName, document.Type, sizeBytes, document.UploadedAt,
        Url.ActionLink(nameof(Download), values: new { id = document.Id })!);
}
