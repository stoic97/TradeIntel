"""TICKET-940: every migration reverses exactly, one step at a time.

The app runs the migrations at every start (create_app -> run_migrations), and a
downgrade is the way back from a bad one. test_the_migration_is_reversible
(test_schema.py) goes head -> base -> head and compares table names only, so a
downgrade that leaves a column behind passes it whenever an older migration drops
that table anyway. This walks the chain one revision at a time, holds every
downgrade to the schema recorded on the way up, and checks that the head it climbs
back to is the head it left.

It compares structure (columns, indexes, foreign keys, views and triggers), not the
CREATE text: on SQLite, Alembic's batch mode rebuilds a table and the rebuilt CREATE
quotes the table's name, which changes the text and nothing else.

Every target is an explicit revision id, never "head", so conftest's template copy
(_fast_upgrade) cannot stand in for a real migration here.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from services.production.db.session import ALEMBIC_INI, make_engine

OTHER = "(views and triggers)"


def _structure(path: Path) -> dict[str, tuple]:
    """Each table's columns, indexes and foreign keys, plus every view and trigger."""
    connection = sqlite3.connect(path)
    try:
        tables = [row[0] for row in connection.execute(
            "select name from sqlite_master where type = 'table' "
            "and name not like 'sqlite_%' order by name").fetchall()]
        found: dict[str, tuple] = {}
        for table in tables:
            columns = tuple(connection.execute(f'pragma table_info("{table}")').fetchall())
            indexes = []
            for row in connection.execute(f'pragma index_list("{table}")').fetchall():
                name, unique = row[1], row[2]
                names = tuple(c[2] for c in
                              connection.execute(f'pragma index_info("{name}")').fetchall())
                label = "autoindex" if name.startswith("sqlite_autoindex") else name
                indexes.append((label, unique, names))
            keys = sorted((tuple(r[2:5]) for r in
                           connection.execute(f'pragma foreign_key_list("{table}")').fetchall()),
                          key=str)
            found[table] = (columns, tuple(sorted(indexes, key=str)), tuple(keys))
        found[OTHER] = tuple(connection.execute(
            "select type, name, coalesce(sql, '') from sqlite_master "
            "where type in ('view', 'trigger') order by type, name").fetchall())
        return found
    finally:
        connection.close()


def _version(path: Path) -> str | None:
    connection = sqlite3.connect(path)
    try:
        row = connection.execute("select version_num from alembic_version").fetchone()
        return row[0] if row else None
    finally:
        connection.close()


def _differences(want: dict[str, tuple], got: dict[str, tuple]) -> list[str]:
    return sorted(k for k in set(want) | set(got) if want.get(k) != got.get(k))


def test_every_migration_step_reverses_to_the_schema_before_it(tmp_path):
    path = tmp_path / "round-trip.db"
    engine = make_engine(f"sqlite:///{path.as_posix()}")
    config = Config(str(ALEMBIC_INI))
    config.attributes["connection"] = engine
    script = ScriptDirectory.from_config(config)
    assert len(script.get_heads()) == 1, script.get_heads()
    chain = [r.revision for r in reversed(list(script.walk_revisions()))]
    assert chain[-1] == script.get_current_head()
    try:
        seen: dict[str, dict[str, tuple]] = {}
        for revision in chain:
            command.upgrade(config, revision)
            assert _version(path) == revision
            seen[revision] = _structure(path)

        for below, revision in reversed(list(zip([None, *chain[:-1]], chain))):
            command.downgrade(config, below or "base")
            got = _structure(path)
            if below is None:
                left = [t for t in got if t not in ("alembic_version", OTHER)]
                assert left == [], f"downgrading {revision} to base left {left}"
                assert got[OTHER] == (), f"downgrading {revision} to base left {got[OTHER]}"
                assert _version(path) is None
            else:
                assert _version(path) == below
                assert got == seen[below], (
                    f"downgrading {revision} did not restore {below}: "
                    f"{_differences(seen[below], got)} differ")

        command.upgrade(config, chain[-1])
        assert _version(path) == chain[-1]
        again = _structure(path)
        head = seen[chain[-1]]
        assert again == head, f"head after the round trip differs: {_differences(head, again)}"
    finally:
        engine.dispose()