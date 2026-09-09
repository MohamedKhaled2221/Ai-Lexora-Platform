namespace LegalAssistant.Api.Email;

public interface IEmailService
{
    Task SendAsync(string recipientEmail, string subject, string htmlBody);
}
