namespace LegalAssistant.Api.Services;

/// <summary>
/// In-process FIFO queue of document IDs awaiting contract analysis.
/// The controller enqueues a document ID and returns to the client
/// immediately (202 Accepted); <see cref="AnalysisBackgroundService"/>
/// dequeues in the background and does the actual — potentially slow,
/// eventually AI-backed — work outside the HTTP request lifecycle.
///
/// This is in-process and memory-only: it does not survive an app restart.
/// Any analysis left in "Processing" status when the app stops is re-queued
/// on the next startup (see AnalysisBackgroundService), so work is retried
/// rather than silently lost, but it will run again from the beginning.
/// </summary>
public interface IAnalysisWorkQueue
{
    ValueTask QueueAsync(int documentId, CancellationToken cancellationToken = default);
    ValueTask<int> DequeueAsync(CancellationToken cancellationToken = default);
}