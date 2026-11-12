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
    return result.before.agreed, result.before.measured, [u.reason for u in result.unmeasured]


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
    for day in days:
        t, stop = datetime.combine(day, start, zone), datetime.combine(day, end, zone)
        while t < stop:
            bars[t] = UP
            t += timedelta(minutes=1)
    return table(bars)


# ---- Gate 2: the minute before is off by neither one minute nor one bar ----------------------
# 10:13 rose, 10:14 FELL, 10:15 rose, 10:16 rose. For a long entered during 10:15 the minute
# that closed just before the entry minute is 10:14, which fell: 0 agree. One minute late reads
# 10:15, the minute he bought into; one bar early reads 10:13. Both rose, so either mistake
# reads 1. Only the right minute reads 0.
NEIGHBOURS = table({
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
    assert before(ist(DAY, "10:15", 30), late) == (0, 0, [pm.Reason.NO_BAR])


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
    assert before(ist(DAY, "09:15", 20), bars) == (0, 0, [pm.Reason.NO_BAR])
    # 09:16:05: the minute before is 09:15, the session's first bar.
    assert before(ist(DAY, "09:16", 5), bars) == (1, 1, [])


def test_the_last_bar_of_the_nse_session_starts_one_minute_before_session_end():
    bars = session_bars("NSE_NIFTY", [DAY])
    assert ist(DAY, "15:29") in bars.bars and ist(DAY, "15:30") not in bars.bars
    assert before(ist(DAY, "15:29", 40), bars) == (1, 1, [])  # 15:28 before, 15:29 entered
    assert before(ist(DAY, "15:30", 10), bars) == (0, 0, [pm.Reason.NO_BAR])  # past the close


def test_crude_open_and_close_in_its_own_session():
    bars = session_bars("MCX_CRUDEOIL", [PREV_DAY, DAY])
    assert ist(PREV_DAY, "23:29") in bars.bars  # last night's last bar is there to be misused
    assert before(ist(DAY, "09:00", 10), bars) == (0, 0, [pm.Reason.NO_BAR])  # 08:59: not open
    assert before(ist(DAY, "09:01", 0), bars) == (1, 1, [])  # 09:00, the first bar
    assert before(ist(DAY, "23:29", 30), bars) == (1, 1, [])  # 23:28 before, 23:29 entered
    late_utc = datetime(2026, 6, 2, 17, 59, 30, tzinfo=UTC)  # 23:29:30 IST
    assert before(late_utc, bars) == (1, 1, [])
    assert before(ist(DAY, "23:30", 5), bars) == (0, 0, [pm.Reason.NO_BAR])  # past the close


# ---- Gate 4: a minute with no data cannot be measured -------------------------------------
def test_a_missing_minute_cannot_be_measured_and_is_never_the_bar_before_it():
    gap = table({ist(DAY, "10:13"): UP, ist(DAY, "10:15"): UP, ist(DAY, "10:16"): UP})
    assert before(ist(DAY, "10:15", 30), gap) == (0, 0, [pm.Reason.NO_BAR])


def test_a_flat_minute_is_data_and_agrees_with_neither_side():
    flat = table({ist(DAY, "10:14"): FLAT, ist(DAY, "10:15"): UP})
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
    assert len(times) > 300  # the demo file's positions, not a handful
    for ts in times:
        assert ts.utcoffset() is not None, f"demo entry_ts has no zone: {ts!r}"
        m0 = _epoch_minute(ts)
        right = table({_at(m0 - 60): DOWN, _at(m0): UP})
        assert before(ts, right) == (0, 1, []), ts  # long; the minute before fell
        late = table({_at(m0): UP, _at(m0 + 60): UP})  # one minute late: starts at the entry
        assert before(ts, late) == (0, 0, [pm.Reason.NO_BAR]), ts
        early = table({_at(m0 - 120): UP, _at(m0): UP})  # one bar early
        assert before(ts, early) == (0, 0, [pm.Reason.NO_BAR]), ts

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
    assert before(ist(DAY, "10:15", 30), naive) == (0, 0, [pm.Reason.NO_BAR])
