"""leaving card (B7): shown once, and his answer or "Not now"

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-03 16:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

import services.production.db.types as dbtypes

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('leaving_card_shown',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('trader_id', sa.Integer(), nullable=False),
    sa.Column('copy_version', sa.String(length=32), nullable=False),
    sa.Column('shown_at', dbtypes.AwareDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['trader_id'], ['trader.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('trader_id')
    )
    op.create_table('leaving_card_answer',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('trader_id', sa.Integer(), nullable=False),
    sa.Column('outcome', sa.String(length=16), nullable=False),
    sa.Column('answer', sa.Text(), nullable=True),
    sa.Column('copy_version', sa.String(length=32), nullable=False),
    sa.Column('answered_at', dbtypes.AwareDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['trader_id'], ['trader.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('trader_id')
    )


def downgrade() -> None:
    op.drop_table('leaving_card_answer')
    op.drop_table('leaving_card_shown')
