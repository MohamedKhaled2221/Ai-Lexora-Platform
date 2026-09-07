from types import SimpleNamespace

from src.orchestration.model_usage_metrics import (
    ModelUsageTracker,
)


class FakeProcess:
    def __init__(self):
        self.values = iter(
            [
                100 * 1024 * 1024,
                125 * 1024 * 1024,
            ]
        )

    def memory_info(self):
        return SimpleNamespace(
            rss=next(self.values)
        )


def test_usage_tracker_records_metrics():
    times = iter(
        [10.0, 10.25]
    )

    vram = iter(
        [500.0, 540.0]
    )

    with ModelUsageTracker(
        clock=lambda: next(times),
        process=FakeProcess(),
        vram_reader=lambda: next(vram),
    ) as tracker:
        pass

    metrics = tracker.metrics

    assert metrics.latency_ms == 250.0

    assert (
        metrics.ram_rss_before_mb
        == 100.0
    )

    assert (
        metrics.ram_rss_after_mb
        == 125.0
    )

    assert (
        metrics.ram_rss_delta_mb
        == 25.0
    )

    assert (
        metrics.vram_used_before_mb
        == 500.0
    )

    assert (
        metrics.vram_used_after_mb
        == 540.0
    )

    assert (
        metrics.vram_used_delta_mb
        == 40.0
    )


def test_vram_is_optional():
    times = iter(
        [5.0, 5.1]
    )

    with ModelUsageTracker(
        clock=lambda: next(times),
        process=FakeProcess(),
        vram_reader=lambda: None,
    ) as tracker:
        pass

    metrics = tracker.metrics

    assert (
        metrics.vram_used_before_mb
        is None
    )

    assert (
        metrics.vram_used_after_mb
        is None
    )

    assert (
        metrics.vram_used_delta_mb
        is None
    )
