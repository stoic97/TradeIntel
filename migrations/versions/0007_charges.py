"""charges: the broker's own charges file, kept apart from the trips

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-05 00:30:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

import services.production.db.types as dbtypes

revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('charge_statement',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('trader_id', sa.Integer(), nullable=False),
    sa.Column('raw_file_id', sa.Integer(), nullable=False),
    sa.Column('reader', sa.String(length=64), nullable=False),
    sa.Column('days', sa.Text(), nullable=False),
    sa.Column('uploaded_at', dbtypes.AwareDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['raw_file_id'], ['raw_file.id'], ),
    sa.ForeignKeyConstraint(['trader_id'], ['trader.id'], ),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('charge_statement')
