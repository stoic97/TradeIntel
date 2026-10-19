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

TEST_SECRET_KEY = "test-secret-key-at-least-32-chars-long"
TEST_FILE_KEY = generate_key()


@pytest.fixture(autouse=True)
def scope_environment(tmp_path, monkeypatch):
    """Every test gets its own database, file store and keys."""
    monkeypatch.setenv("SCOPE_SECRET_KEY", TEST_SECRET_KEY)
    monkeypatch.setenv("SCOPE_FILE_KEY", TEST_FILE_KEY)
    monkeypatch.setenv("SCOPE_DB", f"sqlite:///{tmp_path / 'scope.db'}")
    monkeypatch.setenv("SCOPE_FILES", str(tmp_path / "files"))
    monkeypatch.delenv("SCOPE_PRODUCTION", raising=False)
