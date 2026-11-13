"""Production's price-series layer: one 1-minute series per underlying (TICKET-889).

A trade in an option is measured against its underlying, so the layer holds one series per
underlying, never per contract (spec 4.7.3). Which underlying measures which instrument is data
(``underlyings.yaml``), versioned, and recorded on use: ``Prices.provenance`` gives the mapping's
version and each series' digest and date, for whatever stores a bar-derived figure.

**Every question has an answer, never an exception.** ``Prices.lookup`` returns a bar, or one of
"no series for this underlying", "series does not cover this date" or "no bar for that minute"
(the reasons TICKET-891's count already reports). A series that is missing, unreadable, or fails
its checks at load answers "no series". The fact then shows its "not available" state; nothing
here raises into a request, and no trade is silently skipped.

**Checked at load, not assumed (spec 4.7.2).**

* The manifest says the series is stamped at the start of each minute.
* The file's digest matches the manifest.
* Every timestamp falls on a whole minute and the timestamps strictly rise.
* On the series' recent days, its first bar most often falls at the session's open. A series
  stamped at the end of each minute would open a minute late, and its "minute before" would be
  the entry minute, which agrees with the trade by construction.

**Where the bars live, and what that costs.** Files on disk: one CSV and its manifest per
underlying, written by the monthly refresh (TICKET-893's format). They are not kept in the
product database. Opening a series streams the file once, to check it and to note where each day
starts. After that a lookup reads only the day it needs, and recent days stay cached. A trader
with five years of history touches only the days he traded. Nothing is fetched from a feed while
a request is being served: a series holds every date it covers, for every trader.

Prices are ``Decimal``, read from the file's text. Nothing here imports from research.
"""

from __future__ import annotations

import hashlib
import os
import random
from collections import Counter, OrderedDict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path

import yaml

from services.production.ctr.profiles import registry
from services.shared.market import series as shared_series

HERE = Path(__file__).parent
MAPPING = HERE / "underlyings.yaml"
PROFILES = HERE.parent / "ctr" / "profiles"
RECENT_DAYS = 120
"""The stamping check reads the latest days: session hours have moved over the years (MCX
opened at 10:00 in 2018 and at 09:00 now), and the check is about the series as it stands."""
DAY_CACHE = 64


def market_dir() -> Path:
    return Path(os.environ.get("SCOPE_MARKET_DIR", "data/market"))


class Kind(StrEnum):
    BAR = "bar"
    NO_SERIES = "no series for this underlying"
    NOT_COVERED = "series does not cover this date"
    NO_BAR = "no bar for that minute"


@dataclass(frozen=True)
class Bar:
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal


@dataclass(frozen=True)
class Answer:
    kind: Kind
    bar: Bar | None = None
    why: str = ""


class Unusable(Exception):
    """A series failed a check at load."""


class InvalidMapping(ValueError):
    """underlyings.yaml breaks its own rules."""


def load_mapping(path: Path = MAPPING):
    raise NotImplementedError


class Prices:
    def __init__(self, data_dir=None, mapping_path=MAPPING, profiles_dir=PROFILES) -> None:
        raise NotImplementedError
