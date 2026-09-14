import json
from pathlib import Path

from src.schemas.m6_contract import ContractClause
from src.risk_engine.engine.risk_engine import analyze_clause


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_FILE = PROJECT_ROOT / "outputs" / "m5_output_for_m6.json"


def build_contract_clause(data: dict) -> ContractClause:
    source = data.get("source") or {}
    metadata = source.get("metadata") or {}

    return ContractClause(
        clause_id=data["clause_id"],
        type=data["type"],
        text=data["text"],
        entities=data.get("entities") or {},
        page=data["page"],
        similarity_score=data["similarity_score"],
        is_modified=data["is_modified"],
        confidence=data["confidence"],

        # Frontend location metadata
        source_section_id=source.get("source_section_id"),
        source_chunk_id=metadata.get("source_chunk_id"),
        page_start=metadata.get("page_start"),
        page_end=metadata.get("page_end"),
        bbox=metadata.get("bbox"),
        bboxes=metadata.get("bboxes"),
    )


def test_m6_contract_output():
    assert OUTPUT_FILE.exists(), (
        f"Output file was not found: {OUTPUT_FILE}"
    )

    with OUTPUT_FILE.open("r", encoding="utf-8") as file:
        payload = json.load(file)

    clauses = payload.get("clauses", [])

    assert clauses, "The JSON file does not contain any clauses."

    total_clauses = 0
    total_risks = 0

    print("\n" + "=" * 90)
    print("M6 CONTRACT OUTPUT TEST")
    print("=" * 90)
    print(f"Input file: {OUTPUT_FILE}")
    print(f"Total clauses: {len(clauses)}")

    for clause_data in clauses:
        clause = build_contract_clause(clause_data)
        risks = analyze_clause(clause)

        total_clauses += 1
        total_risks += len(risks)

        print("\n" + "-" * 90)
        print(f"Clause ID: {clause.clause_id}")
        print(f"Type: {clause.type}")
        print(f"Page: {clause.page}")
        print(f"Source section ID: {clause.source_section_id}")
        print(f"Source chunk ID: {clause.source_chunk_id}")
        print(f"Page start: {clause.page_start}")
        print(f"Page end: {clause.page_end}")
        print(f"BBox: {clause.bbox}")
        print(f"BBoxes: {clause.bboxes}")
        print(f"Detected risks: {len(risks)}")

        for risk in risks:
            result = risk.model_dump()

            print("\nRisk result:")
            print(f"  Risk: {result.get('risk')}")
            print(f"  Severity: {result.get('severity')}")
            print(f"  Severity color: {result.get('severity_color')}")
            print(f"  Color code: {result.get('color_code')}")
            print(f"  Page: {result.get('page')}")
            print(f"  Clause: {result.get('clause')}")
            print(f"  Source section ID: {result.get('source_section_id')}")
            print(f"  Source chunk ID: {result.get('source_chunk_id')}")
            print(f"  Page start: {result.get('page_start')}")
            print(f"  Page end: {result.get('page_end')}")
            print(f"  BBox: {result.get('bbox')}")
            print(f"  BBoxes: {result.get('bboxes')}")

            assert result.get("severity_color") in {
                "green",
                "yellow",
                "red",
                "dark_red",
                "gray",
            }

            assert result.get("color_code") == result.get(
                "severity_color"
            )

            assert result.get("page") == clause.page
            assert result.get("clause") == clause.clause_id

    print("\n" + "=" * 90)
    print("FINAL RESULT")
    print("=" * 90)
    print(f"Clauses tested: {total_clauses}")
    print(f"Risks detected: {total_risks}")
    print("color_code and severity_color checks passed.")
    print("=" * 90)

    assert total_clauses == len(clauses)
