"""TICKET-892: the clock alignment of "the minute before his entry", held by tests.

Research spec section 4.7: 1-minute bars, each labelled by the minute it starts, and the
minute before entry only. A one-minute shift makes the figure go up and the page read better,
so it is the one error that survives review. T-001 checked this by hand; these tests check it
on every run.

Every expected answer below is written by hand from the bars in this file, never computed by
the code under test. Every bar is made up: nothing here is anyone's market data or trades,
and nothing reaches a network.
"""

from __future__ import annotations

import re
import socket
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from services.production.mirror import prior_minute as pm

IST = ZoneInfo("Asia/Kolkata")
PROFILES = Path(__file__).resolve().parents[3] / "services" / "production" / "ctr" / "profiles"
OUT_OF_SCOPE = {"CME_ES"}  # TICKET-889: another vendor, no series planned
IN_SCOPE = sorted(p.stem for p in PROFILES.glob("*.yaml") if p.stem not in OUT_OF_SCOPE)

UP = pm.Bar(open=100.0, close=101.0)
DOWN = pm.Bar(open=101.0, close=100.0)
FLAT = pm.Bar(open=100.0, close=100.0)
PREV_DAY, DAY = date(2026, 6, 1), date(2026, 6, 2)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("TICKET-892: these tests must not reach a network")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def ist(day: date, hhmm: str, second: int = 0, micro: int = 0) -> datetime:
    hour, minute = (int(x) for x in hhmm.split(":"))
    return datetime(day.year, day.month, day.day, hour, minute, second, micro, tzinfo=IST)


def table(bars: dict[datetime, pm.Bar]) -> pm.BarTable:
    days = sorted({k.date() for k in bars})
    return pm.BarTable(bars=bars, first_day=days[0], last_day=days[-1])


def before(entry_ts: datetime, bars: pm.BarTable, direction: int = 1):
    """(agreed, measured, reasons left out) of the before-count for one trip."""
    entry = pm.Entry("t1", "UNDER", entry_ts, direction)
    result = pm.count([entry], {"UNDER": bars}, draws=10)
    return result.before.agreed, result.before.measured, [u.reason for u in (*result.unmeasured, *result.unmeasured_before)]


def profile(name: str) -> dict[str, str]:
    text = (PROFILES / f"{name}.yaml").read_text(encoding="utf-8")
    found = {}
    for key in ("timezone", "session_start", "session_end"):
        match = re.search(rf'^\s*{key}\s*:\s*"?([^"\s#]+)"?', text, re.MULTILINE)
        assert match, f"{name}.yaml has no {key}"
        found[key] = match.group(1)
    return found


def session_bars(name: str, days: list[date]) -> pm.BarTable:
    """Every minute of the profile's session in its own zone, labelled by its start: the first
    bar is session_start, the last starts one minute before session_end. All rising."""
    p = profile(name)
    zone = ZoneInfo(p["timezone"])
    start = time.fromisoformat(p["session_start"])
    end = time.fromisoformat(p["session_end"])
    bars = {}
    n = 0  # each bar closes one above the last, so every minute reads "up" close to close
    for day in days:
        t, stop = datetime.combine(day, start, zone), datetime.combine(day, end, zone)
        while t < stop:
            bars[t] = pm.Bar(open=100.0 + n, close=101.0 + n)
            n += 1
            t += timedelta(minutes=1)
    return table(bars)


# ---- Gate 2: the minute before is off by neither one minute nor one bar ----------------------
# 10:12 fell, 10:13 rose, 10:14 FELL, 10:15 rose, 10:16 rose. The minute before an entry is read
# close to close (D2): for a long entered during 10:15 that is the close of 10:13 against the
# close of 10:14, which fell: 0 agree. One minute late reads 10:15, the minute he bought into;
# one bar early reads 10:13. Both rose, so either mistake reads 1. Only the right minute reads 0.
NEIGHBOURS = table({
    ist(DAY, "10:12"): DOWN,
    ist(DAY, "10:13"): UP,
    ist(DAY, "10:14"): DOWN,
    ist(DAY, "10:15"): UP,
    ist(DAY, "10:16"): UP,
})


@pytest.mark.parametrize(
    ("entry_ts", "long_agrees", "why"),
    [
        (ist(DAY, "10:15", 30), 0, "10:15:30 -> 10:14, which fell"),
        (ist(DAY, "10:15", 0, 0), 0, "10:15:00.000 exactly is in 10:15 -> 10:14"),
        (ist(DAY, "10:15", 59, 999_999), 0, "10:15:59.999999 is still 10:15 -> 10:14"),
        (datetime(2026, 6, 2, 4, 45, 30, tzinfo=UTC), 0, "04:45:30 UTC = 10:15:30 IST"),
        (ist(DAY, "10:16", 10), 1, "10:16:10 -> 10:15, which rose"),
        (ist(DAY, "10:14", 45), 1, "10:14:45 -> 10:13, which rose"),
    ],
)
def test_the_minute_before_is_the_one_that_closed_before_the_entry_minute(
    entry_ts, long_agrees, why
):
    assert before(entry_ts, NEIGHBOURS, direction=1) == (long_agrees, 1, []), why
    assert before(entry_ts, NEIGHBOURS, direction=-1) == (1 - long_agrees, 1, []), why


def test_a_timestamp_with_no_zone_is_refused_not_read_in_the_machines_own_zone():
    # Read as machine-local, 10:15:30 is right on a laptop in India and five and a half hours
    # out on a server in UTC: one history, two figures. It must not be read at all.
    naive = datetime(2026, 6, 2, 10, 15, 30)  # noqa: DTZ001 (naive on purpose)
    with pytest.raises(ValueError, match="zone"):
        before(naive, NEIGHBOURS)


# ---- Gate 1 (the part this module can hold): a mis-stamped bar gives no figure -------------
def test_bars_stamped_with_seconds_give_no_figure_rather_than_a_shifted_one():
    late = table({k.replace(second=59): v for k, v in NEIGHBOURS.bars.items()})
    assert before(ist(DAY, "10:15", 30), late) == (0, 0, [pm.Reason.NO_PRIOR_BAR])


# ---- Gate 3: the session's open and close, in the instrument's own zone ---------------------
def test_the_count_reads_in_ist():
    assert pm.IST.key == "Asia/Kolkata"


@pytest.mark.parametrize("name", IN_SCOPE)
def test_every_in_scope_profile_is_in_the_zone_the_count_reads(name):
    zone = profile(name)["timezone"]
    assert zone == "Asia/Kolkata", (
        f"{name}: the count reads every bar in IST, so a profile in {zone} would be shifted "
        "by its offset without a word"
    )


def test_the_first_minute_of_the_nse_session_cannot_be_measured_and_is_not_yesterdays_close():
    bars = session_bars("NSE_NIFTY", [PREV_DAY, DAY])
    assert ist(PREV_DAY, "15:29") in bars.bars  # yesterday's last bar is there to be misused
    # 09:15:20: the minute before is 09:14, before the open.
    assert before(ist(DAY, "09:15", 20), bars) == (0, 0, [pm.Reason.NO_PRIOR_BAR])
    # 09:16:05: the minute before is 09:15, the first bar. Close to close needs the bar before
    # it too (D2): 09:14 is not there, and yesterday's 15:29 is never borrowed.
    assert before(ist(DAY, "09:16", 5), bars) == (0, 0, [pm.Reason.NO_BAR_TWO_BEFORE])
    # 09:17:05: 09:16 against 09:15, both there, rising.
    assert before(ist(DAY, "09:17", 5), bars) == (1, 1, [])


def test_the_last_bar_of_the_nse_session_starts_one_minute_before_session_end():
    bars = session_bars("NSE_NIFTY", [DAY])
    assert ist(DAY, "15:29") in bars.bars and ist(DAY, "15:30") not in bars.bars
    assert before(ist(DAY, "15:29", 40), bars) == (1, 1, [])  # 15:28 before, 15:29 entered
    # No 15:30 bar exists: the bar before (15:29) is there, so the before count reads it (D5);
    # the entry-minute bar is not, so every after count leaves the trip out.
    assert before(ist(DAY, "15:30", 10), bars) == (1, 1, [])


def test_crude_open_and_close_in_its_own_session():
    bars = session_bars("MCX_CRUDEOIL", [PREV_DAY, DAY])
    assert ist(PREV_DAY, "23:29") in bars.bars  # last night's last bar is there to be misused
    assert before(ist(DAY, "09:00", 10), bars) == (0, 0, [pm.Reason.NO_PRIOR_BAR])  # 08:59: not open
    # 09:00 is the first bar and nothing is before it: close to close cannot be read yet.
    assert before(ist(DAY, "09:01", 0), bars) == (0, 0, [pm.Reason.NO_BAR_TWO_BEFORE])
    assert before(ist(DAY, "09:02", 0), bars) == (1, 1, [])  # 09:01 against 09:00
    assert before(ist(DAY, "23:29", 30), bars) == (1, 1, [])  # 23:28 before, 23:29 entered
    late_utc = datetime(2026, 6, 2, 17, 59, 30, tzinfo=UTC)  # 23:29:30 IST
    assert before(late_utc, bars) == (1, 1, [])
    assert before(ist(DAY, "23:30", 5), bars) == (1, 1, [])  # no 23:30 bar: 23:29 is there


# ---- Gate 4: a minute with no data cannot be measured -------------------------------------
def test_a_missing_minute_cannot_be_measured_and_is_never_the_bar_before_it():
    gap = table({ist(DAY, "10:13"): UP, ist(DAY, "10:15"): UP, ist(DAY, "10:16"): UP})
    assert before(ist(DAY, "10:15", 30), gap) == (0, 0, [pm.Reason.NO_PRIOR_BAR])


def test_a_flat_minute_is_data_and_agrees_with_neither_side():
    # close(10:13) 100 then close(10:14) 100: flat close to close.
    flat = table({ist(DAY, "10:13"): pm.Bar(open=99.0, close=100.0),
                  ist(DAY, "10:14"): FLAT, ist(DAY, "10:15"): UP})
    assert before(ist(DAY, "10:15", 30), flat, direction=1) == (0, 1, [])
    assert before(ist(DAY, "10:15", 30), flat, direction=-1) == (0, 1, [])

# ---- Gate 5: the real demo file, no network --------------------------------------------------
DEMO = Path(__file__).resolve().parents[3] / "data" / "fixtures" / "demo" / "scope_demo_tradebook.csv"


def _demo_entry_times() -> list[datetime]:
    from services.production.ctr.intake import pipeline as pl

    plan = pl.plan_import(
        DEMO.read_text(encoding="utf-8"),
        context=pl.ImportContext(trader_id="demo", source_account="DEMO", code_version="test",
                                 export_date="2026-09-01", export_date_source="trader"),
        production=True,
    )
    return [p.entry_ts for p in plan.positions]


def _epoch_minute(ts: datetime) -> int:
    """Start of the minute the timestamp is in, as whole seconds since the epoch. Plain integer
    arithmetic on UTC seconds: it shares no code with the module's own clock handling."""
    seconds = int(ts.timestamp())
    return seconds - seconds % 60


def _at(seconds: int) -> datetime:
    return datetime.fromtimestamp(seconds, IST)


def test_every_demo_entry_lines_up_on_the_minute_before_and_on_no_other():
    times = _demo_entry_times()
    assert len(times) >= 100  # the demo file's positions, not a handful
    for ts in times:
        assert ts.utcoffset() is not None, f"demo entry_ts has no zone: {ts!r}"
        m0 = _epoch_minute(ts)
        right = table({_at(m0 - 120): UP, _at(m0 - 60): DOWN, _at(m0): UP})
        assert before(ts, right) == (0, 1, []), ts  # long; close to close the minute before fell
        late = table({_at(m0): UP, _at(m0 + 60): UP})  # one minute late: starts at the entry
        assert before(ts, late) == (0, 0, [pm.Reason.NO_PRIOR_BAR]), ts
        early = table({_at(m0 - 120): UP, _at(m0): UP})  # one bar early
        assert before(ts, early) == (0, 0, [pm.Reason.NO_PRIOR_BAR]), ts

# ---- Gate 1, the part that needs no loader: a stamping check that names the series -----------
def stamping_fault(
    series: str, minutes: list[datetime], session_start: str, session_end: str
) -> str | None:
    """Why these bars are not stamped at the start of the minute (research spec 4.7.2), or None.

    A start-stamped session runs from session_start to one minute before session_end. An
    end-stamped one runs from one minute after the open to the close itself, and a series
    shifted by a minute or by seconds does neither. TICKET-889's loader owes the same check
    at load: when it lands, point this at each series it ships.
    """
    if not minutes:
        return f"{series}: no bars, so its stamping cannot be established"
    for m in minutes:
        if m.second or m.microsecond:
            return f"{series}: bar stamped {m.isoformat()} is not on a minute boundary"
    opens, closes = time.fromisoformat(session_start), time.fromisoformat(session_end)
    last_start = (datetime.combine(DAY, closes, IST) - timedelta(minutes=1)).time()
    first, last = min(m.time() for m in minutes), max(m.time() for m in minutes)
    if (first, last) != (opens, last_start):
        return (
            f"{series}: bars run {first:%H:%M}-{last:%H:%M}, but a series stamped at the start "
            f"of the minute runs {opens:%H:%M}-{last_start:%H:%M} (session {session_start}-"
            f"{session_end}); it is unusable until its stamping is shown"
        )
    return None


@pytest.mark.parametrize("name", ["NSE_NIFTY", "MCX_CRUDEOIL"])
def test_a_series_stamped_at_the_start_of_the_minute_has_no_fault(name):
    p = profile(name)
    minutes = list(session_bars(name, [PREV_DAY, DAY]).bars)
    assert stamping_fault(name, minutes, p["session_start"], p["session_end"]) is None


@pytest.mark.parametrize("name", ["NSE_NIFTY", "MCX_CRUDEOIL"])
@pytest.mark.parametrize(
    "move",
    [timedelta(minutes=1), timedelta(minutes=-1), timedelta(seconds=59)],
    ids=["end-of-interval", "one-minute-early", "59-seconds-in"],
)
def test_a_series_not_stamped_at_the_start_of_the_minute_is_refused_by_name(name, move):
    p = profile(name)
    minutes = [m + move for m in session_bars(name, [DAY]).bars]
    fault = stamping_fault(name, minutes, p["session_start"], p["session_end"])
    assert fault is not None and name in fault


def test_bars_with_no_zone_never_match_a_trade_so_the_book_is_unmeasured_not_shifted():
    naive = table({k.replace(tzinfo=None): v for k, v in NEIGHBOURS.bars.items()})
    assert before(ist(DAY, "10:15", 30), naive) == (0, 0, [pm.Reason.NO_PRIOR_BAR])

# ---- Gate 3 again: the day a trade is covered on is its IST day, not its UTC day -------------
def test_the_day_a_trade_is_covered_on_is_its_ist_day():
    # 00:30 IST on DAY is 19:00 UTC the day before. These bars cover DAY only.
    night = table({ist(DAY, "00:28"): DOWN, ist(DAY, "00:29"): UP, ist(DAY, "00:30"): UP})
    assert before(ist(DAY, "00:30", 20), night) == (1, 1, [])
    # A series that stops the day before does not cover DAY, whatever the UTC date says.
    stale = table({ist(PREV_DAY, "23:28"): UP, ist(PREV_DAY, "23:29"): UP})
    assert before(ist(DAY, "00:00", 20), stale) == (0, 0, [pm.Reason.NOT_COVERED])


def _assert_counted_before_and_left_out_of_every_after(result, trip_id):
    """D5: the bar before the entry minute is there, the entry-minute bar is not."""
    assert (result.before.agreed, result.before.measured) == (1, 1)
    assert result.unmeasured == () and result.unmeasured_before == ()
    for h in pm.HORIZONS:
        assert (result.after[h].agreed, result.after[h].measured) == (0, 0)
        left_out = [(u.trip_id, u.reason) for u in result.unmeasured_after[h]]
        assert left_out == [(trip_id, pm.Reason.NO_ENTRY_BAR)]


def test_an_entry_in_a_minute_with_no_bar_is_counted_before_and_left_out_of_every_after_count():
    # D5. The code does not know why the entry-minute bar is missing (a gap, a late broker stamp,
    # or a minute after the session), so the reason says only that the bar is missing.
    bars = session_bars("NSE_NIFTY", [DAY])
    entry = pm.Entry("t1", "UNDER", ist(DAY, "15:30", 10), 1)
    result = pm.count([entry], {"UNDER": bars}, draws=10)
    _assert_counted_before_and_left_out_of_every_after(result, "t1")


def test_the_same_holds_on_a_winter_crude_date_where_the_missing_bar_is_a_data_gap():
    # 1 Dec 2026: the US is on standard time, MCX non-agri runs to 23:55, so 23:30:05 is inside
    # the session and the missing 23:30 bar is a gap in the data. The answer is the same as above.
    winter = date(2026, 12, 1)
    bars = table({ist(winter, "23:28"): pm.Bar(open=99.0, close=100.0), ist(winter, "23:29"): UP})
    entry = pm.Entry("t2", "UNDER", ist(winter, "23:30", 5), 1)
    result = pm.count([entry], {"UNDER": bars}, draws=10)
    _assert_counted_before_and_left_out_of_every_after(result, "t2")


def test_a_missing_bar_two_before_cannot_be_measured_and_is_never_the_bar_before_that():
    gap = table({ist(DAY, "10:12"): UP, ist(DAY, "10:14"): UP, ist(DAY, "10:15"): UP})
    assert before(ist(DAY, "10:15", 30), gap) == (0, 0, [pm.Reason.NO_BAR_TWO_BEFORE])


def test_both_bars_must_be_on_the_entry_day_so_nothing_is_borrowed_from_the_night_before():
    rising = table({
        ist(PREV_DAY, "23:58"): pm.Bar(open=99.0, close=100.0),
        ist(PREV_DAY, "23:59"): pm.Bar(open=100.0, close=101.0),
        ist(DAY, "00:00"): pm.Bar(open=101.0, close=102.0),
        ist(DAY, "00:01"): pm.Bar(open=102.0, close=103.0),
    })
    # 00:00:30: the minute before is 23:59 of the day before, not the entry's day.
    assert before(ist(DAY, "00:00", 30), rising) == (0, 0, [pm.Reason.NO_PRIOR_BAR])
    # 00:01:30: 00:00 is there, but the bar before it is 23:59 of the day before.
    assert before(ist(DAY, "00:01", 30), rising) == (0, 0, [pm.Reason.NO_BAR_TWO_BEFORE])
    # 00:02:30: 00:01 against 00:00, both on the day.
    assert before(ist(DAY, "00:02", 30), rising) == (1, 1, [])
