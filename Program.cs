using System.Text;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.AspNetCore.Identity;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using Microsoft.IdentityModel.Tokens;
using Microsoft.OpenApi.Models;
using FluentValidation;
using FluentValidation.AspNetCore;
using Serilog;
using LegalAssistant.Api.Auth;
using LegalAssistant.Api.Data;
using LegalAssistant.Api.Email;
using LegalAssistant.Api.Repositories;
using LegalAssistant.Api.Services;
using LegalAssistant.Api.Common;
using LegalAssistant.Api.Middleware;

var builder = WebApplication.CreateBuilder(args);

// ---------- Logging (Serilog) ----------
Log.Logger = new LoggerConfiguration()
    .ReadFrom.Configuration(builder.Configuration)
    .Enrich.FromLogContext()
    .WriteTo.Console()
    .CreateLogger();
builder.Host.UseSerilog();

// ---------- Database (SQL Server via EF Core) ----------
builder.Services.AddDbContext<AppDbContext>(options =>
    options.UseSqlServer(builder.Configuration.GetConnectionString("DefaultConnection")));

// ---------- ASP.NET Identity (users + roles), backed by the same DbContext ----------
builder.Services.AddIdentity<ApplicationUser, IdentityRole>(options =>
{
    // reasonable defaults for a first version; tighten later if needed
    options.Password.RequiredLength = 8;
    options.Password.RequireNonAlphanumeric = false;
    options.User.RequireUniqueEmail = true;
})
    .AddEntityFrameworkStores<AppDbContext>()
    .AddDefaultTokenProviders();

// ---------- JWT token generator used by AuthController ----------
builder.Services.AddScoped<JwtTokenService>();
builder.Services.AddScoped<RefreshTokenService>();
builder.Services.AddScoped<IEmailService, SmtpEmailService>();
builder.Services.AddScoped<IDocumentRepository, DocumentRepository>();
builder.Services.AddScoped<IAnalysisRepository, AnalysisRepository>();
builder.Services.AddScoped<IDocumentService, DocumentService>();
// Text extraction: one strategy registered per supported file format.
// Add a new ITextExtractionStrategy implementation (Word, OCR-for-images,
// etc.) and register it here to support more formats — nothing else changes.
builder.Services.AddScoped<ITextExtractionStrategy, PlainTextExtractionStrategy>();
builder.Services.AddScoped<ITextExtractionStrategy, PdfTextExtractionStrategy>();
builder.Services.AddScoped<IDocumentTextExtractor, CompositeDocumentTextExtractor>();
// Contract Analyzer — now backed by the AI-Lexora M1 -> M5 -> M6 pipeline
// (three separate local services). Swapping back to the rule-based
// placeholder for local dev without those services running is a one-line
// change below.
builder.Services.AddHttpClient("M1Service", (sp, client) =>
{
    var config = sp.GetRequiredService<IConfiguration>();
    client.BaseAddress = new Uri(config["M1Service:BaseUrl"] ?? "http://localhost:8001");
    client.Timeout = TimeSpan.FromSeconds(config.GetValue<int?>("M1Service:TimeoutSeconds") ?? 120);
});
builder.Services.AddHttpClient("M5Service", (sp, client) =>
{
    var config = sp.GetRequiredService<IConfiguration>();
    client.BaseAddress = new Uri(config["M5Service:BaseUrl"] ?? "http://localhost:8002");
    client.Timeout = TimeSpan.FromSeconds(config.GetValue<int?>("M5Service:TimeoutSeconds") ?? 60);
});
builder.Services.AddHttpClient("M6Service", (sp, client) =>
{
    // M6's risk endpoint lives inside the main AI-Lexora app — same base URL as the chatbot.
    var config = sp.GetRequiredService<IConfiguration>();
    var baseUrl = config["AiService:BaseUrl"] ?? "http://localhost:8000";
    var timeoutSeconds = config.GetValue<int?>("AiService:TimeoutSeconds") ?? 60;
    client.BaseAddress = new Uri(baseUrl);
    client.Timeout = TimeSpan.FromSeconds(timeoutSeconds);
});
builder.Services.AddScoped<IContractAnalysisService, LexoraContractAnalysisService>();
// To fall back to the offline rule-based placeholder instead (e.g. the M1/
// M5/M6 services aren't running locally), comment the line above and
// uncomment this one:
// builder.Services.AddScoped<IContractAnalysisService, RuleBasedContractAnalysisService>();
// Background analysis pipeline: the controller enqueues a document ID and
// returns immediately; AnalysisBackgroundService dequeues and does the
// actual work outside the HTTP request lifecycle. IAnalysisWorkQueue must be
// a singleton — it's shared between (scoped) controller instances and the
// singleton hosted service.
builder.Services.AddSingleton<IAnalysisWorkQueue, AnalysisWorkQueue>();
builder.Services.AddHostedService<AnalysisBackgroundService>();

// Search — now backed by the AI-Lexora Python RAG service's ranked search
// endpoint (M2 embedding -> M3 Qdrant vector retrieval, no LLM call).
// SearchController doesn't change. To fall back to the offline placeholder
// (e.g. the AI service isn't running locally), comment the block below and
// uncomment: builder.Services.AddScoped<ISearchService, KeywordSearchService>();
builder.Services.AddHttpClient<LexoraRagSearchService>(
    (sp, client) =>
    {
        var config = sp.GetRequiredService<IConfiguration>();

        var baseUrl =
            config["AiService:BaseUrl"]
            ?? "http://localhost:8000";

        var timeoutSeconds =
            config.GetValue<int?>("AiService:SearchTimeoutSeconds")
            ?? config.GetValue<int?>("AiService:TimeoutSeconds")
            ?? 60;

        client.BaseAddress = new Uri(baseUrl);
        client.Timeout = TimeSpan.FromSeconds(timeoutSeconds);
    });

builder.Services.AddScoped<ISearchService>(
    sp => sp.GetRequiredService<LexoraRagSearchService>());

// Document Generator (placeholder: one built-in template, token substitution).
builder.Services.AddScoped<IDocumentGenerationService, TemplateDocumentGenerationService>();
builder.Services.AddScoped<IGeneratedDocumentRepository, GeneratedDocumentRepository>();

// Chatbot — now backed by the AI-Lexora Python RAG service (as is Search,
// above). Swapping back to the placeholder for local dev without the AI
// service running is a one-line change below.
builder.Services.AddScoped<IChatRepository, ChatRepository>();
// Package 1 document ingestion:
// Backend document -> main AI API -> M1 -> M2 -> Qdrant.
builder.Services.AddHttpClient<LexoraDocumentIndexingService>(
    (sp, client) =>
    {
        var config =
            sp.GetRequiredService<IConfiguration>();

        var baseUrl =
            config["AiService:BaseUrl"]
            ?? "http://localhost:8000";

        var timeoutSeconds =
            config.GetValue<int?>(
                "AiService:IngestionTimeoutSeconds")
            ?? 360;

        client.BaseAddress =
            new Uri(baseUrl);

        client.Timeout =
            TimeSpan.FromSeconds(timeoutSeconds);
    });

builder.Services.AddScoped<ILexoraDocumentIndexingService>(
    sp => sp.GetRequiredService<LexoraDocumentIndexingService>());
builder.Services.AddHttpClient<LexoraRagChatbotService>((sp, client) =>
{
    var config = sp.GetRequiredService<IConfiguration>();
    var baseUrl = config["AiService:BaseUrl"] ?? "http://localhost:8000";
    var timeoutSeconds = config.GetValue<int?>("AiService:TimeoutSeconds") ?? 60;
    client.BaseAddress = new Uri(baseUrl);
    client.Timeout = TimeSpan.FromSeconds(timeoutSeconds);
});
builder.Services.AddHttpClient<LexoraDocumentQuestionService>(
    (sp, client) =>
    {
        var config =
            sp.GetRequiredService<IConfiguration>();

        var baseUrl =
            config["AiService:BaseUrl"]
            ?? "http://localhost:8000";

        var timeoutSeconds =
            config.GetValue<int?>(
                "AiService:QuestionTimeoutSeconds")
            ?? config.GetValue<int?>(
                "AiService:TimeoutSeconds")
            ?? 180;

        client.BaseAddress =
            new Uri(baseUrl);

        client.Timeout =
            TimeSpan.FromSeconds(timeoutSeconds);
    });

builder.Services.AddScoped<ILexoraDocumentQuestionService>(
    sp => sp.GetRequiredService<LexoraDocumentQuestionService>());
builder.Services.AddScoped<IChatbotService>(sp => sp.GetRequiredService<LexoraRagChatbotService>());
// To fall back to the offline placeholder instead (e.g. the AI service isn't
// running locally), comment the two lines above and uncomment this one:
// builder.Services.AddScoped<IChatbotService, PlaceholderChatbotService>();

// ---------- JWT Authentication ----------
var jwtKey = builder.Configuration["Jwt:Key"] ?? "dev-only-placeholder-key-change-me-1234567890";
builder.Services.AddAuthentication(options =>
{
    // AddIdentity() above registers ASP.NET Identity's cookie scheme and
    // sets it as the default Authenticate/Challenge scheme. Without
    // overriding those explicitly here, [Authorize] falls back to the
    // cookie scheme — which redirects unauthenticated requests to
    // /Account/Login instead of validating the Bearer token and
    // returning a plain 401. Setting all three explicitly forces JWT
    // Bearer to be used everywhere.
    options.DefaultAuthenticateScheme = JwtBearerDefaults.AuthenticationScheme;
    options.DefaultChallengeScheme = JwtBearerDefaults.AuthenticationScheme;
    options.DefaultScheme = JwtBearerDefaults.AuthenticationScheme;
})
    .AddJwtBearer(options =>
    {
        options.TokenValidationParameters = new TokenValidationParameters
        {
            ValidateIssuer = true,
            ValidateAudience = true,
            ValidateLifetime = true,
            ValidateIssuerSigningKey = true,
            ValidIssuer = builder.Configuration["Jwt:Issuer"],
            ValidAudience = builder.Configuration["Jwt:Audience"],
            IssuerSigningKey = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(jwtKey))
        };
    });
builder.Services.AddAuthorization();

// ---------- Controllers / Swagger ----------
builder.Services.AddControllers();
builder.Services.AddFluentValidationAutoValidation();
builder.Services.AddValidatorsFromAssemblyContaining<Program>();
builder.Services.Configure<ApiBehaviorOptions>(options =>
{
    options.InvalidModelStateResponseFactory = context =>
    {
        var errors = context.ModelState
            .Where(entry => entry.Value?.Errors.Count > 0)
            .ToDictionary(
                entry => entry.Key,
                entry => entry.Value!.Errors.Select(error => string.IsNullOrWhiteSpace(error.ErrorMessage) ? "The value is invalid." : error.ErrorMessage).ToArray());
        return new BadRequestObjectResult(new ApiErrorResponse(
            StatusCodes.Status400BadRequest,
            "Validation failed",
            null,
            context.HttpContext.TraceIdentifier,
            errors));
    };
});
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen(options =>
{
    options.AddSecurityDefinition("Bearer", new OpenApiSecurityScheme
    {
        Name = "Authorization",
        Type = SecuritySchemeType.Http,
        Scheme = "Bearer",
        BearerFormat = "JWT",
        In = ParameterLocation.Header,
        Description = "Paste the access token only — no need to type 'Bearer ' first, Swagger adds it automatically."
    });
    options.AddSecurityRequirement(new OpenApiSecurityRequirement
    {
        {
            new OpenApiSecurityScheme
            {
                Reference = new OpenApiReference { Type = ReferenceType.SecurityScheme, Id = "Bearer" }
            },
            Array.Empty<string>()
        }
    });
});

// ---------- CORS ----------
// Cors:AllowedOrigins in appsettings.json is the real, deployed frontend
// origin(s). AllowAnyOrigin is only tolerated in Development when that list
// is empty (local dev convenience); any other environment MUST set real
// origins, or the app refuses to start rather than silently shipping an
// open CORS policy to production.
var allowedOrigins = builder.Configuration.GetSection("Cors:AllowedOrigins").Get<string[]>() ?? Array.Empty<string>();
if (allowedOrigins.Length == 0 && !builder.Environment.IsDevelopment())
{
    throw new InvalidOperationException(
        "Cors:AllowedOrigins is empty. Set it to the real frontend origin(s) in appsettings.json " +
        "(or via environment/secret configuration) before running outside Development.");
}

builder.Services.AddCors(options =>
{
    options.AddDefaultPolicy(policy =>
    {
        if (allowedOrigins.Length > 0)
        {
            policy.WithOrigins(allowedOrigins).AllowAnyHeader().AllowAnyMethod().AllowCredentials();
        }
        else
        {
            // Development-only fallback - no origins configured.
            policy.AllowAnyOrigin().AllowAnyHeader().AllowAnyMethod();
        }
    });
});

// ---------- Health check dependencies ----------
// Short-timeout clients dedicated to /health probes, separate from the
// long-timeout typed clients used for actual AI calls above, so a slow/dead
// AI service doesn't make /health itself hang.
builder.Services.AddHttpClient("AiServiceHealth", (sp, client) =>
{
    var config = sp.GetRequiredService<IConfiguration>();
    client.BaseAddress = new Uri(config["AiService:BaseUrl"] ?? "http://localhost:8000");
    client.Timeout = TimeSpan.FromSeconds(config.GetValue<int?>("HealthCheck:AiService:TimeoutSeconds") ?? 5);
});
builder.Services.AddHttpClient("M1ServiceHealth", (sp, client) =>
{
    var config = sp.GetRequiredService<IConfiguration>();
    client.BaseAddress = new Uri(config["M1Service:BaseUrl"] ?? "http://localhost:8001");
    client.Timeout = TimeSpan.FromSeconds(config.GetValue<int?>("HealthCheck:M1Service:TimeoutSeconds") ?? 5);
});
builder.Services.AddHttpClient("M5ServiceHealth", (sp, client) =>
{
    var config = sp.GetRequiredService<IConfiguration>();
    client.BaseAddress = new Uri(config["M5Service:BaseUrl"] ?? "http://localhost:8002");
    client.Timeout = TimeSpan.FromSeconds(config.GetValue<int?>("HealthCheck:M5Service:TimeoutSeconds") ?? 5);
});
builder.Services.AddScoped<SystemHealthCheckService>();

var app = builder.Build();

app.UseMiddleware<ExceptionHandlingMiddleware>();

if (app.Environment.IsDevelopment())
{
    app.UseSwagger();
    app.UseSwaggerUI();
    app.MapGet("/", () => Results.Redirect("/swagger"));
}

app.UseCors();
app.UseAuthentication();
app.UseAuthorization();

// ---------- Health check ----------
// Real readiness probe: checks the database AND the 3 external AI services
// (AiService/8000, M1Service/8001, M5Service/8002), not just "the .NET
// process is alive". Returns 200 only if every dependency is reachable, so
// the frontend can trust "System is ready" instead of just backend uptime.
app.MapGet("/health", async (SystemHealthCheckService healthCheckService, CancellationToken cancellationToken) =>
{
    var report = await healthCheckService.CheckAsync(cancellationToken);
    var payload = new
    {
        status = report.Healthy ? "ok" : "degraded",
        service = "dotnet-backend",
        dependencies = report.Dependencies.Select(d => new { d.Name, healthy = d.Healthy, detail = d.Detail })
    };
    return report.Healthy ? Results.Ok(payload) : Results.Json(payload, statusCode: StatusCodes.Status503ServiceUnavailable);
});

app.MapControllers();

// ---------- Seed roles + default Admin account (local/dev convenience) ----------
using (var scope = app.Services.CreateScope())
{
    var logger = scope.ServiceProvider.GetRequiredService<ILogger<Program>>();
    await DbSeeder.SeedAsync(scope.ServiceProvider, app.Configuration, logger);
}

app.Run();