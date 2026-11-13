"""rule_declaration gains the tapped rule; pre_trade_note holds what he tapped before a click (TICKET-922)

A rule is built from chips, never typed: a factor his file can check and a value. It is
dated, and a later one never rewrites it. All new columns are nullable, so the free-text
rows the table was made for (none written yet) stay valid.

Revision ID: 0011
Revises: 0010
"""
import sqlalchemy as sa
from alembic import op

from services.production.db import types as dbtypes

revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('rule_declaration') as batch:
        batch.add_column(sa.Column('factor', sa.String(length=32), nullable=True))
        batch.add_column(sa.Column('value', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('applies_from', sa.String(length=10), nullable=True))
        batch.add_column(sa.Column('applies_to', sa.String(length=10), nullable=True))
        batch.add_column(sa.Column('screen', sa.String(length=32), nullable=True))
    op.create_table(
        'pre_trade_note',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('trader_id', sa.Integer(), nullable=False),
        sa.Column('book', sa.String(length=64), nullable=False),
        sa.Column('reason', sa.String(length=32), nullable=False),
        sa.Column('entered_at', dbtypes.AwareDateTime(), nullable=False),
        sa.ForeignKeyConstraint(['trader_id'], ['trader.id']),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('pre_trade_note')
    with op.batch_alter_table('rule_declaration') as batch:
        for column in ('screen', 'applies_to', 'applies_from', 'value', 'factor'):
            batch.drop_column(column)
