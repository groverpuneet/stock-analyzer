"""Allow NULL stock_id in news_sentiment for unmatched headlines.

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-20

Engineering note:
  The proactive news collector stores ALL headlines, not just ones matched
  to a watchlist stock. Headlines with no stock match get stock_id = NULL.
  This preserves everything — nothing is lost, and unmatched headlines can
  be queried later when we add more stocks to the universe.

  The UNIQUE constraint (stock_id, date, headline) needs updating too —
  NULL != NULL in SQL, so multiple NULL stock_id rows with the same headline
  would all be inserted. We add a partial unique index instead.
"""
from alembic import op

revision = '0005'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade():
    # Drop the foreign key constraint that prevents NULL
    op.execute("""
        ALTER TABLE news_sentiment
        ALTER COLUMN stock_id DROP NOT NULL
    """)

    # Add index for fast lookup of unmatched headlines
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_news_sentiment_no_stock
        ON news_sentiment(date, source)
        WHERE stock_id IS NULL
    """)

    # Add index for opportunity detection:
    # "find all stocks mentioned 5+ times today that aren't in my watchlist"
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_news_sentiment_stock_date
        ON news_sentiment(stock_id, date)
        WHERE stock_id IS NOT NULL
    """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_news_sentiment_no_stock")
    op.execute("DROP INDEX IF EXISTS idx_news_sentiment_stock_date")
    op.execute("ALTER TABLE news_sentiment ALTER COLUMN stock_id SET NOT NULL")
