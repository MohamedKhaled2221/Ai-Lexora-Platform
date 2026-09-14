using LegalAssistant.Api.Data;
using Microsoft.EntityFrameworkCore;

namespace LegalAssistant.Api.Services;

public record DependencyHealth(string Name, bool Healthy, string? Detail = null);

public record SystemHealthReport(bool Healthy, IReadOnlyList<DependencyHealth> Dependencies);

/// <summary>
/// Real readiness check used by GET /health. Unlike a "the process is alive" ping,
/// this actually verifies the database and the three external AI services
/// (AiService:8000, M1Service:8001, M5Service:8002) are reachable, so the
/// frontend can trust an "System is ready" state instead of just "the .NET
/// process didn't crash".
///
/// ASSUMPTION: each Python AI service exposes a lightweight GET /health (or
/// equivalent) endpoint. If the real path differs, update
/// "HealthCheck:*:Path" in appsettings.json — no code change needed.
/// </summary>
public class SystemHealthCheckService
{
    private readonly IHttpClientFactory _httpClientFactory;
    private readonly AppDbContext _dbContext;
    private readonly IConfiguration _configuration;
    private readonly ILogger<SystemHealthCheckService> _logger;

    public SystemHealthCheckService(
        IHttpClientFactory httpClientFactory,
        AppDbContext dbContext,
        IConfiguration configuration,
        ILogger<SystemHealthCheckService> logger)
    {
        _httpClientFactory = httpClientFactory;
        _dbContext = dbContext;
        _configuration = configuration;
        _logger = logger;
    }

    public async Task<SystemHealthReport> CheckAsync(CancellationToken cancellationToken)
    {
        var dependencies = new List<DependencyHealth>();

        dependencies.Add(await CheckDatabaseAsync(cancellationToken));
        dependencies.Add(await CheckServiceAsync("AiService", "AiServiceHealth", cancellationToken));
        dependencies.Add(await CheckServiceAsync("M1Service", "M1ServiceHealth", cancellationToken));
        dependencies.Add(await CheckServiceAsync("M5Service", "M5ServiceHealth", cancellationToken));

        var allHealthy = dependencies.All(d => d.Healthy);
        return new SystemHealthReport(allHealthy, dependencies);
    }

    private async Task<DependencyHealth> CheckDatabaseAsync(CancellationToken cancellationToken)
    {
        try
        {
            var canConnect = await _dbContext.Database.CanConnectAsync(cancellationToken);
            return new DependencyHealth("database", canConnect, canConnect ? null : "CanConnectAsync returned false");
        }
        catch (Exception exception)
        {
            _logger.LogWarning(exception, "Health check: database connection failed");
            return new DependencyHealth("database", false, exception.Message);
        }
    }

    private async Task<DependencyHealth> CheckServiceAsync(string configSection, string httpClientName, CancellationToken cancellationToken)
    {
        var path = _configuration[$"HealthCheck:{configSection}:Path"] ?? "/health";
        try
        {
            var client = _httpClientFactory.CreateClient(httpClientName);
            using var response = await client.GetAsync(path, cancellationToken);
            var healthy = response.IsSuccessStatusCode;
            return new DependencyHealth(
                configSection,
                healthy,
                healthy ? null : $"{(int)response.StatusCode} {response.ReasonPhrase} from {client.BaseAddress}{path}");
        }
        catch (Exception exception)
        {
            _logger.LogWarning(exception, "Health check: {Service} unreachable", configSection);
            return new DependencyHealth(configSection, false, exception.Message);
        }
    }
}