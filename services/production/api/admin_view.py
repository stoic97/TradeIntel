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
from services.production.api import admin_ladder, formatting
from services.production.api import scope_map as SM
from services.production.ctr.intake import pipeline
from services.production.db import models as m
from services.production.journal import constants as k
from services.production.journal import leaving as LC
from services.production.journal import wtp as WTP
from services.production.mirror import feedback as FB
from services.production.mirror import guess as GU
from services.shared.schemas import scope_v1 as s

NOT_RECORDED = "—"
FEED_LENGTH = 40
TRAIL_LENGTH = 20
MINUTE_MS = 60 * 1000
ZONE = ZoneInfo("Asia/Kolkata")
NEVER = datetime.min.replace(tzinfo=UTC)
UNKNOWN_VERSION = "unknown"
VIEW_ACTION = "admin_view"
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


def _shown_id(login_id: str) -> str:
    """A login id that is an email is someone's address, and this page gets screenshotted, so
    it shows only enough to tell two apart."""
    local, at, domain = login_id.partition("@")
    return f"{local[:2]}…@{domain[:1]}…" if at and local and domain else login_id


def _tallies(sess: Session) -> dict:
    """The page's small counts in one statement, so a panel's tally doesn't cost a query of its own.

    The load-budget test caps queries per load; page views, the last wrong-reports run and
    deletions were three statements and are now one.
    """
    is_view = m.AdminAction.action == VIEW_ACTION
    views, last_view, last_read, deleted, last_deleted = sess.execute(
        select(func.count().filter(is_view), func.max(m.AdminAction.at).filter(is_view),
               func.max(m.AdminAction.at).filter(m.AdminAction.action == "wrong_reports"),
               select(func.count()).select_from(m.DeletionRecord).scalar_subquery(),
               select(func.max(m.DeletionRecord.completed_at)).scalar_subquery())
        .select_from(m.AdminAction)
    ).one()
    return {"views": views, "last_view": last_view, "last_read": last_read,
            "deleted": deleted, "last_deleted": last_deleted}


def _trail(sess: Session, accounts: list[tuple], tally: dict) -> tuple[list[dict], dict]:
    """What admins did, newest first. Page views would crowd out the rest, so they are a count."""
    ids = {f"trader:{a.id}": _shown_id(a.login_id) for a in accounts}
    rows = sess.execute(
        select(m.AdminAction.actor, m.AdminAction.action, m.AdminAction.target, m.AdminAction.at)
        .where(m.AdminAction.action != VIEW_ACTION).order_by(m.AdminAction.at.desc(), m.AdminAction.id.desc())
        .limit(TRAIL_LENGTH)
    ).all()
    return ([{"who": ids.get(actor, _name(actor)), "action": action,
              "target": _name(_shown_id(target)) if target else NOT_RECORDED, "when": _when(at)}
             for actor, action, target, at in rows],
            {"count": tally["views"], "last": _when(tally["last_view"])})


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
    drawer_opens: int = 0
    chapters: dict[int, str] = field(default_factory=dict)
    said_wrong: bool = False
    report: str | None = None
    journals_written: int = 0
    journals_opened: int = 0
    first_upload: datetime | None = None
    own_files: int = 0  # the demo is no upload, so these leave it out
    first_own_file: datetime | None = None
    days_active: set = field(default_factory=set)
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
               m.Import.trips_reconstructed, m.Import.reconstruction_version,
               m.Import.adapter_id, m.Import.adapter_version)
        .order_by(m.Import.id)
    ).all()
    read = []
    for row in imports:
        reader = real.get(row.trader_id)
        if reader is None:
            continue
        read.append(row)
        reader.uploads += 1
        reader.first_upload = reader.first_upload or row.created_at
        reader.latest_any = row
        reader.seen.append(row.created_at)
        if demo.is_demo(row):
            reader.tried_demo = True
        else:
            reader.brought_real = True
            reader.own_files += 1
            reader.first_own_file = reader.first_own_file or row.created_at
        if row.outcome is s.ImportOutcome.REJECTED:
            reader.uploads_refused += 1
        else:
            reader.latest_read = row
        # The record a report reads is the newest import with trades (loader.current_import).
        # The import's own count says so: this page reads no trade, as its limits require.
        if row.trips_reconstructed:
            reader.file = FILE_DEMO if demo.is_demo(row) else FILE_REAL
    return read


def _read_dwell(sess: Session, real: dict[int, _Reader]) -> dict[str, int]:
    """Drawer opens per fact, while filling in what each reader read."""
    rows = sess.execute(
        select(m.DwellEvent.trader_id, m.DwellEvent.surface, m.DwellEvent.key, m.DwellEvent.event,
               func.count(), func.sum(m.DwellEvent.duration_ms), func.max(m.DwellEvent.at))
        .group_by(m.DwellEvent.trader_id, m.DwellEvent.surface, m.DwellEvent.key,
                  m.DwellEvent.event)
    ).all()
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
            reader.fact_ms[fact] = reader.fact_ms.get(fact, 0) + (total_ms or 0)
            reader.dwell_ms += total_ms or 0
    return drawers


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
        select(m.Journal.trader_id, func.max(m.Journal.opened_at), func.count())
        .where(m.Journal.opened_at.is_not(None)).group_by(m.Journal.trader_id)
    ).all()
    for trader_id, last, times in opened:
        if trader_id in real:
            real[trader_id].journal_opened = True
            real[trader_id].journals_opened = times
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


def _told(sess: Session, real: dict[int, _Reader], chapters: list[int], last_read: datetime | None) -> dict:
    """What traders said, in counts. Each trader's latest answer counts once. Notes are asked
    for only as present or not, so no typed word is ever fetched."""
    latest: dict[tuple[int, int], tuple[int, str]] = {}
    reasons: dict[int, list[str]] = {}
    for row_id, trader_id, chapter, answer, reason in sess.execute(
        select(m.ChapterFeedback.id, m.ChapterFeedback.trader_id, m.ChapterFeedback.chapter,
               m.ChapterFeedback.answer, m.ChapterFeedbackReason.reason)
        .outerjoin(m.ChapterFeedbackReason, m.ChapterFeedbackReason.feedback_id == m.ChapterFeedback.id)
        .order_by(m.ChapterFeedback.id)
    ):
        if trader_id in real:
            latest[trader_id, chapter] = (row_id, answer)
            if reason in FB.REASONS:
                reasons.setdefault(row_id, []).append(reason)
    rows = []
    for number in chapters:
        said = [found for (_, chapter), found in latest.items() if chapter == number]
        why = [reason for row_id, _ in said for reason in reasons.get(row_id, [])]
        rows.append({
            "chapter": number,
            "reached": sum(1 for r in real.values() if r.furthest_chapter >= number),
            **{key: sum(1 for _, answer in said if answer == key) for key in FB.ANSWERS},
            "reasons": ", ".join(f"{label} {why.count(key)}" for key, label in FB.REASONS.items()
                                 if why.count(key)) or NOT_RECORDED,
        })
    whole: dict[int, str] = {}
    days, waiting = set(), 0
    for trader_id, answer, day, noted, at in sess.execute(
        select(m.ReportFeedback.trader_id, m.ReportFeedback.answer, m.ReportFeedback.trading_day,
               m.ReportFeedback.note.is_not(None), m.ReportFeedback.answered_at)
        .order_by(m.ReportFeedback.id)
    ):
        if trader_id not in real:
            continue
        if day == FB.WHOLE_REPORT:
            whole[trader_id] = answer
        else:
            days.add((trader_id, day))
        if (answer == "wrong" or noted) and (last_read is None or at > last_read):
            waiting += 1
    wtp_noted = sum(1 for trader_id, noted in sess.execute(
        select(m.WtpAnswer.trader_id, m.WtpAnswer.free_text.is_not(None))) if noted and trader_id in real)
    return {"chapters": rows, "report": {key: list(whole.values()).count(key) for key in FB.ANSWERS},
            "days_wrong": len(days), "waiting": waiting, "wtp_noted": wtp_noted}


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
    return lines


def _code_seen(imports: list[tuple]) -> list[dict]:
    """Each version the first time an import shows it, newest first. Not a deploy time."""
    first_seen: dict[str, datetime] = {}
    for row in imports:
        if row.code_version != UNKNOWN_VERSION:
            first_seen.setdefault(row.code_version, row.created_at)
    return [{"version": version, "when": _when(at)} for version, at in
            sorted(first_seen.items(), key=lambda item: item[1], reverse=True)]


def _feed_of_joining(sess: Session, real: dict[int, _Reader], accounts: list[tuple]) -> list[tuple]:
    """Budget, charges, deletion, consent and sign-up, in the order a tie should read newest first.
    A budget line fetches no amount. A deleted account has no name left to give."""
    lines = []
    for trader_id, at in sess.execute(
        select(m.RiskBudgetDeclaration.trader_id, m.RiskBudgetDeclaration.declared_at)
        .where(m.RiskBudgetDeclaration.trader_id.in_(_not_development()))
        .order_by(m.RiskBudgetDeclaration.id.desc()).limit(FEED_LENGTH)
    ):
        lines.append((at, f"{real[trader_id].login_id} set a budget"))
    for trader_id, at in sess.execute(
        select(m.ChargeStatement.trader_id, m.ChargeStatement.uploaded_at)
        .where(m.ChargeStatement.trader_id.in_(_not_development()))
        .order_by(m.ChargeStatement.id.desc()).limit(FEED_LENGTH)
    ):
        lines.append((at, f"{real[trader_id].login_id} added a charges file"))
    development = {a.id for a in accounts if a.development_data}
    for trader_id, at in sess.execute(
        select(m.DeletionRecord.trader_id, m.DeletionRecord.completed_at)
        .where(m.DeletionRecord.completed_at.is_not(None))
        .order_by(m.DeletionRecord.id.desc()).limit(FEED_LENGTH)
    ):
        if trader_id not in development:
            lines.append((at, "An account was deleted"))
    for trader_id, purpose, granted, at in sess.execute(
        select(m.ConsentEvent.trader_id, m.ConsentEvent.purpose, m.ConsentEvent.granted, m.ConsentEvent.at)
        .where(m.ConsentEvent.trader_id.in_(_not_development()))
        .order_by(m.ConsentEvent.id.desc()).limit(FEED_LENGTH)
    ):
        said = "gave consent" if granted else "withdrew consent"
        lines.append((at, f"{real[trader_id].login_id} {said} for {purpose.value.lower().replace('_', ' ')}"))
    lines += [(a.created_at, f"{real[a.id].login_id} signed up") for a in accounts
              if a.id in real and a.created_at is not None]  # older accounts have no time to place
    return lines


def _feed(lines: list[tuple]) -> list[dict]:
    """Newest first and cut off, with an IST day heading on each day's first line."""
    out, day = [], None
    for at, text in sorted(lines, key=lambda line: line[0], reverse=True)[:FEED_LENGTH]:
        local = at.astimezone(ZONE)
        heading = local.strftime("%d %b %Y")
        out.append({"when": _when(at), "time": local.strftime("%H:%M"), "text": _name(text),
                    "day_head": heading if heading != day else None})
        day = heading
    return out


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


def _read_active_days(sess: Session, real: dict[int, _Reader]) -> None:
    """India dates with any stored action, one distinct query per table. A visit that writes
    nothing leaves no date, so this is a floor."""
    stamps = ((m.Trader.id, m.Trader.created_at), (m.ConsentEvent.trader_id, m.ConsentEvent.at),
              (m.Import.trader_id, m.Import.created_at), (m.DwellEvent.trader_id, m.DwellEvent.at),
              (m.ChapterFeedback.trader_id, m.ChapterFeedback.answered_at),
              (m.ReportFeedback.trader_id, m.ReportFeedback.answered_at),
              (m.Journal.trader_id, m.Journal.opened_at),
              (m.RiskBudgetDeclaration.trader_id, m.RiskBudgetDeclaration.declared_at))
    queries = [select(who, when).distinct() for who, when in stamps]
    queries.append(select(m.Journal.trader_id, m.JournalFieldEntry.entered_at).distinct()
                   .join(m.JournalFieldEntry, m.JournalFieldEntry.journal_id == m.Journal.id))
    for query in queries:
        for trader_id, at in sess.execute(query):
            if trader_id in real and at is not None:
                real[trader_id].days_active.add(at.astimezone(ZONE).date())


def _journey(reader: _Reader) -> list[dict]:
    """Each step on its own, because one word hid the rest. Reaching the reveal leaves no trace."""
    chapter = f"chapter {reader.furthest_chapter}" if reader.furthest_chapter else "chapter"
    return [{"label": label, "done": done} for label, done in (
        ("consent", reader.consented), ("demo" if reader.file == FILE_DEMO else "file", bool(reader.uploads)),
        (chapter, bool(reader.furthest_chapter)),
        ("journal", reader.journal_opened or bool(reader.journals_written)),
        ("budget", reader.budget))]


def _pay_progress(reader: _Reader, now: datetime) -> str:
    """How close the would-pay question is, by the rule in wtp.should_ask."""
    settled = reader.uploads >= 2 or (reader.first_upload is not None and (
        now - reader.first_upload).days >= k.WTP_DAYS_SINCE_FIRST_UPLOAD)
    return (f"{reader.journals_opened} of {WTP.JOURNALS_BEFORE_ASKING} journals; "
            f"settled in: {'yes' if settled else 'no'}")


def _reads_differently(reader: _Reader) -> str:
    """Whether today's code would build the latest file read differently: the question the
    trader's read-again offer asks, never the deploy, which moves on every merge. A refused
    file reads nothing, so it neither counts nor hides the reading he is still looking at."""
    if reader.latest_read is None:
        return NOT_RECORDED
    return "yes" if pipeline.out_of_date(reader.latest_read) else "no"


def _health_from(reader: _Reader):
    """The latest file read, or with none read, the latest refused."""
    return reader.latest_read or reader.latest_any


def _row(reader: _Reader, *, duplicates: dict[int, int],
         guess_on: bool, leaving_on: bool, feedback_chapters: list[int]) -> dict:
    latest = _health_from(reader)
    return {
        "href": f"/admin/traders/{reader.id}",
        "name": _name(reader.name),
        "login_id": _name(reader.login_id),
        "file": reader.file,
        "journey": _journey(reader),
        "files_uploaded": reader.own_files,
        "first_upload": _when(reader.first_own_file),
        "days_active": len(reader.days_active),
        "journals_opened": reader.journals_opened,
        "pay_progress": _pay_progress(reader, datetime.now(UTC)),
        "rows_read": _rows_read(latest) if latest else NOT_RECORDED,
        # A set-aside row was read and not refused. Older readings counted it in both.
        "rows_refused": (max(0, latest.rows_in - latest.rows_parsed - latest.rows_excluded)
                         if latest else NOT_RECORDED),
        "uploads_refused": reader.uploads_refused,
        "duplicates": duplicates.get(latest.id, 0) if latest else NOT_RECORDED,
        "reads_differently": _reads_differently(reader),
        "facts_read": f"{len(reader.fact_ms)} of {len(SM.FACTS)}",
        "minutes": _span(reader.dwell_ms),
        "drawer_opens": reader.drawer_opens,
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


def _most_opened(drawers: dict[str, int]) -> str:
    if not drawers:
        return NOT_RECORDED
    return SM.FACTS[max(drawers, key=lambda key: drawers[key])].title


def _left_out(count: int) -> str:
    """How many accounts the cards do not count, so a low number is not misread."""
    if count == 0:
        return "No development accounts are left out"
    return ("1 development account is left out" if count == 1
            else f"{formatting.count(count)} development accounts are left out")


def build(sess: Session, *, running_version: str, production: bool, now: datetime | None = None,
          last_looked: datetime | None = None, admin_ids: frozenset[str] = frozenset()) -> dict:
    """Everything the page draws, written out: the template computes nothing (T7)."""
    accounts = sess.execute(
        select(m.Trader.id, m.Trader.display_name, m.Trader.login_id, m.Trader.created_at,
               m.Trader.development_data).order_by(m.Trader.id)
    ).all()
    real = {a.id: _Reader(id=a.id, name=a.display_name, login_id=_shown_id(a.login_id),
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
    drawers = _read_dwell(sess, real)
    answer_lines = _read_answers(sess, real)
    _read_journals(sess, real)
    _read_active_days(sess, real)
    wtp_answers = _read_features(sess, real)
    wtp_asked = 0
    for trader_id, at in sess.execute(select(m.WtpAsked.trader_id, m.WtpAsked.asked_at)):
        if trader_id in real:
            wtp_asked += 1
            real[trader_id].seen.append(at)
    tally = _tallies(sess)
    deleted, last_deleted = tally["deleted"], tally["last_deleted"]

    feed_lines = (answer_lines + _feed_of_uploads(sess, real, imports)
                  + _feed_of_reading(sess, real) + _feed_of_joining(sess, real, accounts))

    guess_on, leaving_on = GU.ready(production), LC.ready(production)
    feedback_chapters = [c.number for c in SM.CHAPTERS if c.feedback]
    rows = [_row(r, duplicates=duplicates, guess_on=guess_on,
                 leaving_on=leaving_on, feedback_chapters=feedback_chapters)
            for r in sorted(real.values(), key=_last_seen, reverse=True)]
    on_real = [r for r in real.values() if r.file == FILE_REAL]
    on_demo = [r for r in real.values() if r.file == FILE_DEMO]
    trail, admin_views = _trail(sess, accounts, tally)
    return {
        "new_since": {"last_looked": _when(last_looked) if last_looked else None,
                      "lines": admin_ladder.new_since(sess, real, imports, last_looked)},
        "ladder": admin_ladder.ladder(sess, real, imports, now=now or datetime.now(UTC),
                                      fact_of=fact_of),
        "admins": sorted(_name(_shown_id(login_id)) for login_id in admin_ids),
        "trail": trail,
        "admin_views": admin_views,
        "running_version": running_version,
        "fact_total": len(SM.FACTS),
        "feedback_chapters": feedback_chapters,
        "features_off": [name for name, on in (("guess", guess_on), ("leaving card", leaving_on))
                         if not on],
        "cards": {
            "signed_up": len(real),
            "tried_demo": sum(1 for r in real.values() if r.tried_demo),
            "uploaded_real": sum(1 for r in real.values() if r.brought_real),
            "said_wrong": sum(1 for r in real.values() if r.said_wrong),
            "said_wrong_demo": sum(1 for r in real.values()
                                   if r.said_wrong and r.file == FILE_DEMO),
        },
        "rows": rows,
        "feed": _feed(feed_lines),
        "code_seen": _code_seen(imports),
        "told": _told(sess, real, feedback_chapters, tally["last_read"]),
        "fact_table": _fact_table(on_real, on_demo),
        "quiet": {
            "most_opened": _most_opened(drawers),
            "wtp": wtp_answers,
            "wtp_asked": wtp_asked,
            "deletions": deleted,
            "last_deletion": _when(last_deleted),
            "consent_declines": declines,
        },
        "dev_left_out": _left_out(sum(1 for a in accounts if a.development_data)),
        "dev_accounts": [{"name": _name(a.display_name), "login_id": _name(_shown_id(a.login_id)),
                          "joined": _when(a.created_at)}
                         for a in accounts if a.development_data],
    }
