# Stock Analyzer — Engineering Reference

This document is the single source of truth for how this project is set up,
how to work with it, and the decisions made along the way. Update it whenever
something changes.

---

## Table of Contents

1. [Local Setup](#1-local-setup)
2. [Every Time You Open a Terminal](#2-every-time-you-open-a-terminal)
3. [Git & GitHub](#3-git--github)
4. [Database & Migrations](#4-database--migrations)
5. [Project Structure](#5-project-structure)
6. [Data Refresh Schedule](#6-data-refresh-schedule)
7. [Dagster Orchestration](#7-dagster-orchestration)
8. [Integrations Roadmap](#9-integrations-roadmap)
9. [Engineering Decisions Log](#10-engineering-decisions-log)
10. [Common Errors & Fixes](#11-common-errors--fixes)

---

## 1. Local Setup

**Machine:** MacBook Air M1, 8GB RAM, 512GB SSD  
**OS:** macOS  
**Python:** 3.9 (inside virtualenv at `~/stock-analyzer/venv`)  
**Database:** PostgreSQL 15 (via Homebrew)  
**Repo:** `git@github.com:groverpuneet/stock-analyzer.git`

### One-time setup (already done — for reference only)

```bash
# Install Homebrew
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install PostgreSQL
brew install postgresql@15
brew services start postgresql@15

# Clone repo
git clone git@github.com:groverpuneet/stock-analyzer.git
cd stock-analyzer

# Create virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Make terminal always ready (run once, permanent)

```bash
echo 'cd ~/stock-analyzer' >> ~/.zshrc
echo 'source ~/stock-analyzer/venv/bin/activate' >> ~/.zshrc
```

After this, every new terminal window automatically activates the venv and
navigates to the project. You'll see `(venv)` in your prompt.

---

## 2. Every Time You Open a Terminal

If you didn't add the lines to `~/.zshrc` above, run these manually:

```bash
cd ~/stock-analyzer
source venv/bin/activate
export DATABASE_URL='postgresql://puneetgrover@localhost/stock_analyzer'
```

> **Why DATABASE_URL every time?** Environment variables set with `export` only
> live for the current terminal session. For a permanent fix, add it to `~/.zshrc`:
> `echo "export DATABASE_URL='postgresql://puneetgrover@localhost/stock_analyzer'" >> ~/.zshrc`

---

## 3. Git & GitHub

### Remote URL

The repo uses **SSH** (not HTTPS). This is important — HTTPS requires a token
every time, SSH uses your key silently.

```bash
# Verify it's SSH (should show git@github.com, not https://)
git remote -v

# If it ever shows https://, fix it with:
git remote set-url origin git@github.com:groverpuneet/stock-analyzer.git
```

### SSH Key

Your SSH key is already set up at `~/.ssh/id_ed25519` and registered on GitHub.
To verify it still works:

```bash
ssh -T git@github.com
# Should print: Hi groverpuneet! You've successfully authenticated...
```

### Daily Git Workflow

```bash
# See what changed
git status

# Stage all changes
git add -A

# Commit with a descriptive message
git commit -m "feat: describe what you built"

# Push to GitHub — always do this before ending a session
git push
```

> **Rule:** Never end a working session without `git push`. Code only exists
> in one place — GitHub. Everything else is temporary.

### Commit Message Conventions

```
feat:     new feature or integration
fix:      bug fix
refactor: code restructure, no behaviour change
docs:     documentation only
chore:    dependency updates, config changes
```

---

## 4. Database & Migrations

### Connection

```bash
# Test DB is running
brew services list | grep postgresql

# Start if not running
brew services start postgresql@15

# Connect directly (useful for debugging)
psql stock_analyzer
```

### Alembic — Schema Version Control

**Never manually alter the database schema.** Every change goes through Alembic.

```bash
# Apply all pending migrations (run after every git pull)
alembic upgrade head

# Check current migration version
alembic current

# See migration history
alembic history

# Create a new migration (after deciding on a schema change)
alembic revision -m "describe the change"
# Then edit the file created in alembic/versions/ to write upgrade() and downgrade()

# Roll back one migration (emergency use only)
alembic downgrade -1
```

### Migration Files

Located in `alembic/versions/`. Named `YYYYMMDD_XXXX_description.py`.

| Migration | What it does |
|-----------|-------------|
| `0001_baseline_existing_schema` | Original tables: stocks, daily_prices, quotes, fundamentals, technical_indicators, watchlist |
| `0002_add_integrations_and_multi_market` | New tables for all integrations + multi-market `market` column |
| `0005_allow_null_stock_id_in_news_sentiment` | Makes news_sentiment.stock_id nullable for unmatched headlines |
| `0006_add_stock_scores_and_baselines` | stock_scores + indicator_baselines tables for monthly model refresh |
| `0009_add_expiry_calendar` | expiry_calendar table — weekly/monthly/quarterly F&O expiry dates from Kite NFO |

### Useful DB Queries

```bash
# See all tables
python3 -c "
import psycopg2, os
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()
cur.execute(\"SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename\")
for r in cur.fetchall(): print(r[0])
"

# See refresh log (what ran, when, how many rows)
python3 -c "
import psycopg2, os
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()
cur.execute(\"SELECT source, tier, status, completed_at, rows_upserted FROM data_refresh_log ORDER BY tier, source\")
for r in cur.fetchall(): print(f'{r[0]:<24} {r[1]:<10} {r[2]:<12} {str(r[3])[:16]} {r[4]}')
"
```

---

## 5. Project Structure

```
stock-analyzer/
│
├── alembic/                    # DB migration files — one per schema change
│   └── versions/
│       ├── 0001_baseline...py
│       ├── 0002_integrations...py
│       └── 0003_whatsapp...py
│
├── analysis/
│   ├── calculate_indicators.py # RSI, SMA, EMA, MACD, Bollinger Bands
│   └── generate_signals.py     # BUY/SELL/WATCH signal logic
│
├── data_collectors/
│   ├── collect_watchlist_data.py   # Kite Connect OHLCV (daily)
│   ├── fii_dii_collector.py        # FII/DII flows from NSE (daily)
│   ├── nse_actions_collector.py    # Corporate actions + earnings calendar (event)
│   ├── screener_collector.py       # Fundamentals from Screener.in (weekly)
│   └── whatsapp_collector.py       # WhatsApp expert chat analysis (daily, future)
│
├── database/
│   └── migrate_integrations.py # Legacy — replaced by Alembic. Do not use.
│
├── logs/                       # Rotating log files (10MB max, 7 backups)
│   └── *.log                   # One file per module, gitignored
│
├── scheduler/
│   └── daily_tasks.py          # Master scheduler — all tiers wired here
│
├── utils/
│   ├── db.py                   # DB connection, refresh_log context manager
│   └── logger.py               # Centralised logging config
│
├── whatsapp_exports/           # Drop .txt exports here (gitignored)
│
├── alembic.ini                 # Alembic config (reads DATABASE_URL from env)
├── requirements.txt            # Python dependencies
├── ENGINEERING.md              # This file
└── README.md                   # Project overview
```

---

## 6. Data Refresh Schedule

The scheduler runs via `python scheduler/daily_tasks.py`. All times are IST.

| Time | Days | Task | Source |
|------|------|------|--------|
| 07:00 | Mon–Fri | WhatsApp signals | `whatsapp_exports/` |
| 16:00 | Mon–Fri | OHLCV prices | Kite Connect |
| 16:15 | Mon–Fri | Technical indicators | Calculated locally |
| 16:30 | Mon–Fri | FII/DII flows | NSE API |
| 16:45 | Mon–Fri | Corporate actions + earnings | NSE API |
| 17:00 | Mon–Fri | Signal report | All of the above |
| 08:00 | Sunday | Fundamentals | Screener.in |
| 08:30 | Sunday | RBI macro indicators | RBI DBIE API |
| 09:00 | Sunday | Insider trades + Bulk deals | NSE API |
| 09:30 | Sunday | Sector indices | NSE |
| 06:00 | 1st Sunday of month | Model refresh (scores + FinBERT + baselines) | Local DB |

### Scheduler Commands

```bash
# Start the live scheduler
python scheduler/daily_tasks.py

# Run everything right now (for testing)
python scheduler/daily_tasks.py --test

# Check what ran and when
python scheduler/daily_tasks.py --status

# Run individual tasks manually
python scheduler/daily_tasks.py --screener
python scheduler/daily_tasks.py --fii
python scheduler/daily_tasks.py --actions
python scheduler/daily_tasks.py --insider
python scheduler/daily_tasks.py --model
python scheduler/daily_tasks.py --whatsapp
```

---

## 7. Dagster Orchestration

### Why we migrated from APScheduler to Dagster

APScheduler worked for a single-machine single-market setup, but has three failure modes
we hit immediately upon expanding to multi-market:
1. **No dependency graph** — APScheduler fires jobs by time, not by data readiness. If
   `kite_ohlcv` runs late, `technical_indicators` fires at 16:15 on stale data anyway.
   Dagster declares `nse_technical_indicators` as a downstream asset of `nse_raw_prices`
   and only runs it after prices are materialized.
2. **No UI or run history** — APScheduler has no visibility into what ran, when, and why
   it failed. Dagster's webserver shows asset lineage, run logs, and failure alerts.
3. **Multi-market scheduling** — NSE runs IST, US runs EST. APScheduler needs separate
   cron expressions in UTC and manual conversion. Dagster schedules declare timezone
   directly (`execution_timezone="Asia/Kolkata"`).

### Asset graph

```
kite_infra group (daily 08:00 IST):
  kite_token_refreshed

nse_daily group (Mon-Fri 16:00 IST):
  nse_raw_prices → nse_technical_indicators
                                           ↘
  nse_fii_dii_flows ───────────────────────→ nse_signals
  nse_corporate_actions ───────────────────↗
  nse_news_sentiment ──────────────────────↗

nse_weekly group (Sunday 07:30 IST):
  nse_stock_universe, nse_fundamentals, nse_macro_indicators, nse_insider_trades

nse_monthly group (1st of month 02:00 IST):
  nse_model_refresh

us_daily group (Mon-Fri 16:30 EST — placeholder):
  us_raw_prices → us_signals
```

### Running Dagster

**Local dev (simplest — no Docker needed):**
```bash
pip install dagster dagster-webserver
dagster dev -w workspace.yaml        # UI at http://localhost:3000
```

**Local dev with Postgres storage** (run history persists across restarts):
```bash
docker compose up dagster-db -d      # start just the metadata DB
export DAGSTER_HOME="$PWD/dagster"
export DAGSTER_POSTGRES_USER=dagster_user DAGSTER_POSTGRES_PASSWORD=dagster_pass
export DAGSTER_POSTGRES_DB=dagster_db DAGSTER_POSTGRES_HOSTNAME=localhost DAGSTER_POSTGRES_PORT=5433
dagster dev -w workspace.yaml
```

**Full Docker stack:**
```bash
docker compose up --build            # first build ~15-20 min (PyTorch ~2.5GB)
docker compose up                    # subsequent starts (layer cache)
# Open http://localhost:3000
```
Note: host Postgres must allow Docker bridge network connections.
See docker-compose.yml Prerequisites section.

**Triggering jobs manually:**
```bash
# Via Dagster CLI
dagster job execute -f dagster/repository.py --job nse_daily_job
dagster asset materialize -f dagster/repository.py --select nse_fii_dii_flows

# Via task runner (still available for debugging)
python scheduler/daily_tasks.py --fii
python scheduler/daily_tasks.py --status
```

### Key files (modular layout)
`dagster/repository.py` is a thin entrypoint — it only imports the modules below and
assembles `Definitions`. Assets/jobs/schedules/sensors live in their own files.

| File | Purpose |
|------|---------|
| `dagster/repository.py` | Thin orchestration: imports modules → `Definitions(assets, jobs, schedules, sensors)` |
| `dagster/assets/kite_infra.py` | `kite_token_refreshed` |
| `dagster/assets/nse_daily.py` | nse_raw_prices, technical_indicators, fii_dii, corporate_actions, news_sentiment, fno_data, block_deals, bse_bulk_deals, signals |
| `dagster/assets/nse_weekly.py` | stock_universe, fundamentals, macro_indicators, insider_trades, shareholding_pattern, expiry_calendar, nse_google_trends |
| `dagster/assets/nse_monthly.py` | `nse_model_refresh` (loads project-root `jobs/model_refresh.py` by file path — see below) |
| `dagster/assets/us_daily.py` | us_raw_prices, us_insider_trades, us_signals |
| `dagster/assets/us_weekly.py` | `us_macro` (FRED) |
| `dagster/jobs.py` | All `define_asset_job`s (incl. `nse_news_job` used by the sensor) → `ALL_JOBS` |
| `dagster/schedules.py` | All `ScheduleDefinition`s → `ALL_SCHEDULES` |
| `dagster/sensors.py` | `watchlist_change_sensor` (60s) → `ALL_SENSORS` |
| `workspace.yaml` / `dagster/workspace.docker.yaml` | Code locations (python_file / grpc_server) |
| `dagster/Dockerfile`, `docker-compose.yml` | Image + four services (dagster-db, user-code, webserver, daemon) |
| `scheduler/daily_tasks.py` | Manual CLI task runner (no APScheduler — Dagster schedules instead) |

**Import note (name collisions):** the local `dagster/` dir is put first on `sys.path` so
sibling modules import by bare name (`from jobs import …`, `from assets.nse_daily import …`).
This shadows the project-root `jobs/` package on the bare name `jobs`, so `nse_monthly`
loads `jobs/model_refresh.py` by explicit file path. `from dagster import …` still resolves
to the installed library (our dir isn't a `dagster`-named package on the path).

### Watchlist change sensor
`watchlist_change_sensor` (in `dagster/sensors.py`, `default_status=RUNNING`) polls every 60s,
finds Default-watchlist **NSE** stocks with no `daily_prices` in 30 days that aren't already in
`watchlist_changes` (migration 0011), logs them, and triggers `nse_daily_job → nse_weekly_job →
nse_news_job`. MF instruments (NAV, not OHLCV) are excluded so they don't fire forever.
One-off backfill of stale watchlist prices: `data_collectors/backfill_watchlist_prices.py`.

### Historical P/E + valuation percentile
`data_collectors/screener_pe_history_collector.py` seeds ~10yr **monthly** P/E history per NSE
watchlist stock from Screener's chart API (`/api/company/{id}/chart/?q=Price to Earning…`), stored
in `fundamentals` (date, pe_ratio, `source='screener_pe_history'`). It then computes, per stock,
where current P/E sits within its own 5yr range → `stock_scores.pe_percentile` (migration 0012;
0 = cheapest, 100 = most expensive). **Use the `screener_pe_history` series consistently** for
history/percentile — the weekly `screener` top-ratio P/E uses a different earnings basis and would
skew the comparison. Folded into the weekly `nse_fundamentals` asset so it refreshes automatically.

### Web UI additions
- `GET /api/dashboard` — every datum per watchlist stock (price/52w, technicals, fundamentals +
  P/E percentile, sentiment, scores, insider 30d) + market-wide FII/DII. Frontend dashboard is a
  sortable/filterable table (no sector column in the schema — filters are signal/score/search).
- `GET /api/stocks/{id}/pe-history` — P/E series + current vs 1yr/5yr avg + p25/p75 zones (chart).
- `POST /api/refresh/trigger-all` / `trigger-failed` — bulk-launch Dagster assets (deduped).

---

## 9. Integrations Roadmap

Priority order — build top to bottom.

| Priority | Integration | Frequency | Status |
|----------|------------|-----------|--------|
| 1 | Screener.in fundamentals | Weekly | ✅ Built |
| 2 | NSE corporate actions + earnings | Event/daily | ✅ Built |
| 3 | FII/DII flows | Daily | ✅ Built |
| 4 | News sentiment (Claude API) | Daily | ⬜ Next |
| 5 | RBI macro data (DBIE) | Weekly | ⬜ Stub only |
| 6 | Insider / bulk deals | Weekly | ✅ Built |
| 7 | WhatsApp expert chats | Daily | ⬜ Built, needs auto-export |
| — | US market (NYSE/NASDAQ) | — | ⬜ Future |
| — | Other markets (LSE etc.) | — | ⬜ Future |

### WhatsApp Note

Manual `.txt` export is not acceptable. Automation options when we get to it:
- **WhatsApp Business API** — requires registered business number
- **whatsapp-web.js** — mirrors WhatsApp Web session, grey area on ToS
- Decision to be made when this reaches priority

---

## 10. Engineering Decisions Log

A record of *why* we made key decisions. Future-you will thank present-you.

### Why Alembic instead of manual SQL scripts?
Schema changes are code. They need version control, history, and the ability
to roll back. `database/migrate_integrations.py` was the old approach — it
worked once but was not repeatable or reversible. Alembic gives us numbered
migrations with `upgrade()` and `downgrade()` that apply in order.

### Why virtualenv instead of system Python?
Each project needs its own isolated dependencies. System Python is shared across
your whole Mac — installing one package can break another project. `venv` gives
this project its own copy of Python and packages.

### Why `DATABASE_URL` environment variable instead of hardcoded credentials?
Credentials in source code get committed to Git and become public. Environment
variables live only in your terminal session and never touch the repo.

### Why SSH instead of HTTPS for GitHub?
HTTPS requires a Personal Access Token on every push (or keychain, which has
its own password). SSH uses a key pair — authenticate once during setup, silent
forever after.

### Why `ON CONFLICT DO NOTHING` / `DO UPDATE` on all inserts?
Collectors run on a schedule and can be re-run manually. Without conflict
handling, re-running would crash with duplicate key errors. With it, re-running
is safe — already-existing rows are silently skipped or updated.

### Why a `data_refresh_log` table?
So the scheduler can answer: "did this source run successfully today?" without
reading log files. The `needs_refresh(source, min_hours)` function in `utils/db.py`
queries this table to skip redundant runs.

### Why `RotatingFileHandler` for logging?
`print()` disappears. Log files persist but can grow forever and fill disk.
`RotatingFileHandler` with `maxBytes=10MB` and `backupCount=7` caps total log
storage at ~80MB regardless of how long the process runs.

### Why separate `whatsapp_messages` (raw) and `news_sentiment` (scored)?
Raw messages are stored first, scoring happens separately. This means if we
improve the Claude prompt in 3 months, we can re-score all historical messages
without re-exporting from WhatsApp. Always preserve raw data.

### Why `market` column on `stocks` instead of separate tables per market?
One schema, all markets. NSE stocks have `market='NSE'`, future NYSE stocks
will have `market='NYSE'`. Queries filter by market. No schema change needed
when expanding to new markets.

---

## 11. Common Errors & Fixes

### `zsh: command not found: alembic` or `python`
Virtual environment not activated.
```bash
cd ~/stock-analyzer
source venv/bin/activate
```

### `FAILED: No 'script_location' key found`
You're not in the project root, or `alembic.ini` doesn't exist.
```bash
pwd   # should show /Users/puneetgrover/stock-analyzer
ls alembic.ini   # should find the file
```

### `KeyError: '0001'` during alembic upgrade
A migration file is missing from `alembic/versions/`. Check:
```bash
ls alembic/versions/
```

### `fatal: Authentication failed` on git push
Remote is set to HTTPS instead of SSH. Fix:
```bash
git remote set-url origin git@github.com:groverpuneet/stock-analyzer.git
git push
```

### `connection refused` on psycopg2 connect
PostgreSQL isn't running.
```bash
brew services start postgresql@15
```

### Heredoc gets stuck (terminal shows `heredoc>`)
You pasted a multi-line block and the closing `EOF` got cut off.
Press `Ctrl+C` to cancel, then use the Python approach instead:
```bash
python3 << 'PYEOF'
open('filename.py', 'w').write('''file content here''')
PYEOF
```

### Python 3.9 vs 3.10+ type hint syntax
float | None syntax only works on Python 3.10+. On Python 3.9, remove the type hints.
Fix: python3 -c "content = open('file.py').read(); content = content.replace('-> float | None:', '-> float:'); open('file.py', 'w').write(content)"

### Kite access token expires daily
Run python3 data_collectors/kite_test.py, open the login URL, paste the request_token from the redirect URL. Token saved to .kite_access_token.

### Scheduler imports WhatsApp collector which may not exist
If daily_tasks.py throws ModuleNotFoundError for whatsapp_collector, remove that import line until the collector is deployed.

### base64 file transfer method
When pasting large files fails, use base64 encoding via Python:
  In sandbox: python3 -c "import base64; print(base64.b64encode(open('file.py','rb').read()).decode())"
  On Mac: python3 -c "import base64; open('file.py','wb').write(base64.b64decode('BASE64STRING'))"

## Token Optimization Standard

When using LLM APIs (Claude, etc.) in this project, optimize for minimum token usage:

1. **System prompts**: Keep concise — no verbose instructions or examples
2. **Batch over serial**: Score all headlines in one API call, not one per headline
3. **Local models first**: Use FinBERT/local models for bulk scoring; reserve API calls for high-value decisions only
4. **Structured outputs**: Request JSON responses with specific field names to minimize parsing overhead
5. **Context window discipline**: Never pass full article text when headline suffices
6. **Tiered scoring**: Use cheap/free local model (FinBERT) for all stocks, expensive API only for signals above threshold (e.g. score > 0.5)
7. **File transfers**: Split base64 transfers at ~9KB chunks to avoid corruption

## MoSPI Macro — GDP + WPI (DONE)
- Source: official MoSPI MCP server at `https://mcp.mospi.gov.in/mcp` via `fastmcp.Client` (async).
  Tools: list_datasets, get_indicators, get_metadata, get_data. Workflow: get_indicators -> get_metadata
  (to discover arbitrary filter codes) -> get_data.
- Collector: `data_collectors/mospi_macro_collector.py`. Wired into `nse_macro_indicators` Dagster asset.
- GDP: dataset NAS, indicator_code=5 (Gross Domestic Product), base_year=2011-12, series=Current,
  frequency_code=2 (Quarterly). Stores gdp_constant_price (real), gdp_current_price (nominal) in INR crore,
  and gdp_growth_yoy (computed from constant_price vs same quarter prior FY).
- WPI: dataset WPI, base_year=2011-12, major_group_code=1000000000 (headline index), fetched per calendar
  year. Stores wpi_index and wpi_inflation (computed YoY from index).
- Date convention: quarter-end date for GDP, month-start date for WPI — accumulates a time series in
  macro_indicators; re-runs upsert on (date, market, indicator).
- **Requires venv310 (Python 3.10+)** — fastmcp does not support 3.9.

## RBI DBIE — Forex Reserves + Bank Credit Growth (DONE)
- Source: RBI DBIE portal `data.rbi.org.in` driven by Playwright (headless Chromium,
  `ignore_https_errors=True` — sidesteps Mac LibreSSL 2.8.3 rejecting RBI's TLS).
- Collector: `data_collectors/rbi_dbie_collector.py`. Wired into `nse_macro_indicators` Dagster asset.
- **Gateway auth crack (key insight):** the DBIE SPA mints a per-session token stored in
  `sessionStorage['sessionId']` (format `<5 rand chars>0<epoch_ms>197`). The gateway at
  `/CIMS_Gateway_DBIE/GATEWAY/SERVICES/` accepts it as the `authorization` header (+ `channelkey: key2`).
  We load the home page so the SPA mints the token, read it from sessionStorage, then **replay** the
  gateway calls via the shared request context. Forging the token fails ("Internal Server Error");
  intercepting responses corrupts binary (Chromium re-encodes the XLSX to a UTF-8 string). Replay with
  the live token is the only clean path.
- Forex reserves: `dbie_foreignExchangeReserves` service, reserveCode in {TR, FCA, GOLD, SDR, IMF},
  frequency Weekly. Amount is raw USD -> stored as USD_billion. Total + components latest value;
  12-week trend kept for the total.
- Bank credit / deposits: the official "Macro-economic Indicators" XLSX
  (`download/dbie_FileDownloadHDFSAction`, Filename "MacroeconomicIndicators"), Fortnightly sheet —
  Bank Credit, Non-Food Credit, Aggregate Deposits outstanding (₹ crore). YoY growth computed vs the
  fortnight ~365 days earlier. Requires openpyxl.
- Indicators (source='rbi_dbie'): forex_reserves_total/_fca/_gold/_sdr/_imf, bank_credit_outstanding,
  bank_credit_growth_yoy, non_food_credit_growth_yoy, aggregate_deposits_growth_yoy, credit_deposit_ratio.

## Docker note — Python 3.10 required
- `dagster/Dockerfile` is now `python:3.10-slim` (was 3.9). fastmcp (MoSPI MCP) needs 3.10+.
- After pulling these changes run `docker compose up --build` once so the image picks up the new base
  image + openpyxl. Code changes alone need no rebuild (live `.:/opt/dagster/app` mount); dependency/
  base-image changes do. docker-compose.yml needs no edits — it builds from the Dockerfile.

## MoSPI CPI/IIP note
- data.gov.in API key broken — superseded by the MoSPI MCP server (see "MoSPI Macro" above; also serves CPI, IIP).

## Tier 3 — US Markets

### US stock universe (migration 0010)
- 30 NYSE/NASDAQ large/mega caps seeded into `stocks` (market = exchange = 'NYSE'|'NASDAQ').
- Synthetic `instrument_token = 9_000_000_000 + index` (Kite tokens are < 4e9, so no collision).
- SEC CIK is resolved at runtime (not stored) via www.sec.gov/files/company_tickers.json.
- Migration 0010 also seeds data_refresh_log rows: us_prices, fred_macro, sec_form4, us_news.

### US OHLCV — Polygon.io (DONE)
- Source: Polygon.io Aggregates (Bars) API, free tier (5 calls/min, end-of-day, ~2yr history).
- Key: `POLYGON_API_KEY` in `.env` (loaded via python-dotenv, same pattern as Kite collectors).
  Also added to `docker-compose.yml` `x-stock-env` anchor and `.env.example`.
- Collector: `data_collectors/polygon_prices_collector.py`. Dagster asset `us_raw_prices` (us_daily).
- Rate limiting: sleep ~13s between calls (<5/min) + exponential backoff on HTTP 429.
- `collect_us_prices(lookback_days=7)` for the daily asset; `collect_us_prices(years=2)` (default) for a
  one-time backfill. Bars upsert on the existing daily_prices unique key (stock_id, date).
- Polygon `t` is epoch ms at ET-midnight start-of-day → convert to calendar date (UTC date is correct).

### FRED US macro (DONE)
- Source: FRED keyless `fredgraph.csv` download endpoint (no API key, unlike the JSON API).
- Collector: `data_collectors/fred_macro_collector.py`. Dagster asset `us_macro` (us_weekly group,
  Sunday 07:00 EST via us_weekly_job).
- **Fetch crack (important):** FRED is behind Akamai. Python's TLS stack (requests/urllib/httpx,
  even on OpenSSL 3.6) gets its ClientHello dropped → `RemoteDisconnected`. curl's fingerprint is
  accepted. Additionally Akamai **tarpits a custom `User-Agent`** on this endpoint (connection hangs,
  0 bytes received) — so we shell out to curl with its **default UA** and `--http1.1`. curl is already
  installed in the Dagster image (`dagster/Dockerfile`), so the collector is portable host↔container.
- Series → indicators (market='US', source='fred'):
  FEDFUNDS→fed_funds_rate, CPIAUCSL→cpi_index + cpi_inflation_yoy (computed YoY),
  UNRATE→unemployment_rate, GDPC1→gdp_real + gdp_growth_yoy (computed YoY). ~4yr history, 227 rows.
- Date convention: FRED observation_date as-is; upsert on (date, market, indicator).

### SEC EDGAR Form 4 — US insider trades (DONE)
- Source: SEC EDGAR (free). Unlike FRED, SEC accepts Python `requests` TLS directly. SEC fair-access
  policy **requires a descriptive User-Agent with a contact email** — we send the project owner's.
  Throttled to 0.15s/request (SEC guidance is <10 req/s).
- Collector: `data_collectors/sec_form4_collector.py`. Dagster asset `us_insider_trades` (us_daily group).
- Flow: `www.sec.gov/files/company_tickers.json` (ticker→CIK, fetched once) →
  `data.sec.gov/submissions/CIK<cik>.json` (filings.recent; keep form=='4' filed within 30 days) →
  fetch the ownership XML and parse `nonDerivativeTable/nonDerivativeTransaction`.
- **Raw-XML gotcha:** `primaryDocument` points at the XSL-rendered HTML (`xslF345X06/form4.xml`).
  The raw XML is the same path with that render prefix stripped — take `primaryDocument.rsplit('/',1)[-1]`.
- Leaf values: Form 4 fields are sometimes wrapped in a `<value>` child, sometimes bare — handle both.
- Mapping → insider_trades (source='sec_form4'): transaction code P→BUY, S→SELL, else the raw code
  (M exercise, F tax, A grant, G gift, X, C…); person_category from isDirector/isOfficer(+title)/
  isTenPercentOwner; price NULL for grants/exercises. Upsert on (stock_id,date,person_name,transaction,quantity).

### US news sentiment (DONE — folded into the existing pipeline)
- The proactive news pipeline (`data_collectors/news_collector.py`, asset `nse_news_sentiment`) is
  one unified multi-market collector. US support = added feeds + universe matching; no new asset/table.
- US feeds added to MARKET_FEEDS: Google News US, CNBC, MarketWatch, Yahoo Finance, Seeking Alpha.
- `build_stock_universe()` already loads ALL stocks, so the seeded US universe is matchable. Expanded
  `ABBREVIATION_MAP` with the 30 US names (Apple, BofA, Nvidia, Nike, …).
- **Precision guards (important for US tickers):** flashtext is case-insensitive, so bare US tickers
  that are common English words (e.g. COST→"cost") or ≤2 chars (V, MA, KO, HD) generated false
  positives. We now skip adding the bare ticker as a keyword when `len(symbol) <= 2` or symbol is in
  `COMMON_WORD_TICKERS`; those stocks still match via company name/abbreviation. A `_GENERIC_FIRST_WORDS`
  set also stops the "first word of name" heuristic from adding generic keywords ("Bank of America"→"Bank").
- US headlines land on their RSS published date in news_sentiment (so query a date window, not just today).

## TODO: MF Portfolio Holdings
- AMFI portfolio holdings page is JS-rendered (Next.js) — not scrapable with requests
- Each AMC publishes monthly holdings on their own website by 10th of month
- Options to explore:
  1. mfapi.in — has clean JSON NAV data, check if holdings available
  2. Playwright/Selenium for JS rendering (set up when building UI)
  3. Some AMCs provide direct CSV downloads — could scrape those individually
- For now track via bulk deals (MF bulk purchases show up there)
