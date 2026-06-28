"""refresh_log_quality_cols

Coverage/quality columns on data_refresh_log. status now also takes
'partial' / 'retrying' (no schema change — it's a free-text varchar).

Revision ID: 0015
Revises: 0014
Create Date: 2026-06-28
"""
from alembic import op
import sqlalchemy as sa

revision = '0015'
down_revision = '0014'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('data_refresh_log', sa.Column('expected_rows', sa.Integer(), nullable=True))
    op.add_column('data_refresh_log', sa.Column('actual_rows', sa.Integer(), nullable=True))
    op.add_column('data_refresh_log', sa.Column('coverage_pct', sa.Numeric(), nullable=True))
    op.add_column('data_refresh_log', sa.Column('gaps_detected', sa.JSON(), nullable=True))
    op.add_column('data_refresh_log', sa.Column('retry_count', sa.Integer(),
                                                nullable=False, server_default='0'))


def downgrade():
    for col in ('retry_count', 'gaps_detected', 'coverage_pct', 'actual_rows', 'expected_rows'):
        op.drop_column('data_refresh_log', col)
