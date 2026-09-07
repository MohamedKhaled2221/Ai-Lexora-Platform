"""
Lightweight M4 runtime usage metrics.

Records:
- end-to-end latency
- Python process RSS RAM
- total visible NVIDIA VRAM usage

VRAM measurements are best-effort. If nvidia-smi is unavailable,
VRAM fields are returned as None rather than failing the request.
"""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from typing import Callable

import psutil


_MB = 1024 * 1024


@dataclass(frozen=True)
class ModelUsageMetrics:
    latency_ms: float

    ram_rss_before_mb: float
    ram_rss_after_mb: float
    ram_rss_delta_mb: float

    vram_used_before_mb: float | None
    vram_used_after_mb: float | None
    vram_used_delta_mb: float | None


def read_total_vram_used_mb() -> float | None:
    """
    Return total used VRAM reported by visible NVIDIA GPUs.

    This is a device-level snapshot, not memory attributed solely
    to the Python process, because Ollama normally runs in its own
    process.

    Failure to read NVIDIA metrics is non-fatal.
    """

    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.used",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=2.0,
            check=True,
        )

    except (
        FileNotFoundError,
        subprocess.SubprocessError,
        OSError,
    ):
        return None

    values: list[float] = []

    for line in completed.stdout.splitlines():
        value = line.strip()

        if not value:
            continue

        try:
            values.append(float(value))

        except ValueError:
            return None

    if not values:
        return None

    return sum(values)


class ModelUsageTracker:
    """
    Context manager for one M4 operation.
    """

    def __init__(
        self,
        *,
        clock: Callable[[], float] = (
            time.perf_counter
        ),
        process=None,
        vram_reader: Callable[
            [],
            float | None,
        ] = read_total_vram_used_mb,
    ) -> None:
        self._clock = clock

        self._process = (
            process
            or psutil.Process(
                os.getpid()
            )
        )

        self._vram_reader = (
            vram_reader
        )

        self._started_at: float | None = None
        self._ram_before: float | None = None
        self._vram_before: float | None = None

        self._metrics: (
            ModelUsageMetrics | None
        ) = None

    def __enter__(
        self,
    ) -> "ModelUsageTracker":
        self._started_at = self._clock()

        self._ram_before = (
            self._read_ram_mb()
        )

        self._vram_before = (
            self._vram_reader()
        )

        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ) -> bool:
        finished_at = self._clock()

        ram_after = self._read_ram_mb()
        vram_after = self._vram_reader()

        if (
            self._started_at is None
            or self._ram_before is None
        ):
            raise RuntimeError(
                "ModelUsageTracker was not started."
            )

        vram_delta = None

        if (
            self._vram_before is not None
            and vram_after is not None
        ):
            vram_delta = (
                vram_after
                - self._vram_before
            )

        self._metrics = ModelUsageMetrics(
            latency_ms=(
                (
                    finished_at
                    - self._started_at
                )
                * 1000.0
            ),
            ram_rss_before_mb=(
                self._ram_before
            ),
            ram_rss_after_mb=ram_after,
            ram_rss_delta_mb=(
                ram_after
                - self._ram_before
            ),
            vram_used_before_mb=(
                self._vram_before
            ),
            vram_used_after_mb=vram_after,
            vram_used_delta_mb=vram_delta,
        )

        return False

    @property
    def metrics(
        self,
    ) -> ModelUsageMetrics:
        if self._metrics is None:
            raise RuntimeError(
                "Usage metrics are not available "
                "until tracking has completed."
            )

        return self._metrics

    def _read_ram_mb(
        self,
    ) -> float:
        return (
            self._process
            .memory_info()
            .rss
            / _MB
        )
