namespace LegalAssistant.Api.Services;

public interface ILexoraDocumentQuestionService
{
    Task<DocumentQuestionResult> AskAsync(
        string question,
        IReadOnlyCollection<int> documentIds,
        string userId,
        CancellationToken cancellationToken = default);
}

public sealed record DocumentQuestionResult(
    string QueryId,
    string Answer,
    double Confidence,
    IReadOnlyCollection<DocumentQuestionCitation> Citations);

public sealed record DocumentQuestionCitation(
    string EvidenceId,
    int DocumentId,
    string FileName,
    string ChunkId,
    int? Page,
    string? Section);
