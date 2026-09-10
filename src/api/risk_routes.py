from typing import Any

from fastapi import APIRouter

from src.risk_engine.engine.risk_engine import analyze_clause
from src.risk_engine.integration.m5_adapter import convert_m5_payload
from src.schemas.m6_contract import ContractRisk


router = APIRouter(
    prefix="/api/v1/risk",
    tags=["Risk"],
)


@router.post(
    "/analyze",
    response_model=list[ContractRisk],
)
async def analyze_risk(
    payload: dict[str, Any],
) -> list[ContractRisk]:

    clauses = convert_m5_payload(payload)

    risks: list[ContractRisk] = []

    for clause in clauses:
        risks.extend(analyze_clause(clause))

    return risks