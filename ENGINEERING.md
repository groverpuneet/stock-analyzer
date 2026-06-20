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
7. [Integrations Roadmap](#7-integrations-roadmap)
8. [Engineering Decisions Log](#8-engineering-decisions-log)
9. [Common Errors & Fixes](#9-common-errors--fixes)

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
| `0003_add_whatsapp_messages_table` | WhatsApp raw message store |

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
| 09:00 | Sunday | Sector indices | NSE |

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
python scheduler/daily_tasks.py --whatsapp
```

---

## 7. Integrations Roadmap

Priority order — build top to bottom.

| Priority | Integration | Frequency | Status |
|----------|------------|-----------|--------|
| 1 | Screener.in fundamentals | Weekly | ✅ Built |
| 2 | NSE corporate actions + earnings | Event/daily | ✅ Built |
| 3 | FII/DII flows | Daily | ✅ Built |
| 4 | News sentiment (Claude API) | Daily | ⬜ Next |
| 5 | RBI macro data (DBIE) | Weekly | ⬜ Stub only |
| 6 | Insider / bulk deals | Weekly | ⬜ Not started |
| 7 | WhatsApp expert chats | Daily | ⬜ Built, needs auto-export |
| — | US market (NYSE/NASDAQ) | — | ⬜ Future |
| — | Other markets (LSE etc.) | — | ⬜ Future |

### WhatsApp Note

Manual `.txt` export is not acceptable. Automation options when we get to it:
- **WhatsApp Business API** — requires registered business number
- **whatsapp-web.js** — mirrors WhatsApp Web session, grey area on ToS
- Decision to be made when this reaches priority

---

## 8. Engineering Decisions Log

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

## 9. Common Errors & Fixes

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
