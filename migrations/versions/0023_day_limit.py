"""day_limit_declaration: the most a day may lose, as the trader declared it (TICKET-974)

Insert-only, like risk_budget_declaration. effective_from is the day it was declared and never
earlier; the app writes it, and no form field can set it.

Revision ID: 0023
Revises: 0021
"""
import sqlalchemy as sa
from alembic import op

import services.production.db.types as dbtypes

revision = '0023'
down_revision = '0021'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('day_limit_declaration',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('trader_id', sa.Integer(), nullable=False),
    sa.Column('value', dbtypes.DecimalText(), nullable=False),
    sa.Column('effective_from', sa.String(length=10), nullable=False),
    sa.Column('declared_at', dbtypes.AwareDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['trader_id'], ['trader.id'], ),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('day_limit_declaration')
