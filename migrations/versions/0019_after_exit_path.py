"""after_exit_path: each trade's 30 minutes after it closed (TICKET-1009)

One nullable column on ``bar_trade_figure``: the close at +1 ... +30 minutes after the exit
minute, less the exit's close, in the trade's direction, as JSON. Points only; nothing from a
market file but what the worker worked out. Older rows stay empty until their import is worked
out again.

Revision ID: 0019
Revises: 0017
"""
import sqlalchemy as sa
from alembic import op

revision = '0019'
down_revision = '0017'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('bar_trade_figure') as batch:
        batch.add_column(sa.Column('after_exit', sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('bar_trade_figure') as batch:
        batch.drop_column('after_exit')
