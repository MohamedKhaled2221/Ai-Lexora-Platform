using System.Text.Json;
using FluentValidation;
using LegalAssistant.Api.Common;

namespace LegalAssistant.Api.Middleware;

public class ExceptionHandlingMiddleware
{
    private readonly RequestDelegate _next;
    private readonly ILogger<ExceptionHandlingMiddleware> _logger;

    public ExceptionHandlingMiddleware(RequestDelegate next, ILogger<ExceptionHandlingMiddleware> logger)
    {
        _next = next;
        _logger = logger;
    }

    public async Task InvokeAsync(HttpContext context)
    {
        try
        {
            await _next(context);
        }
        catch (ValidationException exception)
        {
            var errors = exception.Errors
                .GroupBy(error => error.PropertyName)
                .ToDictionary(group => group.Key, group => group.Select(error => error.ErrorMessage).ToArray());
            await WriteErrorAsync(context, StatusCodes.Status400BadRequest, "Validation failed", null, errors);
        }
        catch (ArgumentException exception)
        {
            await WriteErrorAsync(context, StatusCodes.Status400BadRequest, "Invalid request", exception.Message);
        }
        catch (KeyNotFoundException exception)
        {
            await WriteErrorAsync(context, StatusCodes.Status404NotFound, "Resource not found", exception.Message);
        }
        catch (Exception exception)
        {
            _logger.LogError(exception, "Unhandled exception for {Method} {Path}. TraceId: {TraceId}",
                context.Request.Method, context.Request.Path, context.TraceIdentifier);
            await WriteErrorAsync(context, StatusCodes.Status500InternalServerError,
                "An unexpected error occurred", "Please try again later.");
        }
    }

    private static async Task WriteErrorAsync(
        HttpContext context,
        int status,
        string title,
        string? detail,
        IReadOnlyDictionary<string, string[]>? errors = null)
    {
        if (context.Response.HasStarted) return;
        context.Response.Clear();
        context.Response.StatusCode = status;
        context.Response.ContentType = "application/json";
        var response = new ApiErrorResponse(status, title, detail, context.TraceIdentifier, errors);
        await context.Response.WriteAsync(JsonSerializer.Serialize(response, new JsonSerializerOptions(JsonSerializerDefaults.Web)));
    }
}
