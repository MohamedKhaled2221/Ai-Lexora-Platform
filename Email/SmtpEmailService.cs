using System.Net;
using System.Net.Mail;

namespace LegalAssistant.Api.Email;

public class SmtpEmailService : IEmailService
{
    private readonly IConfiguration _configuration;
    private readonly ILogger<SmtpEmailService> _logger;

    public SmtpEmailService(IConfiguration configuration, ILogger<SmtpEmailService> logger)
    {
        _configuration = configuration;
        _logger = logger;
    }

    public async Task SendAsync(string recipientEmail, string subject, string htmlBody)
    {
        var host = _configuration["Email:Smtp:Host"];
        if (string.IsNullOrWhiteSpace(host))
        {
            _logger.LogWarning("Email is not configured; message to {Recipient} with subject {Subject} was not sent.", recipientEmail, subject);
            return;
        }

        var port = _configuration.GetValue<int>("Email:Smtp:Port", 587);
        var from = _configuration["Email:From"] ?? throw new InvalidOperationException("Email:From must be configured.");
        var username = _configuration["Email:Smtp:Username"];
        var password = _configuration["Email:Smtp:Password"];

        using var client = new SmtpClient(host, port)
        {
            EnableSsl = _configuration.GetValue("Email:Smtp:EnableSsl", true)
        };
        if (!string.IsNullOrWhiteSpace(username))
            client.Credentials = new NetworkCredential(username, password);

        using var message = new MailMessage(from, recipientEmail, subject, htmlBody) { IsBodyHtml = true };
        await client.SendMailAsync(message);
    }
}
