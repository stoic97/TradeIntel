"""Shared test environment.

The app refuses to start without SCOPE_SECRET_KEY and SCOPE_FILE_KEY, deliberately:
a defaulted session key signs every deployment's cookies with a value from the
repository, and a defaulted file key looks like encryption and is not.

That strictness would otherwise mean every test fixture repeats the same three
lines and breaks whenever a setting is added, so the environment is set once here.
The keys below are test values and are never valid anywhere else.
"""

from __future__ import annotations

import pytest

from services.production.accounts.file_store import generate_key
from services.production.db.session import dispose_all_engines

TEST_SECRET_KEY = "test-secret-key-at-least-32-chars-long"
TEST_FILE_KEY = generate_key()


@pytest.fixture(autouse=True)
def scope_environment(tmp_path, monkeypatch):
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
    monkeypatch.setenv("SCOPE_DB", f"sqlite:///{tmp_path / 'scope.db'}")
    monkeypatch.setenv("SCOPE_FILES", str(tmp_path / "files"))
    monkeypatch.delenv("SCOPE_PRODUCTION", raising=False)

    yield

    dispose_all_engines()
