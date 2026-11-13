"""TICKET-825: the report gets a real ending.

What it found, what it doesn't do and why, three next steps, a way back, and one
question about the whole report. Figures here are synthetic and worked by hand.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from services.production.api import cli
from services.production.api import scope_facts as SF
from services.production.db import models as m
from services.production.db.session import make_session
from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s
from tests.unit.api.test_no_claims import CLAIM_PATTERNS, NEVER_USED

PAGE = "/mirror/fact/not-told"
TOKEN = re.compile(r'name="csrf_token" value="([^"]+)"')


def trip(net, *, name="t", option=True, held_days=0, symbol="WIDGET") -> mx.Trip:
    entry = datetime(2025, 3, 3, 10, 0, tzinfo=UTC)
    leave = entry + timedelta(days=held_days, minutes=10)
    return mx.Trip(
        trip_id=f"{name}{net}", symbol=symbol, trading_day="2025-03-03", entry_ts=entry,
        exit_ts=leave, holding_seconds=int((leave - entry).total_seconds()),
        net=Decimal(str(net)), lots=1, risk_unit_source=s.RiskUnitSourceV1.PREMIUM_PAID,
        is_option=option,
    )


def text_of(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html).replace("&#39;", "'").split())


def section(html: str, name: str) -> str:
    found = re.search(rf'<section class="ending__{name}[ "].*?</section>', html, re.DOTALL)
    assert found, f"no {name} section"
    return found.group(0)


# ---------- The figures ----------


def test_the_option_result_adds_up_options_alone():
    book = mx.option_result([trip(-100), trip(-50), trip(30, option=False)])
    assert book.net == Decimal(-150) and book.count == 2


def test_the_trade_set_against_it_is_the_largest_held_gain_outside_options():
    book = mx.option_result([
        trip(-150),
        trip(500, option=False),  # same-day, so it was not held
        trip(70, option=False, held_days=40, symbol="SMALLER"),
        trip(90, option=False, held_days=30, symbol="LARGER"),
        trip(900, held_days=30),  # an option, so already inside the total
    ])
    assert book.held_gain.symbol == "LARGER" and book.held_gain_days == 30


def test_no_held_gain_outside_options_means_nothing_is_set_against_it():
    book = mx.option_result([trip(-150), trip(-20, option=False, held_days=30)])
    assert book.held_gain is None and book.held_gain_days is None


def test_a_history_with_no_options_has_no_option_result():
    assert mx.option_result([trip(40, option=False)]) is None


# ---------- The page ----------


def test_it_leads_with_a_statement_and_not_a_count(client):
    page = client.get(PAGE).text
    assert re.search(r"<h1[^>]*>\s*This report counts\. It doesn(&#39;|')t judge\.\s*</h1>", page)
    assert "num--hero" not in page


def test_it_promises_nothing_with_yet(client):
    assert not re.search(r"\byet\b", text_of(client.get(PAGE).text), re.IGNORECASE)


def test_the_takeaways_come_first_one_line_per_chapter(client):
    page = client.get(PAGE).text
    found = section(page, "found")
    assert found.count("<li") == 3
    assert "Your option trades" in text_of(found)
    assert "Your longest run of consecutive losers was" in text_of(found)
    assert "Your busiest was" in text_of(found)
    assert page.index("ending__found") < page.index("ending__table")


def test_a_loss_is_said_once_not_as_lost_minus(client):
    found = text_of(section(client.get(PAGE).text, "found"))
    assert "Your option trades lost ₹" in found or "Your option trades made ₹" in found
    assert "lost −" not in found


def test_no_line_that_waits_on_the_research_seat_ships(client):
    found = text_of(section(client.get(PAGE).text, "found"))
    for line in ("options you bought", "5 and 7 pm", "crude", "Right after two losses",
                 "already down"):
        assert line not in found


@pytest.mark.parametrize("row", [
    ("Name a cause", "Your file has your trades, not what the market was doing",
     "Shows where and when the results came from"),
    ("Score you", "Scope doesn't grade traders, against anyone or against yourself",
     "Counts your trades against a number you choose"),
    ("Estimate what a habit cost you",
     "That needs a fair \"what you'd have done instead\", which a file of fills can't give",
     "Shows what each group of trades actually made or lost"),
    ("Recommend a change", "Counts, not advice. No buy or sell calls, ever.",
     "Leaves the decision with you"),
])
def test_the_four_statements_are_a_table(client, row):
    table = section(client.get(PAGE).text, "table")
    said = text_of(table).replace("&#34;", '"').replace("&quot;", '"')
    for cell in row:
        assert cell in said
    assert table.count("<tr") == 5  # the header and the four


def test_the_table_does_not_use_the_kits_figure_table(client):
    """The kit's .table is monospace and never wraps: this one ran 675 px wide on a phone."""
    assert 'class="table"' not in section(client.get(PAGE).text, "table")


def test_the_number_you_choose_links_to_the_budget(client):
    assert 'href="/budget"' in section(client.get(PAGE).text, "table")


def test_the_honest_line_stays(client):
    assert ("The checks that could say more need work we have not finished and evidence "
            "we have not earned.") in text_of(client.get(PAGE).text)


def test_the_steps_are_a_day_a_page_and_a_journal(client):
    """Ruling on TICKET-825, 4 Nov: three things to look at, never three things to do."""
    steps = section(client.get(PAGE).text, "steps")
    assert "Where to look next" in text_of(steps)
    links = re.findall(r'<a class="step" href="([^"]+)"', steps)
    assert len(links) == 3
    assert links[0].startswith("/mirror/fact/run")
    assert links[1].startswith("/mirror/fact/worst-days")
    assert links[2].startswith("/journals")


def test_no_step_reads_as_advice(client):
    said = text_of(section(client.get(PAGE).text, "steps")).lower()
    for word in ("try", "avoid", "set", "stop", "consider", "upload", "should", "can do"):
        assert not re.search(rf"\b{word}\b", said), word


def test_no_step_sends_him_to_do_something(client):
    steps = section(client.get(PAGE).text, "steps")
    assert 'href="/budget"' not in steps and 'href="/upload"' not in steps


def test_each_step_says_what_is_there_with_its_number(client):
    said = text_of(section(client.get(PAGE).text, "steps"))
    day = r"\d{2} \w{3}(?: \d{4})?"
    assert re.search(rf"{day} — ?\s*\d+ losses in a row", said), said
    assert re.search(r"Your five worst days — [−+]?₹[\d,]+", said), said
    assert re.search(rf"Your journal for {day} — one of your five worst days:\s+\d+ trades?, "
                     r"[−+]?₹[\d,]+", said), said


@pytest.mark.parametrize(("minutes", "written"), [
    (45, "45 minutes"), (1, "1 minute"), (60, "1 hour"), (119, "2 hours"),
])
def test_a_run_is_timed_in_plain_words(minutes, written):
    assert SF.span_words(minutes) == written


def test_there_is_a_way_back_to_the_report(client):
    assert 'class="ending__back" href="/mirror"' in client.get(PAGE).text


def _journals(engine, **versions) -> None:
    """A Journal for each trading day in the fixture; version_no from versions, or 1."""
    with make_session(engine) as sess:
        imp = sess.scalars(select(m.Import)).first()
        days = sorted(set(sess.scalars(select(m.Trip.trading_day))))
        for day in days:
            for version in range(1, versions.get("top", 1) + 1):
                sess.add(m.Journal(
                    trader_id=imp.trader_id, import_id=imp.id, unit=s.JournalUnit.DAY,
                    period_start=day, period_end=day, version_no=version,
                    generated_at=datetime.now(UTC), trip_ids="[]", sections="{}"))
        sess.commit()


def test_the_journal_step_opens_on_the_flagged_day(client, engine):
    _journals(engine)
    steps = section(client.get(PAGE).text, "steps")
    opened = re.findall(r'href="/journals/(\d+)"', steps)
    assert len(opened) == 1
    with make_session(engine) as sess:
        assert sess.get(m.Journal, int(opened[0])).period_start


def test_the_flagged_day_opens_on_its_latest_version(client, engine):
    _journals(engine, top=2)
    with make_session(engine) as sess:
        latest = {j.id for j in sess.scalars(select(m.Journal).where(m.Journal.version_no == 2))}
    opened = re.findall(r'href="/journals/(\d+)"', section(client.get(PAGE).text, "steps"))
    assert opened and {int(i) for i in opened} <= latest


def test_with_no_journal_for_that_day_the_step_opens_the_list(client):
    steps = section(client.get(PAGE).text, "steps")
    assert 'href="/journals"' in steps and not re.search(r'href="/journals/\d+"', steps)


def _a_later_file(engine, keep: int) -> None:
    """A second import: `keep` of the first file's trades."""
    with make_session(engine) as sess:
        first = sess.scalars(select(m.Import)).first()
        raw = m.RawFile(trader_id=first.trader_id, sha256="e" * 64, original_name="later.csv",
                        size=1, stored_path="/tmp/later", uploaded_at=datetime.now(UTC))
        sess.add(raw)
        sess.flush()
        later = m.Import(
            trader_id=first.trader_id, raw_file_id=raw.id, source_account="A",
            adapter_id=first.adapter_id, adapter_version="1", filemap_version="1",
            code_version="fixturesha", outcome=first.outcome, rows_in=keep, rows_parsed=keep,
            rows_excluded=0, fees_available=False, version_no=2, trips_reconstructed=keep,
            trips_refused=0, density_default_unit="day", created_at=datetime.now(UTC))
        sess.add(later)
        sess.flush()
        for t in sess.scalars(select(m.Trip).where(m.Trip.import_id == first.id)
                              .order_by(m.Trip.id).limit(keep)).all():
            sess.add(m.Trip(
                import_id=later.id, trip_id=t.trip_id, trading_day=t.trading_day,
                exchange=t.exchange, symbol=t.symbol, segment=t.segment, direction=t.direction,
                entry_ts=t.entry_ts, exit_ts=t.exit_ts, quantity=t.quantity,
                entry_price=t.entry_price, exit_price=t.exit_price, gross=t.gross, fees=t.fees,
                net=t.net, fees_available=False, risk_unit_source=t.risk_unit_source))
        sess.commit()


def test_one_file_has_nothing_to_compare(client):
    assert "ending__changed" not in client.get(PAGE).text


def test_a_second_file_compares_counts_and_never_a_score(client, engine):
    _a_later_file(engine, 38)
    said = text_of(section(client.get(PAGE).text, "changed"))
    assert "What changed since your last file" in said
    assert "Trades: 38 in this file, 40 in your last file." in said
    assert re.search(r"Trading days: \d+ in this file, \d+ in your last file\.", said)
    for word in ("better", "worse", "improved", "progress", "%"):
        assert word not in said.lower()


def test_nothing_new_on_the_page_makes_a_claim(client):
    said = text_of(client.get(PAGE).text).lower().replace("estimate what a habit cost you", "")
    for word in NEVER_USED:
        assert not re.search(rf"\b{re.escape(word)}\b", said), word
    for pattern, why in CLAIM_PATTERNS:
        found = re.search(pattern, said)
        assert found is None, f"{why}: {found.group(0)!r}"


# ---------- The question about the whole report ----------


def ask(client, **data):
    token = TOKEN.search(section(client.get(PAGE).text, "check")).group(1)
    return client.post("/mirror/feedback", data={"csrf_token": token, **data},
                       follow_redirects=False)


def stored(engine) -> list[tuple]:
    with make_session(engine) as sess:
        return [(r.answer, r.note, r.trading_day)
                for r in sess.scalars(select(m.ReportFeedback).order_by(m.ReportFeedback.id))]


def test_the_page_asks_about_the_whole_report(client):
    check = section(client.get(PAGE).text, "check")
    said = text_of(check)
    assert "Does this match your trading?" in said
    for label in ("Accurate", "Not sure", "Wrong"):
        assert f">{label}</button>" in check
    assert "What did we get wrong?" in said
    assert "We use this only to check and fix your report." in said
    assert '<textarea' in check and 'name="note"' in check


def test_an_answer_and_its_note_are_kept_and_the_page_says_so(client, engine):
    response = ask(client, answer="wrong", note="  27 Mar is one spread, not two trades  ")
    assert response.status_code == 303 and response.headers["location"] == f"{PAGE}#report-check"
    assert stored(engine) == [("wrong", "27 Mar is one spread, not two trades", "")]
    check = section(client.get(PAGE).text, "check")
    assert "Recorded. Thank you." in check and "<textarea" not in check


def test_a_note_is_optional(client, engine):
    ask(client, answer="accurate", note="   ")
    assert stored(engine) == [("accurate", None, "")]


def test_a_long_note_is_kept_to_the_limit(client, engine):
    ask(client, answer="wrong", note="x" * 5000)
    assert len(stored(engine)[0][1]) == 2000


def test_the_first_answer_stands(client, engine):
    token = TOKEN.search(section(client.get(PAGE).text, "check")).group(1)
    for answer in ("wrong", "accurate"):
        client.post("/mirror/feedback", data={"csrf_token": token, "answer": answer},
                    follow_redirects=False)
    assert [row[0] for row in stored(engine)] == ["wrong"]


def test_a_new_file_is_a_new_report_and_is_asked_again(client, engine):
    ask(client, answer="wrong")
    _a_later_file(engine, 38)
    assert "<textarea" in section(client.get(PAGE).text, "check")


@pytest.mark.parametrize("answer", [None, "nonsense"])
def test_only_the_three_answers_count(client, engine, answer):
    data = {"answer": answer} if answer else {}
    assert ask(client, **data).status_code == 400
    assert stored(engine) == []


def test_a_form_with_no_token_is_refused(client, engine):
    assert client.post("/mirror/feedback", data={"answer": "wrong"}).status_code == 403
    assert stored(engine) == []


# ---------- Who reads it ----------


def test_the_admin_command_lists_what_needs_checking(client, engine, capsys):
    import os

    ask(client, answer="wrong", note="27 Mar\nis one spread")
    cli.main(["--db", os.environ["SCOPE_DB"], "wrong-reports"])
    out = capsys.readouterr().out
    assert "fx" in out and "whole report" in out and "27 Mar is one spread" in out
    with make_session(engine) as sess:
        assert sess.scalars(select(m.AdminAction.action)).all().count("wrong_reports") == 1


def test_an_accurate_answer_with_nothing_said_needs_no_checking(client, capsys):
    import os

    ask(client, answer="accurate")
    cli.main(["--db", os.environ["SCOPE_DB"], "wrong-reports"])
    assert "whole report" not in capsys.readouterr().out


def test_a_note_on_any_answer_reaches_the_list(client, capsys):
    import os

    ask(client, answer="not_sure", note="2 Apr looks short")
    cli.main(["--db", os.environ["SCOPE_DB"], "wrong-reports"])
    assert "2 Apr looks short" in capsys.readouterr().out
