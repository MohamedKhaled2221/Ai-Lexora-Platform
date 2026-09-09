"""Token counting against the embedding model's real tokenizer.

Why this exists
---------------
M1 chunks by characters; M2 embeds with BGE-M3, which truncates at 512 tokens.
Those two limits were never reconciled, and the gap is not small. Measured over
``test_corpus/synthetic`` with BGE-M3's own tokenizer:

    Arabic : 78% of chunks exceed 512 tokens, median 741, worst 1332
    English: 23% exceed, worst 1198

The worst Arabic chunk packed 1999 characters into 1332 tokens -- 1.50
chars/token -- so 62% of its text was never seen by the encoder. The
untruncated text still sits in the Qdrant payload, so keyword search happily
matches a passage that neither the dense nor the sparse vector has any
knowledge of.

A character budget cannot fix this. The observed chars-per-token ratio spans
1.50 (dense Arabic legal text) to 5.03 (English), a threefold spread: any
single character limit either truncates Arabic or shreds English into
fragments. The only reliable measure is the tokenizer the encoder actually
uses.

Cost
----
``transformers`` is already a pinned M1 dependency (via docling), so this adds
no new package. The tokenizer is loaded once per process and cached; loading is
a few hundred milliseconds and encoding is fast enough to run over every chunk.

Degradation
-----------
If the tokenizer cannot be loaded -- no cached weights, no network in a strict
offline deployment -- counting falls back to a conservative character estimate
rather than failing the pipeline. The estimate deliberately assumes the *worst*
observed ratio, so it over-splits rather than under-splits: an over-split chunk
loses a little context, while an under-split one loses its tail entirely and
silently.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Callable, Protocol

log = logging.getLogger(__name__)


DEFAULT_TOKENIZER_MODEL = "BAAI/bge-m3"
"""The model whose tokenizer decides the budget.

Must stay in step with ``EmbeddingService``'s model in the M2/M3 service. If
they diverge, chunks are sized against the wrong vocabulary and the truncation
gap reopens quietly.
"""

FALLBACK_CHARS_PER_TOKEN = 1.5
"""Worst ratio observed on the real corpus (dense Arabic legal text).

Used only when the real tokenizer is unavailable. Assuming the worst ratio
makes the fallback over-split, which costs a little context; assuming an
average ratio would let dense Arabic through under-split, which costs the tail
of the chunk with no warning.
"""


class TokenCounter(Protocol):
    def __call__(self, text: str) -> int: ...


_lock = threading.Lock()
_cache: dict[str, Callable[[str], int]] = {}


def _load_tokenizer(model_name: str):
    """Load the tokenizer, preferring anything already on disk."""

    from transformers import AutoTokenizer

    return AutoTokenizer.from_pretrained(model_name)


def _estimating_counter(text: str) -> int:
    """Conservative character-based stand-in. Over-counts on purpose."""

    return int(len(text) / FALLBACK_CHARS_PER_TOKEN) + 2


def get_token_counter(
    model_name: str = DEFAULT_TOKENIZER_MODEL,
) -> Callable[[str], int]:
    """Return a cached ``text -> token count`` function for ``model_name``.

    The count includes the two special tokens BGE-M3 adds, because those
    consume budget against the 512 limit exactly as content tokens do.
    """

    with _lock:
        cached = _cache.get(model_name)

        if cached is not None:
            return cached

        try:
            tokenizer = _load_tokenizer(model_name)

        except Exception as exc:  # noqa: BLE001 -- any failure degrades alike
            log.warning(
                "Could not load tokenizer %r (%s: %s). Falling back to a "
                "conservative character estimate at %.2f chars/token, which "
                "over-splits rather than truncating.",
                model_name,
                type(exc).__name__,
                exc,
                FALLBACK_CHARS_PER_TOKEN,
            )
            _cache[model_name] = _estimating_counter
            return _estimating_counter

        def count(text: str) -> int:
            if not text:
                return 0

            return len(
                tokenizer.encode(text, add_special_tokens=True)
            )

        log.info("Token budget will use the %r tokenizer.", model_name)
        _cache[model_name] = count
        return count


def reset_token_counter_cache() -> None:
    """Drop the cached tokenizers. For tests."""

    with _lock:
        _cache.clear()


def tokenizer_is_real(
    model_name: str = DEFAULT_TOKENIZER_MODEL,
) -> bool:
    """Whether counting uses the real tokenizer rather than the estimate.

    Worth recording on chunk metadata: a corpus chunked under the estimate has
    different (more conservative) boundaries than one chunked under the real
    tokenizer, and that is the kind of difference that is impossible to
    reconstruct later from the chunks alone.
    """

    return get_token_counter(model_name) is not _estimating_counter
