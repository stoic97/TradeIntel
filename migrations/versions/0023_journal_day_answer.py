"""journal_day_answer: his answers to the day's questions (TICKET-915)

Yes, no or wrong, a new row for each answer, with the question as he saw it and the day it
is about. No typed word: a fixed answer. Numbered 0023 on main's head 0021 (Pawan, 26 Nov 2026);
first written as 0014 on 0013, before main's chain moved on.

Revision ID: 0023
Revises: 0021
"""
import sqlalchemy as sa
from alembic import op

import services.production.db.types as dbtypes

revision = '0023'
down_revision = '0021'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('journal_day_answer',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('trader_id', sa.Integer(), nullable=False),
    sa.Column('journal_id', sa.Integer(), nullable=False),
    sa.Column('trading_day', sa.String(length=10), nullable=False),
    sa.Column('question_key', sa.String(length=32), nullable=False),
    sa.Column('question_text', sa.Text(), nullable=False),
    sa.Column('answer', sa.String(length=5), nullable=False),
    sa.Column('answered_at', dbtypes.AwareDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['journal_id'], ['journal.id'], ),
    sa.ForeignKeyConstraint(['trader_id'], ['trader.id'], ),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('journal_day_answer')