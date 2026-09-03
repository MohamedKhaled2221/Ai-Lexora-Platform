using System.Security.Claims;
using LegalAssistant.Api.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace LegalAssistant.Api.Search;

[ApiController]
[Authorize]
[Route("api/search")]
public class SearchController : ControllerBase
{
    private readonly ISearchService _searchService;
    private readonly ILexoraDocumentQuestionService _documentQuestionService;

    public SearchController(
        ISearchService searchService,
        ILexoraDocumentQuestionService documentQuestionService)
    {
        _searchService = searchService;
        _documentQuestionService = documentQuestionService;
    }

    [HttpGet]
    public async Task<ActionResult<SearchResponse>> Search([FromQuery] string q, [FromQuery] int page = 1, [FromQuery] int pageSize = 10)
    {
        if (string.IsNullOrWhiteSpace(q))
            return BadRequest(new { message = "Query parameter 'q' is required." });
        if (page < 1) page = 1;
        if (pageSize is < 1 or > 50) pageSize = 10;

        var userId = User.FindFirstValue(ClaimTypes.NameIdentifier) ?? User.FindFirstValue("sub");
        if (userId is null) return Unauthorized();

        var result = await _searchService.SearchAsync(q, userId, page, pageSize, HttpContext.RequestAborted);

        var response = new SearchResponse(
            result.Hits.Select(h => new SearchHitResponse(h.DocumentId, h.FileName, h.Snippet, h.Score)).ToList(),
            result.TotalCount,
            page,
            pageSize);

        return Ok(response);
    }

    [HttpPost("ask")]
    public async Task<ActionResult<AskDocumentsResponse>> Ask(
        AskDocumentsRequest request)
    {
        if (string.IsNullOrWhiteSpace(request.Question))
        {
            return BadRequest(
                new { message = "Question is required." });
        }

        if (request.Question.Length > 4000)
        {
            return BadRequest(
                new
                {
                    message =
                        "Question must be 4000 characters or fewer."
                });
        }

        var userId =
            User.FindFirstValue(
                ClaimTypes.NameIdentifier)
            ?? User.FindFirstValue("sub");

        if (userId is null)
        {
            return Unauthorized();
        }

        var result =
            await _documentQuestionService.AskAsync(
                request.Question,
                userId,
                HttpContext.RequestAborted);

        return Ok(
            new AskDocumentsResponse(
                result.QueryId,
                result.Answer,
                result.Confidence,
                result.Citations
                    .Select(
                        citation =>
                            new SearchCitationResponse(
                                citation.EvidenceId,
                                citation.DocumentId,
                                citation.FileName,
                                citation.ChunkId,
                                citation.Page,
                                citation.Section))
                    .ToList()));
    }
}