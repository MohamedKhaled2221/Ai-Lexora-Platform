from fastapi import APIRouter

from src.api.schemas import M6RiskRequest, M6RiskResponse
from src.risk_engine.integration.m5_adapter import convert_m5_payload
from src.risk_engine.engine.risk_engine import analyze_clause


router = APIRouter(
    prefix="/api/v1/risk",
    tags=["Risk"],
)


@router.post(
    "/analyze",
    response_model=M6RiskResponse,
)
async def analyze_risk(
    request: M6RiskRequest,
) -> M6RiskResponse:

    clauses = convert_m5_payload(
        request.model_dump()
    )

    risks = []

    for clause in clauses:
        risks.extend(
            analyze_clause(clause)
        )

    return M6RiskResponse(
        risks=risks
    )