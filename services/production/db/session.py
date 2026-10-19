"""Engine, session and migrations.

One SQLite file at Phase 0 (ADR-005; Postgres 16 at Phase 1, schema kept portable).
Two SQLite settings are not optional here:

``PRAGMA foreign_keys=ON`` -- SQLite ignores foreign keys unless asked, so without it
an orphan trip would be accepted and the credit chain would have a hole.

``PRAGMA journal_mode=WAL`` -- a reader does not block the writer, which matters when
an upload is reconstructing while the trader's other tab loads a page.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from services.production.db.models import install_insert_only_guard

ALEMBIC_INI = Path(__file__).resolve().parents[3] / "alembic.ini"


_ENGINES: list[Engine] = []
"""Every engine this process has built.

Only for teardown in tests: each engine holds a connection pool, and a suite that
builds one per test runs out of file descriptors. The app builds exactly one engine
for the life of the process, so nothing here affects it.
"""


def dispose_all_engines() -> int:
    """Close every pooled connection. Returns how many engines were disposed."""
    count = 0
    while _ENGINES:
        engine = _ENGINES.pop()
        engine.dispose()
        count += 1
    return count


def make_engine(url: str) -> Engine:
    engine = create_engine(url, future=True)
    _ENGINES.append(engine)

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    return engine


@contextmanager
def make_session(engine: Engine) -> Iterator[Session]:
    factory = sessionmaker(bind=engine, future=True, expire_on_commit=False)
    install_insert_only_guard(factory.class_)
    session = factory()
    try:
        yield session
    finally:
        session.close()


def run_migrations(engine: Engine, target: str = "head") -> None:
    """Run alembic against an existing engine, so tests and the app share one path."""
    config = Config(str(ALEMBIC_INI))
    config.attributes["connection"] = engine
    if target == "base":
        command.downgrade(config, "base")
    else:
        command.upgrade(config, target)
