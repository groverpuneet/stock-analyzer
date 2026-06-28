# Stock Analyzer — Integration Build Queue

## Ground Rules (read before every session)
- No personal data: Do not access, store, or display personal portfolio, holdings, P&L, or positions
- Public market data only: All integrations use publicly available market-wide data
- Kite Connect scope: Use only for market data (OHLCV, quotes, instruments) — never call place_order, positions, holdings, or portfolio endpoints
- Token optimization: Local models (FinBERT) for bulk scoring, Claude API only for on-demand research queries
- Dagster first: Every new collector must be wrapped as a Dagster asset with correct dependencies
- Test before commit: Run collector against live DB, verify rows inserted, then commit
- One commit per integration: Clear commit message, update TASKS.md status, update ENGINEERING.md
- Rate limits: If you hit a token or rate limit mid-session, wait for the limit to reset and automatically retry — do not stop or ask me. Log the wait in STATUS.md and continue where you left off.

---

## Current Status

### DONE
- [x] Dagster migration — replacing APScheduler with Dagster assets + jobs
  - 15 assets across 6 groups, 6 jobs, 6 schedules (IST + EST)
  - dagster/repository.py, workspace.yaml, docker-compose.yml
  - Committed: 925834c

- [x] F&O data — India VIX, Put/Call ratio (index/stock/total/FII/DII), futures positioning
  - Source: NSE allIndices API (VIX) + participant OI archive CSV (PCR)
  - Table: fno_data — 1 row inserted (2026-06-25)
  - Dagster asset: nse_fno_data (nse_daily group) + dedicated nse_fno_job (16:45 IST)
  - Note: Per-strike option chain blocked by NSE JS challenge; max_pain NULL pending browser automation

- [x] Block deals — large negotiated trades (separate from bulk deals)
  - Source: NSE snapshot-capital-market-largedeal API (BLOCK_DEALS_DATA key)
  - Table: bulk_deals with deal_type='block', source='nse_block' — 25 rows (2026-06-25)
  - Dagster asset: nse_block_deals (nse_daily group, feeds into nse_signals)
  - --block-deals flag added to scheduler/daily_tasks.py

- [x] Shareholding pattern — promoter %, FII %, DII %, government %, public %
  - Source: Screener.in (aggregates NSE/BSE SEBI quarterly filings)
  - Table: shareholding_pattern — 120 rows (10 stocks × 12 quarters), 2023-Q2 to 2026-Q1/Q2
  - Dagster asset: nse_shareholding_pattern (nse_weekly group, Sunday 7:30 IST)
  - Lag handling: skips stocks already up to date; ON CONFLICT upsert on new quarter arrival
  - NSE API blocked by JS challenge — Screener.in used as authoritative proxy

### IN PROGRESS
- None

---

## Tier 1 — High signal, NSE market data (do next, in order)

- [x] BSE bulk + block deals — BSE-listed stocks
  - BSE API (api.bseindia.com) is JS-challenge blocked (returns HTML; even Playwright gets "Access Denied")
  - Source: NSE archive CSV (bulk.csv, block.csv) + NSE snapshot API — covers dual-listed stocks (90%+ match)
  - BSE-exclusive stocks require browser automation; deferred (same as NSE option chain)
  - Table: bulk_deals with source=nse_bulk/nse_block — 442 bulk + 25 block rows
  - Dagster asset: bse_bulk_deals (nse_daily group) → bse_bulk_job at 16:30 IST, feeds into nse_signals
  - --bse-bulk flag added to scheduler/daily_tasks.py

- [ ] MF portfolio holdings — what each mutual fund owns monthly
  - Source: AMFI monthly disclosure — BLOCKED: new AMFI site is Next.js SPA; portfolio pages 404;
    individual AMC download URLs 403/404; no consolidated API endpoint accessible
  - Workaround path: scrape 44 individual AMC websites (each has its own PDF format) — deferred
  - DII% in shareholding_pattern already captures aggregate MF+insurance ownership direction
  - Table: mf_holdings (new) — deferred until accessible API found
  - No personal data involved

- [x] Google Trends — search interest as sentiment proxy
  - Source: pytrends library (geo=IN, company names as search terms)
  - Table: macro_indicators with indicator=google_trends_{symbol} — 920 rows (10 stocks × 92 days)
  - Dagster asset: google_trends (nse_weekly group, Sunday 07:30 IST)
  - --google-trends flag added to scheduler/daily_tasks.py; added to run_weekly_pipeline()
  - Timeframe: 3-month history on first run, 1-month on subsequent runs

---

## Tier 2 — Macro completeness

- [x] RBI credit growth + forex reserves
  - Source: RBI DBIE (data.rbi.org.in) via Playwright (ignore_https_errors=True — bypasses Mac LibreSSL)
  - Collector: data_collectors/rbi_dbie_collector.py
  - Auth crack: SPA mints a session token in sessionStorage['sessionId']; replay gateway calls
    with it as the 'authorization' header (+ channelkey: key2) for clean JSON / XLSX
  - Forex: dbie_foreignExchangeReserves gateway service — total + FCA/gold/SDR/IMF, weekly, USD billion
    (latest $672.6B; 12-week trend stored for total)
  - Credit: official "Macro-economic Indicators" XLSX (Fortnightly sheet) — bank credit, non-food credit,
    aggregate deposits outstanding (₹ crore) -> computed YoY growth
    (bank credit +17.65%, non-food +17.81%, deposits +12.21% as of 31-May-26; merger-inflated base)
  - Table: macro_indicators — 20 rows, source='rbi_dbie'
  - Dagster asset: nse_macro_indicators (nse_weekly group) now also calls collect_rbi_dbie()
  - Runs on venv310 (Playwright + openpyxl)

- [x] GDP + WPI inflation
  - Source: MoSPI MCP server (mcp.mospi.gov.in) via fastmcp — datasets NAS (GDP) + WPI
  - Collector: data_collectors/mospi_macro_collector.py (async fastmcp.Client)
  - Table: macro_indicators — 112 rows, source='mospi_mcp'
    - gdp_constant_price / gdp_current_price (24 quarters), gdp_growth_yoy (20, computed YoY real growth)
    - wpi_index (28 months), wpi_inflation (16, computed YoY)
  - Dagster asset: nse_macro_indicators (nse_weekly group) now also calls collect_mospi_macro()
  - Latest: GDP growth Q2 FY26 = 8.23%, WPI inflation Mar-26 = 3.88%
  - Runs on venv310 (Python 3.10) — fastmcp requires 3.10+

- [x] F&O expiry calendar
  - Source: Kite Connect instruments('NFO') — 46,402 instruments, 18 unique expiries
  - Table: expiry_calendar — 18 rows (4 weekly, 3 monthly, 11 quarterly)
  - Dagster asset: nse_expiry_calendar (nse_weekly group, Sunday 07:30 IST)
  - Classification: weekly (NIFTY CE/PE only ≤60d), monthly (has FUT ≤95d), quarterly (far-dated)
  - Used by: F&O data asset to know current expiry

- [ ] RBI monetary policy calendar
  - Source: RBI website (MPC meeting dates published annually)
  - Table: existing macro_indicators with indicator=mpc_meeting_date
  - Manual seed + annual update

---

## Tier 3 — US market (after NSE Tier 1 + 2 complete)

- [ ] US OHLCV prices
  - Source: Polygon.io free tier (5 API calls/min, 2 years history)
  - API key needed: register at polygon.io (free)
  - Table: existing daily_prices with market=NYSE or NASDAQ
  - Dagster asset: us_raw_prices
  - Schedule: Daily 4:30 PM EST (weekdays)
  - No personal data involved

- [ ] US fundamentals
  - Source: Financial Modeling Prep API (free tier) or SEC EDGAR
  - Table: existing fundamentals with market=US
  - Dagster asset: us_fundamentals

- [ ] FRED macro data — Fed rate, US CPI, GDP, unemployment
  - Source: FRED API (free, no key needed for basic access)
  - Table: existing macro_indicators with market=US
  - Dagster asset: us_macro
  - Schedule: Weekly

- [ ] US insider trades — SEC Form 4 filings
  - Source: SEC EDGAR API (free, https://data.sec.gov/api/xbrl/)
  - Table: existing insider_trades with source=sec_form4
  - Dagster asset: us_insider_trades
  - Schedule: Daily

- [ ] US news sentiment
  - Source: Same RSS pipeline + FinBERT (already multi-market ready)
  - Add US feeds to MARKET_FEEDS in news_collector.py
  - No new table needed — existing news_sentiment handles it
  - Dagster asset: extend existing news_sentiment asset

- [ ] Congress trades — US politicians stock trades (high signal)
  - Source: Quiver Quant API (free tier available)
  - Table: congress_trades (new) — politician, symbol, transaction, amount, date
  - Dagster asset: congress_trades → feeds into us_signals
  - Schedule: Daily

---

## Tier 4 — Alternative data

- [ ] Job postings signals — hiring trends as growth proxy
  - Source: Adzuna API (free tier)
  - Table: job_signals (new) — symbol, date, posting_count, yoy_change
  - Schedule: Weekly

- [ ] Short interest (US)
  - Source: FINRA free data (https://www.finra.org/investors/market-data)
  - Table: short_interest (new)
  - Schedule: Bi-weekly (FINRA releases twice monthly)

- [ ] App store sentiment
  - Source: Apple App Store + Google Play RSS/API
  - Table: existing news_sentiment with source=app_store
  - Schedule: Weekly

---

## UI / Dashboard (after Tier 1 complete)

- [ ] Signal dashboard — today's BUY/SELL/WATCH across all stocks
- [ ] Stock detail page — price + indicators + news + insider + macro in one view
- [ ] Watchlist manager — add/remove stocks, create multiple lists
- [ ] Opportunity alerts — stocks with strong sentiment not in watchlist
- [ ] Macro snapshot — RBI rates, CPI, FII flows at a glance
- [ ] Multi-market view — NSE + US side by side (after Tier 3)

---

## Completion Criteria (for every integration)

1. Collector file written and tested against live DB
2. Dagster asset created with correct upstream dependencies declared
3. Data visible in PostgreSQL (SELECT COUNT(*) FROM table)
4. Committed with message: feat: {integration_name} — {row_count} rows, {source}
5. TASKS.md updated (check the box)
6. ENGINEERING.md updated with new data source

---

## How to resume autonomously

Start each Claude Code session with:

Read TASKS.md and ENGINEERING.md first.
Find the next unchecked item in Tier 1.
Build it completely per the completion criteria.
Commit and push when done.
Move to the next item.
Ask me only if: blocked by missing API key, need a permission decision, or Tier 1 is fully complete.
Never access personal portfolio, holdings, positions, or P&L data.
Never call kite.place_order() or any order placement endpoint.
If you hit a token or rate limit mid-session, wait for the limit to reset and automatically retry — do not stop or ask me. Log the wait in STATUS.md and continue where you left off.
