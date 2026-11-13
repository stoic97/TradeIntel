"""The finding bar's correction: a family fixed in advance, and step-down min-p on one shuffle.

Every statistic here is drawn from a seeded generator: no one's trades.
"""

from __future__ import annotations

import numpy as np
import pytest

from services.shared.conditions import multiplicity as M
from services.shared.prereg import reader


def test_the_family_is_the_core_list_fixed_in_the_framework():
    checks = M.family()
    assert len(checks) == 18
    assert "B2" in checks and M.EDGE_MAP not in checks
    assert set(checks) == {t.id for t in reader.load().tests} - {M.EDGE_MAP}


def test_a_check_that_cannot_run_stays_in_the_family_at_one():
    rng = np.random.default_rng(1)
    adjusted = M.step_down_min_p({"B2": -5.0}, {"B2": rng.normal(size=2000)}, ("B2", "B1", "S1"))
    assert adjusted["B1"] == adjusted["S1"] == 1.0
    assert set(adjusted) == {"B2", "B1", "S1"}


def test_p_is_never_zero():
    null = np.zeros(1000)
    assert M.raw_p(-1.0, null) == 1 / 1001
    assert M.step_down_min_p({"A": -1.0}, {"A": null}, ("A",))["A"] > 0


def test_one_check_alone_keeps_about_its_own_p():
    rng = np.random.default_rng(2)
    null = rng.normal(size=5000)
    for observed in (-2.5, -1.7, 0.0):
        raw = M.raw_p(observed, null)
        adjusted = M.step_down_min_p({"A": observed}, {"A": null}, ("A",))["A"]
        assert abs(adjusted - raw) <= 2 / 5000


def correlated(rng, m: int, n: int, rho: float) -> np.ndarray:
    cov = np.full((m, m), rho) + np.eye(m) * (1 - rho)
    return rng.multivariate_normal(np.zeros(m), cov, size=n).T  # checks x draws


def test_adjusted_p_is_monotone_never_below_raw_and_never_weaker_than_holm():
    rng = np.random.default_rng(3)
    checks = ("A", "B", "C", "D", "E")
    draws = correlated(rng, 5, 4000, 0.5)
    observed = dict(zip(checks, (-2.9, -2.2, -1.1, 0.3, -2.0), strict=True))
    null = dict(zip(checks, draws, strict=True))
    adjusted = M.step_down_min_p(observed, null, checks)
    raw = {c: M.raw_p(observed[c], null[c]) for c in checks}
    holm = M.holm(raw, checks)
    by_raw = sorted(checks, key=lambda c: raw[c])
    assert [adjusted[c] for c in by_raw] == sorted(adjusted[c] for c in by_raw)
    for c in checks:
        assert adjusted[c] >= raw[c] - 1e-12
        assert adjusted[c] <= holm[c] + 2 / 4000


def test_the_familywise_error_is_five_percent_on_books_with_nothing_planted():
    """Five correlated checks, nothing real in any of them: about 5 in 100 books get at least
    one finding at adjusted p <= 0.05, inside the ruled band. Bonferroni gets fewer: that is
    the power it throws away."""
    rng = np.random.default_rng(909)
    checks = tuple("ABCDE")
    books, draws = 1000, 999
    any_wy = any_bonf = 0
    for _ in range(books):
        sample = correlated(rng, 5, draws + 1, 0.6)
        observed = dict(zip(checks, sample[:, 0], strict=True))
        null = dict(zip(checks, sample[:, 1:], strict=True))
        adjusted = M.step_down_min_p(observed, null, checks)
        any_wy += min(adjusted.values()) <= 0.05
        any_bonf += min(M.bonferroni(M.raw_p(observed[c], null[c]), checks) for c in checks) <= 0.05
    assert 0.035 <= any_wy / books <= 0.065
    assert any_bonf < any_wy


def test_draws_must_line_up_across_checks():
    with pytest.raises(ValueError):
        M.step_down_min_p({"A": 0.0, "B": 0.0}, {"A": np.zeros(10), "B": np.zeros(11)}, ("A", "B"))


def test_holm_on_the_whole_family():
    adjusted = M.holm({"A": 0.01, "B": 0.04, "C": None}, ("A", "B", "C"))
    assert adjusted == {"A": 0.03, "B": 0.08, "C": 1.0}
