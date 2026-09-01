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

    public SearchController(ISearchService searchService) => _searchService = searchService;

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
}