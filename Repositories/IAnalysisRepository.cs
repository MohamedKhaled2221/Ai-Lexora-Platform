using LegalAssistant.Api.Data;

namespace LegalAssistant.Api.Repositories;

public interface IAnalysisRepository
{
    Task<ContractAnalysis?> GetByDocumentIdAsync(int documentId);
    Task<bool> DocumentExistsAsync(int documentId);
    Task<List<int>> GetDocumentIdsByStatusAsync(string status);
    void Add(ContractAnalysis analysis);
    Task SaveChangesAsync();
}