# Stock Analyzer — Session Summary
*Generated: June 28, 2026*

## Project Overview
Building a quantitative stock analysis system for Indian equities (expanding to US + global markets).
- Repo: git@github.com:groverpuneet/stock-analyzer.git
- Machine: MacBook Air M1, Python 3.9, PostgreSQL 15
- Venv: ~/stock-analyzer/venv
- DB: postgresql://puneetgrover@localhost/stock_analyzer

## Architecture Decisions
- Scheduler: Dagster (migrating from APScheduler) — multi-market, data lineage, visual UI
- Sentiment scoring: FinBERT local — free, no API cost at scale
- News collection: Proactive (broad RSS → flashtext NER → FinBERT) — surfaces opportunities outside watchlist
- MF holdings: mfdata.in API — free, no auth, 14000+ schemes
- Orchestration: Dagster in Docker — Docker already running for other apps
- Token optimization: Local models bulk, Claude API on-demand only — see ENGINEERING.md

## What's Built & Working
- Kite OHLCV + quotes — daily 4:00 PM IST
- Technical indicators (RSI, MACD, BB, SMA, EMA) — daily 4:15 PM IST
- BUY/SELL/WATCH signal generator — daily 5:00 PM IST
- FII/DII flows — daily 4:30 PM IST
- NSE corporate actions + earnings — event-driven
- Screener.in fundamentals — weekly Sunday
- News sentiment (proactive RSS + flashtext + FinBERT) — daily 5:15 PM IST
- RBI macro (manually seeded, live blocked by SSL) — weekly Sunday
- Insider trades + bulk deals — weekly Sunday
- F&O data (VIX=13.05, PCR=1.060, FII OI) — daily 4:45 PM IST
- NSE stock universe expansion — weekly Sunday 7:30 AM
- Shareholding pattern — done
- Block deals NSE + BSE — done
- Google Trends — done (920 rows)

## Current Blockers
- MF portfolio holdings: mfdata.in URL not resolving — test curl https://mfdata.in/api/v1/search?q=hdfc
- RBI DBIE SSL: Mac LibreSSL 2.8.3 incompatible — needs server with OpenSSL 1.1.1+
- MoSPI CPI/IIP: data.gov.in broken — use mcp.mospi.gov.in via fastmcp
- Kite token daily expiry: manual refresh daily — build TOTP auto-refresh (pyotp + playwright)
- Dagster Docker: not confirmed running — check docker ps + localhost:3000

## Database Tables
stocks, daily_prices, technical_indicators, signals, fundamentals,
fii_dii_flows, news_sentiment, insider_trades, bulk_deals, fno_data,
macro_indicators, shareholding_pattern, mf_holdings, corporate_actions,
earnings_calendar, data_refresh_log, model_versions, watchlist
Alembic migrations at: 0007

## Remaining Work

### Immediate
1. Verify Dagster running — docker ps + localhost:3000
2. Fix MF holdings — mfdata.in
3. Kite TOTP auto-refresh — pyotp + playwright, daily 8am IST
4. Verify launchd running persistently

### Tier 2 — Macro
5. RBI credit growth + forex reserves (SSL fix needed)
6. GDP + WPI via MoSPI MCP (pip install fastmcp)
7. F&O expiry calendar (NSE API)
8. RBI MPC meeting calendar (manual seed)

### Tier 3 — US Markets
9. US OHLCV — Polygon.io (free, needs API key)
10. FRED macro data (free, no key)
11. SEC EDGAR insider trades (free)
12. US news sentiment (extend existing pipeline)
13. Congress trades — Quiver Quant (free tier)

### Tier 4 — Alternative Data
14. Job postings (Adzuna API)
15. Short interest US (FINRA)
16. App store sentiment

### UI/Dashboard (after Tier 1 complete)
17. Signal dashboard
18. Stock detail page
19. Watchlist manager
20. Opportunity alerts
21. Macro snapshot
22. Multi-market view

## Ground Rules (always apply)
- No personal data — no portfolio, holdings, P&L, positions
- Public market data only
- Kite Connect: read-only (OHLCV, quotes, instruments only)
- FinBERT local for bulk scoring, Claude API only for on-demand research
- Every integration needs Dagster asset + DB test before commit
- Token optimization standard in ENGINEERING.md
- Rate limits: wait and retry automatically, log to STATUS.md
