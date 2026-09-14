using LegalAssistant.Api.Data;
using Microsoft.EntityFrameworkCore;

namespace LegalAssistant.Api.Repositories;

public class AnalysisRepository : IAnalysisRepository
{
    private readonly AppDbContext _db;

    public AnalysisRepository(AppDbContext db) => _db = db;

    public Task<ContractAnalysis?> GetByDocumentIdAsync(int documentId) =>
        _db.ContractAnalyses.Include(a => a.RiskyClauses).SingleOrDefaultAsync(a => a.DocumentId == documentId);

    public Task<bool> DocumentExistsAsync(int documentId) => _db.Documents.AnyAsync(d => d.Id == documentId);

    public Task<List<int>> GetDocumentIdsByStatusAsync(string status) =>
        _db.ContractAnalyses.Where(a => a.Status == status).Select(a => a.DocumentId).ToListAsync();

    public void Add(ContractAnalysis analysis) => _db.ContractAnalyses.Add(analysis);

    public Task SaveChangesAsync() => _db.SaveChangesAsync();
}