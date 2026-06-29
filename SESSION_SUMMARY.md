# Stock Analyzer — Session Summary
*Updated: June 29, 2026*

## Project Overview
Building a quantitative stock analysis system for Indian equities (expanding to US + global markets).
- Repo: git@github.com:groverpuneet/stock-analyzer.git
- Machine: MacBook Air M1, Python 3.10, PostgreSQL 15
- Venv: ~/stock-analyzer/venv310
- DB: postgresql://puneetgrover@localhost/stock_analyzer

## Architecture Decisions
- Scheduler: Dagster (migrating from APScheduler) — multi-market, data lineage, visual UI
- Sentiment scoring: FinBERT local — free, no API cost at scale
- News collection: Proactive (broad RSS → flashtext NER → FinBERT) — surfaces opportunities outside watchlist
- MF holdings: mfdata.in API — free, no auth, 14000+ schemes
- Orchestration: Dagster in Docker — Docker already running for other apps
- Token optimization: Local models bulk, Claude API on-demand only — see ENGINEERING.md

## Completed Sessions

### Session A-E: Core Infrastructure
- Kite OHLCV + quotes — daily 4:00 PM IST
- Technical indicators (RSI, MACD, BB, SMA, EMA) — daily 4:15 PM IST
- BUY/SELL/WATCH signal generator — daily 5:00 PM IST
- FII/DII flows — daily 4:30 PM IST
- NSE corporate actions + earnings — event-driven
- Screener.in fundamentals — weekly Sunday
- News sentiment (proactive RSS + flashtext + FinBERT) — daily 5:15 PM IST
- RBI macro (DBIE via Playwright) — weekly Sunday
- Insider trades + bulk deals — weekly Sunday
- F&O data (VIX, PCR, FII OI) — daily 4:45 PM IST
- NSE stock universe expansion — weekly Sunday 7:30 AM
- Shareholding pattern — done
- Block deals NSE + BSE — done
- Google Trends — done (920 rows)
- F&O expiry calendar — done
- GDP + WPI — done (MoSPI MCP)
- RBI forex reserves + bank credit growth — done (DBIE)
- Raw data pages for all 32 DB tables — done

### Session F: UI Improvements
- India Fear & Greed history (backfilled 30 days)
- Smart Money page (13F, SAST, insider trades, DII trend)
- Risk Alerts page (pledging, SMA200, FII selling, news clusters)
- India/US market demarcation across all pages

### Session G: Cloudflare Tunnel + iPhone Widget
- Cloudflare quick tunnel for remote access
- Fear & Greed API endpoint (/api/fear-greed)
- Scriptable widget for iPhone home screen (moved to fear-greed-api repo)

### Session H: Telegram Bot
- Daily digest at 08:00 IST (Fear&Greed, top-5, alerts, FII/DII, earnings, news, macro)
- Rule commands: /start /help /top5 /fear /macro /alerts /earnings /news /signal /fundamentals /insider /watchlist
- AI queries via Gemini (primary) → Groq (fallback)
- Persistent listener via launchd

### Session I: Fear & Greed API Separation
- Extracted to separate repo: fear-greed-api
- Deployed to Render (free tier)
- iPhone widget updated to use Render URL

### Session J: Security Hardening (COMPLETE)
- **Auth enabled**: bcrypt password hashing + session cookies (24hr expiry)
- **Read-only DB user**: stock_reader for webapp (SELECT only)
- **Rate limiting**: 100 req/min per IP via slowapi
- **Security headers**: HSTS, X-Frame-Options, CSP, etc.
- **Pre-commit hook**: Blocks commits with secret patterns
- **SQL injection audit**: All queries parameterized
- **Dependency audit**: Known vulnerabilities documented (accepted risk)

## Current State

### Running Services (launchd)
- com.stockanalyzer.backend — FastAPI on port 8009 (auth enabled)
- com.stockanalyzer.frontend — Vite preview on port 5173
- com.stockanalyzer.scheduler — Dagster scheduler
- com.stockanalyzer.telegram — Telegram bot listener
- com.stockanalyzer.tunnel — ngrok tunnel (permanent domain)

### Authentication
- Username: puneet
- Password: StockAnalyzer2026!
- Login: POST /api/auth/login with JSON body
- All /api/* require valid session (except health/login/logout/status)

### Database Tables
stocks, daily_prices, technical_indicators, signals, fundamentals,
fii_dii_flows, news_sentiment, insider_trades, bulk_deals, fno_data,
macro_indicators, shareholding_pattern, mf_holdings, corporate_actions,
earnings_calendar, data_refresh_log, model_versions, watchlist, expiry_calendar,
data_quality_log, stock_scores, indicator_baselines, recompute_queue,
pledging_alerts, sast_disclosures, institutional_holdings_13f, tracked_filers,
quarterly_financials, concall_transcripts, analyst_targets, congress_trades
Alembic migrations at: 0016

## Remaining Work

### Tier 4 — Alternative Data
- Intraday alerts via Telegram
- NAV refresh collector for 18 MFs
- Congress trades (blocked — Quiver/Capitol Trades require paid API)
- US signals computation
- App store sentiment

### Future
- Multi-app shell
- Update iPhone widget to use Render URL
- Docker compose for full deployment

## Ground Rules (always apply)
- No personal data — no portfolio, holdings, P&L, positions
- Public market data only
- Kite Connect: read-only (OHLCV, quotes, instruments only)
- FinBERT local for bulk scoring, Claude API only for on-demand research
- Every integration needs Dagster asset + DB test before commit
- Token optimization standard in ENGINEERING.md
- Rate limits: wait and retry automatically, log to STATUS.md
