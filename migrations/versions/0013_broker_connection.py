"""broker_connection: the stored key behind a read-only broker pull (TICKET-896)

One row per trader per broker, holding the encrypted connection key. Disconnecting deletes
the row and so does /delete. The consent for it is a ``broker_pull`` row in consent_event:
no change to that table, because ``purpose`` is plain text.

Revision ID: 0013
Revises: 0012
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

import services.production.db.types as dbtypes

revision = '0013'
down_revision = '0012'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('broker_connection',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('trader_id', sa.Integer(), nullable=False),
    sa.Column('broker', sa.String(length=32), nullable=False),
    sa.Column('token_ciphertext', sa.Text(), nullable=False),
    sa.Column('connected_at', dbtypes.AwareDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['trader_id'], ['trader.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('trader_id', 'broker', name='uq_broker_connection_trader_broker')
    )


def downgrade() -> None:
    op.drop_table('broker_connection')