"""The shuffle test that decides whether Chapter 3 may say a direction [TICKET-838].

The rule was committed here before any real file went through it:

* null: the framework's N-B, outcomes shuffled within each day, 2,000 draws, the condition
  worked out again on each draw;
* statistic: the two means the sentence prints, in rupees;
* pass: p <= 0.05 two-sided, because the sentence says whichever way the means point;
* minimum: the framework's 30 condition and 60 comparison, and closed below it;
* no 0.25R cutoff: most traders have no R, and this gates a sentence that prints both figures.
  It isn't a research Finding.

Inputs are synthetic.
"""

from __future__ import annotations

import ast
import re
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import numpy as np
import pytest

from services.production.mirror import metrics as mx
from services.shared.conditions import b2_shuffle as T
from services.shared.conditions.b2_condition import Obs, population_and_condition
from services.shared.schemas import scope_v1 as s
from tests.unit.api.test_scope_chapters import IMP
from tests.unit.api.test_scope_facts import fact_page

CLOSED = "No difference we can stand behind."
OPEN = "After two straight losses, your next trades averaged"


def synthetic(seed: int, days: int = 200, per_day: int = 6, effect: float = 0.0, noise: str = "normal") -> list[Obs]:
    """Trades one after another each day. effect shifts a trade that follows two losses."""
    rng = np.random.default_rng(seed)
    out = []
    for day in range(days):
        recent: list[float] = []
        for k in range(per_day):
            draw = rng.standard_t(3) if noise == "fat" else rng.normal()
            r = float(draw * 1000 + (effect if len(recent) >= 2 and recent[-1] < 0 and recent[-2] < 0 else 0))
            out.append(Obs(day=day, entry_at=float(day * 1000 + k * 10), exit_at=float(day * 1000 + k * 10 + 5), r=r))
            recent.append(r)
    return out


def trips_from(obs: list[Obs]) -> list[mx.Trip]:
    start = datetime.fromisoformat("2025-01-01T09:15:00+05:30")
    out = []
    for i, o in enumerate(obs):
        entry = start + timedelta(days=o.day, seconds=(o.entry_at - o.day * 1000) * 60)
        leave = entry + timedelta(seconds=(o.exit_at - o.entry_at) * 60)
        out.append(mx.Trip(f"T-{i}", "WIDGET", entry.date().isoformat(), entry, leave,
                           int((leave - entry).total_seconds()), Decimal(str(round(o.r, 2))), 1,
                           s.RiskUnitSourceV1.DECLARED_BUDGET, is_option=True))
    return out


# ---------- The rule is the framework's where the framework has one ----------


def test_the_draws_and_minimums_are_the_frameworks_own():
    framework = Path("services/research/prereg/framework_v1.yaml").read_text(encoding="utf-8")
    assert "2,000 draws each" in framework
    b2 = next(line for line in framework.splitlines() if "id: B2," in line)
    assert "null: N-B" in b2
    assert "n_min: 30/60" in b2
    assert (T.DRAWS, T.MIN_CONDITION, T.MIN_COMPARISON) == (2000, 30, 60)


def test_the_bar_is_five_percent_two_sided():
    assert T.ALPHA == 0.05


def test_production_can_run_it_without_the_research_packages():
    tree = ast.parse(Path(T.__file__).read_text(encoding="utf-8"))
    imported = {n.names[0].name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import)}
    imported |= {(n.module or "").split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert imported <= {"__future__", "collections", "dataclasses", "numpy", "services"}
    assert "services.research" not in Path(T.__file__).read_text(encoding="utf-8")


# ---------- The groups are the shared definition's ----------


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_the_groups_are_exactly_the_shared_definitions(seed):
    rng = np.random.default_rng(seed)
    obs = []
    for day in range(40):
        for k in range(int(rng.integers(1, 9))):
            entry = float(rng.uniform(0, 100))
            obs.append(Obs(day=day, entry_at=entry, exit_at=entry + float(rng.uniform(0, 30)),
                           r=float(rng.choice([-5.0, 0.0, 5.0]))))
    in_pop, cond = population_and_condition(obs)
    pop, first, second = T.last_two_resolved(obs)
    r = np.array([o.r for o in obs])
    assert list(pop) == list(np.flatnonzero(in_pop))
    assert list((r[first] < 0) & (r[second] < 0)) == list(cond[pop])


def test_the_statistic_is_the_two_means_the_sentence_prints():
    trips = trips_from(synthetic(5))
    tl = mx.two_straight_losses(trips)
    got = T.shuffle_test(mx.b2_observations(trips))
    assert got.n_condition == tl.condition
    assert got.n_comparison == tl.comparison
    want = float(tl.condition_net) / tl.condition - float(tl.comparison_net) / tl.comparison
    assert got.difference == pytest.approx(want, abs=1e-6)


# ---------- The shuffle ----------


def test_a_shuffle_keeps_each_days_outcomes_and_only_moves_them_within_it():
    day = np.array([0, 0, 0, 1, 1, 2, 2, 2, 2])
    r = np.arange(9.0)
    moved = T.shuffle_within_days(r, day, np.random.default_rng(1))
    for d in (0, 1, 2):
        assert sorted(moved[day == d]) == sorted(r[day == d])
    assert list(moved) != list(r)


def test_the_same_file_always_gets_the_same_answer():
    obs = synthetic(6)
    assert T.shuffle_test(obs) == T.shuffle_test(obs)


def test_the_p_value_never_reads_zero():
    assert T.shuffle_test(synthetic(7, effect=-3000)).p >= 1 / (T.DRAWS + 1)


# ---------- It opens and closes for the right reasons ----------


def test_a_planted_effect_opens_it():
    assert T.shuffle_test(synthetic(8, effect=-1500)).passes


def test_a_planted_effect_the_other_way_opens_it_too():
    """The sentence says whichever way the means point, so the test looks both ways."""
    assert T.shuffle_test(synthetic(9, effect=1500)).passes


def test_a_clean_trader_keeps_it_closed():
    assert not T.shuffle_test(synthetic(10)).passes


@pytest.mark.parametrize("noise", ["normal", "fat"])
def test_on_noise_it_opens_about_as_often_as_the_framework_allows(noise):
    """validation_fp_band [0.02, 0.08], on both noise classes. Seeds are fixed, so not flaky."""
    runs = [T.shuffle_test(synthetic(seed, days=80, per_day=6, noise=noise), draws=400).passes for seed in range(200)]
    assert 0.02 <= sum(runs) / len(runs) <= 0.08


def test_too_few_condition_trades_keep_it_closed_whatever_the_means_say():
    got = T.shuffle_test(synthetic(11, days=20, per_day=4, effect=-5000))
    assert got.n_condition < T.MIN_CONDITION
    assert not got.passes
    assert got.p is None


def test_too_few_comparison_trades_keep_it_closed():
    obs = [Obs(day=d, entry_at=float(k), exit_at=k + 0.5, r=-1.0) for d in range(20) for k in range(6)]
    got = T.shuffle_test(obs)
    assert got.n_comparison < T.MIN_COMPARISON
    assert not got.passes


def test_nothing_to_test_keeps_it_closed():
    assert not T.shuffle_test([]).passes


# ---------- The gate on the page ----------


def test_the_gate_answers_the_test_on_a_planted_trader():
    assert mx.post_loss_sentence_may_show(trips_from(synthetic(12, effect=-1500))) is True


def test_the_gate_stays_closed_on_a_clean_trader():
    assert mx.post_loss_sentence_may_show(trips_from(synthetic(10))) is False


def test_no_trades_keep_the_gate_closed():
    assert mx.post_loss_sentence_may_show([]) is False


def test_the_page_says_the_sentence_when_the_test_passes():
    html = fact_page("down", trips_from(synthetic(12, effect=-1500)))
    assert OPEN in html
    assert CLOSED not in html


def test_the_page_says_nothing_about_a_direction_when_it_doesnt():
    html = fact_page("down", trips_from(synthetic(10)))
    assert CLOSED in html
    assert OPEN not in html


def test_a_page_view_runs_the_draws_once_per_file(monkeypatch):
    mx._post_loss_gate.cache_clear()
    calls = []
    real = T.shuffle_test

    def counted(obs):
        calls.append(1)
        return real(obs, draws=50)

    monkeypatch.setattr(T, "shuffle_test", counted)
    trips = trips_from(synthetic(13, days=60))
    for _ in range(3):
        mx.post_loss_sentence_may_show(trips)
    assert len(calls) == 1
    mx._post_loss_gate.cache_clear()


def test_a_closed_gate_is_not_said_to_be_a_finding_about_the_trader():
    html = fact_page("down", trips_from(synthetic(10)))
    assert not re.search(r"(?i)no effect|you don't|you do not trade differently", html)
    assert IMP is not None
