"""TICKET-990 - the release path check reads upgrade() only.

Gate 1-4.  RED first: deploy/classify_release.py does not exist yet.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "deploy" / "classify_release.py"

PATH_A, PATH_B, BY_HAND, DID_NOT_RUN = 0, 1, 2, 3


@pytest.fixture(scope="module")
def mod():
    if not SCRIPT.exists():
        pytest.fail("missing deploy/classify_release.py")
    spec = importlib.util.spec_from_file_location("classify_release", SCRIPT)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


CREATE_ONLY_DROP_IN_DOWNGRADE = """
import sqlalchemy as sa
from alembic import op

def upgrade():
    op.create_table("report_feedback", sa.Column("id", sa.Integer(), nullable=False))
    op.create_index(op.f("ix_rf_id"), "report_feedback", ["id"])

def downgrade():
    op.drop_index(op.f("ix_rf_id"), table_name="report_feedback")
    op.drop_table("report_feedback")
"""

BATCH_DROP_IN_UPGRADE = """
from alembic import op

def upgrade():
    with op.batch_alter_table("trips") as batch:
        batch.drop_column("invite_code")

def downgrade():
    pass
"""

BATCH_ADD_DROP_IN_DOWNGRADE = """
import sqlalchemy as sa
from alembic import op

def upgrade():
    with op.batch_alter_table("trip_positions") as batch:
        batch.add_column(sa.Column("note", sa.String()))

def downgrade():
    with op.batch_alter_table("trip_positions") as batch:
        batch.drop_column("note")
"""

OP_DROP_IN_UPGRADE = """
from alembic import op

def upgrade():
    op.drop_column("traders", "invite_code")

def downgrade():
    pass
"""

ALTER_COLUMN_IN_UPGRADE = """
import sqlalchemy as sa
from alembic import op

def upgrade():
    op.alter_column("trips", "qty", type_=sa.Numeric())

def downgrade():
    pass
"""

EXECUTE_REWRITE = """
from alembic import op

def upgrade():
    op.execute("UPDATE trips SET qty = qty * -1 WHERE side = 'SELL'")

def downgrade():
    pass
"""

NULLABLE_ADD_IMPLICIT = """
import sqlalchemy as sa
from alembic import op

def upgrade():
    op.add_column("trips", sa.Column("note", sa.String()))

def downgrade():
    op.drop_column("trips", "note")
"""

NON_NULLABLE_ADD = """
import sqlalchemy as sa
from alembic import op

def upgrade():
    op.add_column("trips", sa.Column("book", sa.String(), nullable=False))

def downgrade():
    op.drop_column("trips", "book")
"""

NO_UPGRADE = """
from alembic import op

def downgrade():
    op.drop_table("x")
"""

WILL_NOT_PARSE = "def upgrade(:\n    pass\n"

HELPER_CALLED_FROM_UPGRADE = """
from alembic import op

def _move_rows():
    op.execute("DELETE FROM trips")

def upgrade():
    _move_rows()

def downgrade():
    pass
"""

UNLISTED_OP = """
from alembic import op

def upgrade():
    op.rename_table("trips", "trips_old")

def downgrade():
    pass
"""


@pytest.mark.parametrize(
    "name,source,expected",
    [
        ("drop only in downgrade is Path A", CREATE_ONLY_DROP_IN_DOWNGRADE, PATH_A),
        ("batch add, drop in downgrade is Path A", BATCH_ADD_DROP_IN_DOWNGRADE, PATH_A),
        ("nullable add_column is Path A", NULLABLE_ADD_IMPLICIT, PATH_A),
        ("batch drop in upgrade is Path B", BATCH_DROP_IN_UPGRADE, PATH_B),
        ("op drop in upgrade is Path B", OP_DROP_IN_UPGRADE, PATH_B),
        ("alter_column in upgrade is Path B", ALTER_COLUMN_IN_UPGRADE, PATH_B),
        ("op.execute is read by hand", EXECUTE_REWRITE, BY_HAND),
        ("non-nullable add_column is read by hand", NON_NULLABLE_ADD, BY_HAND),
        ("no upgrade() is read by hand", NO_UPGRADE, BY_HAND),
        ("unparseable file is read by hand", WILL_NOT_PARSE, BY_HAND),
        ("helper call is read by hand", HELPER_CALLED_FROM_UPGRADE, BY_HAND),
        ("op not on the Path A list is read by hand", UNLISTED_OP, BY_HAND),
    ],
)
def test_classify_source(mod, name, source, expected):
    verdict, reasons = mod.classify_source(source, name)
    assert verdict == expected, f"{name}: got {verdict}, reasons={reasons}"


RANGES = [
    ("d4e2014", "98687f2", PATH_A),
    ("98687f2", "ff4e8ce", PATH_A),
    ("ff4e8ce", "ad97504", PATH_B),
    ("ad97504", "a18d03e", PATH_A),
    ("a18d03e", "f496cdd", PATH_A),
    ("f496cdd", "7a40e2f", PATH_A),
]


@pytest.mark.parametrize("live,tag,expected", RANGES)
def test_against_this_repos_history(live, tag, expected):
    for ref in (live, tag):
        probe = subprocess.run(
            ["git", "cat-file", "-e", f"{ref}^{{commit}}"], cwd=REPO_ROOT, check=False
        )
        assert probe.returncode == 0, f"{ref} not in this clone - run: git fetch --unshallow"
    done = subprocess.run(
        [sys.executable, str(SCRIPT), live, tag],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == expected, (
        f"{live}..{tag}: got {done.returncode}, want {expected}\n{done.stdout}\n{done.stderr}"
    )


def test_a_check_that_cannot_run_is_not_path_a():
    if not SCRIPT.exists():
        pytest.fail("missing deploy/classify_release.py")
    done = subprocess.run(
        [sys.executable, str(SCRIPT), "no-such-ref-990", "HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == DID_NOT_RUN
