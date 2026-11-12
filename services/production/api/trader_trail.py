"""/admin/traders/<id>: the trail around one trader's report, oldest first (TICKET-875).

When a trader says "it wouldn't take my file", this answers what happened and when, without
anyone running SQL on the box. ADR-007's sealing holds: no admin view of a trader's Mirror or
Journals. So, as in ``admin_view``, queries name their columns: a trade, a day's result, a
journal's text, a note, a budget's amount and a file's name, which is the broker's and can
hold the account number, are never fetched, and what was never read cannot be drawn.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from services.production import demo
from services.production.api import admin_view as av
from services.production.api import formatting
from services.production.api import scope_map as SM
from services.production.db import models as m
from services.production.journal import leaving as LC
from services.production.mirror import feedback as FB
from services.shared.schemas import scope_v1 as s


@dataclass(frozen=True)
class _Line:
    at: datetime
    text: str


def _how_many(n: int, one: str, many: str | None = None) -> str:
    return f"{formatting.count(n)} {one if n == 1 else many or one + 's'}"


def _consents(sess: Session, trader_id: int) -> list[_Line]:
    rows = sess.execute(
        select(m.ConsentEvent.purpose, m.ConsentEvent.granted, m.ConsentEvent.terms_version,
               m.ConsentEvent.at).where(m.ConsentEvent.trader_id == trader_id)
    ).all()
    return [
        _Line(at, f"Consent {'given' if granted else 'withdrawn'}: "
                  f"{purpose.value.lower().replace('_', ' ')}, terms version {terms}")
        for purpose, granted, terms, at in rows
    ]


def _file_facts(row, duplicates: int) -> str:
    refused = max(0, row.rows_in - row.rows_parsed - row.rows_excluded)
    return (f"{_how_many(row.rows_in, 'row')} in, {formatting.count(row.rows_parsed)} read, "
            f"{formatting.count(row.rows_excluded)} set aside, {formatting.count(refused)} refused, "
            f"{_how_many(duplicates, 'duplicate')} flagged, "
            f"reconstruction version {row.reconstruction_version or 'not recorded'}")


def _files(sess: Session, trader_id: int) -> list[_Line]:
    rows = sess.execute(
        select(m.Import.id, m.Import.outcome, m.Import.rejection_text, m.Import.source_account,
               m.Import.rows_in, m.Import.rows_parsed, m.Import.rows_excluded,
               m.Import.reconstruction_version, m.Import.raw_file_id, m.Import.created_at)
        .where(m.Import.trader_id == trader_id).order_by(m.Import.id)
    ).all()
    duplicates = dict(sess.execute(
        select(m.ImportRow.import_id, func.count())
        .join(m.Import, m.Import.id == m.ImportRow.import_id)
        .where(m.Import.trader_id == trader_id, m.ImportRow.flag.in_(av.DUPLICATE_FLAGS))
        .group_by(m.ImportRow.import_id)
    ).all())
    lines, seen_files = [], set()
    for row in rows:
        facts = _file_facts(row, duplicates.get(row.id, 0))
        again = row.raw_file_id in seen_files
        seen_files.add(row.raw_file_id)
        if row.outcome is s.ImportOutcome.REJECTED:
            reason = av.refusal_reason(row.rejection_text)
            said = f"Reason: {reason}" if reason else "No reason we can show"
            text = f"A file was refused: {facts}. {said}"
        elif demo.is_demo(row):
            text = f"The demo was read again: {facts}" if again else f"Loaded the demo: {facts}"
        elif again:
            text = f"A file was read again: {facts}"
        else:
            text = f"Uploaded a real file: {facts}"
        lines.append(_Line(row.created_at, text))
    charges = sess.scalars(
        select(m.ChargeStatement.uploaded_at).where(m.ChargeStatement.trader_id == trader_id)
    ).all()
    return lines + [_Line(at, "Sent a charges file") for at in charges]


def _reading(sess: Session, trader_id: int) -> list[_Line]:
    """One line per fact, at its first reading, with the time on it all told."""
    first: dict[str, datetime] = {}
    total: dict[str, int] = {}
    for key, ms, at in sess.execute(
        select(m.DwellEvent.key, m.DwellEvent.duration_ms, m.DwellEvent.at)
        .where(m.DwellEvent.trader_id == trader_id, m.DwellEvent.surface == av.MIRROR_LINE,
               m.DwellEvent.event == "view")
    ):
        fact = av.fact_of(key)
        if fact is None:
            continue
        first[fact] = min(first.get(fact, at), at)
        total[fact] = total.get(fact, 0) + (ms or 0)
    return [_Line(at, f"Read {SM.FACTS[fact].title}: {av._span(total[fact])} in all")
            for fact, at in first.items()]


def _answers(sess: Session, trader_id: int) -> list[_Line]:
    lines = []
    for chapter, answer, reason, at in sess.execute(
        select(m.ChapterFeedback.chapter, m.ChapterFeedback.answer,
               m.ChapterFeedbackReason.reason, m.ChapterFeedback.answered_at)
        .outerjoin(m.ChapterFeedbackReason,
                   m.ChapterFeedbackReason.feedback_id == m.ChapterFeedback.id)
        .where(m.ChapterFeedback.trader_id == trader_id)
    ):
        said = FB.ANSWERS.get(answer, av.NOT_RECORDED)
        why = FB.REASONS.get(reason)
        lines.append(_Line(at, f"Answered {said} on chapter {chapter}" + (f": {why}" if why else "")))
    for answer, day, noted, at in sess.execute(
        select(m.ReportFeedback.answer, m.ReportFeedback.trading_day,
               m.ReportFeedback.note.is_not(None), m.ReportFeedback.answered_at)
        .where(m.ReportFeedback.trader_id == trader_id)
    ):
        if day == FB.WHOLE_REPORT:
            said = FB.ANSWERS.get(answer, av.NOT_RECORDED)
            text = f"Answered {said} on the whole report"
        else:
            named = formatting.day(day) if av.ISO_DAY.fullmatch(day) else "A day"
            text = f"Said {named} looks wrong"
        lines.append(_Line(at, av._with_note(text, noted)))
    lines += [_Line(at, "Answered the guess") for at in sess.scalars(
        select(m.GuessAnswer.answered_at).where(m.GuessAnswer.trader_id == trader_id))]
    lines += [_Line(at, "Leaving card: shown") for at in sess.scalars(
        select(m.LeavingCardShown.shown_at).where(m.LeavingCardShown.trader_id == trader_id))]
    for outcome, at in sess.execute(
        select(m.LeavingCardAnswer.outcome, m.LeavingCardAnswer.answered_at)
        .where(m.LeavingCardAnswer.trader_id == trader_id)
    ):
        said = outcome if outcome in (LC.ANSWERED, LC.DISMISSED) else "shown"
        lines.append(_Line(at, f"Leaving card: {said}"))
    return lines


def _journals(sess: Session, trader_id: int) -> list[_Line]:
    """A Journal row is written by the upload, so only an opened or written one is his."""
    lines = [_Line(at, "Opened a journal") for at in sess.scalars(
        select(m.Journal.opened_at)
        .where(m.Journal.trader_id == trader_id, m.Journal.opened_at.is_not(None)))]
    for entries, last in sess.execute(
        select(func.count(distinct(m.JournalFieldEntry.id)), func.max(m.JournalFieldEntry.entered_at))
        .join(m.Journal, m.Journal.id == m.JournalFieldEntry.journal_id)
        .where(m.Journal.trader_id == trader_id).group_by(m.Journal.id)
    ):
        lines.append(_Line(last, f"Wrote in a journal: {_how_many(entries, 'entry', 'entries')}"))
    return lines


def _budget_and_pay(sess: Session, trader_id: int) -> list[_Line]:
    lines = [_Line(at, "Set a budget") for at in sess.scalars(
        select(m.RiskBudgetDeclaration.declared_at)
        .where(m.RiskBudgetDeclaration.trader_id == trader_id))]
    lines += [_Line(at, "Asked would pay") for at in sess.scalars(
        select(m.WtpAsked.asked_at).where(m.WtpAsked.trader_id == trader_id))]
    for answer, noted, at in sess.execute(
        select(m.WtpAnswer.answer, m.WtpAnswer.free_text.is_not(None), m.WtpAnswer.asked_at)
        .where(m.WtpAnswer.trader_id == trader_id)
    ):
        lines.append(_Line(at, av._with_note(f"Answered would pay: {answer}", noted)))
    return lines


def _deletions(sess: Session, trader_id: int, since: datetime | None, live: bool) -> list[_Line]:
    """An id can come back to a new account, so on a live one only what is after it began."""
    lines = []
    for requested, completed in sess.execute(
        select(m.DeletionRecord.requested_at, m.DeletionRecord.completed_at)
        .where(m.DeletionRecord.trader_id == trader_id)
    ):
        if live and (since is None or requested < since):
            continue
        lines.append(_Line(requested, "Deletion requested"))
        if completed is not None:
            lines.append(_Line(completed, "Deletion completed"))
    return lines


def build(sess: Session, trader_id: int) -> dict | None:
    """The whole page, written out, or None if this id means nothing here."""
    account = sess.execute(
        select(m.Trader.display_name, m.Trader.login_id, m.Trader.created_at,
               m.Trader.development_data).where(m.Trader.id == trader_id)
    ).first()
    deletions = _deletions(sess, trader_id, account.created_at if account else None,
                           live=account is not None)
    if account is None and not deletions:
        return None
    lines = list(deletions)
    if account is not None:
        if account.created_at is not None:
            lines.append(_Line(account.created_at, "Signed up"))
        lines += (_consents(sess, trader_id) + _files(sess, trader_id) + _reading(sess, trader_id)
                  + _answers(sess, trader_id) + _journals(sess, trader_id)
                  + _budget_and_pay(sess, trader_id))
    return {
        "trader_name": av._name(account.display_name) if account else None,
        "login_id": av._name(account.login_id) if account else None,
        "development": bool(account and account.development_data),
        "lines": [{"when": av._when(line.at), "text": av._name(line.text)}
                  for line in sorted(lines, key=lambda line: line.at)],
    }
