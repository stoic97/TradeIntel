"""market_sync: the day's Fyers token, the sync's runs, and stock days on request (TICKET-998)

The token row holds only Fernet ciphertext under the file key; the token can place orders. A run
records counts, dates and reasons, never a price. A stock-day request names a stock and a day,
never a trader.

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
    op.create_table('market_token',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('ciphertext', sa.Text(), nullable=False),
    sa.Column('expires_at', dbtypes.AwareDateTime(), nullable=False),
    sa.Column('connected_at', dbtypes.AwareDateTime(), nullable=False),
    sa.Column('connected_by', sa.String(length=100), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('market_sync_run',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('started_at', dbtypes.AwareDateTime(), nullable=False),
    sa.Column('finished_at', dbtypes.AwareDateTime(), nullable=True),
    sa.Column('result', sa.String(length=32), nullable=False),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('market_day_request',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('underlying', sa.String(length=40), nullable=False),
    sa.Column('trading_day', sa.String(length=10), nullable=False),
    sa.Column('requested_at', dbtypes.AwareDateTime(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('tries', sa.Integer(), nullable=False),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('updated_at', dbtypes.AwareDateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('underlying', 'trading_day')
    )


def downgrade() -> None:
    op.drop_table('market_day_request')
    op.drop_table('market_sync_run')
    op.drop_table('market_token')
