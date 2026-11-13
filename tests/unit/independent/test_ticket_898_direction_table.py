"""My direction table equals the merged one, row for row [TICKET-898].

scripts/independent_count_898.py never imports project code, so it carries its own copy of
the spec s4.7.7 table. This test is the only place the two meet: if services/shared/
option_direction.py ever changes a row, or this script does, the test fails.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from services.shared.option_direction import TABLE, Underlying
from services.shared.schemas.ctr_v1 import Direction

_PATH = Path(__file__).resolve().parents[3] / "scripts" / "independent_count_898.py"
_NAME = "independent_count_898_table_check"


@pytest.fixture(scope="module")
def mine():
    spec = importlib.util.spec_from_file_location(_NAME, _PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[_NAME] = module
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop(_NAME, None)


def _kind(option_type) -> str:
    return "FUT" if option_type is None else {"CE": "CALL", "PE": "PUT"}[option_type.name]


def _side(direction) -> str:
    return "BUY" if direction is Direction.LONG else "SELL"


def test_every_row_of_the_merged_table_is_my_answer(mine):
    expected = {Underlying.LONG: mine.LONG, Underlying.SHORT: mine.SHORT}
    assert len(TABLE) == 6
    for (option_type, direction), underlying in TABLE.items():
        got = mine.direction(_kind(option_type), _side(direction))
        assert got == expected[underlying], (option_type, direction)


def test_a_share_takes_its_own_side_like_a_future(mine):
    for side in ("BUY", "SELL"):
        assert mine.direction("STOCK", side) == mine.direction("FUT", side)


def test_a_multi_leg_trip_has_no_single_direction(mine):
    assert mine.direction("MULTI", "BUY") == mine.NONE
    assert mine.direction("MULTI", "SELL") == mine.NONE
