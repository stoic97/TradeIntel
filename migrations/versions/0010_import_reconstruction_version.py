"""import.reconstruction_version: what read this file (TICKET-844)

Nullable on purpose: an import stored before this has none, which reads as out of date.

Revision ID: 0010
Revises: 0009
"""
import sqlalchemy as sa
from alembic import op

revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('import', sa.Column('reconstruction_version', sa.String(length=32), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('import') as batch:
        batch.drop_column('reconstruction_version')
