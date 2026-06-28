# Stock Analyzer — Web UI

Desktop-first, responsive (mobile + iPad) web interface for the Indian-equity
data pipeline. **FastAPI backend + React (Vite + TypeScript) frontend.** All data
is read live from the project's PostgreSQL `stock_analyzer` database — no mocks.

## Pages

1. **Signal dashboard** (`/`) — BUY/SELL/WATCH across the watchlist with price, RSI, MACD, and the rule hits behind each verdict. Filter by verdict.
2. **Stock detail** (`/stock/:id`) — price + SMA50/200 chart, RSI and MACD subcharts, volume, fundamentals, shareholding, recent news (FinBERT sentiment), and bulk/block deals.
3. **Macro snapshot** (`/macro`) — RBI policy rates, forex reserves (+ trend), bank credit/deposit growth, FII/DII flows, F&O (VIX/PCR), and GDP/WPI trend charts.
4. **Watchlist manager** (`/watchlist`) — named lists; search the full universe to add, remove entries. Tracking only — no holdings/P&L.
5. **Opportunity alerts** (`/opportunities`) — strong-sentiment movers, momentum leaders, and notable deals **outside** the watchlist.
6. **Claude analysis chat** — floating "Ask Claude" widget on every page. Streams the response token-by-token over SSE. Token-optimized: only the rows relevant to the question (focused stock + macro snapshot) are sent as context.

## Architecture

```
webapp/
  backend/                FastAPI (run on venv310 / Python 3.10)
    main.py               app + CORS + /api/health
    db.py                 psycopg2 helpers (read-only over market data)
    signals_engine.py     ports analysis/generate_signals.py rules to the web layer
    routers/              signals, stocks, macro, watchlist, opportunities, chat
  frontend/               Vite + React + TS + Tailwind + recharts
    src/pages/            the 5 pages
    src/components/        SignalBadge, ChatWidget (SSE)
```

The signal verdicts are **computed on demand** from the latest `technical_indicators`
+ `daily_prices` (the project never stored a signals table) using the same
thresholds as the CLI report — RSI<30 BUY / >70 SELL, golden/death cross, MACD
cross, Bollinger bands, volume-spike WATCH.

## Running it

```bash
# 1. Backend (terminal 1) — port 8009
cd webapp/backend
DATABASE_URL='postgresql://puneetgrover@localhost/stock_analyzer' \
  ../../venv310/bin/uvicorn main:app --reload --port 8009

# 2. Frontend (terminal 2) — port 5173, proxies /api -> :8009
cd webapp/frontend
npm install      # first time only
npm run dev
# open http://localhost:5173
```

> Port 8009 (not 8000) because :8000 is taken by another local app. The Vite dev
> proxy in `vite.config.ts` points `/api` at `http://localhost:8009`.

## Claude chat — required config

The chat widget reads **`ANTHROPIC_API_KEY` from the repo-root `.env`**. As of this
writing that key is **not** present in `.env` (only the Kite keys are). Until it is
added, the chat returns a clear "not configured" message and the other five pages
work fully. Add it and restart the backend:

```
ANTHROPIC_API_KEY=sk-ant-...
```

Model: `claude-opus-4-8` (streaming). Ground rule honoured throughout: only public
market data is queried — never portfolio, holdings, P&L, positions, or any order
endpoint.
