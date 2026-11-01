"""guess answer (B6): the trader's one guess before the reveal

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-01 18:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

import services.production.db.types as dbtypes

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('guess_answer',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('trader_id', sa.Integer(), nullable=False),
    sa.Column('answer', sa.String(length=32), nullable=False),
    sa.Column('labels_version', sa.String(length=32), nullable=False),
    sa.Column('import_id', sa.Integer(), nullable=False),
    sa.Column('answered_at', dbtypes.AwareDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['import_id'], ['import.id'], ),
    sa.ForeignKeyConstraint(['trader_id'], ['trader.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('trader_id')
    )


def downgrade() -> None:
    op.drop_table('guess_answer')
