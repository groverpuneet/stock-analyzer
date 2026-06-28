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
- F&O expiry calendar — done (18 rows: weekly/monthly/quarterly, Kite NFO)
- GDP + WPI — done (112 rows, MoSPI MCP: GDP growth Q2 FY26 8.23%, WPI Mar-26 3.88%)
- RBI forex reserves + bank credit growth — done (20 rows, DBIE via Playwright: reserves $672.6B, credit +17.65% YoY)

## Today's Session (2026-06-28)
- **Dagster Docker stack — running and rebuilt**: confirmed up, then rebuilt to `python:3.10-slim`
  (fastmcp needs 3.10+) + openpyxl. All 4 containers verified healthy; collectors import in-container.
- **Kite TOTP auto-refresh**: `kite_auth/auto_login.py` ready; `.env` now carries
  KITE_USERNAME/PASSWORD/TOTP_SECRET (loaded by container) — verify end-to-end next session.
- **F&O expiry calendar**: Kite NFO instruments → expiry_calendar (migration 0009), nse_expiry_calendar asset.
- **MoSPI GDP + WPI**: async fastmcp.Client to mcp.mospi.gov.in (NAS + WPI datasets) → macro_indicators.
- **RBI forex + credit**: Playwright on data.rbi.org.in (ignore_https_errors). Cracked the DBIE gateway
  auth by replaying calls with sessionStorage['sessionId'] as the authorization header.
- All three macro collectors wired into the `nse_macro_indicators` Dagster asset (nse_weekly group).

## Current Blockers
- MF portfolio holdings: mfdata.in URL not resolving / AMFI is JS SPA — deferred (DII% proxy in shareholding_pattern)
- ~~RBI DBIE SSL~~: RESOLVED — Playwright with ignore_https_errors bypasses Mac LibreSSL
- ~~MoSPI CPI/IIP via data.gov.in~~: RESOLVED — MoSPI MCP server (also serves CPI, IIP for later)
- ~~Kite token daily expiry~~: credentials now in .env; auto_login.py ready — verify next session
- ~~Dagster Docker not confirmed~~: RESOLVED — running on python:3.10.20, repository loads clean

## Database Tables
stocks, daily_prices, technical_indicators, signals, fundamentals,
fii_dii_flows, news_sentiment, insider_trades, bulk_deals, fno_data,
macro_indicators, shareholding_pattern, mf_holdings, corporate_actions,
earnings_calendar, data_refresh_log, model_versions, watchlist, expiry_calendar
Alembic migrations at: 0009

## Remaining Work

### Tier 2 — Macro ✅ COMPLETE (except MPC manual seed)
- [x] F&O expiry calendar (Kite NFO)
- [x] GDP + WPI via MoSPI MCP
- [x] RBI credit growth + forex reserves (DBIE via Playwright)
- [ ] RBI MPC meeting calendar — manual seed (only remaining Tier 2 item)

### Immediate (carry-over, not blocking Tier 3)
1. Verify Kite TOTP auto-refresh end-to-end (credentials now in .env)
2. Verify launchd running persistently
3. MF holdings — deferred (no accessible API)

### Tier 3 — US Markets ← NEXT SESSION STARTS HERE
1. US OHLCV — Polygon.io (free, needs API key)
2. FRED macro data (free, no key)
3. SEC EDGAR insider trades (free)
4. US news sentiment (extend existing pipeline)
5. Congress trades — Quiver Quant (free tier)

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
