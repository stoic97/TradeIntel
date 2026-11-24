"""fact_read: the report pages a trader has opened, per upload, for the dial's reading ring

One row per page per upload (and the period and book it was read through), written when the
page is served. A new upload starts unread. No figure and no word of his: a page key and a time.

Numbered 0020: 0016 trip_charge, 0017 broker_connection, 0018 challenge, 0019 after_exit_path are reserved; re-pointed at merge if
the chain lands differently.

Revision ID: 0020
Revises: 0017
"""
import sqlalchemy as sa
from alembic import op

import services.production.db.types as dbtypes

revision = '0020'
down_revision = '0017'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('fact_read',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('trader_id', sa.Integer(), nullable=False),
    sa.Column('import_id', sa.Integer(), nullable=False),
    sa.Column('fact_key', sa.String(length=32), nullable=False),
    sa.Column('period', sa.String(length=16), nullable=False),
    sa.Column('book', sa.String(length=64), nullable=False),
    sa.Column('opened_at', dbtypes.AwareDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['import_id'], ['import.id'], ),
    sa.ForeignKeyConstraint(['trader_id'], ['trader.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('trader_id', 'import_id', 'fact_key', 'period', 'book')
    )


def downgrade() -> None:
    op.drop_table('fact_read')
