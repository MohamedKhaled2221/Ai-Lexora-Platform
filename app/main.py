from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from m5.adapters import analyze_request_to_m1_payload
from m5.m6_adapter import contracts_to_m6
from m5.pipeline import ClauseIntelligencePipeline

app = FastAPI(
    title="M5 Contract Clause Intelligence API",
    version="1.0.0",
)

class ClauseInput(BaseModel):
    clause_id: str = Field(..., min_length=1)
    text: str = Field(..., min_length=1)
    page: int | None = None
    section: str | None = None
    language: str | None = None

class AnalyzeRequest(BaseModel):
    document_id: str = Field(..., min_length=1)
    clauses: list[ClauseInput] = Field(..., min_length=1)

class M6ClauseOutput(BaseModel):
    clause_id: str
    type: str
    text: str
    entities: dict[str, Any]
    page: int | None = None
    similarity_score: float = 0.0
    is_modified: bool = False
    confidence: float

class AnalyzeResponse(BaseModel):
    document_id: str
    clauses: list[M6ClauseOutput]

def run_m5_analysis(request: AnalyzeRequest) -> list[M6ClauseOutput]:
    payload = analyze_request_to_m1_payload(request)
    pipeline = ClauseIntelligencePipeline()
    clauses = pipeline.analyze(payload)
    return [M6ClauseOutput(**item) for item in contracts_to_m6(clauses)]

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "m5-contract-clause-intelligence"}

@app.post("/clauses/analyze", response_model=AnalyzeResponse)
def analyze_clauses(request: AnalyzeRequest) -> AnalyzeResponse:
    try:
        clauses = run_m5_analysis(request)
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"M5 analysis failed: {exc}") from exc
    return AnalyzeResponse(document_id=request.document_id, clauses=clauses)
