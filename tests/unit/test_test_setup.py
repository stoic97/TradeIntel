"""The test setup's shortcuts must not change what is being tested [TICKET-886].

Each shortcut has a way of going quietly wrong: a copied database that is missing tables, or
production's password settings weakening with nobody noticing, because tests no longer use them.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from argon2 import PasswordHasher

from services.production.accounts import auth
from services.production.db.session import make_engine, run_migrations
from tests import conftest


def schema_of(path: Path) -> list[tuple]:
    connection = sqlite3.connect(path)
    try:
        return sorted(connection.execute("select type, name, sql from sqlite_master").fetchall(), key=str)
    finally:
        connection.close()


def test_production_keeps_argon2_at_its_full_strength():
    defaults = PasswordHasher()
    real = conftest.REAL_HASHER
    assert (real.time_cost, real.memory_cost, real.parallelism) == (
        defaults.time_cost, defaults.memory_cost, defaults.parallelism)
    assert real.verify(real.hash("a-long-enough-password"), "a-long-enough-password")


def test_only_the_test_process_uses_cheap_hashing():
    assert auth._hasher is not conftest.REAL_HASHER
    assert auth._hasher.time_cost < conftest.REAL_HASHER.time_cost


def test_a_copied_database_is_exactly_what_the_real_migrations_build(tmp_path):
    copied, migrated = tmp_path / "copied.db", tmp_path / "migrated.db"
    engine = make_engine(f"sqlite:///{copied.as_posix()}")
    run_migrations(engine)
    engine.dispose()
    conftest.real_upgrade_for_test(migrated)
    assert schema_of(copied) == schema_of(migrated)
    assert len(schema_of(copied)) > 20


def test_a_copied_database_takes_writes_and_keeps_foreign_keys_on(tmp_path):
    path = tmp_path / "copied.db"
    engine = make_engine(f"sqlite:///{path.as_posix()}")
    run_migrations(engine)
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
        assert connection.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
        assert connection.exec_driver_sql("select count(*) from trader").scalar() == 0
        assert connection.exec_driver_sql("select count(*) from alembic_version").scalar() == 1


def test_running_migrations_again_changes_nothing(tmp_path):
    path = tmp_path / "again.db"
    engine = make_engine(f"sqlite:///{path.as_posix()}")
    run_migrations(engine)
    before = schema_of(path)
    run_migrations(engine)
    engine.dispose()
    assert schema_of(path) == before


def test_each_test_starts_with_its_own_database(tmp_path, monkeypatch):
    one, two = tmp_path / "one.db", tmp_path / "two.db"
    first = make_engine(f"sqlite:///{one.as_posix()}")
    run_migrations(first)
    with first.begin() as connection:
        connection.exec_driver_sql("create table only_in_one (x integer)")
    second = make_engine(f"sqlite:///{two.as_posix()}")
    run_migrations(second)
    with second.connect() as connection:
        found = connection.exec_driver_sql(
            "select count(*) from sqlite_master where name = 'only_in_one'").scalar()
    assert found == 0
