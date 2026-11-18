# ruff: noqa: DTZ001 - the series are naive IST by convention (TICKET-893); so are these bars
"""TICKET-889: production's price-series layer.

One series per underlying, chosen by a versioned mapping. Every lookup is answered: a bar, "no
series", "not covered" or "no bar for that minute". Stamping is checked at load, prices are
Decimal from text, and the Mirror fixture works with no network. All bars here are made up.
"""

from __future__ import annotations

import ast
import hashlib
import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from services.production.mirror import prior_minute as PM
from services.production.prices import layer as L
from services.shared.market import series as SS

T = datetime(2026, 3, 2, 9, 15)  # a Monday, NSE's open


def write_series(folder: Path, name: str, rows: list[str], *, as_of: date | None = None,
                 clock: str = SS.CLOCK, sha: str | None = None) -> Path:
    path = folder / name
    body = "timestamp,open,high,low,close,volume\n" + "".join(r + "\n" for r in rows)
    path.write_bytes(body.encode())
    stamps = [datetime.strptime(r.split(",")[0], "%Y-%m-%d %H:%M:%S") for r in rows] or [T]  # noqa: DTZ007
    SS.write_manifest(SS.SeriesManifest(
        underlying=name.split("_")[0].upper(), serves=(name.split("_")[0].upper(),), file=name,
        sha256=sha or hashlib.sha256(body.encode()).hexdigest(), rows=len(rows),
        first_bar=stamps[0], last_bar=stamps[-1], as_of=as_of or stamps[-1].date(),
        source="made up for a test", roll="", clock=clock, interval="1 minute", built=date(2026, 11, 13),
        extended_from=stamps[0].date(), sessions=()), path.with_suffix(".json"))
    return path


def nse_day(day: date, start=(9, 15), minutes=30, price=22000) -> list[str]:
    t0 = datetime.combine(day, datetime.min.time()).replace(hour=start[0], minute=start[1])
    return [f"{(t0 + timedelta(minutes=i)):%Y-%m-%d %H:%M:%S},{price + i},{price + i + 2},{price + i - 1},"
            f"{price + i + 1}.5,10" for i in range(minutes)]


@pytest.fixture()
def prices(tmp_path):
    write_series(tmp_path, "nifty_1m.csv", nse_day(date(2026, 3, 2)) + nse_day(date(2026, 3, 3)))
    return L.Prices(data_dir=tmp_path)


def test_every_instrument_in_the_profiles_has_its_underlying_except_cme():
    p = L.Prices(data_dir=Path("does-not-exist"))
    for (exchange, symbol) in p.profiles:
        if symbol == "*" or exchange == "CME":
            continue
        assert p.underlying_of(exchange, symbol), f"{exchange}:{symbol} has no underlying"
    assert p.underlying_of("CME", "ES") is None


def test_an_option_and_its_mini_share_one_series_and_a_share_is_its_own():
    p = L.Prices(data_dir=Path("does-not-exist"))
    assert p.underlying_of("MCX", "CRUDEOIL") == p.underlying_of("MCX", "CRUDEOILM") == "CRUDEOIL"
    assert p.underlying_of("MCX", "GOLD") == p.underlying_of("MCX", "GOLDM") == "GOLD"
    assert p.underlying_of("NSE", "INFY") == "INFY"
    assert p.underlying_of("NSE", "RELIANCE") == "RELIANCE"


def test_a_bar_is_decimal_read_from_the_text(prices):
    a = prices.lookup("NIFTY", T + timedelta(minutes=3))
    assert a.kind is L.Kind.BAR
    assert a.bar.close == Decimal("22004.5") and isinstance(a.bar.close, Decimal)


def test_every_lookup_has_one_of_the_four_answers(prices):
    assert prices.lookup("NIFTY", T).kind is L.Kind.BAR
    assert prices.lookup("NIFTY", T + timedelta(minutes=45)).kind is L.Kind.NO_BAR
    assert prices.lookup("NIFTY", datetime(2026, 3, 4, 10, 0)).kind is L.Kind.NOT_COVERED
    assert prices.lookup("NIFTY", datetime(2026, 2, 27, 10, 0)).kind is L.Kind.NOT_COVERED
    assert prices.lookup("BANKNIFTY", T).kind is L.Kind.NO_SERIES
    assert prices.lookup(None, T).kind is L.Kind.NO_SERIES


def test_a_series_dated_before_its_last_bar_does_not_cover_the_days_after(tmp_path):
    write_series(tmp_path, "nifty_1m.csv", nse_day(date(2026, 3, 2)) + nse_day(date(2026, 3, 3)),
                 as_of=date(2026, 3, 2))
    assert L.Prices(data_dir=tmp_path).lookup("NIFTY", datetime(2026, 3, 3, 9, 20)).kind is L.Kind.NOT_COVERED


def test_an_aware_entry_time_in_ist_finds_its_bar(prices):
    from zoneinfo import ZoneInfo
    aware = (T + timedelta(minutes=2)).replace(tzinfo=ZoneInfo("Asia/Kolkata"))
    assert prices.lookup("NIFTY", aware).kind is L.Kind.BAR


@pytest.mark.parametrize(("why", "make"), [
    ("whole minute", lambda tmp: write_series(tmp, "nifty_1m.csv", [r.replace(":00,", ":30,", 1) for r in nse_day(date(2026, 3, 2))])),
    ("end of the minute", lambda tmp: write_series(tmp, "nifty_1m.csv", nse_day(date(2026, 3, 2), start=(9, 16)))),
    ("digest", lambda tmp: write_series(tmp, "nifty_1m.csv", nse_day(date(2026, 3, 2)), sha="0" * 64)),
    ("come after", lambda tmp: write_series(tmp, "nifty_1m.csv", list(reversed(nse_day(date(2026, 3, 2)))))),
    ("start-of-minute", lambda tmp: write_series(tmp, "nifty_1m.csv", nse_day(date(2026, 3, 2)), clock="IST, end of minute")),
])
def test_a_series_whose_stamping_cant_be_established_answers_no_series(tmp_path, why, make):
    make(tmp_path)
    p = L.Prices(data_dir=tmp_path)
    a = p.lookup("NIFTY", T + timedelta(minutes=5))
    assert a.kind is L.Kind.NO_SERIES
    assert p.why("NIFTY")


def test_a_file_that_is_not_a_series_never_raises(tmp_path):
    (tmp_path / "nifty_1m.csv").write_text("not, a, series\n\x00garbage")
    (tmp_path / "nifty_1m.json").write_text("{}")
    assert L.Prices(data_dir=tmp_path).lookup("NIFTY", T).kind is L.Kind.NO_SERIES


def test_adding_an_underlying_is_an_entry_and_a_file_not_code(tmp_path):
    mapping = tmp_path / "underlyings.yaml"
    mapping.write_text('version: "7"\nunderlyings:\n  NIFTY: {profiles: ["NSE:NIFTY"], series: idx_1m.csv}\n')
    write_series(tmp_path, "idx_1m.csv", nse_day(date(2026, 3, 2)))
    p = L.Prices(data_dir=tmp_path, mapping_path=mapping)
    assert p.lookup(p.underlying_of("NSE", "NIFTY"), T).kind is L.Kind.BAR
    assert p.provenance(["NIFTY"])["underlying_map"] == "7"


def test_provenance_names_the_mapping_version_and_each_series(prices):
    got = prices.provenance(["NIFTY", "BANKNIFTY"])
    assert got["underlying_map"] == L.load_mapping().version
    assert set(got["series"]["NIFTY"]) == {"sha256", "as_of"}
    assert "none" in got["series"]["BANKNIFTY"]
    json.dumps(got)


@pytest.mark.parametrize("bad", [
    'underlyings:\n  X: {profiles: ["NSE:NIFTY"], series: x.csv}\n',
    'version: "1"\nunderlyings:\n  X: {profiles: ["NSE:NIFTY"]}\n',
    'version: "1"\nunderlyings:\n  X: {profiles: ["NSE:NIFTY"], series: x.csv}\n  Y: {profiles: ["NSE:NIFTY"], series: y.csv}\n',
    'version: "1"\nunderlyings:\n  X: {profiles: ["MCX:WIDGETOIL"], synthetic: {seed: 1, from: "2026-09-01", to: "2026-09-02", start: 5000}}\n',
])
def test_a_mapping_that_breaks_its_rules_is_refused_at_load(tmp_path, bad):
    path = tmp_path / "m.yaml"
    path.write_text(bad)
    with pytest.raises(L.InvalidMapping):
        L.load_mapping(path)


def test_the_mirror_fixture_is_counted_against_bars_with_no_network():
    trips = json.loads(Path("tests/fixtures/mirror_contract/main.json").read_text())
    p = L.Prices(data_dir=Path("does-not-exist"))
    entries = [PM.Entry(t["trip_id"], p.underlying_of(t["exchange"], t["symbol"]),
                        datetime.fromisoformat(t["entry_ts"]), 1) for t in trips]
    got = PM.count(entries, p.for_count(["WIDGETOIL"]), draws=200)
    assert got.total == len(trips)
    assert got.before.measured == len(trips), got.unmeasured


def test_nothing_in_the_layer_imports_research():
    for path in Path("services/production/prices").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module]
        names += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
        assert not [n for n in names if n.startswith("services.research")], path
