"""TICKET-915 gates 1 and 2: up to three questions a day from that day's own trades, which
describe and never lead. Pawan, 17 Nov 2026: a question may state order and timing, never
the day's result in another form - no win/loss tally, no "ended the day down". A day is the
trade dicts the Journal page builds, in the order opened: net, and lots (None on a share)."""

from __future__ import annotations

import itertools
import re
from decimal import Decimal

from services.production.journal import day_questions as dq
from tests.helpers.no_claims import CLAIM_PATTERNS, NEVER_USED

LEADING = [r"\bwhy\b", r"\bbecause\b", r"\bshould\b", r"\bwere you\b"]
RESULT = [
    (r"\b\d+ of (?:your |the )?\d+\b", "a win/loss tally"),
    (r"\bended\b", "says how the day ended"),
    (r"\bdown\b", "says the day's direction"),
    (r"\bnet\b|\bprofit|\bgain", "says the day's result"),
]


def day(*nets, lots=None):
    lots = lots or [None] * len(nets)
    return [{"trip_id": f"t{i}", "net": Decimal(n), "lots": size}
            for i, (n, size) in enumerate(zip(nets, lots), start=1)]


def texts(trades):
    return [q.text for q in dq.questions_for(trades)]


def leads(text: str) -> str | None:
    """Why a sentence is not a plain description of the day's order, or None if it is."""
    low = text.lower()
    for word in NEVER_USED:
        if re.search(rf"\b{re.escape(word)}\b", low):
            return f"never-use word {word!r}"
    for pattern, why in CLAIM_PATTERNS:
        if re.search(pattern, low):
            return why
    for pattern in LEADING:
        if re.search(pattern, low):
            return f"leads: {pattern}"
    for pattern, why in RESULT:
        if re.search(pattern, low):
            return why
    if "\u20b9" in text or "100" in text:
        return "carries money"
    if text.endswith("?"):
        return "asks instead of describing"
    return None


def all_days():
    """Every short day: nets of -100, 0 and 100 over 1 to 6 trades; sizes 1 to 3 on 2 to 4."""
    for n in range(1, 7):
        for nets in itertools.product(["-100", "0", "100"], repeat=n):
            yield day(*nets)
    for n in range(2, 5):
        for lots in itertools.product([1, 2, 3], repeat=n):
            yield day(*["-100"] * n, lots=list(lots))


def timed_days():
    """TICKET-1012: days with times, sides and sessions, and his medians, so every new sentence
    (pace, straight back in, size steps, switching, the last hour, the first trade) is read too.
    Starts 1 to 400 minutes after the open, gaps of 0 to 45 minutes, sides that switch or don't,
    sizes that step or don't, NSE and MCX sessions, with and without his medians."""
    from datetime import datetime, time, timedelta, timezone
    ist = timezone(timedelta(hours=5, minutes=30))
    sessions = [(time(9, 15), time(15, 30), False), (time(9, 0), time(23, 30), True)]
    sides = [("calls", "calls"), ("calls", "puts"), ("long", "short")]
    for opens, closes, mcx in sessions:
        for start in (1, 7, 29, 75, 330, 400):
            for gap in (0, 2, 13, 45):
                for n in (2, 3, 5):
                    for pair in sides:
                        for stepped in (False, True):
                            t0 = datetime(2026, 3, 2, opens.hour, opens.minute, tzinfo=ist) + timedelta(minutes=start)
                            trades, t = [], t0
                            for i in range(n):
                                exit_ = t + timedelta(minutes=4)
                                trades.append({
                                    "trip_id": f"t{i}", "net": Decimal("-100" if i % 2 else "100"),
                                    "lots": (1 + i) if stepped else 1, "entry": t, "exit": exit_,
                                    "side": pair[i % 2], "opens": opens, "closes": closes,
                                    "evening": mcx and t.time() >= time(17, 0)})
                                t = exit_ + timedelta(minutes=gap)
                            for ctx in (None, {"median_gap": 30.0, "median_first": 500.0},
                                        {"median_gap": 1.0, "median_first": 3.0}):
                                yield trades, ctx


def test_no_new_sentence_leads_over_a_thousand_timed_days():
    """TICKET-1012: the same guard, over the new sentences."""
    cases = list(timed_days())
    assert len(cases) >= 1000
    sentences = {q.text for d, ctx in cases for q in dq.questions_for(d, context=ctx)}
    new = {s for s in sentences if any(s.startswith(p) for p in (
        "You took ", "Your next trade came", "You switched", "You opened ", "Your first trade came",
        "Your size went"))}
    assert len(new) > 20, "the guard read almost none of the new sentences"
    bad = {s: leads(s) for s in sentences if leads(s)}
    assert bad == {}
    for d, ctx in cases:
        qs = dq.questions_for(d, context=ctx)
        assert 1 <= len(qs) <= dq.MAX_QUESTIONS and len({q.key for q in qs}) == len(qs)


def test_the_guard_catches_a_verdict_a_tally_and_a_result_and_passes_a_fact():
    assert leads("Why did you revenge trade?") is not None
    assert leads("7 of 9 trades lost.") is not None
    assert leads("You ended the day down.") is not None
    assert leads("Your first trade lost and you traded 8 more times.") is None


def test_no_sentence_the_module_can_write_leads_over_a_thousand_days():
    days = list(all_days())
    assert len(days) >= 1000
    sentences = [s for d in days for s in texts(d)]
    assert len(set(sentences)) > 20, "the guard read almost nothing"
    bad = {s: leads(s) for s in set(sentences) if leads(s)}
    assert bad == {}


def test_every_day_with_a_trade_asks_between_one_and_three():
    for d in all_days():
        assert 1 <= len(dq.questions_for(d)) <= dq.MAX_QUESTIONS, [t["net"] for t in d]


def test_a_day_with_no_trades_asks_nothing():
    assert dq.questions_for([]) == []


def test_a_one_trade_day_says_so_and_not_how_it_went():
    assert texts(day("-500")) == ["You took one trade this day."]
    assert texts(day("200")) == ["You took one trade this day."]
    assert texts(day("-500", lots=[2])) == ["You took one trade this day, at 2 lots."]


def test_the_tickets_own_example():
    assert texts(day("-100", *["50"] * 8))[0] == "Your first trade lost and you traded 8 more times."


def test_one_more_time_is_singular():
    assert texts(day("50", "-10"))[0] == "Your first trade made money and you traded 1 more time."


def test_a_run_of_losses_is_said():
    assert "You had 3 losing trades in a row." in texts(day("50", "-10", "-20", "-30", "40"))


def test_what_came_after_the_biggest_loss_is_said():
    assert "After the day's biggest loss you traded 2 more times." in texts(
        day("50", "-10", "-90", "20", "30"))


def test_a_size_that_went_up_is_said():
    assert "Your size went from 1 lot to 3 lots." in texts(day("-10", "-20", lots=[1, 3]))


TWELVE = ("50", "-50", "-20", "30", "40", "-90", "10", "20", "-5", "60", "-70", "15")


def test_never_more_than_three():
    assert len(dq.questions_for(day(*TWELVE))) == dq.MAX_QUESTIONS == 3
    sized = day(*TWELVE, lots=[1] * 11 + [3])
    assert len(dq.questions_for(sized)) == 3


def test_one_trade_and_twelve_trades_get_different_questions():
    one = dq.questions_for(day("-100"))
    twelve = dq.questions_for(day(*TWELVE))
    assert len(one) == 1 and len(twelve) == 3
    assert {q.key for q in one}.isdisjoint({q.key for q in twelve})


def test_a_days_questions_have_distinct_keys():
    qs = dq.questions_for(day("50", "-10", "-90", "20", "30"))
    assert qs and len({q.key for q in qs}) == len(qs)