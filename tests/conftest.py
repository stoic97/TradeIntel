"""Shared test environment.

The app refuses to start without SCOPE_SECRET_KEY and SCOPE_FILE_KEY, deliberately:
a defaulted session key signs every deployment's cookies with a value from the
repository, and a defaulted file key looks like encryption and is not.

That strictness would otherwise mean every test fixture repeats the same three
lines and breaks whenever a setting is added, so the environment is set once here.
The keys below are test values and are never valid anywhere else.
"""

from __future__ import annotations

import shutil
import sqlite3
import tempfile
from pathlib import Path

import pytest
from alembic import command
from argon2 import PasswordHasher

from services.production.accounts import auth
from services.production.accounts.file_store import generate_key
from services.production.api import app as app_module
from services.production.api import limits
from services.production.db.session import dispose_all_engines, make_engine, run_migrations

TEST_SECRET_KEY = "test-secret-key-at-least-32-chars-long"
TEST_FILE_KEY = generate_key()

# Speed only [TICKET-886]: each of these does the same work the real path would, once.
# Production never imports this file, and test_test_setup.py pins that nothing drifted.
REAL_HASHER = auth._hasher
CHEAP_HASHER = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)
REAL_UPGRADE = command.upgrade
REAL_CODE_VERSION = app_module.code_version
# These walk the migrations themselves, so they keep the real path.
REAL_MIGRATION_FILES = ("test_schema.py", "test_read_again.py")
_template: tuple[Path, str] | None = None
_code_version: str | None = None


def real_upgrade_for_test(path: Path) -> None:
    """Build a database with the real migrations, for comparing against a copy."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(command, "upgrade", REAL_UPGRADE)
        engine = make_engine(f"sqlite:///{path.as_posix()}")
        run_migrations(engine)
        engine.dispose()
    _settle(path)


def _settle(path: Path) -> None:
    """Fold WAL side files into the main file, or a copy of it would be missing tables."""
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        connection.close()


def _migrated_template() -> tuple[Path, str]:
    """The real migrations, run once a process, and the revision they reach."""
    global _template
    if _template is None:
        path = Path(tempfile.mkdtemp(prefix="scope-template-")) / "template.db"
        real_upgrade_for_test(path)
        connection = sqlite3.connect(path)
        try:
            head = connection.execute("select version_num from alembic_version").fetchone()[0]
        finally:
            connection.close()
        _template = (path, head)
    return _template


def _revision_of(path: Path) -> tuple[bool, str | None]:
    """(whether the file holds any table, its alembic revision)."""
    connection = sqlite3.connect(path)
    try:
        tables = connection.execute("select count(*) from sqlite_master").fetchone()[0]
        if not tables:
            return False, None
        found = connection.execute(
            "select count(*) from sqlite_master where name = 'alembic_version'").fetchone()[0]
        row = connection.execute("select version_num from alembic_version").fetchone() if found else None
        return True, row[0] if row else None
    finally:
        connection.close()


def _fast_upgrade(config, revision, *args, **kwargs):
    """Upgrade to head by copying the template onto an empty file; nothing to do if at head.
    Anything else, such as a partial target or a part-built database, takes the real path."""
    engine = config.attributes.get("connection")
    path = engine.url.database if engine is not None else None
    if revision != "head" or not path or path == ":memory:":
        return REAL_UPGRADE(config, revision, *args, **kwargs)
    template, head = _migrated_template()
    target = Path(path)
    has_tables, current = _revision_of(target) if target.exists() else (False, None)
    if has_tables:
        return None if current == head else REAL_UPGRADE(config, revision, *args, **kwargs)
    try:
        engine.dispose()
        for side in (target, Path(f"{path}-wal"), Path(f"{path}-shm")):
            side.unlink(missing_ok=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(template, target)
    except OSError:  # someone holds the file open: the real path copes
        return REAL_UPGRADE(config, revision, *args, **kwargs)
    return None


def _cached_code_version() -> str:
    global _code_version
    if _code_version is None:
        _code_version = REAL_CODE_VERSION()
    return _code_version


@pytest.fixture(autouse=True)
def scope_environment(request, tmp_path, monkeypatch):
    """Every test gets its own database, file store and keys -- and gives them back.

    Each test builds at least one engine of its own and another inside create_app(),
    and SQLAlchemy holds a connection pool per engine. Nothing disposed them, so file
    descriptors accumulated across the suite until it died with 'Too many open files'
    at around 250 tests -- a limit on how many tests we could write, which is no
    limit to have.

    The first fix walked gc.get_objects() looking for engines, which broke tests that
    never touch a database: scanning the heap mid-collection trips over weak
    references. make_engine now records what it builds, so teardown closes a list it
    owns rather than searching the world.

    The app itself does not have this problem: create_app() makes one engine for the
    life of the process. This is test hygiene, and it belongs here rather than in
    every fixture that will ever build an engine.
    """
    monkeypatch.setenv("SCOPE_SECRET_KEY", TEST_SECRET_KEY)
    monkeypatch.setenv("SCOPE_FILE_KEY", TEST_FILE_KEY)
    # The disk check reads a real disk, so uploads in tests would refuse on a full laptop.
    # The tests about the check set their own disk.
    monkeypatch.setattr(limits.shutil, "disk_usage",
                        lambda _path: shutil._ntuple_diskusage(total=100, used=50, free=50))
    monkeypatch.setenv("SCOPE_DB", f"sqlite:///{tmp_path / 'scope.db'}")
    monkeypatch.setenv("SCOPE_FILES", str(tmp_path / "files"))
    monkeypatch.delenv("SCOPE_PRODUCTION", raising=False)
    monkeypatch.delenv("ADMIN_LOGIN_IDS", raising=False)
    monkeypatch.setattr(auth, "_hasher", CHEAP_HASHER)
    monkeypatch.setattr(app_module, "code_version", _cached_code_version)
    if request.path.name not in REAL_MIGRATION_FILES:
        monkeypatch.setattr(command, "upgrade", _fast_upgrade)

    yield

    dispose_all_engines()
