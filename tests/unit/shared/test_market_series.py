"""TICKET-893: the crude series says how current it is, and no session goes missing silently.

All bars here are made up. The real series is gitignored (``data/market/``, logged in
``CROSSINGS.md``); these tests never need it and never touch the network.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from services.shared.market import series as ms

MON, TUE, WED, THU, FRI, SAT, SUN = (date(2026, 3, 2) + timedelta(days=i) for i in range(7))


def full(day: date) -> list[datetime]:
    start = datetime.combine(day, datetime.min.time()).replace(hour=9)
    return [start + timedelta(minutes=i) for i in range(14 * 60 + 30)]


def evening(day: date) -> list[datetime]:
    return [m for m in full(day) if m.hour >= 17]


def morning(day: date) -> list[datetime]:
    return [m for m in full(day) if m.hour < 17]


def cal(*entries: tuple[date, str, str]) -> dict[date, ms.SessionException]:
    return {d: ms.SessionException(d, kind, reason) for d, kind, reason in entries}


def test_a_full_week_with_nothing_missing_passes_with_nothing_listed():
    bars = [m for d in (MON, TUE, WED, THU, FRI) for m in full(d)]
    c = ms.check_sessions(bars, MON, SUN, cal())
    assert c.ok and c.listed == () and c.unexplained == ()


def test_a_weekday_with_no_bars_and_no_reason_fails_the_check():
    bars = [m for d in (MON, TUE, THU, FRI) for m in full(d)]
    c = ms.check_sessions(bars, MON, FRI, cal())
    assert not c.ok
    assert c.unexplained == ((WED, "no bars"),)


def test_a_closed_day_on_the_calendar_is_listed_with_its_reason():
    bars = [m for d in (MON, TUE, THU, FRI) for m in full(d)]
    c = ms.check_sessions(bars, MON, FRI, cal((WED, "closed", "exchange holiday")))
    assert c.ok
    assert c.listed == ((WED, "no bars", "exchange holiday"),)


def test_an_evening_only_session_needs_its_own_reason():
    bars = full(MON) + evening(TUE)
    assert ms.check_sessions(bars, MON, TUE, cal()).unexplained == ((TUE, "evening only"),)
    c = ms.check_sessions(bars, MON, TUE, cal((TUE, "evening_only", "morning closed for a holiday")))
    assert c.ok and c.listed == ((TUE, "evening only", "morning closed for a holiday"),)


def test_a_reason_of_the_wrong_kind_does_not_explain_a_gap():
    bars = full(MON) + evening(TUE)
    c = ms.check_sessions(bars, MON, TUE, cal((TUE, "closed", "said closed")))
    assert c.unexplained == ((TUE, "evening only"),)


def test_a_morning_only_session_is_told_apart_from_an_evening_only_one():
    c = ms.check_sessions(full(MON) + morning(TUE), MON, TUE, cal())
    assert c.unexplained == ((TUE, "morning only"),)


def test_a_holiday_that_traded_a_full_session_is_flagged_not_trusted():
    c = ms.check_sessions(full(MON), MON, MON, cal((MON, "closed", "thought closed")))
    assert c.unexplained == ((MON, "full session, but the calendar says closed"),)


def test_weekends_without_bars_are_not_sessions_but_a_weekend_session_needs_a_reason():
    bars = full(FRI) + evening(SUN)
    assert ms.check_sessions(full(FRI), FRI, SUN, cal()).ok
    assert ms.check_sessions(bars, FRI, SUN, cal()).unexplained == ((SUN, "evening only"),)
    c = ms.check_sessions(bars, FRI, SUN, cal((SUN, "special", "a one-hour special session")))
    assert c.ok and c.listed == ((SUN, "evening only", "a one-hour special session"),)


def test_bars_outside_the_checked_range_are_ignored():
    c = ms.check_sessions(full(MON) + full(WED), TUE, TUE, cal((TUE, "closed", "holiday")))
    assert c.ok and c.listed == ((TUE, "no bars", "holiday"),)


def test_the_shipped_calendar_loads_and_every_entry_has_a_kind_and_a_reason():
    c = ms.load_calendar()
    assert len(c) >= 10
    for d, e in c.items():
        assert e.day == d
        assert e.kind in ms.KINDS
        assert e.reason.strip()


def _manifest(**over) -> ms.SeriesManifest:
    base = {"underlying": "CRUDEOIL", "serves": ("CRUDEOIL", "CRUDEOILM"), "file": "crude_1m_current.csv",
            "sha256": "ab" * 32, "rows": 10,
            "first_bar": datetime(2026, 1, 5, 9, 0),  # noqa: DTZ001 - naive IST, as the series
            "last_bar": datetime(2026, 3, 6, 23, 54),  # noqa: DTZ001
            "as_of": date(2026, 3, 6), "source": "made up", "roll": ms.ROLL_CONVENTION, "clock": ms.CLOCK,
            "interval": "1 minute", "built": date(2026, 3, 9), "extended_from": date(2026, 2, 1),
            "sessions": ("2026-03-03 evening only: a reason",)}
    base.update(over)
    return ms.SeriesManifest(**base)


def test_the_manifest_says_how_current_the_series_is():
    m = _manifest()
    assert m.covers(date(2026, 3, 6))
    assert m.covers(date(2026, 1, 5))
    assert not m.covers(date(2026, 3, 7)), "a day after as_of is not covered, so a claim can refuse"
    assert not m.covers(date(2026, 1, 4))
    assert m.days_behind(date(2026, 3, 16)) == 10


def test_the_manifest_round_trips_through_its_file(tmp_path):
    m = _manifest()
    p = tmp_path / "m.json"
    ms.write_manifest(m, p)
    assert ms.read_manifest(p) == m


def test_the_mini_is_served_by_the_crude_series():
    assert ms.read_manifest  # the manifest records which roots a series answers for
    assert "CRUDEOILM" in _manifest().serves
    assert ms.CRUDE_SERVES == ("CRUDEOIL", "CRUDEOILM")


def test_the_roll_convention_names_the_contract_and_the_roll_day():
    r = ms.ROLL_CONVENTION.lower()
    assert "nearest unexpired" in r and "last trading day" in r and "not back-adjusted" in r


@pytest.mark.parametrize("kind", ["closed", "evening_only", "morning_only", "special"])
def test_every_kind_is_known(kind):
    assert kind in ms.KINDS
