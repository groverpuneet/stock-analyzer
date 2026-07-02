# Stock Analyzer — Session Summary
*Updated: July 2, 2026*

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

### Post-J (unlettered): Unified Refresh Control (COMPLETE)
*(Built after Session J. Not lettered — the K/L letters belong to Portfolio + Signal Engine below, per git commits `dafc9ee` / `d615b21`.)*
- **New `/refresh` page** replaces the old Data Sources + Refresh Status pages
  (both now redirect to `/refresh`). Collectors grouped by market × cadence
  (🇮🇳 India Daily/Weekly/Monthly, 🇺🇸 US Daily/Weekly, + Other), each with real
  status, rows, duration, last run, next scheduled run, and an individual ▶ Run button.
- **Top controls**: ▶ Run All Now, ⚠ Retry Failed (only unhealthy sources),
  🔍 Audit (runs data-quality audit assets). Polls every 5s while jobs run.
- **Fixed status consistency**: every page (page badges, header health banner,
  `/refresh`) now reads from `data_refresh_log` — one source of truth.
- **Root-caused the phantom failures**: Dagster *run* status is unreliable on this
  8GB M1 (run marked FAILURE at finalize even when the step + collector succeeded,
  `stepsFailed: 0`). The old Refresh button polled run status; now everything reads
  the collector's own `data_refresh_log` result. Orphaned `running` rows (process
  killed mid-step) are surfaced as **stalled** (red, retryable), not hidden.
- New endpoints: `GET /api/refresh/control`, `GET /api/refresh/health`,
  `POST /api/refresh/trigger-audit`. See ENGINEERING.md → Unified Refresh Control.

### Post-J (unlettered): Manual refresh buttons everywhere + F&G from Dagster
- **Generic Dagster API**: `POST /api/dagster/materialize` ({asset} or {job}) +
  `GET /api/dagster/run-status/{run_id}`. One uniform path behind every 🔄 button
  (shared `useMaterialize` / `useMaterializeMany` hooks, `RefreshAll` + `AssetRefresh`
  components). `dagster_client.launch_job()` added alongside `launch_asset()`.
- **Fear & Greed**: per-market 🔄 on each gauge (India→`india_fear_greed`,
  US→`us_fear_greed`), shows data date + computed time; the two assets now write
  `data_refresh_log('fear_greed')` so the timestamp is accurate on solo refresh.
- **Dashboard**: 🔄 in the lead column header of each source group (Price→prices,
  RSI→indicators, P/E→fundamentals, News→news, Score→signals, Insider→insider) with
  a "last updated" tooltip; plus a top-right "Refresh All".
- **Refresh All on every page**: Dashboard, Macro, Opportunities, Smart Money,
  Risk Alerts, Watchlist, Stock Detail — materialises that page's assets, live progress.
- **/refresh page**: added "🔄 Refresh All India" / "🔄 Refresh All US"
  (`POST /api/refresh/trigger-region?region=`) alongside Run All / Retry Failed / Audit.
- **ENV FIX (important)**: native `dagster dev` was wedged ~19.5h (Mac sleep) AND
  running on `venv` (Python 3.9), so assets with `X | None` hints failed and runs
  never dequeued. Restarted on **venv310** (Python 3.10) — daemon healthy, runs
  execute to SUCCESS. If Dagster stalls again: `pkill -9 -f dagster` then
  `DATABASE_URL=… nohup venv310/bin/dagster dev -w workspace.yaml >logs/dagster_dev.log 2>&1 &`.

### Session K & L (2026-07-02) — Portfolio + Signal Engine + hardening (complete)
*(The refresh-control work above is now unlettered post-J; K/L below are the real
session letters per commits `dafc9ee` / `d615b21`.)*
- **Portfolio upload (Session K)**: private, **localhost/LAN-only** holdings module —
  TOTP-gated, pgcrypto-encrypted at rest, schema-scoped `portfolio_user`, audit log,
  blocked on the tunnel. CSV/Excel upload + P&L computed live (never stored). The blanket
  "no personal data" rule was scoped to "no personal data on external surfaces."
- **4-pillar signal engine (Session L)**: technical/fundamental/flow/external-sentiment
  pillars with an explainability panel (per-pillar reasoning, contrary indicators,
  "what would change this signal"), multi-horizon.
- **Git author email fixed across the full history (all 89 commits verified)**: were `your.email@example.com`
  (a repo-**local** `.git/config` override that shadowed `--global`); rewritten to
  `puneetgrover1991@gmail.com` via `git filter-branch` (`rebase --root` was blocked by
  `node_modules` committed in early history) and force-pushed. Pre-commit hook now guards
  the author email. See ENGINEERING.md → "Git Author Configuration (CRITICAL)".
- **Watchlist 500 error fixed.**
- **SESSION_SECRET persistent fix**: sessions no longer invalidated on backend restart.
- **13F / institutional pages — data vintage**: quarter labels (Q1 2026), filed-ago,
  freshness colour + 45-day banner; SAST days-to-disclose (>2 working days flagged) +
  SEBI banner (also fixed a 500 from a wrong `date_col`); congress days-to-disclose
  (>30d flagged); shareholding FY-quarter labels; MF month labels; a freshness header
  (data as of / last refreshed / next refresh) on every raw-data page.
- **Logo is now a home link** (→ `/`).
- **Data health restored**: the Kite access token had been expired since **Jun 26**,
  silently staling the NSE pipeline; token refreshed and `auto_login` hardened (captures
  `request_token` from the redirect request). `nse_daily` now records `kite_ohlcv` failures
  in `data_refresh_log` instead of skipping silently.

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
- No personal data on external surfaces — no portfolio/holdings/P&L/positions over the tunnel, Telegram, or public API. Personal portfolio is allowed **local-only** (Session K): localhost/LAN + TOTP + encrypted at rest, blocked on tunnel
- Public market data only
- Kite Connect: read-only (OHLCV, quotes, instruments only)
- FinBERT local for bulk scoring, Claude API only for on-demand research
- Every integration needs Dagster asset + DB test before commit
- Token optimization standard in ENGINEERING.md
- Rate limits: wait and retry automatically, log to STATUS.md
