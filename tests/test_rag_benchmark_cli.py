import random


def shuffled_ids(
    *,
    ids: list[str],
    seed: int,
    repetition: int,
) -> list[str]:
    result = list(
        ids
    )

    rng = random.Random(
        seed + repetition
    )

    rng.shuffle(
        result
    )

    return result


def test_shuffle_is_deterministic():
    ids = [
        "a",
        "b",
        "c",
        "d",
        "e",
        "f",
        "g",
        "h",
        "i",
    ]

    first = shuffled_ids(
        ids=ids,
        seed=42,
        repetition=1,
    )

    second = shuffled_ids(
        ids=ids,
        seed=42,
        repetition=1,
    )

    assert first == second


def test_repetitions_use_different_order():
    ids = [
        "a",
        "b",
        "c",
        "d",
        "e",
        "f",
        "g",
        "h",
        "i",
    ]

    first = shuffled_ids(
        ids=ids,
        seed=42,
        repetition=1,
    )

    second = shuffled_ids(
        ids=ids,
        seed=42,
        repetition=2,
    )

    assert first != second

    assert sorted(first) == sorted(
        ids
    )

    assert sorted(second) == sorted(
        ids
    )
