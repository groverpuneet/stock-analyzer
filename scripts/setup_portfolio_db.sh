#!/usr/bin/env bash
# One-time portfolio DB setup (role + pgcrypto + read-only market grants).
# The portfolio schema + tables + schema-grants are created by alembic migration 0023.
# Password is read from PORTFOLIO_DB_PASSWORD (default matches .env PORTFOLIO_DATABASE_URL).
set -euo pipefail

DB="${1:-stock_analyzer}"
# Password comes from the environment or is parsed from PORTFOLIO_DATABASE_URL in .env —
# never hardcoded here (keeps the credential out of git).
ENV_FILE="$(dirname "$0")/../.env"
if [[ -z "${PORTFOLIO_DB_PASSWORD:-}" && -f "$ENV_FILE" ]]; then
  PORTFOLIO_DB_PASSWORD="$(grep -oE 'postgresql://portfolio_user:[^@]+@' "$ENV_FILE" | sed -E 's#.*:([^@]+)@#\1#')"
fi
PW="${PORTFOLIO_DB_PASSWORD:?set PORTFOLIO_DB_PASSWORD or add PORTFOLIO_DATABASE_URL to .env}"

psql "$DB" <<SQL
CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'portfolio_user') THEN
    CREATE ROLE portfolio_user LOGIN PASSWORD '${PW}';
  END IF;
END \$\$;

-- portfolio_user needs read-only public market data to validate symbols + price holdings
GRANT USAGE ON SCHEMA public TO portfolio_user;
GRANT SELECT ON public.stocks, public.daily_prices, public.earnings_calendar,
      public.fii_dii_flows, public.pledging_alerts, public.insider_trades TO portfolio_user;
SQL

echo "portfolio_user + pgcrypto ready. Now run: alembic upgrade head"
