"""TICKET-893 stub: the crude series' manifest and session check (RED)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

KINDS: tuple[str, ...] = ()
ROLL_CONVENTION = ""
CLOCK = ""
CRUDE_SERVES: tuple[str, ...] = ()


@dataclass(frozen=True)
class SessionException:
    day: date
    kind: str
    reason: str


@dataclass(frozen=True)
class SessionCheck:
    listed: tuple = ()
    unexplained: tuple = ()

    @property
    def ok(self) -> bool:
        return False


@dataclass(frozen=True)
class SeriesManifest:
    underlying: str
    serves: tuple
    file: str
    sha256: str
    rows: int
    first_bar: datetime
    last_bar: datetime
    as_of: date
    source: str
    roll: str
    clock: str
    interval: str
    built: date
    extended_from: date
    sessions: tuple

    def covers(self, day: date) -> bool:
        raise NotImplementedError

    def days_behind(self, today: date) -> int:
        raise NotImplementedError


def check_sessions(minutes, start, end, calendar) -> SessionCheck:
    raise NotImplementedError


def load_calendar(path=None):
    raise NotImplementedError


def read_manifest(path):
    raise NotImplementedError


def write_manifest(m, path):
    raise NotImplementedError
