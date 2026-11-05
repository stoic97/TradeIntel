"""drop invite_code: sign-up is open (TICKET-841)

Revision ID: 0008
Revises: 0007
"""
import sqlalchemy as sa
from alembic import op

import services.production.db.types as dbtypes

revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table('invite_code')


def downgrade() -> None:
    op.create_table('invite_code',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=64), nullable=False),
    sa.Column('created_at', dbtypes.AwareDateTime(), nullable=False),
    sa.Column('redeemed_by', sa.Integer(), nullable=True),
    sa.Column('redeemed_at', dbtypes.AwareDateTime(), nullable=True),
    sa.ForeignKeyConstraint(['redeemed_by'], ['trader.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code')
    )
