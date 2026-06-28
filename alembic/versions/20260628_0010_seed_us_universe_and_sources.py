"""Seed US stock universe (NYSE/NASDAQ large caps) + US data_refresh_log sources.

Tier 3 US market integrations reuse the existing multi-market schema:
  - daily_prices / insider_trades / news_sentiment keyed by stock_id -> need US rows in stocks
  - macro_indicators keyed by (date, market, indicator) -> market='US', no stock_id

US stocks get synthetic instrument_token = 9_000_000_000 + index (Kite tokens are < 4e9,
so this never collides). market = exchange = 'NASDAQ' or 'NYSE'. SEC CIK is resolved at
runtime by the EDGAR collector via www.sec.gov/files/company_tickers.json, so it is not
stored here.

Revision ID: 0010
Revises: 0009
Create Date: 2026-06-28
"""
from alembic import op

revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None

# (tradingsymbol, company name, exchange) — curated US mega/large caps across sectors.
US_UNIVERSE = [
    ("AAPL",  "Apple Inc.",                       "NASDAQ"),
    ("MSFT",  "Microsoft Corporation",            "NASDAQ"),
    ("NVDA",  "NVIDIA Corporation",               "NASDAQ"),
    ("AMZN",  "Amazon.com Inc.",                  "NASDAQ"),
    ("GOOGL", "Alphabet Inc. Class A",            "NASDAQ"),
    ("META",  "Meta Platforms Inc.",              "NASDAQ"),
    ("TSLA",  "Tesla Inc.",                       "NASDAQ"),
    ("AVGO",  "Broadcom Inc.",                    "NASDAQ"),
    ("AMD",   "Advanced Micro Devices Inc.",      "NASDAQ"),
    ("NFLX",  "Netflix Inc.",                     "NASDAQ"),
    ("ORCL",  "Oracle Corporation",               "NYSE"),
    ("CRM",   "Salesforce Inc.",                  "NYSE"),
    ("ADBE",  "Adobe Inc.",                       "NASDAQ"),
    ("INTC",  "Intel Corporation",                "NASDAQ"),
    ("CSCO",  "Cisco Systems Inc.",               "NASDAQ"),
    ("JPM",   "JPMorgan Chase & Co.",             "NYSE"),
    ("BAC",   "Bank of America Corporation",      "NYSE"),
    ("V",     "Visa Inc.",                        "NYSE"),
    ("MA",    "Mastercard Incorporated",          "NYSE"),
    ("WMT",   "Walmart Inc.",                     "NYSE"),
    ("HD",    "The Home Depot Inc.",              "NYSE"),
    ("COST",  "Costco Wholesale Corporation",     "NASDAQ"),
    ("PG",    "The Procter & Gamble Company",     "NYSE"),
    ("KO",    "The Coca-Cola Company",            "NYSE"),
    ("PEP",   "PepsiCo Inc.",                     "NASDAQ"),
    ("JNJ",   "Johnson & Johnson",                "NYSE"),
    ("UNH",   "UnitedHealth Group Incorporated",  "NYSE"),
    ("XOM",   "Exxon Mobil Corporation",          "NYSE"),
    ("DIS",   "The Walt Disney Company",          "NYSE"),
    ("NKE",   "Nike Inc.",                        "NYSE"),
]

_TOKEN_BASE = 9_000_000_000

# New data_refresh_log sources for Tier 3 collectors.
# Note: US news has no separate source — the unified news_collector.collect_news()
# fetches NSE + US feeds together and logs under the existing 'news_sentiment' source.
US_SOURCES = [
    ("us_prices",      "daily"),
    ("fred_macro",     "weekly"),
    ("sec_form4",      "daily"),
]


def upgrade():
    for i, (symbol, name, exchange) in enumerate(US_UNIVERSE):
        token = _TOKEN_BASE + i
        op.execute(
            f"""
            INSERT INTO stocks (instrument_token, tradingsymbol, name, exchange, market, segment, instrument_type)
            VALUES ({token}, '{symbol}', '{name.replace("'", "''")}', '{exchange}', '{exchange}', '{exchange}', 'EQ')
            ON CONFLICT DO NOTHING
            """
        )
    for src, tier in US_SOURCES:
        op.execute(
            f"""
            INSERT INTO data_refresh_log (source, tier, status, rows_upserted)
            VALUES ('{src}', '{tier}', 'never_run', 0)
            ON CONFLICT (source) DO NOTHING
            """
        )


def downgrade():
    symbols = "', '".join(s for s, _, _ in US_UNIVERSE)
    op.execute(f"DELETE FROM stocks WHERE market IN ('NYSE','NASDAQ') AND tradingsymbol IN ('{symbols}')")
    srcs = "', '".join(s for s, _ in US_SOURCES)
    op.execute(f"DELETE FROM data_refresh_log WHERE source IN ('{srcs}')")
