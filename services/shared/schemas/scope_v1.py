"""Scope v1 product vocabulary.

The enums every product module keys off, in one file, because the PRD's rules are
about exhaustiveness: three import outcomes and never a fourth (section 5.3); all
seven result states present from the first commit with v1 emitting four (section 8);
no archetype anywhere (section 3, anti-scope).

Each is a ``str`` enum whose value is its lowercase name, so a database row is
readable without a lookup and stays stable if the class is reordered. Nothing here
computes; these are names. The product tables in ``services/production/db`` store
these values, and ``tests/unit/shared/test_scope_v1_enums.py`` fixes their counts.
"""

from __future__ import annotations

from enum import Enum


class _Vocabulary(str, Enum):
    """A string enum whose value is its own lowercase name.

    Every member states its value explicitly rather than using ``auto()``, so the
    stored string is visible at the point of definition; the rule is enforced by
    ``test_every_enum_is_a_str_enum_whose_value_is_its_lowercase_name``.
    """

    def __str__(self) -> str:
        return str(self.value)


class ResultState(_Vocabulary):
    """PRD section 8. All seven exist from day one; v1 emits the first four.

    ``INSUFFICIENT_SAMPLE`` and ``NOT_YET_TESTED`` must never render as a clean bill
    of health: the absence of a finding is never evidence of good trading.
    """

    COUNTED_FACT = "counted_fact"
    INSUFFICIENT_SAMPLE = "insufficient_sample"
    REQUIRED_DATA_MISSING = "required_data_missing"
    NOT_YET_TESTED = "not_yet_tested"
    VALIDATED_FINDING = "validated_finding"
    NO_EFFECT_ABOVE_THRESHOLD = "no_effect_above_threshold"
    COULD_NOT_COMPUTE = "could_not_compute"


V1_EMITTABLE_STATES = frozenset(
    {
        ResultState.COUNTED_FACT,
        ResultState.INSUFFICIENT_SAMPLE,
        ResultState.REQUIRED_DATA_MISSING,
        ResultState.NOT_YET_TESTED,
    }
)
"""The four v1 may emit. The other three belong to v2 and are never written in v1."""


class ImportOutcome(_Vocabulary):
    """PRD section 5.3. Three states, never a fourth.

    A clean file is ``ACCEPTED_WITH_EXCLUSIONS`` with an exclusion count of zero
    (definitions_v1.md section 4), and exclusions take precedence over partial
    fields when both apply.
    """

    REJECTED = "rejected"
    ACCEPTED_WITH_EXCLUSIONS = "accepted_with_exclusions"
    ACCEPTED_PARTIAL_FIELDS = "accepted_partial_fields"


class RowFlag(_Vocabulary):
    """PRD section 5.4. A row is never discarded on a hash alone.

    ``DUPLICATE_FILL_ID`` excludes and retains; ``SUSPECTED_DUPLICATE`` keeps the row
    and shows it; ``TRADER_CONFIRMED_DUPLICATE`` excludes it after the trader says so.
    """

    DUPLICATE_FILL_ID = "duplicate_fill_id"
    SUSPECTED_DUPLICATE = "suspected_duplicate"
    TRADER_CONFIRMED_DUPLICATE = "trader_confirmed_duplicate"


class DayDiff(_Vocabulary):
    """PRD section 5.4. How a trading day changed when a later upload superseded it.

    A day that shrank is flagged and shown; uploads version days, never append.
    """

    IDENTICAL = "identical"
    GROWN = "grown"
    SHRUNK = "shrunk"


class CapturePhase(_Vocabulary):
    """PRD section 7.4. Derived by the system from ``entered_at``, never chosen.

    In v1 every Journal field resolves to ``AFTER_CLOSE`` by construction, because the
    Journal exists only after an upload. The other two exist so that when v3 captures a
    stop before the trade, hindsight and commitment are never confused.
    """

    BEFORE_ENTRY = "before_entry"
    DURING_TRADE = "during_trade"
    AFTER_CLOSE = "after_close"


class RiskUnitSourceV1(_Vocabulary):
    """PRD section 5.5. What a trip's result was divided by.

    Distinct from ``ctr_v1.RiskUnitSource``, which records what reconstruction knew.
    This one is filled once the trader's declaration is known. ``INFERRED_ATR`` is
    reserved for the research protocol; nothing in v1 writes it.
    """

    DECLARED_BUDGET = "declared_budget"
    DEFINED_STOP = "defined_stop"
    PREMIUM_PAID = "premium_paid"
    INFERRED_ATR = "inferred_atr"
    UNAVAILABLE = "unavailable"


SHOWABLE_DENOMINATORS = frozenset(
    {RiskUnitSourceV1.DECLARED_BUDGET, RiskUnitSourceV1.DEFINED_STOP}
)
"""The only two that may be a denominator on a v1 screen, labelled in words.

"x your declared budget" and "x your stop". The unqualified symbol R never appears
(PRD section 5.5 and the anti-scope table).
"""


class JournalUnit(_Vocabulary):
    """PRD section 7.2. Trading day by default; the trader's setting overrides."""

    DAY = "day"
    WEEK = "week"
    PER_N_TRIPS = "per_n_trips"


class ConsentPurpose(_Vocabulary):
    """Thesis section 19.3's six separable purposes, plus engine testing.

    Engine testing is the claims register's C24: a tradebook is used for the trader's
    diagnosis and for checking the engine, and the thesis list had no purpose covering
    the second. Each purpose is opt-in independently; only ``DIAGNOSIS`` is required for
    the product to run, and refusing any other never degrades the diagnosis. v1 asks
    ``DIAGNOSIS`` and ``ENGINE_TESTING``, because those are the two that become real at
    the first upload.
    """

    DIAGNOSIS = "diagnosis"
    ENGINE_TESTING = "engine_testing"
    RETAIN_MODEL = "retain_model"
    POPULATION_PRIORS = "population_priors"
    PUBLISHED_RESEARCH = "published_research"
    THIRD_PARTY_SUMMARY = "third_party_summary"
    MARKETING = "marketing"
