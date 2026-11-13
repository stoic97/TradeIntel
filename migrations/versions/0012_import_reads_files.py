"""import.reads_files: every file a record reads, when it reads more than one (TICKET-926)

Groww gives stocks and F&O as two downloads with one header, so a record can be built from
several files of one broker. Nullable: an import that reads one file, which every import
made before this does, leaves it empty and reads ``raw_file_id`` alone.

Revision ID: 0012
Revises: 0011
"""
import sqlalchemy as sa
from alembic import op

revision = '0012'
down_revision = '0011'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('import', sa.Column('reads_files', sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('import') as batch:
        batch.drop_column('reads_files')
