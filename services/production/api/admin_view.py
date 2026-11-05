"""What /admin shows: the tables the app already writes, read, and nothing else (TICKET-848).

Three things decide the shape of this module.

**Only what is stored.** Nothing here estimates. A step that leaves no row (the reveal, a
chapter being opened, a byte-identical upload being refused) is shown as "—", or counted
only by what truly proves it, and the page says which.

**No free text and no money.** Queries name their columns, so a note, a journal answer, a
stored row of a file, a budget or a trade's result is never fetched at all: what was never
read cannot be drawn. A rejection is shown only through ``refusal_reason``.

**One load is a fixed number of queries.** Each table is read once, grouped by trader, and
the rows are put together here. Neither loops over traders with a query.

Development accounts are dropped from every count, row and feed line, and listed apart.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from services.production.api import formatting
from services.production.api import scope_map as SM
from services.production.db import models as m
from services.production.journal import leaving as LC
from services.production.journal import wtp as WTP
from services.production.mirror import feedback as FB
from services.production.mirror import guess as GU
from services.shared.schemas import scope_v1 as s

NOT_RECORDED = "—"
FEED_LENGTH = 40
MINUTE_MS = 60 * 1000
ZONE = ZoneInfo("Asia/Kolkata")
NEVER = datetime.min.replace(tzinfo=UTC)
UNKNOWN_VERSION = "unknown"
MIRROR_LINE = "mirror_line"
DUPLICATE_FLAGS = (s.RowFlag.SUSPECTED_DUPLICATE, s.RowFlag.DUPLICATE_FILL_ID,
                   s.RowFlag.TRADER_CONFIRMED_DUPLICATE)
ISO_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")
OUR_REFUSAL = re.compile(r"This looks like ([a-z -]+), and it has no ([a-z -]+)\.")
"""The start of the sentence outcomes.rejection_for builds from its own fixed words."""
CHAPTER_OF = {f.key: c.number for c in SM.CHAPTERS for f in c.facts}


def fact_of(key: str) -> str | None:
    """The fact page a stored dwell key is read on now, or None. A browser can post any
    key without a digit, so a key that is no fact is ignored, and never drawn."""
    fact = SM.OLD_DWELL_LINES.get(key, key)
    return fact if fact in SM.FACTS else None


def refusal_reason(rejection_text: str | None) -> str | None:
    """Why a file was refused, only where the words are certainly ours.

    Letters, spaces and hyphens only, in the sentence we write, so no figure can be in it.
    Anything else is not shown: the page gives the outcome instead.
    """
    found = OUR_REFUSAL.match(rejection_text or "")
    return f"{found[1]}, no {found[2]}" if found else None


def _when(at: datetime | None) -> str:
    return at.astimezone(ZONE).strftime("%d %b %Y %H:%M") if at is not None else NOT_RECORDED


def _span(ms: float | None) -> str:
    if ms is None:
        return NOT_RECORDED
    return f"{int(ms // 1000)} s" if ms < MINUTE_MS else f"{formatting.count(ms // MINUTE_MS)} min"


def _name(text: str) -> str:
    """A name is free text too, so even here the page keeps its one promise about rupees."""
    return text.replace(formatting.RUPEE, "")


def _with_note(answer: str, noted: bool) -> str:
    return f"{answer}, with a note" if noted else answer


@dataclass
class _Reader:
    """What one trader's rows came to, as the queries find it."""

    id: int
    name: str
    login_id: str
    consented: bool = False
    latest_any: tuple | None = None
    latest_read: tuple | None = None  # the latest not refused
    uploads: int = 0
    uploads_refused: int = 0
    facts: set[str] = field(default_factory=set)
    furthest_chapter: int = 0
    dwell_ms: int = 0
    chapter_four_ms: int = 0
    drawer_opens: int = 0
    chapters: dict[int, str] = field(default_factory=dict)
    said_wrong: bool = False
    report: str | None = None
    journals_written: int = 0
    journal_opened: bool = False
    budget: bool = False
    guess: bool = False
    leaving: str | None = None
    wtp: str | None = None
    seen: list[datetime] = field(default_factory=list)


def _read_imports(sess: Session, real: dict[int, _Reader]) -> list[tuple]:
    imports = sess.execute(
        select(m.Import.id, m.Import.trader_id, m.Import.outcome, m.Import.code_version,
               m.Import.rows_in, m.Import.rows_parsed, m.Import.created_at, m.Import.raw_file_id)
        .order_by(m.Import.id)
    ).all()
    read = []
    for row in imports:
        reader = real.get(row.trader_id)
        if reader is None:
            continue
        read.append(row)
        reader.uploads += 1
        reader.latest_any = row
        reader.seen.append(row.created_at)
        if row.outcome is s.ImportOutcome.REJECTED:
            reader.uploads_refused += 1
        else:
            reader.latest_read = row
    return read


def _read_dwell(sess: Session, real: dict[int, _Reader]) -> tuple[dict, dict]:
    """Readers per fact, and drawer opens per fact, while filling in each reader."""
    rows = sess.execute(
        select(m.DwellEvent.trader_id, m.DwellEvent.surface, m.DwellEvent.key, m.DwellEvent.event,
               func.count(), func.sum(m.DwellEvent.duration_ms), func.max(m.DwellEvent.at))
        .group_by(m.DwellEvent.trader_id, m.DwellEvent.surface, m.DwellEvent.key,
                  m.DwellEvent.event)
    ).all()
    readers: dict[str, set[int]] = {key: set() for key in SM.FACTS}
    drawers: dict[str, int] = {}
    for trader_id, surface, key, kind, times, total_ms, last in rows:
        reader = real.get(trader_id)
        if reader is None:
            continue
        reader.seen.append(last)
        fact = fact_of(key)
        if surface != MIRROR_LINE or fact is None:
            continue
        reader.furthest_chapter = max(reader.furthest_chapter, CHAPTER_OF[fact])
        if kind == "drawer_open":
            reader.drawer_opens += times
            drawers[fact] = drawers.get(fact, 0) + times
        elif kind == "view":
            reader.facts.add(fact)
            readers[fact].add(trader_id)
            reader.dwell_ms += total_ms or 0
            if CHAPTER_OF[fact] == 4:
                reader.chapter_four_ms += total_ms or 0
    return readers, drawers


def _read_answers(sess: Session, real: dict[int, _Reader]) -> list[tuple]:
    """Chapter and whole-report answers on each reader. Returns the feed's lines for them."""
    lines = []
    chapter_rows = sess.execute(
        select(m.ChapterFeedback.trader_id, m.ChapterFeedback.chapter, m.ChapterFeedback.answer,
               m.ChapterFeedbackReason.reason, m.ChapterFeedback.answered_at)
        .outerjoin(m.ChapterFeedbackReason,
                   m.ChapterFeedbackReason.feedback_id == m.ChapterFeedback.id)
    ).all()
    for trader_id, chapter, answer, reason, at in chapter_rows:
        reader = real.get(trader_id)
        if reader is None:
            continue
        said = FB.ANSWERS.get(answer, NOT_RECORDED)
        why = FB.REASONS.get(reason)
        reader.chapters[chapter] = f"{said}: {why}" if why else said
        reader.said_wrong = reader.said_wrong or answer == "wrong"
        reader.furthest_chapter = max(reader.furthest_chapter, chapter)
        lines.append((at, f"{reader.login_id} answered {said} on chapter {chapter}"))

    report_rows = sess.execute(
        select(m.ReportFeedback.trader_id, m.ReportFeedback.answer, m.ReportFeedback.trading_day,
               m.ReportFeedback.note.is_not(None), m.ReportFeedback.answered_at)
        .order_by(m.ReportFeedback.id)
    ).all()
    for trader_id, answer, trading_day, noted, at in report_rows:
        reader = real.get(trader_id)
        if reader is None:
            continue
        said = FB.ANSWERS.get(answer, NOT_RECORDED)
        if trading_day == FB.WHOLE_REPORT:
            reader.report = _with_note(said, noted)
            text = f"{reader.login_id} answered {said} on the whole report"
        else:
            day = formatting.day(trading_day) if ISO_DAY.fullmatch(trading_day) else "a day"
            text = f"{reader.login_id} said {day} looks wrong"
        lines.append((at, _with_note(text, noted)))
    return lines


def _read_journals(sess: Session, real: dict[int, _Reader]) -> None:
    """A Journal row is written by the upload, so only an opened or written one is his."""
    written = sess.execute(
        select(m.Journal.trader_id, func.count(distinct(m.JournalFieldEntry.journal_id)),
               func.max(m.JournalFieldEntry.entered_at))
        .join(m.JournalFieldEntry, m.JournalFieldEntry.journal_id == m.Journal.id)
        .group_by(m.Journal.trader_id)
    ).all()
    for trader_id, journals, last in written:
        if trader_id in real:
            real[trader_id].journals_written = journals
            real[trader_id].seen.append(last)
    opened = sess.execute(
        select(m.Journal.trader_id, func.max(m.Journal.opened_at))
        .where(m.Journal.opened_at.is_not(None)).group_by(m.Journal.trader_id)
    ).all()
    for trader_id, last in opened:
        if trader_id in real:
            real[trader_id].journal_opened = True
            real[trader_id].seen.append(last)


def _read_features(sess: Session, real: dict[int, _Reader]) -> dict[str, int]:
    """Budget, guess, leaving card and willingness to pay. Returns the answers to the last."""
    for trader_id in sess.scalars(select(m.RiskBudgetDeclaration.trader_id).distinct()):
        if trader_id in real:
            real[trader_id].budget = True
    for trader_id in sess.scalars(select(m.GuessAnswer.trader_id)):
        if trader_id in real:
            real[trader_id].guess = True
    for trader_id in sess.scalars(select(m.LeavingCardShown.trader_id)):
        if trader_id in real:
            real[trader_id].leaving = "shown"
    for trader_id, outcome in sess.execute(
        select(m.LeavingCardAnswer.trader_id, m.LeavingCardAnswer.outcome)
    ):
        if trader_id in real:
            real[trader_id].leaving = outcome if outcome in (LC.ANSWERED, LC.DISMISSED) else "shown"

    answers = dict.fromkeys(("yes", "no", "maybe"), 0)
    for trader_id, answer, noted in sess.execute(
        select(m.WtpAnswer.trader_id, m.WtpAnswer.answer, m.WtpAnswer.free_text.is_not(None))
        .order_by(m.WtpAnswer.id)
    ):
        if trader_id in real and answer in WTP.ANSWERS:
            answers[answer] += 1
            real[trader_id].wtp = _with_note(answer, noted)
    return answers


def _feed_of_uploads(sess: Session, real: dict[int, _Reader], imports: list[tuple]) -> list[tuple]:
    rejections = dict(sess.execute(
        select(m.Import.id, m.Import.rejection_text)
        .where(m.Import.trader_id.in_(_not_development()),
               m.Import.outcome == s.ImportOutcome.REJECTED)
        .order_by(m.Import.id.desc()).limit(FEED_LENGTH)
    ).all())
    # Only a re-read gives a second import to one stored file: it sent nothing new.
    first_import_of = {}
    for row in imports:
        first_import_of.setdefault(row.raw_file_id, row.id)
    lines = []
    for row in imports[-FEED_LENGTH:]:
        who = real[row.trader_id].login_id
        if row.outcome is s.ImportOutcome.REJECTED:
            reason = refusal_reason(rejections.get(row.id))
            text = f"{who} had a file refused: {reason}" if reason else f"{who} had a file refused"
        elif first_import_of[row.raw_file_id] != row.id:
            text = f"{who} had a file read again: {_rows_read(row)} rows read"
        else:
            text = f"{who} uploaded a file: {_rows_read(row)} rows read"
        lines.append((row.created_at, text))
    first_seen: dict[str, datetime] = {}
    for row in imports:
        if row.code_version != UNKNOWN_VERSION:
            first_seen.setdefault(row.code_version, row.created_at)
    lines += [(at, f"First import on code {version}") for version, at in first_seen.items()]
    return lines


def _not_development():
    return select(m.Trader.id).where(m.Trader.development_data.is_(False))


def _feed_of_reading(sess: Session, real: dict[int, _Reader]) -> list[tuple]:
    """Drawer opens and journals, newest first and cut off, because these can run long."""
    lines = []
    drawers = sess.execute(
        select(m.DwellEvent.trader_id, m.DwellEvent.key, m.DwellEvent.at)
        .where(m.DwellEvent.event == "drawer_open", m.DwellEvent.surface == MIRROR_LINE,
               m.DwellEvent.trader_id.in_(_not_development()))
        .order_by(m.DwellEvent.id.desc()).limit(FEED_LENGTH)
    ).all()
    for trader_id, key, at in drawers:
        fact = fact_of(key)
        title = SM.FACTS[fact].title if fact else "a line no longer on any page"
        lines.append((at, f"{real[trader_id].login_id} opened a drawer: {title}"))
    written = sess.execute(
        select(m.Journal.trader_id, func.max(m.JournalFieldEntry.entered_at).label("last"))
        .join(m.JournalFieldEntry, m.JournalFieldEntry.journal_id == m.Journal.id)
        .where(m.Journal.trader_id.in_(_not_development()))
        .group_by(m.Journal.id).order_by(func.max(m.JournalFieldEntry.entered_at).desc())
        .limit(FEED_LENGTH)
    ).all()
    lines += [(at, f"{real[t].login_id} wrote in a journal") for t, at in written]
    opened = sess.execute(
        select(m.Journal.trader_id, m.Journal.opened_at)
        .where(m.Journal.opened_at.is_not(None), m.Journal.trader_id.in_(_not_development()))
        .order_by(m.Journal.opened_at.desc()).limit(FEED_LENGTH)
    ).all()
    lines += [(at, f"{real[t].login_id} opened a journal") for t, at in opened]
    return lines


def _rows_read(row) -> str:
    return f"{formatting.count(row.rows_parsed)} of {formatting.count(row.rows_in)}"


def _step(reader: _Reader) -> str:
    """The furthest step with a stored trace, in the order the ticket walks them. The reveal
    is no step here: reaching it leaves no trace."""
    if reader.budget:
        return "budget"
    if reader.journal_opened or reader.journals_written:
        return "journal"
    if reader.furthest_chapter:
        return f"chapter {reader.furthest_chapter}"
    if reader.guess:
        return "guess"
    if reader.uploads:
        return "uploaded"
    return "consented" if reader.consented else "signed up"


def _on_current(reader: _Reader, running_version: str) -> str:
    """The latest file read, against this deploy. A refused file reads nothing, so it neither
    counts nor hides that what he is looking at was read by an older deploy."""
    if reader.latest_read is None:
        return NOT_RECORDED
    stamped = reader.latest_read.code_version
    if UNKNOWN_VERSION in (stamped, running_version):
        return NOT_RECORDED
    return "yes" if stamped == running_version else "no"


def _health_from(reader: _Reader):
    """The latest file read, or with none read, the latest refused."""
    return reader.latest_read or reader.latest_any


def _row(reader: _Reader, *, running_version: str, duplicates: dict[int, int],
         guess_on: bool, leaving_on: bool, feedback_chapters: list[int]) -> dict:
    latest = _health_from(reader)
    return {
        "name": _name(reader.name),
        "login_id": _name(reader.login_id),
        "step": _step(reader),
        "rows_read": _rows_read(latest) if latest else NOT_RECORDED,
        "rows_refused": latest.rows_in - latest.rows_parsed if latest else NOT_RECORDED,
        "uploads_refused": reader.uploads_refused,
        "duplicates": duplicates.get(latest.id, 0) if latest else NOT_RECORDED,
        "on_current": _on_current(reader, running_version),
        "facts_read": f"{len(reader.facts)} of {len(SM.FACTS)}",
        "minutes": _span(reader.dwell_ms),
        "drawer_opens": reader.drawer_opens,
        "chapters": [reader.chapters.get(n, NOT_RECORDED) for n in feedback_chapters],
        "report": reader.report or NOT_RECORDED,
        "journals_written": reader.journals_written,
        "budget": "set" if reader.budget else "no",
        "guess": "answered" if reader.guess else ("no" if guess_on else NOT_RECORDED),
        "leaving": reader.leaving or ("no" if leaving_on else NOT_RECORDED),
        "wtp": reader.wtp or NOT_RECORDED,
        "last_seen": _when(max(reader.seen, default=None)),
    }


def _last_seen(reader: _Reader) -> datetime:
    return max(reader.seen, default=NEVER)


def _least_read(readers: dict[str, set[int]]) -> str:
    """The fact the fewest read, every one of them if tied. Empty until anyone read anything."""
    if not any(readers.values()):
        return NOT_RECORDED
    fewest = min(len(who) for who in readers.values())
    return ", ".join(SM.FACTS[key].title for key, who in readers.items() if len(who) == fewest)


def _most_opened(drawers: dict[str, int]) -> str:
    if not drawers:
        return NOT_RECORDED
    return SM.FACTS[max(drawers, key=lambda key: drawers[key])].title


def build(sess: Session, *, running_version: str, production: bool) -> dict:
    """Everything the page draws, written out: the template computes nothing (T7)."""
    accounts = sess.execute(
        select(m.Trader.id, m.Trader.display_name, m.Trader.login_id, m.Trader.created_at,
               m.Trader.development_data).order_by(m.Trader.id)
    ).all()
    real = {a.id: _Reader(id=a.id, name=a.display_name, login_id=a.login_id)
            for a in accounts if not a.development_data}

    declines = 0
    for trader_id, purpose, granted in sess.execute(
        select(m.ConsentEvent.trader_id, m.ConsentEvent.purpose, m.ConsentEvent.granted)
    ):
        reader = real.get(trader_id)
        if reader is None:
            continue
        if not granted:
            declines += 1
        elif purpose is s.ConsentPurpose.DIAGNOSIS:
            reader.consented = True

    imports = _read_imports(sess, real)
    latest_ids = {_health_from(r).id for r in real.values() if r.uploads}
    duplicates = {
        import_id: times for import_id, times in sess.execute(
            select(m.ImportRow.import_id, func.count())
            .where(m.ImportRow.flag.in_(DUPLICATE_FLAGS))
            .group_by(m.ImportRow.import_id)
        ) if import_id in latest_ids
    }
    readers, drawers = _read_dwell(sess, real)
    answer_lines = _read_answers(sess, real)
    _read_journals(sess, real)
    wtp_answers = _read_features(sess, real)
    wtp_asked = sum(1 for t in sess.scalars(select(m.WtpAsked.trader_id)) if t in real)
    deleted, last_deleted = sess.execute(
        select(func.count(), func.max(m.DeletionRecord.completed_at))
    ).one()

    feed_lines = (answer_lines + _feed_of_uploads(sess, real, imports)
                  + _feed_of_reading(sess, real))
    feed_lines.sort(key=lambda line: line[0], reverse=True)

    guess_on, leaving_on = GU.ready(production), LC.ready(production)
    feedback_chapters = [c.number for c in SM.CHAPTERS if c.feedback]
    rows = [_row(r, running_version=running_version, duplicates=duplicates, guess_on=guess_on,
                 leaving_on=leaving_on, feedback_chapters=feedback_chapters)
            for r in sorted(real.values(), key=_last_seen, reverse=True)]
    uploaded = [r for r in real.values() if r.uploads]
    chapter_four = [r.chapter_four_ms for r in real.values() if r.chapter_four_ms]
    return {
        "running_version": running_version,
        "fact_total": len(SM.FACTS),
        "feedback_chapters": feedback_chapters,
        "features_off": [name for name, on in (("guess", guess_on), ("leaving card", leaving_on))
                         if not on],
        "cards": {
            "signed_up": len(real),
            "uploaded": len(uploaded),
            "reached_reveal": NOT_RECORDED,
            "upload_to_reveal": NOT_RECORDED,
            "read_all": sum(1 for r in uploaded if len(r.facts) == len(SM.FACTS)),
            "stopped_early": sum(1 for r in uploaded if 0 < len(r.facts) < len(SM.FACTS)),
            "read_none": sum(1 for r in uploaded if not r.facts),
            "said_wrong": sum(1 for r in real.values() if r.said_wrong),
        },
        "rows": rows,
        "feed": [{"when": _when(at), "text": _name(text)} for at, text in feed_lines[:FEED_LENGTH]],
        "quiet": {
            "least_read": _least_read(readers),
            "most_opened": _most_opened(drawers),
            "chapter_four_median": _span(statistics.median(chapter_four)) if chapter_four
            else NOT_RECORDED,
            "wtp": wtp_answers,
            "wtp_asked": wtp_asked,
            "deletions": deleted,
            "last_deletion": _when(last_deleted),
            "consent_declines": declines,
        },
        "dev_accounts": [{"name": _name(a.display_name), "login_id": _name(a.login_id),
                          "joined": _when(a.created_at)}
                         for a in accounts if a.development_data],
    }
