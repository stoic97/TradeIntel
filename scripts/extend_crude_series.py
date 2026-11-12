"""TICKET-893 stub: extend the crude series (RED)."""
from __future__ import annotations


class Refused(Exception):
    pass


def near_month_symbol(client, today):
    raise NotImplementedError


def manifest_path(series):
    raise NotImplementedError


def extend(base, out, client, *, today, calendar, built):
    raise NotImplementedError
