"""/admin's system health panel: what would lose a trader without leaving a row (TICKET-871).

Read when the page loads and never stored. The counts are the process's own
(``limits.SinceRestart``), and hold no person. Backups are out of the app's reach, so the
page says so rather than show anything that could look like a check.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from sqlalchemy.engine import Engine

from services.production.api import admin_view, limits
from services.production.ctr.adapters import filemap
from services.production.ctr.intake import outcomes as oc
from services.production.journal import constants as k

UNITS = ("B", "KB", "MB", "GB", "TB")
UNIT_STEP = 1024


def size_words(size: float) -> str:
    unit = 0
    while size >= UNIT_STEP and unit < len(UNITS) - 1:
        size /= UNIT_STEP
        unit += 1
    return f"{int(size)} B" if unit == 0 else f"{size:.1f} {UNITS[unit]}"


def _database_bytes(engine: Engine) -> int | None:
    """The database with its write-ahead log, where much of it can sit between checkpoints."""
    name = engine.url.database
    if not name or not Path(name).exists():
        return None
    wal = Path(f"{name}-wal")
    return Path(name).stat().st_size + (wal.stat().st_size if wal.exists() else 0)


def _stored_bytes(root: Path) -> int:
    total = 0
    for folder, _subfolders, names in os.walk(root):
        for name in names:
            try:
                total += (Path(folder) / name).stat().st_size
            except OSError:  # deleted while this was walking
                continue
    return total


def _unverified_maps(production: bool) -> list[str]:
    """What the pipeline would refuse in production: the same gate, asked of each broker."""
    if not production:
        return []
    closed = []
    for adapter in oc.ADAPTERS:
        file_map = adapter.file_map()
        try:
            filemap.require_verified(file_map)
        except filemap.UnverifiedFileMap:
            closed.append(f"the {file_map.broker} file map has not been verified")
    return closed


def _upload_answer(used: float | None, production: bool) -> str:
    reasons = ["the disk is past the refusal line"] if limits.past_the_line(used) else []
    reasons += _unverified_maps(production)
    return f"No: {'; '.join(reasons)}" if reasons else "Yes"


def _disk_words(used: float | None) -> str:
    if used is None:
        return "Could not be read"
    return f"{used:.1f}% used; uploads are refused at {k.UPLOADS_REFUSED_AT_DISK_PERCENT}%"


def build(app: FastAPI) -> dict:
    """Everything the panel draws, written out: the template computes nothing."""
    config = app.state.settings
    used = limits.disk_reading(config.file_store)
    database = _database_bytes(app.state.engine)
    counts = app.state.since_restart
    return {
        "upload": {"answer": _upload_answer(used, config.production),
                   "daily_cap": k.UPLOADS_PER_ACCOUNT_PER_DAY},
        "disk": _disk_words(used),
        "database_size": size_words(database) if database is not None else admin_view.NOT_RECORDED,
        "stored_size": size_words(_stored_bytes(config.file_store)),
        "started": admin_view._when(app.state.started_at),
        "refusals": [{"label": kind, "count": n} for kind, n in counts.refusals().items()],
        "server_errors": counts.errors(),
    }
