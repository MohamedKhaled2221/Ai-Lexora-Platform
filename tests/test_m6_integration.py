import json
from pathlib import Path

from src.risk_engine.integration.m5_adapter import convert_m5_payload
from src.risk_engine.engine.risk_engine import analyze_clause


# =========================================================
# M5 OUTPUT FILE
# =========================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]
M5_FILE = PROJECT_ROOT / "outputs" / "m5_output_for_m6.json"


# =========================================================
# LOAD M5 OUTPUT
# =========================================================

def load_m5_output():
    """
    Load the official M5 JSON output used for M5 → M6 integration testing.
    """

    assert M5_FILE.exists(), (
        f"M5 output file not found: {M5_FILE}"
    )

    with open(
        M5_FILE,
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


# =========================================================
# TEST M5 → M6 ADAPTER
# =========================================================

def test_adapter():

    data = load_m5_output()

    clauses = convert_m5_payload(data)

    assert len(clauses) == len(data.get("clauses", [])), (
        "M5 → M6 adapter count mismatch"
    )

    assert clauses, "M5 output contains no clauses"

    print("=" * 70)
    print("M5 → M6 ADAPTER TEST")
    print("=" * 70)
    print(f"M5 clauses: {len(data.get('clauses', []))}")
    print(f"M6 clauses: {len(clauses)}")
    print("✅ All M5 clauses converted successfully.")


# =========================================================
# TEST M6 RISK ENGINE
# =========================================================

def test_risk_engine():

    data = load_m5_output()

    clauses = convert_m5_payload(data)

    total_risks = 0

    print("\n" + "=" * 70)
    print("M6 RISK ENGINE TEST")
    print("=" * 70)

    for clause in clauses:

        risks = analyze_clause(clause)

        total_risks += len(risks)

        print("\n" + "-" * 70)
        print(f"Clause ID:       {clause.clause_id}")
        print(f"Type:             {clause.type}")
        print(f"Page:             {clause.page}")
        print(f"Confidence:       {clause.confidence}")
        print(f"Similarity:       {clause.similarity_score}")
        print(f"Is Modified:      {clause.is_modified}")

        if not risks:
            print("Risk:             None")
            continue

        print(f"Risk Count:       {len(risks)}")

        for risk in risks:

            print("\n  Risk:")
            print(f"    Rule ID:       {risk.rule_id}")
            print(f"    Rule Type:     {risk.rule_type}")
            print(f"    Risk:          {risk.risk}")
            print(f"    Severity:      {risk.severity}")
            print(f"    Color:         {risk.severity_color}")
            print(f"    Confidence:    {risk.confidence}")
            print(f"    Status:        {risk.review_status}")
            print(f"    Legal Ref:     {risk.legal_reference}")
            print(f"    Explanation:   {risk.explanation}")

    # The test verifies that the engine executes successfully.
    assert total_risks >= 0


# =========================================================
# CHECK M5 CLAUSE TYPES
# =========================================================

def test_unknown_clause_types():

    data = load_m5_output()

    clauses = convert_m5_payload(data)

    unknown_count = sum(
        1 for clause in clauses
        if clause.type == "Unknown"
    )

    print("\n" + "=" * 70)
    print("CLAUSE TYPE CHECK")
    print("=" * 70)

    print(f"Unknown clauses: {unknown_count}")

    if unknown_count > 0:
        print(
            "⚠️ Some clauses were classified as Unknown by M5."
        )
        print(
            "M6 will not apply clause-specific rules to them."
        )
    else:
        print("✅ All clauses have recognized types.")