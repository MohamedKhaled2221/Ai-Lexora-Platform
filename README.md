# M5 Public API Delivery

M5 public API contract:
- POST /clauses/analyze
- GET /health

M1 owns POST /ingest and POST /clauses.

The FastAPI adapter is intentionally thin. Connect `run_m5_analysis()` in
`app/main.py` to the existing M5 pipeline and M5→M6 adapter before
end-to-end use.
