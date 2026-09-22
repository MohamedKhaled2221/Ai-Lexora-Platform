from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


CASES_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "p4_cases.json"
)

EXPECTED_COLLECTION = "legal_documents_acceptance_test"

NUMBER_WORDS = {
    "zero": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
    "eleven": "11",
    "twelve": "12",
    "thirteen": "13",
    "fourteen": "14",
    "fifteen": "15",
    "sixteen": "16",
    "seventeen": "17",
    "eighteen": "18",
    "nineteen": "19",
    "twenty": "20",
}


def normalize_text(value: Any) -> str:
    return " ".join(
        str(value).casefold().split()
    )


def normalize_expected_text(value: Any) -> str:
    normalized = normalize_text(value)

    for word, number in NUMBER_WORDS.items():
        normalized = re.sub(
            rf"\b{word}\b",
            number,
            normalized,
        )

    # Collapse equivalent duplicated numeric forms such as
    # "fifteen (15)" or "15 (fifteen)" after word conversion.
    normalized = re.sub(
        r"\b(\d+)\s*\(\s*\1\s*\)",
        r"\1",
        normalized,
    )

    return normalized


def compact_text(value: Any) -> str:
    return re.sub(
        r"[\s,._-]+",
        "",
        normalize_expected_text(value),
    )


def http_json(
    base_url: str,
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 180,
) -> tuple[int, dict[str, Any]]:
    data = None

    if body is not None:
        data = json.dumps(
            body,
            ensure_ascii=False,
        ).encode("utf-8")

    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=data,
        method=method,
        headers=headers or {},
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=timeout,
        ) as response:
            raw = response.read().decode("utf-8")

            return (
                response.status,
                json.loads(raw),
            )

    except urllib.error.HTTPError as exc:
        raw = exc.read().decode(
            "utf-8",
            errors="replace",
        )

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"raw": raw}

        return exc.code, payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run Package 4 acceptance cases against "
            "the isolated QA API."
        )
    )

    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8010",
    )

    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help=(
            "Case ID to exclude. May be supplied "
            "multiple times."
        ),
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=180,
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    excluded = set(args.exclude)

    print("===== P4 ACCEPTANCE BATCH =====")
    print()

    status, readiness = http_json(
        args.base_url,
        "GET",
        "/ready",
        timeout=args.timeout,
    )

    print("Readiness HTTP:", status)
    print("Status:", readiness.get("status"))
    print(
        "Collection:",
        readiness.get("qdrant_collection_name"),
    )
    print("Model:", readiness.get("model_name"))
    print()

    if status != 200:
        print(
            "FAIL: readiness endpoint is not HTTP 200."
        )
        return 1

    if readiness.get("status") != "ready":
        print("FAIL: API is not ready.")
        return 1

    if (
        readiness.get("qdrant_collection_name")
        != EXPECTED_COLLECTION
    ):
        print(
            "FAIL: server is not using "
            f"{EXPECTED_COLLECTION}."
        )
        return 1

    cases = json.loads(
        CASES_PATH.read_text(
            encoding="utf-8",
        )
    )

    cases = [
        case
        for case in cases
        if case["id"] not in excluded
    ]

    print(
        f"Running {len(cases)} cases"
        + (
            f" (excluded: {', '.join(sorted(excluded))})"
            if excluded
            else ""
        )
    )
    print()

    results: list[
        tuple[str, bool, list[str]]
    ] = []

    for index, case in enumerate(
        cases,
        start=1,
    ):
        case_id = case["id"]

        print("=" * 72)
        print(
            f"[{index}/{len(cases)}] {case_id}"
        )
        print("Question:", case["question"])
        print(
            "Confidentiality ceiling:",
            case.get(
                "confidentiality_ceiling",
                "privileged",
            ),
        )

        status, response = http_json(
            args.base_url,
            "POST",
            "/api/v1/p4/chat",
            body={
                "question": case["question"],
                "filters": {},
                "safe_context": [],
            },
            headers={
                "Content-Type": "application/json",
                "X-Client-Id": "client_test",
                "X-Matter-Id": "qa-general",
                "X-Confidentiality-Ceiling": (
                    case.get(
                        "confidentiality_ceiling",
                        "privileged",
                    )
                ),
            },
            timeout=args.timeout,
        )

        failures: list[str] = []

        if status != 200:
            failures.append(
                f"HTTP status was {status}, "
                "expected 200"
            )

            print("HTTP:", status)
            print(
                json.dumps(
                    response,
                    ensure_ascii=False,
                    indent=2,
                )
            )

            results.append(
                (case_id, False, failures)
            )
            print("RESULT: FAIL")
            continue

        answer = response.get("answer", "")
        citations = response.get(
            "citations",
            [],
        )

        citation_documents = {
            citation.get("document_id")
            for citation in citations
            if citation.get("document_id")
        }

        insufficient = response.get(
            "insufficient_evidence"
        )

        print("HTTP:", status)
        print("Answer:", answer)
        print(
            "Citations:",
            sorted(citation_documents),
        )
        print(
            "Insufficient:",
            insufficient,
        )
        print(
            "Grounding valid:",
            response.get("grounding_valid"),
        )
        print(
            "Citations valid:",
            response.get("citations_valid"),
        )
        print(
            "Structured output valid:",
            response.get(
                "structured_output_valid"
            ),
        )
        print(
            "Unsupported claims:",
            response.get(
                "unsupported_claims"
            ),
        )

        if (
            response.get("grounding_valid")
            is not True
        ):
            failures.append(
                "grounding_valid is not true"
            )

        if (
            response.get("citations_valid")
            is not True
        ):
            failures.append(
                "citations_valid is not true"
            )

        if (
            response.get(
                "structured_output_valid"
            )
            is not True
        ):
            failures.append(
                "structured_output_valid "
                "is not true"
            )

        if response.get("unsupported_claims"):
            failures.append(
                "unsupported_claims is not empty: "
                f"{response['unsupported_claims']}"
            )

        if "expected_insufficient" in case:
            expected_insufficient = bool(
                case["expected_insufficient"]
            )

            if (
                insufficient
                != expected_insufficient
            ):
                failures.append(
                    "insufficient_evidence was "
                    f"{insufficient!r}, expected "
                    f"{expected_insufficient!r}"
                )

        elif insufficient is True:
            failures.append(
                "unexpected "
                "insufficient_evidence=true"
            )

        if "expected" in case:
            expected = normalize_expected_text(
                case["expected"]
            )

            normalized_answer = (
                normalize_expected_text(answer)
            )

            if expected not in normalized_answer:
                failures.append(
                    "answer does not contain "
                    "expected text: "
                    f"{case['expected']!r}"
                )

        answer_compact = compact_text(answer)

        for expected in case.get(
            "expected_contains",
            [],
        ):
            if (
                compact_text(expected)
                not in answer_compact
            ):
                failures.append(
                    "answer does not contain "
                    "expected value: "
                    f"{expected!r}"
                )

        for document_id in case.get(
            "must_use",
            [],
        ):
            if (
                document_id
                not in citation_documents
            ):
                failures.append(
                    "required citation missing: "
                    f"{document_id}"
                )

        for document_id in case.get(
            "must_not_use",
            [],
        ):
            if (
                document_id
                in citation_documents
            ):
                failures.append(
                    "forbidden citation used: "
                    f"{document_id}"
                )

        normalized_answer = normalize_text(
            answer
        )

        for forbidden in case.get(
            "must_not_contain",
            [],
        ):
            if (
                normalize_text(forbidden)
                in normalized_answer
            ):
                failures.append(
                    "answer contains forbidden "
                    f"text: {forbidden!r}"
                )

        passed = not failures

        results.append(
            (
                case_id,
                passed,
                failures,
            )
        )

        if passed:
            print("RESULT: PASS")
        else:
            print("RESULT: FAIL")

            for failure in failures:
                print("  -", failure)

    print()
    print("=" * 72)
    print("FINAL SUMMARY")
    print("=" * 72)

    passed_count = sum(
        1
        for _, passed, _ in results
        if passed
    )

    failed_count = (
        len(results) - passed_count
    )

    for case_id, passed, failures in results:
        print(
            f"{'PASS' if passed else 'FAIL'}  "
            f"{case_id}"
        )

        if not passed:
            for failure in failures:
                print(
                    f"      - {failure}"
                )

    print()
    print(
        f"Passed: {passed_count}/"
        f"{len(results)}"
    )
    print(
        f"Failed: {failed_count}/"
        f"{len(results)}"
    )

    if failed_count:
        return 1

    print()
    print(
        "PASS: selected P4 acceptance "
        "cases passed."
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
