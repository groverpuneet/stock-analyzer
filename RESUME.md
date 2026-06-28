# How to Resume — Stock Analyzer

## Quick Start (new account on same machine)
cd ~/stock-analyzer  (or git clone if first time)
source venv/bin/activate
cp /path/to/.env.example .env  # fill in your keys

## Start Claude Code
cd ~/stock-analyzer && claude

## Paste this to resume:
Read SESSION_SUMMARY.md, TASKS.md, and ENGINEERING.md first.
Check git log --oneline -10 to see latest work.
Find next unchecked item in TASKS.md and continue.
Never access personal portfolio, holdings, P&L, or positions.
Never call kite.place_order() or any order placement endpoint.
If you hit a rate limit, wait and retry. Log waits to STATUS.md.

## Notes for second account on same Mac
- PostgreSQL runs system-wide — both accounts share the same DB automatically
- FinBERT model: re-downloads per user account (~500MB) unless you symlink:
  mkdir -p ~/.cache && ln -s /Users/PRIMARY_ACCOUNT/.cache/huggingface ~/.cache/huggingface
- .env file: copy manually, never commit
- venv: run python3 -m venv venv && pip install -r requirements.txt once per account

## Current priorities (June 28, 2026)
1. Verify Dagster running — docker ps + localhost:3000
2. Fix MF portfolio holdings — mfdata.in API
3. Build Kite TOTP auto-refresh — pyotp + playwright
4. Tier 2 integrations — see TASKS.md
