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

## Current state & next steps (2026-07-06)

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

### Next up (see TASKS.md DONE list + Current Status)
1. **Upstox account** — was erroring on signup; retry. Once the **Analytics token** exists
   (activate segments, keep ₹0 balance): build OHLCV → quotes → option-chain collectors,
   each its own commit (live-test then commit). Target tables already exist (migration 0025).
2. **Backtest foundation** — needs NO Upstox account, can proceed in parallel:
   - **P0b** survivorship security master: add `listing_date/delisting_date/is_active` to
     `stocks`; seed current universe; populate listing_date from NSE `EQUITY_L.csv`; flag
     delisted-name bias.
   - **P0c** point-in-time signal replay: backward-compatible `as_of` param on
     `signals/engine.py` + pillars (defaults to today → live behavior unchanged) +
     historical `signal_explanations` backfill.
   - **Phase 1**: vectorbt EOD engine behind a Strategy interface, PIT data provider,
     costs/slippage, risk metrics, new isolated `backtest` schema.

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
