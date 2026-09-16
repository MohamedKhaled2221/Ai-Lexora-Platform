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