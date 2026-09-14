using System.Net;
using System.Text;
using System.Text.Json;
using LegalAssistant.Api.Data;
using LegalAssistant.Api.Repositories;
using LegalAssistant.Api.Services;
using Microsoft.Extensions.Logging.Abstractions;

namespace LegalAssistant.Api.Tests.Services;

public sealed class LexoraDocumentQuestionServiceTests
{
    [Fact]
    public async Task AskAsync_SendsAllAuthorizedDocumentsToRag()
    {
        var repository =
            new FakeDocumentRepository(
                new[]
                {
                    new Document
                    {
                        Id = 2006,
                        OwnerId = "user-a",
                        FileName = "authorized-a.pdf",
                        FilePath = "/test/authorized-a.pdf"
                    },
                    new Document
                    {
                        Id = 3001,
                        OwnerId = "user-a",
                        FileName = "authorized-b.pdf",
                        FilePath = "/test/authorized-b.pdf"
                    }
                });

        var handler =
            new RecordingHttpMessageHandler(
                HttpStatusCode.OK,
                """
                {
                  "query_id": "q_test",
                  "answer": "Grounded test answer.",
                  "confidence": 0.95,
                  "citations": [
                    {
                      "evidence_id": "E1",
                      "document_id": "backend-doc-2006",
                      "chunk_id": "chunk_009",
                      "page": 7,
                      "section": "test-section"
                    }
                  ]
                }
                """);

        using var httpClient =
            new HttpClient(handler)
            {
                BaseAddress =
                    new Uri("http://localhost:8000")
            };

        var service =
            new LexoraDocumentQuestionService(
                httpClient,
                repository,
                NullLogger<
                    LexoraDocumentQuestionService
                >.Instance);

        var result =
            await service.AskAsync(
                "  Test question  ",
                "user-a");

        Assert.Equal(
            "user-a",
            repository.LastRequestedOwnerId);

        Assert.Equal(
            1,
            handler.CallCount);

        Assert.NotNull(
            handler.LastRequestBody);

        using var requestJson =
            JsonDocument.Parse(
                handler.LastRequestBody!);

        Assert.Equal(
            "Test question",
            requestJson.RootElement
                .GetProperty("question")
                .GetString());

        var documentIds =
            requestJson.RootElement
                .GetProperty("filters")
                .GetProperty("document_ids")
                .EnumerateArray()
                .Select(element =>
                    element.GetString())
                .OrderBy(value => value)
                .ToArray();

        Assert.Equal(
            new[]
            {
                "backend-doc-2006",
                "backend-doc-3001"
            },
            documentIds);

        var citation =
            Assert.Single(result.Citations);

        Assert.Equal(
            2006,
            citation.DocumentId);

        Assert.Equal(
            "authorized-a.pdf",
            citation.FileName);

        Assert.Equal(
            "E1",
            citation.EvidenceId);

        Assert.Equal(
            "chunk_009",
            citation.ChunkId);
    }

    [Fact]
    public async Task AskAsync_WithNoOwnedDocuments_DoesNotCallRag()
    {
        var repository =
            new FakeDocumentRepository(
                Array.Empty<Document>());

        var handler =
            new RecordingHttpMessageHandler(
                HttpStatusCode.OK,
                """
                {
                  "query_id": "unused",
                  "answer": "unused",
                  "confidence": 1.0,
                  "citations": []
                }
                """);

        using var httpClient =
            new HttpClient(handler)
            {
                BaseAddress =
                    new Uri("http://localhost:8000")
            };

        var service =
            new LexoraDocumentQuestionService(
                httpClient,
                repository,
                NullLogger<
                    LexoraDocumentQuestionService
                >.Instance);

        var exception =
            await Assert.ThrowsAsync<
                KeyNotFoundException>(
                () =>
                    service.AskAsync(
                        "Test question",
                        "user-a"));

        Assert.Equal(
            "No documents are available for question answering.",
            exception.Message);

        Assert.Equal(
            0,
            handler.CallCount);
    }

    [Fact]
    public async Task AskAsync_RejectsCitationOutsideAuthorizedDocuments()
    {
        var repository =
            new FakeDocumentRepository(
                new[]
                {
                    new Document
                    {
                        Id = 2006,
                        OwnerId = "user-a",
                        FileName = "authorized.pdf",
                        FilePath = "/test/authorized.pdf"
                    }
                });

        var handler =
            new RecordingHttpMessageHandler(
                HttpStatusCode.OK,
                """
                {
                  "query_id": "q_test",
                  "answer": "Grounded test answer.",
                  "confidence": 0.8,
                  "citations": [
                    {
                      "evidence_id": "E1",
                      "document_id": "backend-doc-9999",
                      "chunk_id": "chunk_001",
                      "page": 1,
                      "section": null
                    }
                  ]
                }
                """);

        using var httpClient =
            new HttpClient(handler)
            {
                BaseAddress =
                    new Uri("http://localhost:8000")
            };

        var service =
            new LexoraDocumentQuestionService(
                httpClient,
                repository,
                NullLogger<
                    LexoraDocumentQuestionService
                >.Instance);

        var exception =
            await Assert.ThrowsAsync<
                AiQuestionAnsweringException>(
                () =>
                    service.AskAsync(
                        "Test question",
                        "user-a"));

        Assert.Equal(
            502,
            exception.ResponseStatusCode);

        Assert.Equal(
            "The AI service returned an invalid citation.",
            exception.Message);
    }

    private sealed class RecordingHttpMessageHandler
        : HttpMessageHandler
    {
        private readonly HttpStatusCode _statusCode;
        private readonly string _responseBody;

        public RecordingHttpMessageHandler(
            HttpStatusCode statusCode,
            string responseBody)
        {
            _statusCode = statusCode;
            _responseBody = responseBody;
        }

        public int CallCount { get; private set; }

        public string? LastRequestBody
        {
            get;
            private set;
        }

        protected override async Task<
            HttpResponseMessage> SendAsync(
                HttpRequestMessage request,
                CancellationToken cancellationToken)
        {
            CallCount++;

            if (request.Content is not null)
            {
                LastRequestBody =
                    await request.Content
                        .ReadAsStringAsync(
                            cancellationToken);
            }

            return new HttpResponseMessage(
                _statusCode)
            {
                Content =
                    new StringContent(
                        _responseBody,
                        Encoding.UTF8,
                        "application/json")
            };
        }
    }

    private sealed class FakeDocumentRepository
        : IDocumentRepository
    {
        private readonly IReadOnlyCollection<Document>
            _ownedDocuments;

        public FakeDocumentRepository(
            IReadOnlyCollection<Document>
                ownedDocuments)
        {
            _ownedDocuments =
                ownedDocuments;
        }

        public string? LastRequestedOwnerId
        {
            get;
            private set;
        }

        public Task<
            IReadOnlyCollection<Document>>
            GetAllOwnedAsync(
                string ownerId,
                CancellationToken cancellationToken =
                    default)
        {
            LastRequestedOwnerId =
                ownerId;

            return Task.FromResult(
                _ownedDocuments);
        }

        public Task<Document?> GetOwnedAsync(
            int id,
            string ownerId)
        {
            throw new NotSupportedException();
        }

        public Task<Document?> GetByIdAsync(
            int id)
        {
            throw new NotSupportedException();
        }

        public Task<PagedResult<Document>>
            GetPagedOwnedAsync(
                string ownerId,
                int page,
                int pageSize,
                string? search,
                string? type)
        {
            throw new NotSupportedException();
        }

        public Task<
            IReadOnlyCollection<Document>>
            GetOwnedByIdsAsync(
                IReadOnlyCollection<int> ids,
                string ownerId,
                CancellationToken cancellationToken =
                    default)
        {
            throw new NotSupportedException();
        }

        public Task AddAsync(
            Document document)
        {
            throw new NotSupportedException();
        }

        public Task SaveChangesAsync()
        {
            throw new NotSupportedException();
        }

        public void Remove(
            Document document)
        {
            throw new NotSupportedException();
        }
    }
}
