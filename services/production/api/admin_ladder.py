"""/admin's first screen: what's new since the last look, and how far people got (TICKET-867).

Counts only, as TICKET-848 ruled: no percentage and no chart while there are so few traders.
Everything is read from what the app already stores, by named columns, one query a table, and
development accounts count for nothing. A line says how many traders ever did this, and how many
did it in the last seven days.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from services.production import demo
from services.production.api import scope_map as SM
from services.production.db import models as m
from services.shared.schemas import scope_v1 as s

INDIA_ZONE = ZoneInfo("Asia/Kolkata")
WINDOW = timedelta(days=7)
MIRROR_LINE = "mirror_line"


def _line(label: str, times: dict[int, Iterable[datetime]], since: datetime) -> dict:
    return {"label": label, "all_time": len(times),
            "last_7_days": sum(1 for at in times.values() if any(t >= since for t in at))}


def _by_trader(rows, real: dict) -> dict[int, list[datetime]]:
    found: dict[int, list[datetime]] = {}
    for trader_id, at in rows:
        if trader_id in real and at is not None:
            found.setdefault(trader_id, []).append(at)
    return found


def _read_facts(sess: Session, real: dict, fact_of: Callable) -> tuple[dict, dict]:
    """Who read any fact, and who read them all, dated by the fact that finished it."""
    first: dict[int, dict[str, datetime]] = {}
    for trader_id, key, at in sess.execute(
        select(m.DwellEvent.trader_id, m.DwellEvent.key, func.min(m.DwellEvent.at))
        .where(m.DwellEvent.surface == MIRROR_LINE, m.DwellEvent.event == "view")
        .group_by(m.DwellEvent.trader_id, m.DwellEvent.key)
    ):
        fact = fact_of(key)
        if trader_id in real and fact is not None:
            read = first.setdefault(trader_id, {})
            read[fact] = min(read.get(fact, at), at)
    some = {t: list(read.values()) for t, read in first.items()}
    every = {t: [max(read.values())] for t, read in first.items() if len(read) == len(SM.FACTS)}
    return some, every


def _came_back(real: dict) -> dict[int, list[datetime]]:
    """Any stored action on a later day, in India, than the trader's first."""
    found = {}
    for trader_id, reader in real.items():
        if not reader.seen:
            continue
        first_day = min(at.astimezone(INDIA_ZONE).date() for at in reader.seen)
        later = [at for at in reader.seen if at.astimezone(INDIA_ZONE).date() > first_day]
        if later:
            found[trader_id] = later
    return found


def ladder(sess: Session, real: dict, imports: list, *, now: datetime, fact_of: Callable) -> list[dict]:
    since = now - WINDOW
    some, every = _read_facts(sess, real, fact_of)
    return [
        _line("Signed up", {t: [r.signed_up] for t, r in real.items() if r.signed_up}
              | {t: [] for t in real if real[t].signed_up is None}, since),
        _line("Agreed to consent", _by_trader(sess.execute(
            select(m.ConsentEvent.trader_id, m.ConsentEvent.at)
            .where(m.ConsentEvent.purpose == s.ConsentPurpose.DIAGNOSIS,
                   m.ConsentEvent.granted.is_(True))), real), since),
        _line("Tried the demo", _by_trader(
            ((i.trader_id, i.created_at) for i in imports if demo.is_demo(i)), real), since),
        _line("Uploaded a real file", _by_trader(
            ((i.trader_id, i.created_at) for i in imports if not demo.is_demo(i)), real), since),
        _line("Read at least one fact", some, since),
        _line("Read all the facts", every, since),
        _line("Opened a journal", _by_trader(sess.execute(
            select(m.Journal.trader_id, m.Journal.opened_at)
            .where(m.Journal.opened_at.is_not(None))), real), since),
        _line("Came back on a later day", _came_back(real), since),
        _line("Asked would they pay", _by_trader(sess.execute(
            select(m.WtpAsked.trader_id, m.WtpAsked.asked_at)), real), since),
        _line("Answered would they pay", _by_trader(sess.execute(
            select(m.WtpAnswer.trader_id, m.WtpAnswer.asked_at)), real), since),
    ]


def _answers_after(sess: Session, real: dict, after: datetime) -> int:
    tables = ((m.ChapterFeedback.trader_id, m.ChapterFeedback.answered_at),
              (m.ReportFeedback.trader_id, m.ReportFeedback.answered_at),
              (m.GuessAnswer.trader_id, m.GuessAnswer.answered_at),
              (m.LeavingCardAnswer.trader_id, m.LeavingCardAnswer.answered_at),
              (m.WtpAnswer.trader_id, m.WtpAnswer.asked_at))
    return sum(1 for who, at in tables
               for trader_id in sess.scalars(select(who).where(at > after)) if trader_id in real)


def new_since(sess: Session, real: dict, imports: list, last_looked: datetime | None) -> list[dict]:
    """What has come in since this admin's last look. Nothing is new on a first look."""
    if last_looked is None:
        return []
    first_import_of: dict[int, int] = {}
    for row in imports:
        first_import_of.setdefault(row.raw_file_id, row.id)
    fresh = [i for i in imports if i.created_at > last_looked]
    read = [i for i in fresh if i.outcome is not s.ImportOutcome.REJECTED
            and first_import_of[i.raw_file_id] == i.id]
    counts = (
        ("Sign-ups", sum(1 for r in real.values() if r.signed_up and r.signed_up > last_looked)),
        ("Demo loads", sum(1 for i in read if demo.is_demo(i))),
        ("Real uploads", sum(1 for i in read if not demo.is_demo(i))),
        ("Refused files", sum(1 for i in fresh if i.outcome is s.ImportOutcome.REJECTED)),
        ("Answers", _answers_after(sess, real, last_looked)),
    )
    return [{"label": label, "count": count} for label, count in counts]
