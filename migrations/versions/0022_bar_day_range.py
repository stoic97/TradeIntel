"""bar_day_range: how far the market moved on each day a trader traded (TICKET-1011)

One row per (import, underlying, day): the session's highest high less its lowest low, in points,
from that one day file, with the file's sha256. Written by the bar-figures worker, never by a page.
Older imports have none until they are worked out again.

Revision ID: 0022
Revises: 0019
"""
import sqlalchemy as sa
from alembic import op

revision = '0022'
down_revision = '0019'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('bar_day_range',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('import_id', sa.Integer(), nullable=False),
    sa.Column('underlying', sa.String(length=40), nullable=False),
    sa.Column('day', sa.String(length=10), nullable=False),
    sa.Column('range_points', sa.String(length=32), nullable=False),
    sa.Column('sha256', sa.String(length=64), nullable=False),
    sa.ForeignKeyConstraint(['import_id'], ['import.id'], ),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('bar_day_range')
