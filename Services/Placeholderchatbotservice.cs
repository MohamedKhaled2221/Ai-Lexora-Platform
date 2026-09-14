using LegalAssistant.Api.Data;

namespace LegalAssistant.Api.Services;

/// <summary>
/// Placeholder <see cref="IChatbotService"/>: matches a few keywords in the
/// latest user message to canned Arabic legal-FAQ-style answers, otherwise
/// returns a generic fallback. Proves the conversation -&gt; reply flow
/// end-to-end before a real LLM + RAG pipeline is wired in behind the same
/// interface. Not legal advice.
/// </summary>
public sealed class PlaceholderChatbotService : IChatbotService
{
    private static readonly (string[] Keywords, string Reply)[] CannedAnswers =
    {
        (new[] { "عقد", "contract" },
            "العقد وثيقة قانونية ملزمة بين طرفين أو أكثر تحدد التزامات كل طرف. هذا رد تجريبي مبدئي وليس استشارة قانونية."),
        (new[] { "إنهاء", "termination" },
            "شروط إنهاء العقد يجب أن تحدد مدة الإخطار المطلوبة وأسباب الإنهاء المسموح بها لكل طرف. هذا رد تجريبي مبدئي وليس استشارة قانونية."),
        (new[] { "سرية", "confidential", "nda" },
            "بنود السرية يجب أن تحدد نطاق المعلومات المحمية، ومدة الالتزام، والاستثناءات المسموح بها. هذا رد تجريبي مبدئي وليس استشارة قانونية.")
    };

    public Task<string> ReplyAsync(IReadOnlyList<ChatTurn> history, CancellationToken cancellationToken = default)
    {
        var lastUserMessage = history.LastOrDefault(t => t.Role == ChatMessageRoles.User)?.Content ?? string.Empty;

        foreach (var (keywords, reply) in CannedAnswers)
        {
            if (keywords.Any(k => lastUserMessage.Contains(k, StringComparison.OrdinalIgnoreCase)))
                return Task.FromResult(reply);
        }

        return Task.FromResult(
            "هذا رد تجريبي (placeholder) ولسه مفيش نموذج ذكاء اصطناعي حقيقي متصل بالمحادثة. " +
            "جرّب تسأل عن كلمة زي \"عقد\" أو \"سرية\" أو \"إنهاء\" لترى رد تجريبي، أو انتظر ربط الذكاء الاصطناعي الفعلي.");
    }
}