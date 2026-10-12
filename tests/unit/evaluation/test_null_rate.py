"""Step E: how often does B2 announce a leak in a trader who has none?

The Class B gate (R-Spec §6.2) puts the false-positive rate in [2%, 8%].
These tests cover the accounting, not the fits: fire vectors are built by
hand so the arithmetic and the interval are checked in milliseconds, before
any sweep spends an hour of sampling.

Three things the machinery must not get wrong, each a way to flatter
ourselves:

* A starved history (fewer than n_min condition trades) cannot fire, so
  counting it in the denominator deflates the rate. Starved histories are
  excluded and reported.
* The nulls share one crude series, so their outcomes are correlated and a
  binomial interval claims precision we do not have. The authority is the
  wider of binomial and a block bootstrap over calendar clusters (TD-017).
* A rate with no named clustering unit is not a rate (SR-007).
"""

from __future__ import annotations

import json

import pytest

from services.research.evaluation import null_rate as nr


def outcomes(fires_by_cluster: dict[int, int], per_cluster: int, starved: int = 0):
    """One outcome per history: `per_cluster` histories in each cluster."""
    out = []
    for cluster in sorted(fires_by_cluster):
        n_fire = fires_by_cluster[cluster]
        for i in range(per_cluster):
            out.append(
                nr.NullOutcome(
                    history_id=f"null-{cluster}-{i}",
                    cluster=cluster,
                    evaluable=True,
                    fired=i < n_fire,
                )
            )
    for i in range(starved):
        out.append(
            nr.NullOutcome(
                history_id=f"starved-{i}",
                cluster=0,
                evaluable=False,
                fired=False,
                reason="fewer than n_min condition trades in the training zone",
            )
        )
    return out


def test_rate_is_over_evaluable_histories_and_starved_ones_are_reported():
    o = outcomes({c: (1 if c < 5 else 0) for c in range(10)}, per_cluster=10, starved=40)
    r = nr.assess(o, clustering_unit="calendar window of 90 days", seed=1)
    assert r.n_histories == 140
    assert r.n_evaluable == 100
    assert r.n_starved == 40
    assert r.n_fired == 5
    assert r.rate == pytest.approx(0.05)


def test_clustering_by_window_groups_histories_that_share_calendar_time():
    spans = {"a": 10, "b": 40, "c": 100, "d": 110, "e": 400}
    assigned = nr.cluster_by_window(spans, width_days=90)
    assert assigned["a"] == assigned["b"]
    assert assigned["c"] == assigned["d"]
    assert len({assigned["a"], assigned["c"], assigned["e"]}) == 3


def test_clustered_interval_is_wider_when_fires_concentrate_in_one_cluster():
    """Five fires in one cluster is weaker evidence than five spread over five."""
    concentrated = nr.assess(
        outcomes({0: 5, **{c: 0 for c in range(1, 10)}}, per_cluster=10),
        clustering_unit="cluster",
        seed=7,
    )
    spread = nr.assess(
        outcomes({c: (1 if c < 5 else 0) for c in range(10)}, per_cluster=10),
        clustering_unit="cluster",
        seed=7,
    )
    assert concentrated.rate == pytest.approx(spread.rate)
    assert concentrated.hi - concentrated.lo > spread.hi - spread.lo


def test_the_wider_interval_is_the_authority():
    o = outcomes({0: 5, **{c: 0 for c in range(1, 10)}}, per_cluster=10)
    r = nr.assess(o, clustering_unit="cluster", seed=7)
    assert r.interval_source in ("block bootstrap", "binomial")
    assert r.hi - r.lo >= r.binomial_hi - r.binomial_lo
    assert r.hi - r.lo >= r.bootstrap_hi - r.bootstrap_lo


def test_both_gate_readings_are_reported_and_neither_is_chosen():
    """TD-012 is open: the point estimate and the interval can disagree."""
    o = outcomes({0: 5, **{c: 0 for c in range(1, 10)}}, per_cluster=10)
    r = nr.assess(o, clustering_unit="cluster", seed=7)
    assert r.point_inside is True
    assert r.interval_inside is (r.lo >= nr.GATE_LOW and r.hi <= nr.GATE_HIGH)
    assert not hasattr(r, "passed")


def test_a_test_that_never_fires_is_below_the_band_not_passing_it():
    r = nr.assess(outcomes({c: 0 for c in range(10)}, per_cluster=10), clustering_unit="c", seed=1)
    assert r.rate == 0.0
    assert r.point_inside is False
    assert "below" in r.verdict


def test_a_rate_must_name_its_clustering_unit():
    with pytest.raises((TypeError, ValueError)):
        nr.assess(outcomes({0: 1}, per_cluster=10), seed=1)


def test_refuses_when_nothing_is_evaluable():
    with pytest.raises(ValueError, match="evaluable"):
        nr.assess(outcomes({}, per_cluster=0, starved=20), clustering_unit="c", seed=1)


# --- the zero-event cluster bound -------------------------------------------
#
# The first real sweep found the hole: at zero fires the block bootstrap
# returns [0%, 0%], because every resample of every cluster gives zero. The
# "wider wins" rule then hands authority to the binomial, which assumes the
# histories are independent — and they are not. A bound that assumes 278
# independent observations when there are 18 calendar windows claims precision
# the corpus does not contain.
#
# So the clustered reading is computed too: each cluster is one Bernoulli
# observation of "did anything in this window fire?". That is the maximally
# correlated reading, the conservative end of the envelope. Neither end is
# chosen here — the truth lies between them, and which binds is TD-012.


def test_cluster_level_bound_is_much_wider_when_clusters_are_few():
    o = outcomes({c: 0 for c in range(18)}, per_cluster=15)  # 270 histories, 18 windows
    r = nr.assess(o, clustering_unit="90-day window", seed=1)
    assert r.n_clusters == 18
    assert r.binomial_hi < 0.02, r.binomial_hi
    assert r.cluster_hi > 0.15, r.cluster_hi
    assert r.envelope_hi == pytest.approx(r.cluster_hi)


def test_bootstrap_degeneracy_is_flagged_at_zero_fires():
    r = nr.assess(outcomes({c: 0 for c in range(10)}, per_cluster=10),
                  clustering_unit="c", seed=1)
    assert r.bootstrap_degenerate is True
    assert r.bootstrap_lo == r.bootstrap_hi == 0.0


def test_bootstrap_is_not_degenerate_once_a_cluster_fires():
    o = outcomes({0: 2, **{c: 0 for c in range(1, 10)}}, per_cluster=10)
    assert nr.assess(o, clustering_unit="c", seed=1).bootstrap_degenerate is False


def test_cluster_bound_counts_windows_that_contain_a_fire_not_fires():
    o = outcomes({0: 3, 1: 1, **{c: 0 for c in range(2, 10)}}, per_cluster=10)
    r = nr.assess(o, clustering_unit="c", seed=1)
    lo, hi = nr.wilson_interval(2, 10)  # 2 of 10 windows contain a fire
    assert r.cluster_lo == pytest.approx(lo)
    assert r.cluster_hi == pytest.approx(hi)


def test_the_envelope_can_bust_the_ceiling_while_the_point_estimate_sits_inside():
    """4% of histories fire, but they sit in 4 of 20 windows: far less certain."""
    o = outcomes({c: (3 if c < 4 else 0) for c in range(20)}, per_cluster=15)
    r = nr.assess(o, clustering_unit="90-day window", seed=3)
    assert r.point_inside is True
    assert r.cluster_hi > nr.GATE_HIGH
    assert r.envelope_inside is False


def test_the_envelope_is_reported_in_the_record_with_both_ends_named():
    o = outcomes({c: 0 for c in range(18)}, per_cluster=15)
    rec = nr.assess(o, clustering_unit="90-day window", seed=1).record()
    env = rec["interval"]["envelope"]
    assert env["independent_hi"] < env["clustered_hi"]
    assert "degenerate" in json.dumps(rec)
