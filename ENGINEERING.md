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

## Git Author Configuration (CRITICAL)

Every session must verify the git author **before any commits**:

```bash
git config user.email        # MUST show puneetgrover1991@gmail.com
```

If it's wrong, fix it immediately:

```bash
git config --global user.email "puneetgrover1991@gmail.com"
git config --global user.name  "Puneet Grover"
# IMPORTANT: also check for a repo-local override that shadows --global:
git config --local user.email  # if set to anything else, this wins over global
```

**Gotcha (this bit us):** the original wrong-email bug lived in the **repo-local**
`.git/config` (`user.email = your.email@example.com`), which shadows `--global`.
`git config --global …` alone does **not** fix it — always confirm the *effective*
value with `git config user.email`.

A **pre-commit hook** (`.git/hooks/pre-commit`) now blocks any commit whose effective
email isn't `puneetgrover1991@gmail.com`, firing before all other checks. (The hook
is local to this clone — it isn't version-controlled, so re-add it on a fresh clone.)

**History note:** on 2026-07-02 all 86 existing commits (which carried the placeholder
`your.email@example.com`) were rewritten to the correct email via
`git filter-branch --env-filter` and force-pushed. `git rebase --root` could **not**
be used because `node_modules/` was committed early in history and its per-commit tree
checkouts collide with the on-disk (now gitignored) `node_modules`. `filter-branch`
rewrites commit metadata only, so it sidesteps that.

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

### Data quality framework
Gap detection, completeness scoring, and auto-retry across every domain. Core module:
`utils/data_quality.py`.

- **Schema** (migrations 0014-0016): `data_quality_log` (one open row per gap, resolved when
  data appears), `data_refresh_log` gains `expected_rows / actual_rows / coverage_pct /
  gaps_detected / retry_count` (status now also `partial` / `retrying`), `stock_scores` gains
  `data_completeness_score`.
- **Gap detectors** (per domain): ohlcv (behind cohort's latest trading day — NSE vs US date skew
  handled), indicators (no RSI/MACD on latest price date), fundamentals (no full row in 7d), news
  (none in 7d), shareholding (none), signals (no composite_score today). Each logs/resolves rows
  in `data_quality_log`.
- **Completeness score** (0-100, weighted): price 20 · indicators 20 · signals 20 · fundamentals 15
  · shareholding 15 · news 10. News is weighted low because availability is limited for small caps.
- **post_run audit**: `nse_daily_audit` (after `nse_signals`) and `nse_weekly_audit` (after
  fundamentals/shareholding) run `run_audit(domain)` — detect gaps, update completeness, append a
  STATUS.md note for any stock < 80%.
- **Auto-retry**: `data_quality_sensor` (every 30 min) finds unresolved gaps older than 1h and
  triggers `nse_gap_fill_job` → `fill_gaps()`, which re-runs **only the affected stocks** (per-stock
  for ohlcv/indicators/fundamentals; collector-level for news/scores), bumps `retry_count`, then
  re-detects to resolve fixed gaps. Never re-runs a full job for partial data.
- **enhanced `refresh_log`**: collectors set `meta['expected']` (and optional `meta['gaps']`); the
  context manager records coverage_pct + `partial` status automatically.
- **Web UI**: dashboard has a colour-coded **Quality** column (green ≥90 / yellow 70-90 / red <70),
  a global **Data health** indicator in the header on every page (`/api/quality/health`), and
  per-source open-gap counts on the Data Sources page.

Note on residual gaps: ETFs (NIFTYBEES/ITBEES/PHARMABEES) have no company fundamentals/shareholding,
and most small caps have no daily news — these are data-availability limits the framework surfaces
honestly (low completeness), not collector bugs.

### RULE: daily_prices writes → recompute indicators
**Any write to `daily_prices` must be followed by technical indicator recomputation for affected
stocks. This is enforced via Dagster asset dependencies and the `indicator_recompute_sensor`.**

Three layers enforce this:
1. **Dagster dependency** — `nse_technical_indicators` declares `deps=[nse_raw_prices]`, so the daily
   16:00 `nse_daily_job` always recomputes indicators right after prices land.
2. **Watchlist sensor** — `watchlist_change_sensor` triggers `nse_daily_job` (which includes the
   indicators step) when a new stock is added.
3. **Safety net** — an `AFTER INSERT` trigger on `daily_prices` (migration 0013) queues affected
   `stock_id`s into `recompute_queue`. `indicator_recompute_sensor` (every 5 min) drains the queue
   via `nse_indicator_recompute_job` → `recompute_queued_indicators()`, recomputing only those
   stocks then clearing them. This catches prices that land outside the normal job (manual backfills,
   one-off scripts). `analysis/calculate_indicators.py` honours `DATABASE_URL` so it works in-container.

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

### Unified Refresh Control (`/refresh` page, Session K)
One page replaces the old **Data Sources** + **Refresh Status** pages. Backend:
`webapp/backend/routers/refresh.py`.
- `GET /api/refresh/control` — the whole page in one call: collectors grouped by
  market × cadence (India Daily/Weekly/Monthly, US Daily/Weekly, + an "Other/Untracked"
  catch-all so nothing is hidden), each with real status, rows, duration, last-run,
  next scheduled run (computed from the Dagster cron via a small `_next_run` helper),
  a derived overall health, and `last_full_refresh` (= when `signals`, the terminal
  daily asset, last succeeded).
- `GET /api/refresh/health` — compact `{level,color,counts}` for the global header
  banner (`DataHealth.tsx`), computed the **same way** as `/control` so no two pages
  can disagree.
- `POST /api/refresh/trigger` / `trigger-all` / `trigger-failed` / `trigger-audit` —
  launch one / all / only-unhealthy / the data-quality audit assets. All go through
  the same `dagster_client.launch_asset` (implicit `__ASSET_JOB`, single-asset select).
- Frontend polls `/control` every 5s while any job is running; individual + bulk Run
  buttons; India/US visually separated.

**Single source of truth = `data_refresh_log`, NOT the Dagster run status.**
Diagnosed root cause of the old "one page says failed, another says fine": on this
8GB M1 a Dagster run can finish its step successfully (collector writes its rows and
marks `data_refresh_log` = `success`) yet the **run** is still marked `FAILURE` at
finalize (`stepsFailed: 0`, empty `RunFailureEvent` — the run-worker subprocess exits
abnormally after the step). The old `RefreshButton` polled the Dagster *run* status and
so showed phantom failures. Every page now reads the collector's own result from
`data_refresh_log`. A run that is *killed mid-step* (process reaped before the
`refresh_log` context manager closes the row) leaves `status='running'`; `refresh.py`
treats a `running` row with a `completed_at` set, or started > 3h ago, as **`stalled`**
(shown red, with a Run button) — these were the two orphaned rows (shareholding_pattern,
analyst_targets) surfacing as the original "failures".

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

## Telegram Bot — Daily Digest + Commands + AI Queries (Session H, DONE)

A Telegram bot with three faces, all reading public market data only (no portfolio/holdings/P&L):

**Files**
- `data_collectors/context_builder.py` — the single DB data layer. Pure read functions
  (`get_fear_greed`, `get_top_signals`, `get_macro_snapshot`, `get_risk_alerts`, `get_fii_dii`,
  `get_upcoming_earnings`, `get_top_news`, `get_signal_detail`, `get_fundamentals`, `get_insider`,
  `get_watchlist_scores`, `get_13f_holdings`) plus `build_context(query)` which assembles a
  compact (<~2000 token) relevant-only context block for the AI. `extract_symbols()` resolves
  tickers mentioned in free text. `get_top_news` dedupes by headline (the proactive news collector
  can tag one wire story to several tickers).
- `data_collectors/telegram_bot.py` — Telegram I/O (raw REST via `requests`, long-poll `getUpdates`
  + `sendMessage`, 4096-char chunking), command router, AI orchestration, and the digest builder.
- `dagster/assets/notifications.py` — `telegram_daily_digest` asset (notifications group).

**No new dependencies.** Uses `requests` + `python-dotenv` (already installed). Telegram, Gemini,
and Groq are all called over their plain REST/HTTP APIs — no SDKs — which keeps the image light and
the token usage minimal (system prompt is terse, context is relevant-rows-only).

**Three faces**
1. *Daily digest* — `send_daily_digest()` builds and pushes the 08:00 IST morning message
   (Fear&Greed India/US with ↑/↓ trend, top-5 by composite score, risk alerts, FII/DII, earnings
   next 7d, top news by |sentiment|, macro VIX/PCR/repo). Pushed by the `telegram_daily_digest`
   Dagster asset → `telegram_digest_job` → `telegram_digest_daily` schedule (08:00 IST, after
   `kite_token_job`). Reads already-materialized tables, so it runs after the overnight pipelines.
2. *Rule commands* (instant, no AI): `/start /help /top5 /fear /macro /alerts /earnings /news`
   `/signal SBIN /fundamentals SBIN /insider SBIN /watchlist`. Routed in `handle_text()`; each
   handler is wrapped so a failure returns a friendly message, never a traceback.
3. *AI queries* — any non-command text. `answer_ai_query()` builds context then asks **Gemini**
   (`gemini-1.5-pro`, `GEMINI_MODEL` override) first; on 429/quota/error falls back to **Groq**
   (`llama-3.3-70b-versatile`, `GROQ_MODEL` override); if both unavailable, returns a rule-based
   apology that still includes the data context so the user always gets something useful.

**Security / privacy**
- The listener only answers messages from `TELEGRAM_CHAT_ID` (if set) — strangers who find the bot
  are ignored. The AI system prompt forbids personalised advice / position sizing.
- All errors are logged to STATUS.md (`log_status()`), never sent raw to Telegram.

**Required `.env` keys** (see `.env.example`): `TELEGRAM_BOT_TOKEN` (BotFather), `TELEGRAM_CHAT_ID`
(@userinfobot), `GEMINI_API_KEY` (aistudio.google.com), `GROQ_API_KEY` (console.groq.com).

**Run**
```bash
# Interactive listener (commands + AI) — long-running process
venv310/bin/python data_collectors/telegram_bot.py
# Persistent on Mac: scripts/com.stockanalyzer.telegram.plist (KeepAlive)
#   cp scripts/com.stockanalyzer.telegram.plist ~/Library/LaunchAgents/ && launchctl load -w ...
# Preview the digest without sending:
venv310/bin/python data_collectors/telegram_bot.py --digest
# Build + send the digest now:
venv310/bin/python data_collectors/telegram_bot.py --digest --send
# Inspect the AI context for a query:
venv310/bin/python data_collectors/context_builder.py "Why is SBIN looking strong?"
```
The digest also fires automatically via Dagster:
`dagster asset materialize -f dagster/repository.py --select telegram_daily_digest`.

## TODO: MF Portfolio Holdings
- AMFI portfolio holdings page is JS-rendered (Next.js) — not scrapable with requests
- Each AMC publishes monthly holdings on their own website by 10th of month
- Options to explore:
  1. mfapi.in — has clean JSON NAV data, check if holdings available
  2. Playwright/Selenium for JS rendering (set up when building UI)
  3. Some AMCs provide direct CSV downloads — could scrape those individually
- For now track via bulk deals (MF bulk purchases show up there)

## Security (Session J)

### Secret management
- **Never commit .env or .kite_access_token** — both are in `.gitignore`
- Use `.env.example` as a template; copy to `.env` and fill in real values
- Pre-commit hook blocks commits containing secret patterns (sk-ant-, AKIA, ghp_, etc.)
- Rotate all credentials every 90 days (Kite, Polygon, Groq, Gemini, Telegram)

### Database access
- **Collectors (read-write):** use `DATABASE_URL` (puneetgrover user)
- **Webapp (read-only):** use `WEBAPP_DATABASE_URL` (stock_reader user)
- The stock_reader user has SELECT-only permissions; cannot INSERT/UPDATE/DELETE
- Create the user:
  ```sql
  CREATE USER stock_reader WITH PASSWORD 'yourpassword';
  GRANT CONNECT ON DATABASE stock_analyzer TO stock_reader;
  GRANT USAGE ON SCHEMA public TO stock_reader;
  GRANT SELECT ON ALL TABLES IN SCHEMA public TO stock_reader;
  ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO stock_reader;
  ```

### Authentication
- Webapp uses session-based auth with bcrypt password hashing
- Set `WEBAPP_USERNAME` and `WEBAPP_PASSWORD_HASH` in `.env`
- Generate hash: `python3 -c "import bcrypt; print(bcrypt.hashpw(b'password', bcrypt.gensalt()).decode())"`
- Session cookies are signed with `SESSION_SECRET` (itsdangerous)
- Sessions expire after 24 hours

### Rate limiting
- All `/api/*` endpoints: max 100 requests/minute per IP (slowapi)
- Login endpoint: max 10 requests/minute per IP
- `/api/health` is exempt from rate limiting
- Returns 429 with Retry-After header when exceeded

### Security headers
All responses include:
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `X-XSS-Protection: 1; mode=block`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Strict-Transport-Security: max-age=31536000` (HTTPS only)

### SQL injection prevention
- All queries use parameterized statements (`%s` placeholders with psycopg2)
- Table names in dynamic queries are validated against hardcoded allowlists
- No f-string SQL with user input

### Pre-commit hook
Located at `.git/hooks/pre-commit`. Blocks commits containing:
- API keys (sk-ant-, AKIA, ghp_, gho_, AIza, xoxb-, xoxp-)
- Hardcoded passwords/secrets (api_key=, password=, secret=, token=)
Bypass with `git commit --no-verify` (use sparingly)

### Known vulnerabilities (accepted risk)
- `autobahn==19.11.2` (PYSEC-2020-25): Header injection in websocket redirects.
  Pinned by kiteconnect; we don't use websocket redirects.
- `requests==2.32.3` (CVE-2024-47081, CVE-2026-25645): .netrc leak and temp file issue.
  We don't use .netrc or `extract_zipped_paths()`

## Session K — Volume indicators, FII/DII trend, US watchlist add, India/US demarcation

### Volume indicators (migration 0022)
- `technical_indicators`: `volume_sma_20`, `volume_ratio` (vol/sma20), `volume_trend`
  (RISING/FALLING/FLAT from 5d-vs-prior-5d avg), `obv` (On Balance Volume, cumulative),
  `vwap` (rolling 20d volume-weighted typical price — daily bars have no intraday ticks,
  so a rolling VWAP is the meaningful overlay).
- `stock_scores.volume_signal`: VOLUME_BREAKOUT (ratio>2 & +1%), VOLUME_BREAKDOWN (ratio>2 & -1%),
  LOW_VOLUME_MOVE (ratio<0.5). Computed in `analysis/calculate_indicators.py` and upserted onto
  the stock's **latest existing** score row (not CURRENT_DATE) so it sits with composite_score
  and never shadows it in the dashboard's DISTINCT-ON-latest query.
- Backfill: `process_all_watchlist_stocks('Default', limit=600)` (full ~2yr). New US stocks get
  indicators at add-time; daily runs recompute via the existing indicators asset / recompute_queue.

### FII/DII day-over-day (niftytrader history source)
- NSE `fiidiiTradeReact` returns only the latest day. `fetch_from_niftytrader()` (webapi.niftytrader.in
  Resource/fii-dii-activity-data) supplies ~30 trading days of net values (matches NSE to the paisa;
  no buy/sell split). `store_fii_dii_net()` upserts net-only with COALESCE so it never clobbers the
  richer same-day NSE row. `collect_fii_dii()` tops up the 30-day window every run; `--backfill` flag
  for a one-shot fill. Endpoint `/api/macro/fii-dii-trend` computes 5d/10d MAs, cumulatives, streaks.

### US watchlist add (Polygon.io)
- `webapp/backend/us_stock_add.py`: `search_us_tickers(q)` (Polygon `v3/reference/tickers`,
  type=CS, active) and `add_us_stock(ticker)` — resolves name/exchange (MIC→NYSE/NASDAQ),
  inserts into `stocks` with a synthetic instrument_token in the reserved US band
  [9.0e9, 9.1e9), fetches 2yr OHLCV via the Polygon collector's `_fetch_bars`/`_store`,
  computes indicators, adds to the watchlist. Market-data writes use the read-write DATABASE_URL.
  Endpoints: `GET /api/watchlist/search-us`, `POST /api/watchlist/add-us`.

### India/US demarcation (frontend)
- `components/MarketBadge.tsx` — flag + exchange badge (India=orange, US=blue), reused everywhere.
- Dashboard: market filter (India default), Market + Volume columns, US price in $ / India in ₹.
- Macro: separate India (RBI/MoSPI/RBI-DBIE) and US (FRED) sections + FII/DII trend chart.
- Opportunities: market filter + badges. Stock detail: VWAP overlay, coloured volume + 20d avg, OBV.
- Raw-data tables render exchange/market as badges. SmartMoney/RiskAlerts/Fear&Greed already demarcated.

## Session K (part 2) — Private Portfolio (localhost-only, TOTP, encrypted)

A private portfolio module, deliberately isolated from all public/market surfaces.
Manual CSV/Excel upload only — NEVER touches Kite/brokerage positions/holdings APIs.

**Isolation & access control (all three required for every /api/portfolio/*):**
1. localhost only — `portfolio_localhost_guard` middleware + `is_localhost()` reject any
   request carrying proxy/tunnel forwarding headers (ngrok always sets `X-Forwarded-For`/
   `X-Forwarded-Host`; the local Vite proxy uses changeOrigin WITHOUT xfwd, so local
   requests carry none). Blocked attempts → 403 + `portfolio.audit_log`.
2. main session (existing puneet login) — enforced by the global auth middleware.
3. portfolio TOTP session — `portfolio_session` cookie, 15-min TTL, issued only after a
   valid 6-digit TOTP (`PORTFOLIO_TOTP_SECRET`). Signed with `PORTFOLIO_ENCRYPTION_KEY`.

**Data at rest:** separate `portfolio` schema owned by `portfolio_user` (rights ONLY on
that schema + read-only market data). Sensitive columns (quantity, buying_price,
target_price, stop_loss) are BYTEA, encrypted with pgcrypto `pgp_sym_encrypt`; the key
lives only in `.env` (`PORTFOLIO_ENCRYPTION_KEY`), never in the DB, never logged.
`stock_reader` (webapp read-only user) is denied all access to the portfolio schema.

**Never stored:** unrealized P&L, current value, pnl% — always computed at query time from
`daily_prices`. Portfolio tables are NOT in the raw-data router allowlist (`/api/data/*` → 404).

**Files:** `webapp/backend/portfolio_db.py` (isolated conn + audit + enc key),
`portfolio_auth.py` (TOTP + localhost + 15-min session + `require_portfolio`),
`routers/portfolio.py` (verify-totp, status, preview, save, holdings, holding PUT/DELETE,
summary, alerts, signal-overlay). Migration `0023` (schema + tables + grants).
Frontend `pages/Portfolio.tsx` (TOTP gate, drag/drop upload + preview, dashboard, 15-min
countdown). Dashboard shows 💼 badge + vs-stop/target columns for held stocks (overlay,
localhost+TOTP only). `scripts/setup_portfolio_db.sh` documents role/pgcrypto setup.

**Alerts:** computed locally (stop-loss breach/approach, target reached, >5% drop, earnings
7d, insider selling, pledging, FII selling streak). Telegram gets alert type + direction
ONLY (`"⚠️ SBIN approaching stop loss zone"`) — never quantities, prices, or P&L.

**.env additions:** `PORTFOLIO_TOTP_SECRET`, `PORTFOLIO_ENCRYPTION_KEY`, `PORTFOLIO_DATABASE_URL`.
One-time: `psql` create role `portfolio_user` + `CREATE EXTENSION pgcrypto` (see setup script).

## Signal Generation — Legacy (Session A-E)

`analysis/generate_signals.py` produced ONE verdict per stock from the latest 5 daily
bars: RSI<30→BUY (STRONG<25) / RSI>70→SELL (STRONG>75); SMA50/200 golden/death cross;
price/SMA20 cross; MACD signal cross; Bollinger touches; volume spike (>2× trailing-4-day
avg)→WATCH. Verdict = majority of BUY vs SELL hits. Text-only report (no storage). The
webapp mirrored these rules live in `webapp/backend/signals_engine.py`. Kept for the CLI
report; the multi-dimensional engine below supersedes it for the dashboard.

## Signal Engine — 4-Pillar Explainable (Session L)

`signals/` package. Each pillar returns a 0-100 score (50 = neutral, >50 bullish) plus
plain-English reasoning[], key_metrics{}, and contrary_indicators[]; missing data is
handled gracefully (pillar score = None, ignored by the combiner).

- **technical** (`signals/technical.py`): SMA trend stack, RSI, MACD (cross + histogram),
  Bollinger, volume_ratio confirmation, OBV trend, VWAP.
- **fundamental** (`fundamental.py`): P/E percentile vs own 5yr, ROE, debt/equity, OPM,
  revenue/PAT YoY (quarterly_financials), earnings surprise, analyst consensus/upside,
  FII%/promoter trend (shareholding), pledging.
- **flow** (`flows.py`): insider (30d), bulk/SAST/13F, MF ownership MoM, news sentiment
  7d + trend, market-wide FII/DII streak + 5d cumulative, options PCR/VIX, Google Trends.
- **external** (`external.py`): fresh DuckDuckGo news + Google-News RSS headlines, VADER
  compound + catalyst keyword hits. The network fetch is cached in
  `signal_explanations.cached_external_sentiment` for 6h (`external_cache_expiry`).
- **advisor** (`advisor.py`): Pillar-5 placeholder (weight 0; `advisor_opinions` table).

`combiner.py` reweights per horizon — SHORT: T50/F5/FL30/E15, MID: T25/F30/FL25/E20,
LONG: T10/F60/FL20/E10 — into overall_score → signal_type (STRONG_BUY≥75, BUY≥60,
WATCH>41, SELL>26, else STRONG_SELL), confidence (pillar agreement), all_pillars_agree,
contrary_indicators, and what_would_change. `engine.py` orchestrates + persists 3 rows
(one per horizon) into `signal_explanations` (migration 0024).

Dagster `nse_signals` (deps incl. `nse_news_sentiment`) calls `signals.engine.run_signals`.
Backfill: `python -c "from signals.engine import run_signals; run_signals()"` (add
`skip_external=True` to skip the web fetch). API: `GET /api/signals/explained` (list) +
`GET /api/signals/explanation/{stock_id}?horizon=`. UI: `/signal-engine` (🎯 Signal Engine)
— 3 horizon tabs, pillar badges, all-pillars-agree filter, slide-in explanation panel.
Note: `duckduckgo_search` emits a deprecation warning (renamed to `ddgs`); still functional.
