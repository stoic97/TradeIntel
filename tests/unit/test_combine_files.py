"""TICKET-926: which of a record's files a new upload is read together with. Pure."""

from __future__ import annotations

import re
from pathlib import Path

from scripts import make_groww_fixture as groww
from services.production.ctr.intake import pipeline as pl

SHARES = [o for o in groww.ORDERS if o[2]]
FNO = [o for o in groww.ORDERS if not o[2] and o[1] != "NOT A CONTRACT"]
STOCKS = pl.text_of(groww.build(SHARES))
FNO_TEXT = pl.text_of(groww.build(FNO))
BOTH = pl.text_of(groww.build())
DHAN = Path("data/fixtures/dhan_tradebook_sample.csv").read_text(encoding="utf-8")


def test_a_file_says_what_it_holds():
    assert pl.kinds_in(STOCKS) == {pl.SHARES}
    assert pl.kinds_in(FNO_TEXT) == {pl.DERIVATIVES}
    assert pl.kinds_in(BOTH) == {pl.SHARES, pl.DERIVATIVES}
    assert pl.kinds_in("Symbol,Realised P&L\nX,1\n") == frozenset()


def test_fno_is_read_with_the_stocks_file_and_the_other_way_round():
    assert pl.files_kept([STOCKS], FNO_TEXT) == [0]
    assert pl.files_kept([FNO_TEXT], STOCKS) == [0]


def test_a_newer_file_of_the_same_kind_replaces_it():
    assert pl.files_kept([STOCKS, FNO_TEXT], STOCKS) == [1]
    assert pl.files_kept([STOCKS, FNO_TEXT], BOTH) == []


def test_another_brokers_file_or_an_unreadable_one_replaces_the_record():
    assert pl.files_kept([DHAN], FNO_TEXT) == []
    assert pl.files_kept([STOCKS], "Symbol,Realised P&L\nX,1\n") == []


def without_order_ids(lines: list[str]) -> list[str]:
    """The fixture numbers order ids by position, so a subset renumbers them."""
    return sorted(re.sub(r",1000\d{12},", ",", line) for line in lines)


def test_combined_files_read_as_the_whole_file_does():
    combined = pl.combine([STOCKS, FNO_TEXT])
    assert combined.splitlines()[0] == BOTH.splitlines()[0]
    assert without_order_ids(combined.splitlines()[1:]) == without_order_ids(
        [line for line in BOTH.splitlines()[1:] if "NOT A CONTRACT" not in line])
    assert pl.combine([STOCKS]) == STOCKS
