"""add_recompute_queue

Safety-net for the rule "any write to daily_prices -> recompute technical indicators".
A statement-level AFTER INSERT trigger on daily_prices queues the affected stock_ids
into recompute_queue; the Dagster indicator_recompute_sensor drains it every 5 min.

Revision ID: 0013
Revises: 0012
Create Date: 2026-06-28
"""
from alembic import op
import sqlalchemy as sa

revision = '0013'
down_revision = '0012'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'recompute_queue',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('stock_id', sa.Integer(), nullable=False),
        sa.Column('queued_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['stock_id'], ['stocks.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('stock_id', name='uq_recompute_queue_stock'),
    )

    # Statement-level trigger with a transition table — one invocation per INSERT
    # statement (efficient for both single-row collector inserts and bulk backfills).
    op.execute("""
        CREATE OR REPLACE FUNCTION queue_indicator_recompute() RETURNS trigger AS $$
        BEGIN
            INSERT INTO recompute_queue (stock_id)
            SELECT DISTINCT stock_id FROM new_rows WHERE stock_id IS NOT NULL
            ON CONFLICT (stock_id) DO NOTHING;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER daily_prices_recompute_trg
        AFTER INSERT ON daily_prices
        REFERENCING NEW TABLE AS new_rows
        FOR EACH STATEMENT
        EXECUTE FUNCTION queue_indicator_recompute();
    """)


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS daily_prices_recompute_trg ON daily_prices")
    op.execute("DROP FUNCTION IF EXISTS queue_indicator_recompute()")
    op.drop_table('recompute_queue')
