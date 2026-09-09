from pathlib import Path

from src.evaluation.m2_evaluation import (
    M2EvaluationRunner,
    load_m2_evaluation_suite,
)


ROOT = Path(
    __file__
).resolve().parents[1]

CASES_PATH = (
    ROOT
    / "evaluation"
    / "m2_cases.json"
)


def test_m2_evaluation_cases_load():
    suite = load_m2_evaluation_suite(
        CASES_PATH
    )

    assert len(
        suite.cases
    ) >= 7


def test_m2_evaluation_has_required_language_categories():
    suite = load_m2_evaluation_suite(
        CASES_PATH
    )

    categories = {
        case.category
        for case in suite.cases
    }

    assert "english" in categories
    assert "arabic" in categories

    assert (
        "egyptian_arabic"
        in categories
    )

    assert "mixed" in categories
    assert "identifiers" in categories


def test_m2_evaluation_does_not_claim_arabizi_support():
    suite = load_m2_evaluation_suite(
        CASES_PATH
    )

    for case in suite.cases:
        combined = (
            f"{case.case_id} "
            f"{case.category}"
        ).casefold()

        assert "arabizi" not in combined


def test_all_m2_deterministic_cases_pass():
    suite = load_m2_evaluation_suite(
        CASES_PATH
    )

    runner = M2EvaluationRunner()

    results = runner.run(
        suite
    )

    failures = [
        result.model_dump()
        for result in results
        if not result.passed
    ]

    assert failures == []


def test_original_query_is_preserved_for_every_case():
    suite = load_m2_evaluation_suite(
        CASES_PATH
    )

    runner = M2EvaluationRunner()

    results = runner.run(
        suite
    )

    assert all(
        result.original_preserved
        for result in results
    )


def test_exact_identifiers_survive_every_query_variant():
    suite = load_m2_evaluation_suite(
        CASES_PATH
    )

    runner = M2EvaluationRunner()

    results = runner.run(
        suite
    )

    assert all(
        result.exact_identifiers_preserved
        for result in results
    )
