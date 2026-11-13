"""TICKET-911: the statutory rate table refuses what it can't cover, never edits a row, and picks
the row in force on the trade's date.

The rules are tested on small made-up tables in a temp dir. The shipped table is tested for
its own coverage, its lock and the real change dates in test_rates_shipped.py.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from services.production.charges import rates as R

HEAD = 'starts: "2020-07-01"\nrows:\n'


def row(id_, seg="NSE_OPT", comp="STT", side="sell", base="premium", rate='"0.0005"',
        frm="2020-07-01", added="2026-11-13", source="Finance Act, made up for the test"):
    return (f"  - {{id: {id_}, segment: {seg}, component: {comp}, side: {side}, base: {base}, "
            f"rate: {rate}, effective_from: \"{frm}\", added: \"{added}\", source: \"{source}\"}}\n")


def table(tmp_path, *rows):
    p = tmp_path / "rates.yaml"
    p.write_text(HEAD + "".join(rows), encoding="utf-8")
    return R.load(p)


def test_a_rate_is_a_decimal_read_from_a_string(tmp_path):
    t = table(tmp_path, row(1))
    assert t[1][0].rate == Decimal("0.0005") and isinstance(t[1][0].rate, Decimal)


def test_a_yaml_float_is_refused_at_load(tmp_path):
    with pytest.raises(R.InvalidTable, match="string"):
        table(tmp_path, row(1, rate="0.0005"))


@pytest.mark.parametrize("bad", [
    {"seg": "NSE_CASH"}, {"comp": "BROKERAGE"}, {"side": "both"}, {"base": "notional"},
    {"source": ""}, {"rate": '"-0.1"'}, {"rate": '"abc"'},
])
def test_a_row_outside_the_vocabulary_or_without_a_source_is_refused(tmp_path, bad):
    with pytest.raises(R.InvalidTable):
        table(tmp_path, row(1, **bad))


def test_ids_only_ever_grow_down_the_file(tmp_path):
    with pytest.raises(R.InvalidTable, match="id"):
        table(tmp_path, row(2), row(1, frm="2024-10-01"))


def test_the_row_in_force_on_the_day_is_chosen_either_side_of_a_change(tmp_path):
    t = table(tmp_path, row(1), row(2, rate='"0.001"', frm="2024-10-01"))
    pick = lambda d: R.rate(R.Segment.NSE_OPT, R.Component.STT, "sell", d, table=t).rate
    assert pick(date(2024, 9, 30)) == Decimal("0.0005")
    assert pick(date(2024, 10, 1)) == Decimal("0.001")
    assert pick(date(2026, 11, 13)) == Decimal("0.001")


def test_before_the_table_starts_it_refuses_rather_than_using_todays_rate(tmp_path):
    t = table(tmp_path, row(1))
    with pytest.raises(R.NotCovered):
        R.rate(R.Segment.NSE_OPT, R.Component.STT, "sell", date(2020, 6, 30), table=t)


def test_a_segment_with_no_row_refuses(tmp_path):
    t = table(tmp_path, row(1))
    with pytest.raises(R.NotCovered):
        R.rate(R.Segment.MCX_OPT, R.Component.CTT, "sell", date(2025, 1, 1), table=t)


def test_a_correction_is_a_new_row_and_an_old_read_still_reproduces(tmp_path):
    # Row 1 was wrong from the start; row 3 corrects it for the same dates, added later.
    t = table(tmp_path, row(1, rate='"0.0004"', added="2026-01-10"),
              row(2, rate='"0.001"', frm="2024-10-01", added="2026-01-10"),
              row(3, rate='"0.0005"', added="2026-03-01"))
    pick = lambda d, as_of=None: R.rate(R.Segment.NSE_OPT, R.Component.STT, "sell", d,
                                        as_of=as_of, table=t).rate
    assert pick(date(2023, 5, 2)) == Decimal("0.0005")
    assert pick(date(2023, 5, 2), as_of=date(2026, 2, 1)) == Decimal("0.0004"), "March's report reproduces"
    assert pick(date(2025, 5, 2)) == Decimal("0.001"), "a correction to old dates leaves later rows alone"


def test_a_row_added_after_as_of_is_not_seen(tmp_path):
    t = table(tmp_path, row(1, added="2026-11-13"))
    with pytest.raises(R.NotCovered):
        R.rate(R.Segment.NSE_OPT, R.Component.STT, "sell", date(2025, 1, 1), as_of=date(2026, 1, 1), table=t)


def test_the_digest_pins_a_row_and_changes_when_any_field_does():
    a = {"id": 1, "rate": "0.0005", "source": "x"}
    assert R.digest(a) == R.digest(dict(reversed(list(a.items()))))
    assert R.digest(a) != R.digest({**a, "rate": "0.0006"})
