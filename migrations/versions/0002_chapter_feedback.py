"""chapter feedback (B4): one answer per chapter per trader, and its optional reason

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-01 17:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

import services.production.db.types as dbtypes

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('chapter_feedback',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('trader_id', sa.Integer(), nullable=False),
    sa.Column('chapter', sa.Integer(), nullable=False),
    sa.Column('answer', sa.String(length=16), nullable=False),
    sa.Column('import_id', sa.Integer(), nullable=False),
    sa.Column('answered_at', dbtypes.AwareDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['import_id'], ['import.id'], ),
    sa.ForeignKeyConstraint(['trader_id'], ['trader.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('trader_id', 'chapter')
    )
    op.create_table('chapter_feedback_reason',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('feedback_id', sa.Integer(), nullable=False),
    sa.Column('reason', sa.String(length=32), nullable=False),
    sa.Column('given_at', dbtypes.AwareDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['feedback_id'], ['chapter_feedback.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('feedback_id')
    )


def downgrade() -> None:
    op.drop_table('chapter_feedback_reason')
    op.drop_table('chapter_feedback')
