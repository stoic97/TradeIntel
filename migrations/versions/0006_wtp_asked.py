"""wtp_asked: which Journal the willingness-to-pay question was put on (TICKET-826)

Revision ID: 0006_wtp_asked
Revises: 0005
Create Date: 2026-11-05 01:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

import services.production.db.types as dbtypes

revision = '0006_wtp_asked'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('wtp_asked',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('trader_id', sa.Integer(), nullable=False),
    sa.Column('journal_id', sa.Integer(), nullable=False),
    sa.Column('asked_at', dbtypes.AwareDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['journal_id'], ['journal.id'], ),
    sa.ForeignKeyConstraint(['trader_id'], ['trader.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('trader_id')
    )


def downgrade() -> None:
    op.drop_table('wtp_asked')
