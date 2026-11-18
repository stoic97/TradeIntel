"""journal_remember_answer: "Do you remember this day?" and the day's age (TICKET-906)

Yes or no, once per trader per trading day, with the day's age in calendar days, so the
seven-day window (NEW_DAY_WITHIN_DAYS) can be checked against what traders answer. No
typed word: a fixed answer, counted.

Revision ID: 0013
Revises: 0012
"""
import sqlalchemy as sa
from alembic import op

import services.production.db.types as dbtypes

revision = '0013'
down_revision = '0012'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('journal_remember_answer',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('trader_id', sa.Integer(), nullable=False),
    sa.Column('journal_id', sa.Integer(), nullable=False),
    sa.Column('trading_day', sa.String(length=10), nullable=False),
    sa.Column('answer', sa.String(length=3), nullable=False),
    sa.Column('day_age_days', sa.Integer(), nullable=False),
    sa.Column('answered_at', dbtypes.AwareDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['journal_id'], ['journal.id'], ),
    sa.ForeignKeyConstraint(['trader_id'], ['trader.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('trader_id', 'trading_day')
    )


def downgrade() -> None:
    op.drop_table('journal_remember_answer')
