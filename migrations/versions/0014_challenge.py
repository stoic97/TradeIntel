"""challenge: the challenge he sets himself (TICKET-1004)

10 or 20 exchange trading days and one to three of the rules he set, from the next trading day
after he taps. How it ended and his share link are the only columns that change after it starts.

Revision ID: 0014
Revises: 0013
"""
import sqlalchemy as sa
from alembic import op

import services.production.db.types as dbtypes

revision = '0014'
down_revision = '0013'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('challenge',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('trader_id', sa.Integer(), nullable=False),
    sa.Column('rule_ids', sa.Text(), nullable=False),
    sa.Column('length', sa.Integer(), nullable=False),
    sa.Column('start_day', sa.String(length=10), nullable=False),
    sa.Column('started_at', dbtypes.AwareDateTime(), nullable=False),
    sa.Column('ended_at', dbtypes.AwareDateTime(), nullable=True),
    sa.Column('ended_how', sa.String(length=16), nullable=True),
    sa.Column('share_token', sa.String(length=64), nullable=True),
    sa.ForeignKeyConstraint(['trader_id'], ['trader.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('share_token')
    )


def downgrade() -> None:
    op.drop_table('challenge')
