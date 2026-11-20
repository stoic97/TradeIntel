"""Market data stored by day (TICKET-997). RED stub: the names exist, the behaviour does not."""

from __future__ import annotations

import os  # noqa: F401 - the writer moves files with os.replace

MANIFEST = "manifest.json"
CALENDAR_CHECK, OPEN_CHECK, STAMPS_ONLY = "calendar", "open", "stamps only"


class Refused(Exception):
    pass


class DayStore:
    def __init__(self, folder, underlying):
        self.folder, self.underlying, self.days = folder, underlying, {}

    def put(self, *a, **kw):
        raise NotImplementedError

    def save(self, **kw):
        raise NotImplementedError


def day_path(folder, day):
    raise NotImplementedError


def read_day(folder, day, entry):
    raise NotImplementedError


def read_manifest(folder):
    raise NotImplementedError


def mcx_check(calendar, session_open):
    return None


def open_check(session_open, closed, through):
    return None
