"""bar_figures: each import's bar figures, worked out off the web app (TICKET-999)

A job row per import (pending, waiting, done) with what produced its figures; one row per trade,
in underlying points or with the reason it has none; and per underlying the after-you-clicked
paths beside random moments. Points only, never rupees, and nothing from a market file but the
sha256 of each day read.

Revision ID: 0015
Revises: 0014
"""
import sqlalchemy as sa
from alembic import op

import services.production.db.types as dbtypes

revision = '0015'
down_revision = '0014'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('bar_figure_job',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('import_id', sa.Integer(), nullable=False),
    sa.Column('trader_id', sa.Integer(), nullable=False),
    sa.Column('state', sa.String(length=16), nullable=False),
    sa.Column('waiting_days', sa.Integer(), nullable=False),
    sa.Column('requested_at', dbtypes.AwareDateTime(), nullable=False),
    sa.Column('updated_at', dbtypes.AwareDateTime(), nullable=True),
    sa.Column('provenance', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['import_id'], ['import.id'], ),
    sa.ForeignKeyConstraint(['trader_id'], ['trader.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('import_id')
    )
    op.create_table('bar_trade_figure',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('import_id', sa.Integer(), nullable=False),
    sa.Column('trip_id', sa.String(length=64), nullable=False),
    sa.Column('underlying', sa.String(length=40), nullable=True),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('way', sa.String(length=32), nullable=True),
    sa.Column('against', sa.String(length=32), nullable=True),
    sa.Column('took', sa.String(length=32), nullable=True),
    sa.Column('path', sa.Text(), nullable=True),
    sa.Column('short', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['import_id'], ['import.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('bar_path_summary',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('import_id', sa.Integer(), nullable=False),
    sa.Column('underlying', sa.String(length=40), nullable=False),
    sa.Column('measured', sa.Integer(), nullable=False),
    sa.Column('randoms', sa.Integer(), nullable=False),
    sa.Column('his_median', sa.Text(), nullable=False),
    sa.Column('his_q25', sa.Text(), nullable=False),
    sa.Column('his_q75', sa.Text(), nullable=False),
    sa.Column('random_median', sa.Text(), nullable=False),
    sa.Column('random_lo', sa.Text(), nullable=False),
    sa.Column('random_hi', sa.Text(), nullable=False),
    sa.Column('faint', sa.Text(), nullable=False),
    sa.ForeignKeyConstraint(['import_id'], ['import.id'], ),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('bar_path_summary')
    op.drop_table('bar_trade_figure')
    op.drop_table('bar_figure_job')
