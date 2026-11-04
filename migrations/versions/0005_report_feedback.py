"""report feedback (TICKET-825)

Revision ID: 0005_report_feedback
Revises: 0004
"""
import sqlalchemy as sa
from alembic import op

import services.production.db.types as dbtypes

revision = '0005_report_feedback'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('report_feedback',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('trader_id', sa.Integer(), nullable=False),
    sa.Column('import_id', sa.Integer(), nullable=False),
    sa.Column('trading_day', sa.String(length=10), nullable=False),
    sa.Column('answer', sa.String(length=16), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('answered_at', dbtypes.AwareDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['import_id'], ['import.id'], ),
    sa.ForeignKeyConstraint(['trader_id'], ['trader.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('trader_id', 'import_id', 'trading_day')
    )


def downgrade() -> None:
    op.drop_table('report_feedback')
