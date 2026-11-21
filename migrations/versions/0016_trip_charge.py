"""trip_charge: each trip's charges source and components, as the import computed them (TICKET-995)

912's import works out each trade's charges by component and kept only the total. This keeps
what it computed: the source per trip, and one row per component with its amount, a Decimal
as text like trip.fees. Insert-only.

Revision ID: 0016
Revises: 0015
"""
import sqlalchemy as sa
from alembic import op

import services.production.db.types as dbtypes

revision = '0016'
down_revision = '0015'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('trip_charge',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('import_id', sa.Integer(), nullable=False),
    sa.Column('trip_row_id', sa.Integer(), nullable=False),
    sa.Column('source', sa.String(length=16), nullable=False),
    sa.Column('component', sa.String(length=16), nullable=True),
    sa.Column('amount', dbtypes.DecimalText(), nullable=True),
    sa.ForeignKeyConstraint(['import_id'], ['import.id'], ),
    sa.ForeignKeyConstraint(['trip_row_id'], ['trip.id'], ),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('trip_charge')
