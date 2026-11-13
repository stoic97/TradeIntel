"""Statutory charges, as a dated table somebody maintains (TICKET-911).

STT, CTT, exchange transaction charges, the SEBI turnover fee, stamp duty and GST are set by
Acts, circulars and notifications, and they are the same for every trader. So they are not
asked of a broker or an API. They are rows in ``rates.yaml``, each with the date it took
effect and the document that set it.

Four rules hold the table:

* **A date is covered or it refuses.** ``rate`` finds the row in force on the trade's date.
  Before ``TABLE_STARTS``, or where a segment has no row, it raises :class:`NotCovered`. It
  never falls back to today's rate.
* **Append-only.** Rows are never edited. ``rates.lock`` pins each row's content by digest,
  and a test fails if a pinned row changes. A correction is a new row. It either takes
  effect from a later date, or repeats an earlier ``effective_from`` with a later ``added``
  date. A read can pass ``as_of`` to see the table as it stood on a day, so a report made in
  March reproduces in September.
* **Every row names its source.**
* **Money is Decimal, read from strings.** A YAML float is refused at load.

Brokerage is not here: it varies by broker and plan (TICKET-912). Nothing here is applied
to a trader's figures yet.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from itertools import pairwise
from pathlib import Path

import yaml

HERE = Path(__file__).parent
TABLE = HERE / "rates.yaml"
LOCK = HERE / "rates.lock"


class Segment(StrEnum):
    NSE_EQ_DELIVERY = "NSE_EQ_DELIVERY"
    NSE_EQ_INTRADAY = "NSE_EQ_INTRADAY"
    NSE_FUT = "NSE_FUT"
    NSE_OPT = "NSE_OPT"
    BSE_FUT = "BSE_FUT"
    BSE_OPT = "BSE_OPT"
    MCX_FUT = "MCX_FUT"
    MCX_OPT = "MCX_OPT"


class Component(StrEnum):
    STT = "STT"            # securities transaction tax (NSE, BSE)
    CTT = "CTT"            # commodity transaction tax (MCX)
    EXCHANGE = "EXCHANGE"  # the exchange's transaction charge
    SEBI = "SEBI"          # SEBI turnover fee
    STAMP = "STAMP"        # stamp duty
    GST = "GST"            # on brokerage, exchange charges, the SEBI fee and IPFT
    IPFT = "IPFT"          # NSE's investor protection fund charge


SIDES = ("buy", "sell")
BASES = ("turnover", "premium", "charges")
"""What a rate is a fraction of: the order's turnover, its premium (options), or, for GST,
the charges it is levied on."""


class NotCovered(LookupError):
    """No row covers this segment, component, side and date."""


class InvalidTable(ValueError):
    """The table breaks one of its own rules."""


REQUIRED: dict = {}


def digest(row: dict) -> str:
    raise NotImplementedError


def read_lock(path=None) -> dict[int, str]:
    raise NotImplementedError


def load(path: Path = TABLE):
    raise NotImplementedError


def rate(segment, component, side, on, *, as_of=None, table=None):
    raise NotImplementedError


def statutory(segment, side, value, on, *, as_of=None, table=None):
    raise NotImplementedError
