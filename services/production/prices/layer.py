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
    """A series failed a check at load. It answers "no series", with this as the reason."""


class InvalidMapping(ValueError):
    """underlyings.yaml breaks its own rules. Raised at load, where it is visible."""


def _price(text: str, where: str) -> Decimal:
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise Unusable(f"{where}: {text!r} is not a price") from exc
    if not value.is_finite():
        raise Unusable(f"{where}: {text!r} is not a price")
    return value


def _stamp(text: str, where: str) -> datetime:
    """``YYYY-MM-DD H:MM:SS``. Older rows write single-digit hours, so no fixed width."""
    try:
        day, clock = text.split(" ")
        h, m, s = clock.split(":")
        return datetime(int(day[:4]), int(day[5:7]), int(day[8:10]), int(h), int(m), int(s))  # noqa: DTZ001
    except ValueError as exc:
        raise Unusable(f"{where}: {text!r} is not a timestamp") from exc


@dataclass
class Series:
    """One underlying's bars, from a file on disk, checked at load. Implements the bars
    interface TICKET-891's count reads (``covers``, ``bar``)."""

    underlying: str
    path: Path
    manifest: shared_series.SeriesManifest
    _days: dict[date, tuple[int, int]] = field(default_factory=dict)
    _cache: OrderedDict = field(default_factory=OrderedDict)

    @classmethod
    def open(cls, underlying: str, path: Path, session_open: time) -> Series:
        manifest_path = path.with_suffix(".json")
        if not path.exists() or not manifest_path.exists():
            raise Unusable(f"{path.name} or its manifest is missing")
        manifest = shared_series.read_manifest(manifest_path)
        if manifest.clock != shared_series.CLOCK:
            raise Unusable(f"{path.name}: the manifest doesn't say the bars are start-of-minute")
        s = cls(underlying=underlying, path=path, manifest=manifest)
        digest = s._index(session_open)
        if digest != manifest.sha256:
            raise Unusable(f"{path.name} doesn't match its manifest's digest")
        return s

    def _index(self, session_open: time) -> str:
        """Stream the file once: check every stamp, note where each day starts, hash it. Only
        the index is kept, so memory doesn't grow with the file."""
        sha = hashlib.sha256()
        first_bars: dict[date, time] = {}
        last: tuple = ()
        day: date | None = None
        start = offset = 0
        with self.path.open("rb") as f:
            header = f.readline()
            sha.update(header)
            offset = len(header)
            for raw in f:
                sha.update(raw)
                stamp = raw[:raw.find(b",")].decode()
                d, _, clock = stamp.partition(" ")
                h, m, sec = clock.split(":")
                if sec != "00":
                    raise Unusable(f"{self.path.name}: {stamp} is not on a whole minute")
                key = (d, int(h), int(m))
                if last and key <= last:
                    raise Unusable(f"{self.path.name}: {stamp} doesn't come after the row before it")
                if not last or d != last[0]:
                    this = date.fromisoformat(d)
                    if day is not None:
                        self._days[day] = (start, offset)
                    day, start = this, offset
                    first_bars[day] = time(int(h), int(m))
                last = key
                offset += len(raw)
        if day is not None:
            self._days[day] = (start, offset)
        recent = [first_bars[k] for k in sorted(first_bars)[-RECENT_DAYS:]]
        if not recent:
            raise Unusable(f"{self.path.name} has no bars")
        usual = Counter(recent).most_common(1)[0][0]
        if usual != session_open:
            raise Unusable(f"{self.path.name}: the session's first bar is usually at {usual:%H:%M}, "
                           f"not the open, {session_open:%H:%M}, so its stamping can't be established")
        return sha.hexdigest()

    def covers(self, day: date) -> bool:
        return self.manifest.covers(day)

    def _day(self, day: date) -> dict[datetime, Bar]:
        if day in self._cache:
            self._cache.move_to_end(day)
            return self._cache[day]
        bars: dict[datetime, Bar] = {}
        if day in self._days:
            a, b = self._days[day]
            with self.path.open("rb") as f:
                f.seek(a)
                chunk = f.read(b - a).decode("utf-8")
            for line in chunk.splitlines():
                if not line.strip():
                    continue
                stamp, o, h, low, c, *_ = line.split(",")
                where = f"{self.path.name}, {stamp}"
                bars[_stamp(stamp, where)] = Bar(_price(o, where), _price(h, where), _price(low, where),
                                                 _price(c, where))
        self._cache[day] = bars
        if len(self._cache) > DAY_CACHE:
            self._cache.popitem(last=False)
        return bars

    def bar(self, minute: datetime) -> Bar | None:
        naive = minute.replace(tzinfo=None) if minute.tzinfo else minute
        return self._day(naive.date()).get(naive)


@dataclass
class SyntheticSeries:
    """A seeded random walk over one session a day, for test fixtures only."""

    underlying: str
    first: date
    last: date
    seed: int
    start: Decimal
    session: tuple[time, time]
    _bars: dict[datetime, Bar] = field(default_factory=dict)

    def __post_init__(self) -> None:
        rng = random.Random(self.seed)
        price = self.start
        day = self.first
        while day <= self.last:
            if day.weekday() < 5:
                t = datetime.combine(day, self.session[0])
                end = datetime.combine(day, self.session[1])
                while t < end:
                    move = Decimal(rng.randint(-3, 3))
                    close = price + move
                    self._bars[t] = Bar(price, max(price, close) + 1, min(price, close) - 1, close)
                    price, t = close, t + timedelta(minutes=1)
            day += timedelta(days=1)
        digest = hashlib.sha256(repr(sorted(self._bars.items())).encode()).hexdigest()
        self.manifest_digest = digest

    def covers(self, day: date) -> bool:
        return self.first <= day <= self.last

    def bar(self, minute: datetime) -> Bar | None:
        naive = minute.replace(tzinfo=None) if minute.tzinfo else minute
        return self._bars.get(naive)


@dataclass(frozen=True)
class Mapping:
    version: str
    by_profile: dict[str, str]
    entries: dict[str, dict]
    stocks: dict | None


def load_mapping(path: Path = MAPPING) -> Mapping:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    version = doc.get("version")
    if not isinstance(version, str) or not version:
        raise InvalidMapping("the mapping needs a version, as a string")
    by_profile: dict[str, str] = {}
    entries = doc.get("underlyings") or {}
    for name, entry in entries.items():
        if bool(entry.get("series")) == bool(entry.get("synthetic")):
            raise InvalidMapping(f"{name}: give a series file or a synthetic series, one of them")
        for profile in entry.get("profiles") or []:
            if profile in by_profile:
                raise InvalidMapping(f"{profile} is mapped twice ({by_profile[profile]} and {name})")
            by_profile[profile] = name
        if entry.get("synthetic"):
            start = entry["synthetic"].get("start")
            if not isinstance(start, str):
                raise InvalidMapping(f"{name}: a synthetic start price is written as a string")
    return Mapping(version=version, by_profile=by_profile, entries=entries, stocks=doc.get("stocks"))


class Prices:
    """The layer's front door: which underlying, which series, and the answer for one minute."""

    def __init__(self, data_dir: Path | None = None, mapping_path: Path = MAPPING,
                 profiles_dir: Path = PROFILES) -> None:
        self.data_dir = data_dir if data_dir is not None else market_dir()
        self.mapping = load_mapping(mapping_path)
        self.profiles = registry.load_all(profiles_dir)
        self._series: dict[str, Series | SyntheticSeries | Unusable] = {}

    def underlying_of(self, exchange: str, symbol: str) -> str | None:
        """The underlying that measures this instrument, or None when nothing is mapped."""
        named = self.mapping.by_profile.get(f"{exchange}:{symbol}")
        if named:
            return named
        stocks = self.mapping.stocks or {}
        if f"{exchange}:*" in (stocks.get("profiles") or []) and (exchange, symbol) not in self.profiles:
            return symbol
        return None

    def _session(self, underlying: str) -> tuple[time, time]:
        entry = self.mapping.entries.get(underlying)
        keys = entry["profiles"] if entry else (self.mapping.stocks or {}).get("profiles", [])
        exchange, symbol = keys[0].split(":")
        profile = self.profiles[(exchange, symbol)]
        return profile.session_start, profile.session_end

    def series(self, underlying: str) -> Series | SyntheticSeries | None:
        """The checked series, or None (and the reason in ``why``) when there is none to use."""
        if underlying not in self._series:
            self._series[underlying] = self._open(underlying)
        got = self._series[underlying]
        return None if isinstance(got, Unusable) else got

    def why(self, underlying: str) -> str:
        got = self._series.get(underlying)
        return str(got) if isinstance(got, Unusable) else ""

    def _open(self, underlying: str) -> Series | SyntheticSeries | Unusable:
        entry = self.mapping.entries.get(underlying)
        try:
            session = self._session(underlying)
            if entry and entry.get("synthetic"):
                syn = entry["synthetic"]
                return SyntheticSeries(underlying, date.fromisoformat(syn["from"]), date.fromisoformat(syn["to"]),
                                       int(syn["seed"]), Decimal(syn["start"]), session)
            name = entry["series"] if entry else self.mapping.stocks["series"].format(symbol=underlying.lower())
            return Series.open(underlying, self.data_dir / name, session[0])
        except Unusable as exc:
            return exc
        except (OSError, ValueError, KeyError) as exc:
            return Unusable(f"{underlying}: {exc}")

    def lookup(self, underlying: str | None, minute: datetime) -> Answer:
        """One of: the bar, no series, not covered, or no bar for that minute."""
        if not underlying:
            return Answer(Kind.NO_SERIES, why="no underlying is mapped for this instrument")
        s = self.series(underlying)
        if s is None:
            return Answer(Kind.NO_SERIES, why=self.why(underlying) or f"no series for {underlying}")
        day = (minute.replace(tzinfo=None) if minute.tzinfo else minute).date()
        if not s.covers(day):
            return Answer(Kind.NOT_COVERED, why=f"{underlying}'s series doesn't cover {day.isoformat()}")
        bar = s.bar(minute)
        return Answer(Kind.BAR, bar=bar) if bar else Answer(Kind.NO_BAR, why=f"no {underlying} bar at {minute:%H:%M}")

    def for_count(self, underlyings: list[str]) -> dict[str, Series | SyntheticSeries]:
        """The usable series by underlying, in the shape TICKET-891's count takes. An underlying
        missing here is counted there as "no series for the underlying"."""
        return {u: s for u in underlyings if (s := self.series(u)) is not None}

    def provenance(self, underlyings: list[str]) -> dict:
        """What produced a bar-derived figure: the mapping's version and each series' digest and
        date. Whatever stores the figure stores this beside it."""
        out: dict = {"underlying_map": self.mapping.version, "series": {}}
        for u in sorted(set(underlyings)):
            s = self.series(u)
            if isinstance(s, Series):
                out["series"][u] = {"sha256": s.manifest.sha256, "as_of": s.manifest.as_of.isoformat()}
            elif isinstance(s, SyntheticSeries):
                out["series"][u] = {"synthetic": s.manifest_digest}
            else:
                out["series"][u] = {"none": self.why(u) or "no series"}
        return out
