from math import sqrt


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Calculate cosine similarity between two vectors.

    Input:
        a, b: Equal-length numeric vectors.

    Output:
        Similarity in approximately [-1, 1].

    Side effects:
        None.

    Edge cases:
        Different dimensions or zero vectors raise ValueError.
    """
    if len(a) != len(b):
        raise ValueError("vectors must have equal dimensions")

    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sqrt(sum(x * x for x in a))
    norm_b = sqrt(sum(y * y for y in b))

    if norm_a == 0 or norm_b == 0:
        raise ValueError("zero vector is not valid for cosine similarity")

    return dot / (norm_a * norm_b)
