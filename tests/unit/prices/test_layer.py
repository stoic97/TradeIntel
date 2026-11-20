# ruff: noqa: DTZ001 - the series are naive IST by convention (TICKET-893); so are these bars
"""TICKET-889, TICKET-997: production's price-series layer.

One series per underlying, chosen by a versioned mapping, stored one gzip file per day with a
manifest (TICKET-997). Every lookup is answered: a bar, "no series", "not covered" or "no bar for
that minute". Nothing is read when the layer starts; a lookup reads the underlying's manifest
once and then only the day it needs. Prices are Decimal from text, and the Mirror fixture works
with no network. All bars here are made up.
"""

from __future__ import annotations

import ast
import builtins
import gzip
import hashlib
import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from services.production.mirror import prior_minute as PM
from services.production.prices import layer as L
from services.shared.market import day_store as DS
from services.shared.market import series as SS

T = datetime(2026, 3, 2, 9, 15)  # a Monday, NSE's open
HEADER = "timestamp,open,high,low,close,volume\n"


def nse_day(day: date, start=(9, 15), minutes=30, price=22000) -> list[str]:
    t0 = datetime.combine(day, datetime.min.time()).replace(hour=start[0], minute=start[1])
    return [f"{(t0 + timedelta(minutes=i)):%Y-%m-%d %H:%M:%S},{price + i},{price + i + 2},{price + i - 1},"
            f"{price + i + 1}.5,10" for i in range(minutes)]


def write_days(root: Path, underlying: str, rows: list[str], *, as_of: date | None = None,
               clock: str = SS.CLOCK) -> Path:
    """The day layout, written through the one writer."""
    store = DS.DayStore(root / underlying, underlying)
    by_day: dict[date, list[bytes]] = {}
    for r in rows:
        by_day.setdefault(date.fromisoformat(r[:10]), []).append((r + "\n").encode())
    for day, day_rows in by_day.items():
        store.put(day, HEADER.encode(), day_rows)
    store.save(serves=(underlying,), source="made up for a test", roll="", clock=clock, interval="1 minute",
               built=date(2026, 11, 20), as_of=as_of)
    return root / underlying


def write_series(folder: Path, name: str, rows: list[str], *, as_of: date | None = None) -> Path:
    """The single-file layout TICKET-893 wrote, for the equivalence test and the split script."""
    path = folder / name
    body = HEADER + "".join(r + "\n" for r in rows)
    path.write_bytes(body.encode())
    stamps = [datetime.strptime(r.split(",")[0], "%Y-%m-%d %H:%M:%S") for r in rows]  # noqa: DTZ007
    SS.write_manifest(SS.SeriesManifest(
        underlying=name.split("_")[0].upper(), serves=(name.split("_")[0].upper(),), file=name,
        sha256=hashlib.sha256(body.encode()).hexdigest(), rows=len(rows),
        first_bar=stamps[0], last_bar=stamps[-1], as_of=as_of or stamps[-1].date(),
        source="made up for a test", roll="", clock=SS.CLOCK, interval="1 minute", built=date(2026, 11, 13),
        extended_from=stamps[0].date(), sessions=()), path.with_suffix(".json"))
    return path


@pytest.fixture()
def prices(tmp_path):
    write_days(tmp_path, "NIFTY", nse_day(date(2026, 3, 2)) + nse_day(date(2026, 3, 3)))
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
    write_days(tmp_path, "NIFTY", nse_day(date(2026, 3, 2)) + nse_day(date(2026, 3, 3)), as_of=date(2026, 3, 2))
    assert L.Prices(data_dir=tmp_path).lookup("NIFTY", datetime(2026, 3, 3, 9, 20)).kind is L.Kind.NOT_COVERED


def test_an_aware_entry_time_in_ist_finds_its_bar(prices):
    from zoneinfo import ZoneInfo
    aware = (T + timedelta(minutes=2)).replace(tzinfo=ZoneInfo("Asia/Kolkata"))
    assert prices.lookup("NIFTY", aware).kind is L.Kind.BAR


# ---------- nothing read at start, one day per lookup ----------

def test_the_layer_reads_nothing_until_asked_then_the_manifest_once_and_only_that_day(tmp_path, monkeypatch):
    write_days(tmp_path, "NIFTY", nse_day(date(2026, 3, 2)) + nse_day(date(2026, 3, 3)) + nse_day(date(2026, 3, 4)))
    opened: list[str] = []
    real = builtins.open

    def spy(file, *a, **kw):
        opened.append(Path(file).as_posix())
        return real(file, *a, **kw)

    def no_gzip_open(*a, **kw):
        raise AssertionError("day files are read through open(), never gzip.open")

    monkeypatch.setattr(builtins, "open", spy)
    monkeypatch.setattr(gzip, "open", no_gzip_open)
    p = L.Prices(data_dir=tmp_path)
    assert [o for o in opened if o.startswith(tmp_path.as_posix())] == []
    assert p.lookup("NIFTY", datetime(2026, 3, 3, 9, 20)).kind is L.Kind.BAR
    assert p.lookup("NIFTY", datetime(2026, 3, 3, 9, 25)).kind is L.Kind.BAR
    data = [o.removeprefix(tmp_path.as_posix() + "/") for o in opened if o.startswith(tmp_path.as_posix())]
    assert data == ["NIFTY/manifest.json", "NIFTY/2026/2026-03-03.csv.gz"]


def test_the_old_single_file_layout_and_the_day_layout_answer_every_lookup_the_same(tmp_path):
    rows = nse_day(date(2026, 3, 2)) + nse_day(date(2026, 3, 3), minutes=12) + nse_day(date(2026, 3, 5))
    old = L.Series.open("NIFTY", write_series(tmp_path, "nifty_1m.csv", rows, as_of=date(2026, 3, 3)),
                        session_open=datetime(2026, 1, 1, 9, 15).time())
    write_days(tmp_path / "days", "NIFTY", rows, as_of=date(2026, 3, 3))
    new = L.Prices(data_dir=tmp_path / "days").series("NIFTY")
    assert isinstance(new, L.DaySeries)
    day = date(2026, 2, 27)
    while day <= date(2026, 3, 6):
        assert old.covers(day) == new.covers(day), day
        for minute in range(9 * 60, 16 * 60):
            t = datetime.combine(day, datetime.min.time()) + timedelta(minutes=minute)
            assert old.bar(t) == new.bar(t), t
        day += timedelta(days=1)


def test_a_day_file_that_no_longer_matches_its_hash_answers_no_series_and_never_raises(tmp_path):
    folder = write_days(tmp_path, "NIFTY", nse_day(date(2026, 3, 2)) + nse_day(date(2026, 3, 3)))
    DS.day_path(folder, date(2026, 3, 3)).write_bytes(gzip.compress(b"timestamp\nnot the day\n"))
    p = L.Prices(data_dir=tmp_path)
    a = p.lookup("NIFTY", datetime(2026, 3, 3, 9, 20))
    assert a.kind is L.Kind.NO_SERIES and "2026-03-03" in a.why
    assert not p.series("NIFTY").covers(date(2026, 3, 3))
    assert p.lookup("NIFTY", T).kind is L.Kind.BAR  # the other day is untouched


@pytest.mark.parametrize(("why", "make"), [
    ("missing", lambda tmp: (tmp / "NIFTY").mkdir()),
    ("start-of-minute", lambda tmp: write_days(tmp, "NIFTY", nse_day(date(2026, 3, 2)), clock="IST, end of minute")),
    ("not a manifest", lambda tmp: ((tmp / "NIFTY").mkdir(), (tmp / "NIFTY" / "manifest.json").write_text("{}"))),
    ("not a manifest", lambda tmp: ((tmp / "NIFTY").mkdir(), (tmp / "NIFTY" / "manifest.json").write_bytes(b"\x00garbage"))),
])
def test_a_series_whose_manifest_is_missing_or_unusable_answers_no_series(tmp_path, why, make):
    make(tmp_path)
    p = L.Prices(data_dir=tmp_path)
    assert p.lookup("NIFTY", T + timedelta(minutes=5)).kind is L.Kind.NO_SERIES
    assert why in p.why("NIFTY")


def test_adding_an_underlying_is_an_entry_and_a_folder_not_code(tmp_path):
    mapping = tmp_path / "underlyings.yaml"
    mapping.write_text('version: "7"\nunderlyings:\n  NIFTY: {profiles: ["NSE:NIFTY"], folder: IDX}\n')
    write_days(tmp_path, "IDX", nse_day(date(2026, 3, 2)))
    p = L.Prices(data_dir=tmp_path, mapping_path=mapping)
    assert p.lookup(p.underlying_of("NSE", "NIFTY"), T).kind is L.Kind.BAR
    assert p.provenance(["NIFTY"])["underlying_map"] == "7"


def test_a_share_lands_in_its_own_folder_like_any_other(tmp_path):
    write_days(tmp_path, "INFY", nse_day(date(2026, 3, 2), price=1500))
    p = L.Prices(data_dir=tmp_path)
    assert L.load_mapping().stocks["folder"] == "{symbol}"
    assert p.lookup(p.underlying_of("NSE", "INFY"), T).kind is L.Kind.BAR


def test_provenance_names_the_mapping_version_and_each_series(prices, tmp_path):
    got = prices.provenance(["NIFTY", "BANKNIFTY"])
    assert got["underlying_map"] == L.load_mapping().version
    assert got["series"]["NIFTY"] == {
        "sha256": hashlib.sha256((tmp_path / "NIFTY" / "manifest.json").read_bytes()).hexdigest(),
        "as_of": "2026-03-03"}
    assert "none" in got["series"]["BANKNIFTY"]
    json.dumps(got)


@pytest.mark.parametrize("bad", [
    'underlyings:\n  X: {profiles: ["NSE:NIFTY"], folder: X}\n',
    'version: "1"\nunderlyings:\n  X: {profiles: ["NSE:NIFTY"]}\n',
    'version: "1"\nunderlyings:\n  X: {profiles: ["NSE:NIFTY"], folder: X}\n  Y: {profiles: ["NSE:NIFTY"], folder: Y}\n',
    'version: "1"\nunderlyings:\n  X: {profiles: ["MCX:WIDGETOIL"], synthetic: {seed: 1, from: "2026-09-01", to: "2026-09-02", start: 5000}}\n',
    'version: "1"\nunderlyings:\n  X: {profiles: ["NSE:NIFTY"], series: x.csv}\n',  # a single file is no longer read
])
def test_a_mapping_that_breaks_its_rules_is_refused_at_load(tmp_path, bad):
    path = tmp_path / "m.yaml"
    path.write_text(bad)
    with pytest.raises(L.InvalidMapping):
        L.load_mapping(path)


def test_every_real_underlying_is_a_folder_named_after_it():
    for name, entry in L.load_mapping().entries.items():
        assert entry.get("synthetic") or entry.get("folder") == name, name


def test_the_mirror_fixture_is_counted_against_bars_with_no_network():
    trips = json.loads(Path("tests/fixtures/mirror_contract/main.json").read_text())
    p = L.Prices(data_dir=Path("does-not-exist"))
    entries = [PM.Entry(t["trip_id"], p.underlying_of(t["exchange"], t["symbol"]),
                        datetime.fromisoformat(t["entry_ts"]), 1) for t in trips]
    got = PM.count(entries, p.for_count(["WIDGETOIL"]), draws=200)
    assert got.total == len(trips)
    assert got.before.measured == len(trips), got.unmeasured


def test_the_891_count_reads_day_files_unchanged(tmp_path):
    write_days(tmp_path, "NIFTY", nse_day(date(2026, 3, 2)) + nse_day(date(2026, 3, 3)))
    p = L.Prices(data_dir=tmp_path)
    entries = [PM.Entry(f"t{i}", "NIFTY", T + timedelta(minutes=5 + i), 1) for i in range(3)]
    got = PM.count(entries, p.for_count(["NIFTY"]), draws=50)
    assert got.total == 3 and got.before.measured == 3, got.unmeasured


def test_nothing_in_the_layer_imports_research():
    for path in Path("services/production/prices").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module]
        names += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
        assert not [n for n in names if n.startswith("services.research")], path
