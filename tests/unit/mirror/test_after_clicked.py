"""TICKET-1001: After you clicked - the 30 minutes after each entry, beside random moments.

The page reads what the bar-figure job stored (999) and never a bar. His paths follow the report
filter; the random band is the one stored for the whole record. One underlying at a time, under
30 measured trades no chart, and a counted line with no claim about chance. Every figure here is
made up and worked by hand.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from services.production.api import after_clicked as AC
from services.production.api import scope_geometry as G
from services.production.api import scope_map as S
from services.production.db import models as m
from services.production.db.session import make_session

H = AC.HORIZON


def flat(n: int) -> tuple[Decimal, ...]:
    """A made-up path: 0 at the click, then n points his way every minute after."""
    return (Decimal(0),) + (Decimal(n),) * H


def bars(groups: dict[str, list[tuple]], band=None, reasons=None) -> tuple[list, dict]:
    """Trips and the stored figures for them: groups of paths by underlying, plus reasons."""
    trips, stored = [], {}
    for u, paths in groups.items():
        for i, p in enumerate(paths):
            tid = f"{u}-{i}"
            trips.append(SimpleNamespace(trip_id=tid))
            stored[tid] = {"underlying": u, "reason": None, "path": p, "short": False}
    for i, reason in enumerate(reasons or []):
        tid = f"x-{i}"
        trips.append(SimpleNamespace(trip_id=tid))
        stored[tid] = {"underlying": "CRUDEOIL", "reason": reason, "path": (), "short": False}
    band = band or {"median": (Decimal(0),) * (H + 1), "lo": (Decimal(-9),) * (H + 1),
                    "hi": (Decimal(9),) * (H + 1), "count": 31}
    return trips, {"trades": stored, "random": {u: band for u in groups}, "job": "done", "waiting_days": 0}


THIRTY_ONE = [flat(i) for i in range(1, 32)]


# ---------- the numbers, from stored paths ----------

def test_his_median_and_middle_half_are_worked_out_from_the_stored_paths():
    trips, b = bars({"NIFTY": THIRTY_ONE})
    v = AC.view({"trips": trips, "bars": b})
    assert v["enough"] and v["measured_here"] == 31
    assert v["his_median"][30] == Decimal(16)          # the middle of 1..31
    assert v["his_q25"][30] == Decimal("8.5")          # between the 8th and 9th
    assert v["his_q75"][30] == Decimal("23.5")
    assert v["his_median"][0] == 0
    assert (v["his_end"], v["random_end"]) == (16, 0)


def test_the_report_filter_narrows_his_paths_while_the_random_band_stays():
    trips, b = bars({"NIFTY": THIRTY_ONE})
    whole = AC.view({"trips": trips, "bars": b})
    kept = [t for t in trips if t.trip_id != "NIFTY-30"]  # the filter drops the 31st trade
    narrowed = AC.view({"trips": kept, "bars": b})
    assert narrowed["his_median"][30] == Decimal("15.5") and narrowed["his_end"] == 16
    assert narrowed["random_lo"] == whole["random_lo"] and narrowed["random_hi"] == whole["random_hi"]


def test_one_underlying_at_a_time_the_one_with_most_trades_first():
    trips, b = bars({"NIFTY": THIRTY_ONE, "CRUDEOIL": [flat(1)] * 5})
    v = AC.view({"trips": trips, "bars": b})
    assert v["underlying"] == "NIFTY"
    assert [(c["underlying"], c["trades"], c["on"]) for c in v["chips"]] == [("NIFTY", 31, True), ("CRUDEOIL", 5, False)]
    assert v["chips"][1]["href"] == "/mirror/fact/after?u=CRUDEOIL#after"
    crude = AC.view({"trips": trips, "bars": b}, "CRUDEOIL")
    assert crude["underlying"] == "CRUDEOIL" and crude["measured_here"] == 5
    assert not crude["enough"] and AC.geometry(crude) is None


def test_a_single_underlying_has_no_chips():
    trips, b = bars({"NIFTY": THIRTY_ONE})
    assert AC.view({"trips": trips, "bars": b})["chips"] == []


def test_under_30_measured_trades_is_not_drawn():
    trips, b = bars({"NIFTY": [flat(1)] * 29})
    v = AC.view({"trips": trips, "bars": b})
    assert not v["enough"] and v["minimum"] == 30 and AC.geometry(v) is None


def test_every_trade_not_measured_is_counted_with_its_reason():
    trips, b = bars({"NIFTY": THIRTY_ONE}, reasons=["contract month differs from the near-month series"] * 2
                    + ["no market data for this underlying"])
    trips.append(SimpleNamespace(trip_id="never-worked-out"))
    v = AC.view({"trips": trips, "bars": b})
    assert v["measured"] == 31 and v["not_measured"] == 4
    assert v["reasons"] == [("contract month differs from the near-month series", 2),
                            (AC.NOT_WORKED_OUT, 1), ("no market data for this underlying", 1)]


# ---------- the chart ----------

def test_the_chart_holds_at_most_200_faint_paths_and_stays_under_60_kb():
    paths = [tuple(Decimal((i * k) % 41 - 20) for k in range(H + 1)) for i in range(400)]
    trips, b = bars({"NIFTY": paths})
    v = AC.view({"trips": trips, "bars": b})
    assert len(v["faint"]) == AC.FAINT
    g = AC.geometry(v)
    svg = "".join(f'<path class="chart__{p["role"]}" d="{p["d"]}"/>' for p in g["parts"]) + str(g["labels"])
    assert len(svg.encode()) < 60_000, len(svg.encode())
    roles = [p["role"] for p in g["parts"]]
    assert roles.index("ac-band") < roles.index("ac-faint") < roles.index("ac-his")  # the band behind


def test_the_minutes_are_labelled_0_to_30_and_zero_is_marked():
    trips, b = bars({"NIFTY": THIRTY_ONE})
    g = AC.geometry(AC.view({"trips": trips, "bars": b}))
    labels = re.findall(r">([^<]+)</text>", str(g["labels"]))
    assert labels[:7] == ["0", "5", "10", "15", "20", "25", "30"]
    assert any(p["role"] == "ac-zero" for p in g["parts"])


def test_the_table_reads_minutes_1_5_10_15_20_and_30():
    trips, b = bars({"NIFTY": THIRTY_ONE})
    html = str(AC.table(AC.view({"trips": trips, "bars": b})))
    assert [r for r in re.findall(r"<td>(\d+ min)</td>", html)] == ["1 min", "5 min", "10 min", "15 min", "20 min", "30 min"]


def test_it_is_not_one_of_the_kits_charts():
    assert "after" not in G.CHARTS  # those are held to the kit's JavaScript byte for byte


def test_chapter_two_lists_it_after_the_clock():
    assert [f.key for f in S.chapter(2).facts] == ["math", "run", "clock", "after"]


# ---------- the page, on stored rows ----------

def _store(engine, measured: int, reasons: list[str]):
    trips = json.loads(Path("tests/fixtures/mirror_contract/main.json").read_text(encoding="utf-8"))
    with make_session(engine) as sess:
        imp = sess.scalars(select(m.Import)).first()
        for i, t in enumerate(trips):
            if i < measured:
                path = json.dumps([str(v) for v in flat(1 + i % 9)])
                sess.add(m.BarTradeFigure(import_id=imp.id, trip_id=t["trip_id"], underlying="WIDGETOIL",
                                          reason=None, way="3", against="1", took="2", path=path, short=False))
            elif i - measured < len(reasons):
                sess.add(m.BarTradeFigure(import_id=imp.id, trip_id=t["trip_id"], underlying="WIDGETOIL",
                                          reason=reasons[i - measured], short=False))
        zeros = json.dumps(["0"] * (H + 1))
        sess.add(m.BarPathSummary(import_id=imp.id, underlying="WIDGETOIL", measured=measured, randoms=measured,
                                  his_median=zeros, his_q25=zeros, his_q75=zeros, random_median=zeros,
                                  random_lo=json.dumps(["-4"] * (H + 1)), random_hi=json.dumps(["4"] * (H + 1)),
                                  faint="[]"))
        sess.commit()


@pytest.fixture()
def no_bars(monkeypatch):
    from services.production.market import bar_figures
    from services.production.prices import layer

    def refuse(*a, **kw):
        raise AssertionError("a page read bars or worked out a bar figure")

    monkeypatch.setattr(layer.Prices, "__init__", refuse)
    monkeypatch.setattr(bar_figures, "measure", refuse)


def test_the_page_draws_the_stored_figures_and_reads_no_bar(client, engine, no_bars):
    _store(engine, 34, ["contract month differs from the near-month series"] * 6)
    page = client.get("/mirror/fact/after")
    assert page.status_code == 200
    text = page.text
    assert 'class="chart ac-chart"' in text
    assert "30 minutes after you clicked, the market had moved a median" in re.sub(r"<[^>]+>", "", text)
    assert "drawn from your whole record&#39;s months" in text or "drawn from your whole record's months" in text
    assert "contract month differs from the near-month series" in text
    words = re.sub(r"<[^>]+>", " ", text).lower()
    for claim in ("skill", "edge", "luck", "beat"):
        assert not re.search(rf"\b{claim}", words), claim
    section = text[text.index('id="after"'):]
    section = section[: section.index("</section>")]
    assert "<script" not in section  # the layout's own scripts aside, the fact adds none


def test_under_30_the_page_says_how_many_and_what_it_needs(client, engine, no_bars):
    _store(engine, 10, [])
    text = client.get("/mirror/fact/after").text
    plain = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", text))
    assert "10 trades measured in WIDGETOIL; this needs 30." in plain
    assert "ac-chart" not in text
    assert "Not enough trades yet" in text


def test_see_these_trades_opens_the_measured_trades(client, engine, no_bars):
    _store(engine, 34, [])
    assert client.get("/mirror/fact/after/trades").status_code == 200
    assert "/mirror/fact/after/trades" in client.get("/mirror/fact/after").text


def test_its_chapter_card_shows_on_chapter_two(client, engine, no_bars):
    _store(engine, 34, [])
    page = client.get("/mirror/chapter/2")
    assert page.status_code == 200 and "After you clicked" in page.text
