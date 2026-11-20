"""Split a single-file series into day files (TICKET-997). RED stub."""

from services.shared.market import series as ms  # noqa: F401


class Refused(Exception):
    pass


def split(*a, **kw):
    raise NotImplementedError


def main(argv=None):
    raise NotImplementedError
