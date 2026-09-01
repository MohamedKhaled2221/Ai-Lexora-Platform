using System.Threading.Channels;

namespace LegalAssistant.Api.Services;

public sealed class AnalysisWorkQueue : IAnalysisWorkQueue
{
    // Bounded so a burst of requests can't grow memory without limit;
    // QueueAsync will wait for space instead of dropping work.
    private readonly Channel<int> _channel = Channel.CreateBounded<int>(
        new BoundedChannelOptions(500) { FullMode = BoundedChannelFullMode.Wait });

    public ValueTask QueueAsync(int documentId, CancellationToken cancellationToken = default)
        => _channel.Writer.WriteAsync(documentId, cancellationToken);

    public ValueTask<int> DequeueAsync(CancellationToken cancellationToken = default)
        => _channel.Reader.ReadAsync(cancellationToken);
}