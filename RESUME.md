# How to Resume — Stock Analyzer

## Quick Start (new account on same machine)
cd ~/stock-analyzer  (or git clone if first time)
source venv/bin/activate
cp /path/to/.env.example .env  # fill in your keys

## Start Claude Code
cd ~/stock-analyzer && claude

## Paste this to resume:
First: verify git config user.email shows puneetgrover1991@gmail.com — if not: git config --global user.email 'puneetgrover1991@gmail.com' && git config --global user.name 'Puneet Grover'
Read SESSION_SUMMARY.md, TASKS.md, and ENGINEERING.md first.
Check git log --oneline -10 to see latest work.
Find next unchecked item in TASKS.md and continue.
Never access personal portfolio, holdings, P&L, or positions on external surfaces.
Two-plane brokers (2026-07-05): Upstox (read-only Analytics token) + Angel = DATA plane, unfunded/order-incapable; Zerodha Kite = EXECUTION plane only (funded, isolated, not yet built). Never import an order-capable credential into data/research/backtest code.
If you hit a rate limit, wait and retry. Log waits to STATUS.md.

## Notes for second account on same Mac
- PostgreSQL runs system-wide — both accounts share the same DB automatically
- FinBERT model: re-downloads per user account (~500MB) unless you symlink:
  mkdir -p ~/.cache && ln -s /Users/PRIMARY_ACCOUNT/.cache/huggingface ~/.cache/huggingface
- .env file: copy manually, never commit
- venv: run python3 -m venv venv && pip install -r requirements.txt once per account

## Current state & next steps (2026-07-12)

### Recently shipped (committed + pushed to origin/main)
- **Data-source decision post-Kite** (`DATA_SOURCES_RESEARCH.md`) → two-plane architecture:
  Upstox (read-only Analytics token, primary) + Angel One SmartAPI (failover) = DATA plane
  (unfunded/order-incapable); Zerodha Kite = EXECUTION plane only (funded, isolated).
- **Upstox instrument master** (`5735307`): migration 0025 (`fno_instruments`,
  `intraday_prices`, `option_chain_snapshots`; `stocks.isin/instrument_key`). 43,002 F&O
  contracts + 2,375 equities keyed. `data_collectors/upstox_instruments_collector.py`
  (public, no token). Dagster asset `nse_upstox_instruments`.
- **Backtest Phase 0a** (`91a1ca0`): `adjustment_factors` (migration 0026) from yfinance
  `.splits`; `backtest/adjustments.py` (source-state-aware). Finding: `daily_prices`
  (Yahoo Close) is already SPLIT-adjusted, not dividend-adjusted — split factors apply
  only to a RAW series (future Upstox candles), never to current daily_prices.
- **Backtest Phase 0b** (`a550f3d`): `stocks.listing_date/delisting_date/is_active`
  (migration 0027) + `survivorship_collector.py` matching against NSE's official mainboard
  list. Positive-evidence only — never flips is_active to FALSE. See TASKS.md DONE list.
- **Backtest Phase 0c** (`4e83e94`): backward-compatible `as_of` param threaded through
  `signals/engine.py` + all pillars — every unbounded query now has a `<= as_of` cutoff.
  `run_signals(as_of=...)` is the new historical `signal_explanations` backfill path.
  See TASKS.md DONE list.
- **Incident (2026-07-12):** native `dagster dev` was fully dead 2026-07-06→07-12 (6 days,
  undetected) because `scripts/watchdog.sh` only checked Docker containers, a leftover from
  before the native-Dagster migration. Restarted; also fixed a real silent-data-loss bug in
  `sec_13f_collector.py` (missing `conn.rollback()` after a failed insert dropped the rest of
  that filer's batch). Full detail in STATUS.md's 2026-07-12 incident entry.
- **Backtest Phase 1** (`bfde543`): migration 0028 `backtest` schema (runs/equity_curve/
  trades); `backtest/data_provider.py` (PIT price+signal panels), `backtest/strategy.py`
  (`Strategy` ABC + `SignalThresholdStrategy` reusing `signals/` as the alpha model),
  `backtest/engine.py` (`run_backtest()` — vectorbt `Portfolio.from_signals`, cash-shared
  across the universe, CAGR/Sharpe/Sortino/maxDD/hit-rate/turnover). `vectorbt` added to
  requirements.txt. See TASKS.md DONE list — Phase 0a/0b/0c/1 are all now done.

### Next up (see TASKS.md DONE list + Current Status)
1. **Upstox account** — signup in progress (KYC/document review, awaiting approval; the
   dev/API console is gated behind an actual trading+demat account, no API-only tier). Once
   the **Analytics token** exists (activate segments, keep ₹0 balance): build OHLCV → quotes
   → option-chain collectors, each its own commit (live-test then commit). Target tables
   already exist (migration 0025).
2. **Historical signal backfill** — `signal_explanations` only has ~3 real days so far
   (started 2026-07-02) vs `daily_prices`'s full 2024-06-28+ history. To run a *meaningful*
   multi-year `SignalThresholdStrategy` backtest, loop `signals.engine.run_signals(as_of=d)`
   over each trading day in `daily_prices` for the watchlist — likely slow (many DB queries
   per stock per day), so plan for a long-running/background job, not an inline call.
3. **Backtest usage** — `backtest/engine.py:run_backtest()` is callable now (see docstring);
   no webapp UI or Dagster wiring yet — it's a deliberately-invoked analysis call, not a
   scheduled asset. Consider a `/backtest` webapp page reading `backtest.runs`/`equity_curve`
   once there's enough signal history backfilled to make results meaningful.
4. **Not yet fixed:** `scripts/watchdog.sh` docker-vs-native gap — check git log, may already
   be addressed by a commit outside this session (`5c899da`/`a524d28`) — verify before
   re-doing this work.

### Env / creds (see .env.example)
- Upstox: `UPSTOX_API_KEY/SECRET/REDIRECT_URI` + `UPSTOX_ANALYTICS_TOKEN`.
- Angel (failover): `ANGEL_*`.

### Gotchas
- `alembic` env.py needs `DATABASE_URL` exported (it does not read .env):
  `export DATABASE_URL=postgresql://puneetgrover@localhost/stock_analyzer`
- Pre-commit hook flags `ENGINEERING.md`'s own security-pattern docs as false positives →
  commit those with `--no-verify` (author-email guard still satisfied via git config).
- `dagster asset materialize -f` CLI has a sys.path quirk (`No module named data_collectors`)
  for ALL assets — verify via the running `dagster dev` server (workspace.yaml sets
  working_directory), not the ephemeral CLI.
