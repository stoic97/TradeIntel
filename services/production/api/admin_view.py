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

**The demo is no upload.** It goes through the same pipeline, so its import looks like any
other but for its source account (TICKET-865). Whether anyone trusted us with a real
tradebook is the question this page exists to answer, so the two are told apart everywhere.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from services.production import demo
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
FILE_REAL, FILE_DEMO, FILE_NONE = "real", "demo", "none"
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
    file: str = FILE_NONE  # what his report reads now
    tried_demo: bool = False
    brought_real: bool = False  # any file of his own, refused or read
    latest_any: tuple | None = None
    latest_read: tuple | None = None  # the latest not refused
    uploads: int = 0
    uploads_refused: int = 0
    fact_ms: dict[str, int] = field(default_factory=dict)  # each fact read, and for how long
    furthest_chapter: int = 0
    dwell_ms: int = 0
    chapters: dict[int, str] = field(default_factory=dict)
    said_wrong: bool = False
    report: str | None = None
    journals_written: int = 0
    journal_opened: bool = False
    budget: bool = False
    guess: bool = False
    leaving: str | None = None
    wtp: str | None = None
    signed_up: datetime | None = None
    seen: list[datetime] = field(default_factory=list)  # every stored action of his, sign-up first


def _read_imports(sess: Session, real: dict[int, _Reader]) -> list[tuple]:
    imports = sess.execute(
        select(m.Import.id, m.Import.trader_id, m.Import.outcome, m.Import.code_version,
               m.Import.rows_in, m.Import.rows_parsed, m.Import.rows_excluded,
               m.Import.created_at, m.Import.raw_file_id, m.Import.source_account,
               m.Import.trips_reconstructed)
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
        if demo.is_demo(row):
            reader.tried_demo = True
        else:
            reader.brought_real = True
        if row.outcome is s.ImportOutcome.REJECTED:
            reader.uploads_refused += 1
        else:
            reader.latest_read = row
        # The record a report reads is the newest import with trades (loader.current_import).
        # The import's own count says so: this page reads no trade, as its limits require.
        if row.trips_reconstructed:
            reader.file = FILE_DEMO if demo.is_demo(row) else FILE_REAL
    return read


def _read_dwell(sess: Session, real: dict[int, _Reader]) -> None:
    """What each reader read, and for how long."""
    rows = sess.execute(
        select(m.DwellEvent.trader_id, m.DwellEvent.surface, m.DwellEvent.key, m.DwellEvent.event,
               func.count(), func.sum(m.DwellEvent.duration_ms), func.max(m.DwellEvent.at))
        .group_by(m.DwellEvent.trader_id, m.DwellEvent.surface, m.DwellEvent.key,
                  m.DwellEvent.event)
    ).all()
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
            continue
        if kind == "view":
            reader.fact_ms[fact] = reader.fact_ms.get(fact, 0) + (total_ms or 0)
            reader.dwell_ms += total_ms or 0


def _read_answers(sess: Session, real: dict[int, _Reader]) -> list[tuple]:
    """Chapter and whole-report answers on each reader. Returns the feed's lines for them."""
    lines = []
    chapter_rows = sess.execute(
        select(m.ChapterFeedback.trader_id, m.ChapterFeedback.chapter, m.ChapterFeedback.answer,
               m.ChapterFeedbackReason.reason, m.ChapterFeedback.answered_at,
               m.ChapterFeedbackReason.given_at)
        .outerjoin(m.ChapterFeedbackReason,
                   m.ChapterFeedbackReason.feedback_id == m.ChapterFeedback.id)
    ).all()
    for trader_id, chapter, answer, reason, at, reason_at in chapter_rows:
        reader = real.get(trader_id)
        if reader is None:
            continue
        reader.seen += [at, reason_at] if reason_at else [at]
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
        reader.seen.append(at)
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
    for trader_id, at in sess.execute(
        select(m.RiskBudgetDeclaration.trader_id, m.RiskBudgetDeclaration.declared_at)
    ):
        if trader_id in real:
            real[trader_id].budget = True
            real[trader_id].seen.append(at)
    for trader_id, at in sess.execute(
        select(m.ChargeStatement.trader_id, m.ChargeStatement.uploaded_at)
    ):
        if trader_id in real:
            real[trader_id].seen.append(at)
    for trader_id, at in sess.execute(select(m.GuessAnswer.trader_id, m.GuessAnswer.answered_at)):
        if trader_id in real:
            real[trader_id].guess = True
            real[trader_id].seen.append(at)
    for trader_id, at in sess.execute(
        select(m.LeavingCardShown.trader_id, m.LeavingCardShown.shown_at)
    ):
        if trader_id in real:
            real[trader_id].leaving = "shown"
            real[trader_id].seen.append(at)
    for trader_id, outcome, at in sess.execute(
        select(m.LeavingCardAnswer.trader_id, m.LeavingCardAnswer.outcome,
               m.LeavingCardAnswer.answered_at)
    ):
        if trader_id in real:
            real[trader_id].leaving = outcome if outcome in (LC.ANSWERED, LC.DISMISSED) else "shown"
            real[trader_id].seen.append(at)

    answers = dict.fromkeys(("yes", "no", "maybe"), 0)
    for trader_id, answer, noted, at in sess.execute(
        select(m.WtpAnswer.trader_id, m.WtpAnswer.answer, m.WtpAnswer.free_text.is_not(None),
               m.WtpAnswer.asked_at)
        .order_by(m.WtpAnswer.id)
    ):
        if trader_id in real:
            real[trader_id].seen.append(at)
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
    # Only a re-read or a confirmation gives a second import to one stored file: neither
    # sent anything new.
    first_import_of = {}
    for row in imports:
        first_import_of.setdefault(row.raw_file_id, row.id)
    lines = []
    for row in imports[-FEED_LENGTH:]:
        who = real[row.trader_id].login_id
        if row.outcome is s.ImportOutcome.REJECTED:
            reason = refusal_reason(rejections.get(row.id))
            text = f"{who} had a file refused: {reason}" if reason else f"{who} had a file refused"
        elif demo.is_demo(row):
            again = first_import_of[row.raw_file_id] != row.id
            text = f"{who} had the demo read again" if again else f"{who} loaded the demo"
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
    if reader.file == FILE_DEMO:
        return "loaded the demo"
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


def _times(n: int, one: str, many: str, flagged: str = "refused") -> str | None:
    return f"{formatting.count(n)} {one if n == 1 else many} {flagged}" if n else None


def _issues(reader: _Reader, duplicates: dict[int, int]) -> tuple[str, int]:
    """Files refused, rows refused and duplicates, in words, and how many in all. Empty when
    there are none, so a real problem stands out in its column."""
    latest = _health_from(reader)
    rows = max(0, latest.rows_in - latest.rows_parsed - latest.rows_excluded) if latest else 0
    repeats = duplicates.get(latest.id, 0) if latest else 0
    said = (_times(reader.uploads_refused, "file", "files"), _times(rows, "row", "rows"),
            _times(repeats, "duplicate", "duplicates", "flagged"))
    return ", ".join(s for s in said if s), reader.uploads_refused + rows + repeats


def _row(reader: _Reader, *, running_version: str, duplicates: dict[int, int],
         guess_on: bool, leaving_on: bool, feedback_chapters: list[int]) -> dict:
    latest = _health_from(reader)
    return {
        "name": _name(reader.name),
        "login_id": _name(reader.login_id),
        "issues": _issues(reader, duplicates)[0],
        "file": reader.file,
        "step": _step(reader),
        "rows_read": _rows_read(latest) if latest else NOT_RECORDED,
        # A set-aside row was read and not refused. Older readings counted it in both.
        "rows_refused": (max(0, latest.rows_in - latest.rows_parsed - latest.rows_excluded)
                         if latest else NOT_RECORDED),
        "uploads_refused": reader.uploads_refused,
        "duplicates": duplicates.get(latest.id, 0) if latest else NOT_RECORDED,
        "on_current": _on_current(reader, running_version),
        "facts_read": f"{len(reader.fact_ms)} of {len(SM.FACTS)}",
        "minutes": _span(reader.dwell_ms),
        "chapters": [reader.chapters.get(n, NOT_RECORDED) for n in feedback_chapters],
        "report": reader.report or NOT_RECORDED,
        "journals_written": reader.journals_written,
        "budget": "set" if reader.budget else "no",
        "guess": "answered" if reader.guess else ("no" if guess_on else NOT_RECORDED),
        "leaving": reader.leaving or ("no" if leaving_on else NOT_RECORDED),
        "wtp": reader.wtp or NOT_RECORDED,
        "signed_up": _when(reader.signed_up),
        "last_activity": _when(max(reader.seen, default=None)),
    }


def _last_seen(reader: _Reader) -> datetime:
    return max(reader.seen, default=NEVER)


def _readers_of(key: str, group: list[_Reader]) -> tuple[int, str]:
    """How many of this group read a fact, and the median time of those who did."""
    times = [r.fact_ms[key] for r in group if key in r.fact_ms]
    return len(times), _span(statistics.median(times)) if times else NOT_RECORDED


def _covers(real_file: int, on_demo: int) -> str:
    total = real_file + on_demo
    noun = "trader" if total == 1 else "traders"
    return (f"Covers {formatting.count(total)} {noun}: {formatting.count(real_file)} with a "
            f"real file, {formatting.count(on_demo)} on the demo.")


def _fact_table(group_real: list[_Reader], group_demo: list[_Reader]) -> dict:
    """Every fact in report order, read or not: where readers stop is the point of it."""
    chapters = []
    for chapter in SM.CHAPTERS:
        facts = []
        for fact in chapter.facts:
            real_readers, real_median = _readers_of(fact.key, group_real)
            demo_readers, demo_median = _readers_of(fact.key, group_demo)
            facts.append({"title": fact.title, "real_readers": real_readers,
                          "real_median": real_median, "demo_readers": demo_readers,
                          "demo_median": demo_median})
        chapters.append({"number": chapter.number, "name": chapter.name, "facts": facts})
    return {"chapters": chapters, "covers": _covers(len(group_real), len(group_demo))}


def _reading(group: list[_Reader]) -> tuple[int, int, int]:
    """How many of these read every fact, stopped early, and read none."""
    return (sum(1 for r in group if len(r.fact_ms) == len(SM.FACTS)),
            sum(1 for r in group if 0 < len(r.fact_ms) < len(SM.FACTS)),
            sum(1 for r in group if not r.fact_ms))


SORTS = {
    "name": (lambda r, _d: r.name.lower(), False),
    "file": (lambda r, _d: r.file, False),
    "step": (lambda r, _d: _step(r), False),
    "facts": (lambda r, _d: len(r.fact_ms), True),
    "minutes": (lambda r, _d: r.dwell_ms, True),
    "issues": (lambda r, d: _issues(r, d)[1], True),
    "activity": (lambda r, _d: _last_seen(r), True),
}
"""What the table can sort by, and whether the most comes first. A plain link says which."""


def _sort_links(all_columns: bool) -> dict[str, str]:
    start = "/admin?columns=all&sort=" if all_columns else "/admin?sort="
    return {key: f"{start}{key}" for key in SORTS}


def _left_out(count: int) -> str:
    """How many accounts the cards do not count, so a low number is not misread."""
    if count == 0:
        return "No development accounts are left out"
    return ("1 development account is left out" if count == 1
            else f"{formatting.count(count)} development accounts are left out")


def build(sess: Session, *, running_version: str, production: bool, sort: str | None = None,
          all_columns: bool = False) -> dict:
    """Everything the page draws, written out: the template computes nothing (T7)."""
    accounts = sess.execute(
        select(m.Trader.id, m.Trader.display_name, m.Trader.login_id, m.Trader.created_at,
               m.Trader.development_data).order_by(m.Trader.id)
    ).all()
    real = {a.id: _Reader(id=a.id, name=a.display_name, login_id=a.login_id,
                          signed_up=a.created_at, seen=[a.created_at] if a.created_at else [])
            for a in accounts if not a.development_data}

    declines = 0
    for trader_id, purpose, granted, at in sess.execute(
        select(m.ConsentEvent.trader_id, m.ConsentEvent.purpose, m.ConsentEvent.granted,
               m.ConsentEvent.at)
    ):
        reader = real.get(trader_id)
        if reader is None:
            continue
        reader.seen.append(at)
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
    _read_dwell(sess, real)
    answer_lines = _read_answers(sess, real)
    _read_journals(sess, real)
    wtp_answers = _read_features(sess, real)
    wtp_asked = 0
    for trader_id, at in sess.execute(select(m.WtpAsked.trader_id, m.WtpAsked.asked_at)):
        if trader_id in real:
            wtp_asked += 1
            real[trader_id].seen.append(at)
    deleted, last_deleted = sess.execute(
        select(func.count(), func.max(m.DeletionRecord.completed_at))
    ).one()

    feed_lines = (answer_lines + _feed_of_uploads(sess, real, imports)
                  + _feed_of_reading(sess, real))
    feed_lines.sort(key=lambda line: line[0], reverse=True)

    guess_on, leaving_on = GU.ready(production), LC.ready(production)
    by, most_first = SORTS.get(sort, SORTS["activity"])
    feedback_chapters = [c.number for c in SM.CHAPTERS if c.feedback]
    rows = [_row(r, running_version=running_version, duplicates=duplicates, guess_on=guess_on,
                 leaving_on=leaving_on, feedback_chapters=feedback_chapters)
            for r in sorted(real.values(), key=lambda r: by(r, duplicates), reverse=most_first)]
    on_real = [r for r in real.values() if r.file == FILE_REAL]
    on_demo = [r for r in real.values() if r.file == FILE_DEMO]
    read_all, stopped_early, read_none = _reading(on_real)
    demo_read_all, demo_stopped_early, demo_read_none = _reading(on_demo)
    return {
        "running_version": running_version,
        "fact_total": len(SM.FACTS),
        "feedback_chapters": feedback_chapters,
        "all_columns": all_columns,
        "sort_links": _sort_links(all_columns),
        "guess_on": guess_on,
        "leaving_on": leaving_on,
        "features_off": [name for name, on in (("guess", guess_on), ("leaving card", leaving_on))
                         if not on],
        "cards": {
            "signed_up": len(real),
            "tried_demo": sum(1 for r in real.values() if r.tried_demo),
            "uploaded_real": sum(1 for r in real.values() if r.brought_real),
            "reached_reveal": NOT_RECORDED,
            "upload_to_reveal": NOT_RECORDED,
            "read_all": read_all,
            "stopped_early": stopped_early,
            "read_none": read_none,
            "demo_read_all": demo_read_all,
            "demo_stopped_early": demo_stopped_early,
            "demo_read_none": demo_read_none,
            "said_wrong": sum(1 for r in real.values() if r.said_wrong),
            "said_wrong_demo": sum(1 for r in real.values()
                                   if r.said_wrong and r.file == FILE_DEMO),
        },
        "rows": rows,
        "feed": [{"when": _when(at), "text": _name(text)} for at, text in feed_lines[:FEED_LENGTH]],
        "fact_table": _fact_table(on_real, on_demo),
        "quiet": {
            "wtp": wtp_answers,
            "wtp_asked": wtp_asked,
            "deletions": deleted,
            "last_deletion": _when(last_deleted),
            "consent_declines": declines,
        },
        "dev_left_out": _left_out(sum(1 for a in accounts if a.development_data)),
        "dev_accounts": [{"name": _name(a.display_name), "login_id": _name(a.login_id),
                          "joined": _when(a.created_at)}
                         for a in accounts if a.development_data],
    }
