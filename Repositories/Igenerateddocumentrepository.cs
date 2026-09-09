using LegalAssistant.Api.Data;

namespace LegalAssistant.Api.Repositories;

public interface IGeneratedDocumentRepository
{
    Task AddAsync(GeneratedDocumentRecord record);
    Task SaveChangesAsync();
}