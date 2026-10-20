"""The pre-registered research framework, read by the product.

PRD 5.6 states eligibility before anything else: which checks this history can
support, which cannot, and why. Every threshold in that statement comes from
``framework_v1.yaml`` -- the same file the research engine is bound by -- because
a product that restates the research library's minimums is a second copy of them,
and two copies drift.

The product reads the file; it does not import research code. Same boundary as the
B2 condition, which the Mirror and the library share as one function rather than
two implementations of one rule.

**The lock matters as much as the numbers.** The framework is pre-registered: its
thresholds are fixed before anyone looks at a trader's data, and the proof of that
is a sha256 committed beside it. A threshold read from a draft is a different
claim from the same threshold read from a locked file, so this module reports
which it read and never decides for itself that a draft is good enough. A hash
that is present and does not match is the case the lock exists to catch, and it
refuses.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

FRAMEWORK = (
    Path(__file__).resolve().parents[3]
    / "services" / "research" / "prereg" / "framework_v1.yaml"
)


class TamperedFramework(Exception):
    """A framework whose contents no longer match the hash committed beside it."""


class LockState(str, Enum):
    LOCKED = "locked"
    DRAFT = "draft"
    TAMPERED = "tampered"


class Unit(str, Enum):
    """What a minimum counts.

    The framework writes minimums in the units each test actually needs, which is
    not always trips: a day-level test needs days, an exit test needs winners, a
    session test needs trips within each session bucket.
    """

    TRIPS = "trips"
    DAYS = "days"
    WINNERS = "winners"
    LOSERS = "losers"
    PER_BUCKET = "per_bucket"
    PER_REGIME = "per_regime"
    PER_CELL = "per_cell"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class NMin:
    """One test's minimum, as the framework writes it.

    ``understood`` is false for a shape this reader has not been taught. That is
    deliberately not a fallback to "the first number in the string": an unfamiliar
    rule read as a familiar one puts a confident threshold on a trader's page for
    a check nobody has decided how to run.

    ``inferred`` is true where the shape's meaning was taken by analogy with
    another rather than stated anywhere. It is still used -- refusing a reading
    the convention makes plain would under-report what a history can support --
    but it is countable, and TD-030 asks the research seat to confirm it.
    """

    condition: int | None
    comparison: int | None
    unit: Unit
    raw: str
    inferred: bool = False

    @property
    def understood(self) -> bool:
        return self.unit is not Unit.UNKNOWN and self.condition is not None


_PLAIN = re.compile(r"^(\d+)$")
_PAIR = re.compile(r"^(\d+)/(\d+)$")
_SUFFIXED = re.compile(r"^(\d+)_(days|winners|losers)$")
_PAIR_SUFFIXED = re.compile(r"^(\d+)/(\d+)_(days|winners|losers)$")
_PER = re.compile(r"^(\d+)/(bucket|regime|cell)$")

_PER_UNIT = {
    "bucket": Unit.PER_BUCKET,
    "regime": Unit.PER_REGIME,
    "cell": Unit.PER_CELL,
}
_SUFFIX_UNIT = {
    "days": Unit.DAYS,
    "winners": Unit.WINNERS,
    "losers": Unit.LOSERS,
}


def parse_n_min(raw: Any) -> NMin:
    """Read one ``n_min`` value.

    The shapes in the library today::

        30          a count of trips
        30/60       condition trips / comparison trips
        40_days     a count of trading days
        40_winners  winners; 30_losers likewise
        30/bucket   that many within each session bucket; also /regime, /cell
        20/40_days  condition days / comparison days -- read by analogy with
                    30/60, which is the only reading consistent with the rest of
                    the file, and the only one in here that is not stated (TD-030)
    """
    text = str(raw).strip()

    match = _PLAIN.match(text)
    if match:
        return NMin(int(match[1]), None, Unit.TRIPS, text)

    match = _PAIR.match(text)
    if match:
        return NMin(int(match[1]), int(match[2]), Unit.TRIPS, text)

    match = _SUFFIXED.match(text)
    if match:
        return NMin(int(match[1]), None, _SUFFIX_UNIT[match[2]], text)

    match = _PAIR_SUFFIXED.match(text)
    if match:
        return NMin(int(match[1]), int(match[2]), _SUFFIX_UNIT[match[3]], text,
                    inferred=True)

    match = _PER.match(text)
    if match:
        return NMin(int(match[1]), None, _PER_UNIT[match[2]], text)

    return NMin(None, None, Unit.UNKNOWN, text)


@dataclass(frozen=True)
class LibraryTest:
    """One of the library's checks, as the product needs to talk about it."""

    id: str
    question: str
    model: str
    n_min: NMin
    needs: str | None
    requires_class: str | None
    extras: tuple[str, ...] = ()
    """Other keys the library entry carries, by name.

    ``events``, ``regime``, ``buckets``, ``window`` -- each says the test depends
    on something beyond the trades themselves. Reading them by name means a new
    dependency added to the framework is visible to the product without anyone
    remembering to update a list here.
    """

    @property
    def title(self) -> str:
        """The question as words, for a page. ``post_loss_expectancy`` reads badly."""
        return self.question.replace("_", " ")


@dataclass(frozen=True)
class Framework:
    version: str
    status: str
    lock: LockState
    digest: str
    tests: tuple[LibraryTest, ...]

    @property
    def trustworthy(self) -> bool:
        """Whether a figure read from this file may be presented as pre-registered."""
        return self.lock is LockState.LOCKED

    def test(self, test_id: str) -> LibraryTest:
        for entry in self.tests:
            if entry.id == test_id:
                return entry
        raise KeyError(test_id)


def _lock_state(path: Path, digest: str) -> LockState:
    recorded = path.with_name(path.name + ".sha256")
    if not recorded.exists():
        return LockState.DRAFT
    text = recorded.read_text().split()
    if not text:
        return LockState.TAMPERED
    return LockState.LOCKED if text[0].lower() == digest else LockState.TAMPERED


def load(path: Path | None = None) -> Framework:
    """Read the framework and report its lock state. Never raises on a bad lock.

    A tampered framework is a refusal the caller has to render, not an exception
    out of a page handler: the trader gets a page that says what is wrong, the way
    the consent gate does. ``require_trustworthy`` is there for callers that want
    the exception.
    """
    path = path or FRAMEWORK
    raw_bytes = path.read_bytes()
    digest = hashlib.sha256(raw_bytes).hexdigest()
    data = yaml.safe_load(raw_bytes.decode("utf-8"))

    tests = tuple(
        LibraryTest(
            id=str(entry["id"]),
            question=str(entry["q"]),
            model=str(entry.get("model", "")),
            n_min=parse_n_min(entry.get("n_min")),
            needs=entry.get("needs"),
            requires_class=entry.get("class"),
            extras=tuple(sorted(
                str(key) for key in entry
                # `null:` in the YAML is the null literal used as a key, so it
                # parses to None, not to the string "null" -- and sorted() will
                # not compare None against a string.
                if key is not None
                and key not in {"id", "q", "model", "n_min", "needs", "class",
                                "theta_min", "move"}
            )),
        )
        for entry in data["library"]
    )
    return Framework(
        version=str(data["framework"]["version"]),
        status=str(data["framework"]["status"]),
        lock=_lock_state(path, digest),
        digest=digest,
        tests=tests,
    )


def require_trustworthy(framework: Framework) -> Framework:
    if framework.lock is LockState.TAMPERED:
        raise TamperedFramework(
            "the pre-registered framework does not match the hash committed beside "
            "it: every threshold read from it is a number nobody agreed to. Find "
            "out what changed before anything is shown to a trader."
        )
    return framework
