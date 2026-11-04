"""trip: position_id, option_type and strike (Annex H draft 2, TICKET-810)

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-04 19:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

import services.production.db.types as dbtypes

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('trip') as batch:
        batch.add_column(sa.Column('position_id', sa.String(length=64), nullable=True))
        batch.add_column(sa.Column('option_type', sa.String(length=2), nullable=True))
        batch.add_column(sa.Column('strike', dbtypes.DecimalText(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('trip') as batch:
        batch.drop_column('strike')
        batch.drop_column('option_type')
        batch.drop_column('position_id')
