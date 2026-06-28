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

- [x] MF stock holdings — DII proxy implementation
  - Source: shareholding_pattern DII% (Screener.in quarterly filings)
  - Note: Detailed MF portfolio (which MFs hold which stocks) BLOCKED — AMFI portal requires login;
    all alternatives blocked (Moneycontrol 403, Tickertape 404, ValueResearch timeout, mfapi.in NAV only)
  - Current solution: DII% as proxy for MF ownership (DII = MFs + insurance + banks + pension)
  - Table: mf_stock_holdings — 737 rows (2024-06 to 2026-06), QoQ changes tracked
  - Dagster asset: nse_mf_holdings (nse_monthly group, 1st of month 02:00 IST)
  - Revisit: When AMFI API becomes available or another stock-level MF source found

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

- [x] US OHLCV prices
  - Source: Polygon.io Aggregates API, free tier (5 calls/min, EOD, ~2yr history)
  - Key: POLYGON_API_KEY in .env (+ docker-compose x-stock-env + .env.example placeholder)
  - Collector: data_collectors/polygon_prices_collector.py (requests + dotenv).
    Rate-limited 13s/call (<5/min) with 429 backoff. `lookback_days` for daily incremental,
    `years` for the one-time 2yr backfill.
  - Table: daily_prices (US stocks via stocks join) — 30 stocks × ~500 bars (2yr backfill)
  - Dagster asset: us_raw_prices (us_daily group) — daily incremental pulls last 7 days
  - No personal data involved

- [ ] US fundamentals
  - Source: Financial Modeling Prep API (free tier) or SEC EDGAR
  - Table: existing fundamentals with market=US
  - Dagster asset: us_fundamentals

- [x] FRED macro data — Fed rate, US CPI, GDP, unemployment
  - Source: FRED keyless `fredgraph.csv` endpoint (fred.stlouisfed.org) — no API key
  - Collector: data_collectors/fred_macro_collector.py (fetched via curl subprocess)
  - Fetch note: FRED is behind Akamai. Python requests/urllib/httpx get RemoteDisconnected
    (TLS ClientHello dropped); curl's fingerprint is accepted. Also Akamai TARPITS a custom
    User-Agent on this endpoint (hangs, 0 bytes) — must use curl's default UA. Use --http1.1.
    curl ships in the Dagster container image (dagster/Dockerfile line 21) so this is portable.
  - Series: FEDFUNDS→fed_funds_rate, CPIAUCSL→cpi_index + cpi_inflation_yoy (computed YoY),
    UNRATE→unemployment_rate, GDPC1→gdp_real + gdp_growth_yoy (computed YoY)
  - Table: macro_indicators, market='US', source='fred' — 227 rows (4yr history)
    Latest: Fed funds 3.63%, CPI infl 4.27% YoY, unemployment 4.3%, real GDP +2.68% YoY
  - Dagster asset: us_macro (us_weekly group) → us_weekly_job, Sunday 07:00 EST
  - Migration 0010 seeds the US stock universe (30 NYSE/NASDAQ large caps) + US refresh_log rows

- [x] US insider trades — SEC Form 4 filings
  - Source: SEC EDGAR (free). Needs a contact-email User-Agent per SEC fair-access policy;
    SEC accepts Python requests TLS (unlike FRED). Throttled 0.15s/req (<10 req/s).
  - Collector: data_collectors/sec_form4_collector.py
  - Flow: ticker→CIK (company_tickers.json) → submissions/CIK.json (form=='4', last 30d) →
    fetch ownership XML (raw doc = primaryDocument minus xslF345X##/ prefix) → parse
    nonDerivativeTable transactions
  - Mapping: code P→BUY, S→SELL, else raw code (M/F/A/G/X/...); person_category from
    Director/Officer:title/10% Owner; price NULL for grants/exercises
  - Table: insider_trades, source='sec_form4' — 377 rows, 27 stocks (30-day backfill)
  - Dagster asset: us_insider_trades (us_daily group)

- [x] US news sentiment
  - Source: Same RSS pipeline + FinBERT. Added US feeds: Google News US, CNBC,
    MarketWatch, Yahoo Finance, Seeking Alpha (cnbc occasionally empty — harmless)
  - Universe now matches seeded US stocks; expanded ABBREVIATION_MAP for 30 US names
  - Precision fixes: bare tickers that are common words (COST denylist) or ≤2 chars
    (V, MA, KO, HD) are NOT added as keywords — they matched "cost"/"v"/"ma" etc.
    Generic first-words guard (Bank, The, United...) so "Bank of America"→"Bank" can't
    tag every banking story. All still match via company name/abbrev.
  - No new table; folded into existing collect_news() → nse_news_sentiment asset,
    source stays 'news_sentiment'. Verified clean US matches (AAPL, BAC, NVDA, NKE)

- [ ] Congress trades — US politicians stock trades (high signal)  ⏸ DEFERRED
  - Source: BLOCKED — Capitol Trades requires auth; House/Senate Stock Watcher S3 buckets
    return AccessDenied; Quiver Quant costs $25/month.
  - Table: congress_trades (new) — politician, symbol, transaction, amount, date
  - Dagster asset: congress_trades → feeds into us_signals
  - Revisit: When free accessible source found or Quiver offers free API tier again

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

## Blocked/Deferred — Research Needed

- [ ] Research alternative free sources for MF portfolio holdings at stock level
  - AMFI portal requires login; all tested alternatives blocked (Moneycontrol, Tickertape, ValueResearch, mfapi.in)
  - Need: Which specific MFs hold which stocks (not just aggregate DII%)
  - Check: New AMFI API, finology.in, stockedge.com, other aggregators

- [ ] Research alternative free sources for US Congress trades
  - Capitol Trades requires auth; House/Senate Stock Watcher S3 blocked; Quiver Quant $25/month
  - Check: OpenSecrets API, CapitolGains, senatestockwatcher.com, new free sources

- [ ] Check if Quiver Quant offers free API access again
  - Currently $25/month; dashboard was returning HTTP 500 when trying to issue keys (2026-06-28)
  - Revisit periodically to see if free tier returns

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
