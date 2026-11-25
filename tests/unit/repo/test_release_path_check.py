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
# ---------- review round, 24 Nov 2026 (PR #219) ----------

RUNBOOK = REPO_ROOT / "docs" / "runbooks" / "deploy.md"

DROP_INDEX = """
from alembic import op

def upgrade():
    op.drop_index("ix_trips_day", table_name="trips")

def downgrade():
    pass
"""

DROP_CONSTRAINT = """
from alembic import op

def upgrade():
    op.drop_constraint("uq_trips_day", "trips", type_="unique")

def downgrade():
    pass
"""

BATCH_DROP_INDEX = """
from alembic import op

def upgrade():
    with op.batch_alter_table("trips") as b:
        b.drop_index("ix_trips_day")

def downgrade():
    pass
"""

BULK_INSERT = """
import sqlalchemy as sa
from alembic import op

def upgrade():
    op.bulk_insert(sa.table("trips"), [{"id": 1}])

def downgrade():
    pass
"""

GET_BIND_REWRITE = """
import sqlalchemy as sa
from alembic import op

def upgrade():
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM trips WHERE side = 'SELL'"))

def downgrade():
    pass
"""

GET_BIND_CHAINED = """
from alembic import op

def upgrade():
    op.get_bind().execute("DROP TABLE trips")

def downgrade():
    pass
"""

DOTTED_OP = """
import alembic

def upgrade():
    alembic.op.drop_table("trips")

def downgrade():
    pass
"""

GETATTR_OP = """
import sqlalchemy as sa
from alembic import op

def upgrade():
    op.create_table("t", sa.Column("id", sa.Integer(), nullable=False))
    getattr(op, "drop_table")("trips")

def downgrade():
    pass
"""

ALIASED_OP = """
import sqlalchemy as sa
from alembic import op

def upgrade():
    op.create_table("t", sa.Column("id", sa.Integer(), nullable=False))
    d = op.drop_table
    d("trips")

def downgrade():
    pass
"""

UNBOUND_BATCH = """
from alembic import op

def upgrade():
    b = op.batch_alter_table("trips")
    b.drop_column("invite_code")

def downgrade():
    pass
"""

ADD_COLUMN_KWARGS = """
import sqlalchemy as sa
from alembic import op

def upgrade():
    kw = {"nullable": False}
    op.add_column("trips", sa.Column("book", sa.String(), **kw))

def downgrade():
    pass
"""

TYPES_MODULE_IS_ADDITIVE = """
import sqlalchemy as sa
from alembic import op
from services.production.db import types as dbtypes

def upgrade():
    op.create_table(
        "t",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("at", dbtypes.AwareDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_t_id"), "t", ["id"])

def downgrade():
    op.drop_table("t")
"""


@pytest.mark.parametrize(
    "name,source,expected",
    [
        ("drop_index in upgrade is Path B", DROP_INDEX, PATH_B),
        ("drop_constraint in upgrade is Path B", DROP_CONSTRAINT, PATH_B),
        ("batch drop_index in upgrade is Path B", BATCH_DROP_INDEX, PATH_B),
        ("bulk_insert is read by hand", BULK_INSERT, BY_HAND),
        ("a rewrite through get_bind is read by hand", GET_BIND_REWRITE, BY_HAND),
        ("a chained get_bind().execute is read by hand", GET_BIND_CHAINED, BY_HAND),
        ("alembic.op.drop_table is read by hand", DOTTED_OP, BY_HAND),
        ("getattr(op, ...) is read by hand", GETATTR_OP, BY_HAND),
        ("an aliased op function is read by hand", ALIASED_OP, BY_HAND),
        ("an unbound batch context is read by hand", UNBOUND_BATCH, BY_HAND),
        ("add_column with nullable in **kw is read by hand", ADD_COLUMN_KWARGS, BY_HAND),
        ("sa and a types module stay additive", TYPES_MODULE_IS_ADDITIVE, PATH_A),
    ],
)
def test_classify_source_review_round(mod, name, source, expected):
    verdict, reasons = mod.classify_source(source, name)
    assert verdict == expected, f"{name}: got {verdict}, reasons={reasons}"


# ---------- a scratch history: changed, renamed and deleted migrations ----------

CREATE_ONLY = """
import sqlalchemy as sa
from alembic import op

def upgrade():
    op.create_table("t", sa.Column("id", sa.Integer(), nullable=False))

def downgrade():
    op.drop_table("t")
"""

CREATE_AND_DROP = """
import sqlalchemy as sa
from alembic import op

def upgrade():
    op.create_table("t", sa.Column("id", sa.Integer(), nullable=False))
    op.drop_column("other", "gone")

def downgrade():
    op.drop_table("t")
"""


def _git_in(root, *args):
    done = subprocess.run(
        ["git", "-c", "user.email=t@example.invalid", "-c", "user.name=T", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, f"git {' '.join(args)}: {done.stderr}"
    return done.stdout.strip()


def _commit(root, message):
    _git_in(root, "add", "-A")
    _git_in(root, "commit", "-q", "-m", message)
    return _git_in(root, "rev-parse", "HEAD")


def _answer(root, live, tag):
    done = subprocess.run(
        [sys.executable, str(SCRIPT), live, tag],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    return done.returncode, done.stdout + done.stderr


@pytest.fixture
def scratch(tmp_path):
    root = tmp_path / "repo"
    (root / "migrations" / "versions").mkdir(parents=True)
    _git_in(root, "init", "-q")
    return root


def test_a_migration_changed_in_place_is_read(scratch):
    base = scratch / "migrations" / "versions"
    (base / "0001_first.py").write_text(CREATE_ONLY, encoding="utf-8")
    live = _commit(scratch, "first")
    (base / "0001_first.py").write_text(CREATE_AND_DROP, encoding="utf-8")
    tag = _commit(scratch, "edited in place")
    code, output = _answer(scratch, live, tag)
    assert code == PATH_B, output


def test_a_renamed_and_edited_migration_is_read(scratch):
    base = scratch / "migrations" / "versions"
    (base / "0001_first.py").write_text(CREATE_ONLY, encoding="utf-8")
    live = _commit(scratch, "first")
    (base / "0001_first.py").unlink()
    (base / "0002_renamed.py").write_text(CREATE_AND_DROP, encoding="utf-8")
    tag = _commit(scratch, "renamed and edited")
    status = _git_in(scratch, "diff", "--name-status", live, tag, "--", "migrations/versions")
    assert status.startswith("R"), f"git did not pair these as a rename: {status!r}"
    code, output = _answer(scratch, live, tag)
    assert code == PATH_B, output


def test_a_deleted_migration_is_read_by_hand(scratch):
    base = scratch / "migrations" / "versions"
    (base / "0001_first.py").write_text(CREATE_ONLY, encoding="utf-8")
    (base / "0002_second.py").write_text(CREATE_ONLY.replace('"t"', '"u"'), encoding="utf-8")
    live = _commit(scratch, "two migrations")
    (base / "0002_second.py").unlink()
    tag = _commit(scratch, "second removed")
    code, output = _answer(scratch, live, tag)
    assert code == BY_HAND, output


# ---------- the runbook ----------


def test_the_runbook_no_longer_greps_the_diff():
    text = RUNBOOK.read_text(encoding="utf-8")
    assert r"op\.(drop_" not in text, "the old grep is back in step d"
    assert "no destructive migration" not in text
    for answer in ("PATH A", "PATH B", "READ BY HAND", "CHECK DID NOT RUN"):
        assert answer in text, answer
    assert "Path B applies unless a person has read these migrations" in text
    assert "do not assume Path A" in text
