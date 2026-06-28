"""Stock Analyzer web API.

FastAPI backend serving real data from the PostgreSQL stock_analyzer database.
Read-only over market data; the only writes are to the watchlist table.

Run (from webapp/backend, with venv310):
    DATABASE_URL=postgresql://puneetgrover@localhost/stock_analyzer \
    uvicorn main:app --reload --port 8000
"""
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Load the project .env (ANTHROPIC_API_KEY, etc.) from repo root.
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

from routers import signals, stocks, macro, watchlist, opportunities, chat, refresh, dashboard  # noqa: E402

app = FastAPI(title="Stock Analyzer API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", "http://127.0.0.1:5173",  # Vite dev
        "http://localhost:4173", "http://127.0.0.1:4173",  # Vite preview
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (signals.router, stocks.router, macro.router, watchlist.router,
          opportunities.router, chat.router, refresh.router, dashboard.router):
    app.include_router(r)


@app.get("/api/health")
def health():
    from db import query_one
    row = query_one("SELECT COUNT(*) AS n FROM stocks")
    return {"status": "ok", "stocks": row["n"] if row else 0,
            "claude_configured": bool(os.environ.get("ANTHROPIC_API_KEY"))}
