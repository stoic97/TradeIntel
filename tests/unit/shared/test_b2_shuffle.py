"""The shuffle test that decides whether Chapter 3 may say a direction [TICKET-838].

The rule, written in framework_v1.yaml under production_gates and held to it here:

* null: the framework's N-B, outcomes shuffled within each day, 2,000 draws, the condition
  worked out again on each draw;
* statistic: the two means the sentence prints, in rupees;
* pass: p <= 0.05, one-sided in B2's stated direction, trades after two losses doing worse;
* minimum: the framework's 30 condition and 60 comparison, and closed below it;
* no 0.25R cutoff: most traders have no R, and this gates a sentence, not a Finding.

A result in the other direction keeps the gate closed however strong it is. Scope must not print
a sentence the file argues against. Inputs are synthetic.
"""

from __future__ import annotations

import ast
import re
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import numpy as np
import pytest
import yaml

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


def gate_in_the_framework() -> dict:
    framework = yaml.safe_load(Path("services/research/prereg/framework_v1.yaml").read_text(encoding="utf-8"))
    found = []

    def walk(node):
        if isinstance(node, dict):
            if "production_gates" in node:
                found.append(node["production_gates"])
            for value in node.values():
                walk(value)

    walk(framework)
    assert len(found) == 1, "the bar is written down once, in the framework"
    return found[0]["B2_post_loss_sentence"]


def test_the_bar_is_in_the_framework_not_only_in_the_code():
    gate = gate_in_the_framework()
    assert gate["null_model"] == "N-B"
    assert gate["draws"] == T.DRAWS
    assert gate["bar_p"] == T.ALPHA == 0.05
    assert gate["sided"] == "one"
    assert gate["direction"] == T.DIRECTION == "<"
    assert gate["outcome"] == "net_rupees"
    assert gate["minimum"] == f"{T.MIN_CONDITION}/{T.MIN_COMPARISON}"
    assert gate["opposite_direction"] == "closed"


def test_the_gates_direction_is_b2s_own():
    framework = Path("services/research/prereg/framework_v1.yaml").read_text(encoding="utf-8")
    b2 = Path("services/research/library/b2.py").read_text(encoding="utf-8")
    assert 'DIRECTION = "<"' in b2
    assert "id: B2," in framework


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


def two_sided_p(obs) -> tuple[float, float]:
    """What a two-sided bar would have read on this file: the ruling is that it doesn't count."""
    r = np.array([o.r for o in obs], dtype=float)
    day = np.array([o.day for o in obs])
    pop, first, second = T.last_two_resolved(obs)
    seen, _, _ = T._difference(r, pop, first, second)
    rng = np.random.default_rng(T.SEED)
    wider = sum(
        abs(T._difference(T.shuffle_within_days(r, day, rng), pop, first, second)[0]) >= abs(seen)
        for _ in range(T.DRAWS)
    )
    return seen, (wider + 1) / (T.DRAWS + 1)


def test_a_strong_effect_the_other_way_keeps_it_closed():
    got = T.shuffle_test(synthetic(9, effect=1500))
    assert got.difference > 0
    assert got.p > 0.5
    assert not got.passes


def test_the_other_way_at_a_two_sided_p_of_about_0_033_keeps_it_closed():
    """The case the ruling is about: a two-sided bar would open here, on a sentence the file
    argues against. Trades after two losses did better, so the gate stays shut."""
    obs = synthetic(27, effect=150)
    difference, two_sided = two_sided_p(obs)
    assert difference > 0
    assert 0.028 <= two_sided <= 0.038
    got = T.shuffle_test(obs)
    assert got.p > 0.5
    assert not got.passes


def test_the_gate_on_the_page_stays_closed_the_other_way():
    trips = trips_from(synthetic(27, effect=150))
    assert mx.post_loss_sentence_may_show(trips) is False
    html = fact_page("down", trips)
    assert CLOSED in html
    assert OPEN not in html


def test_a_level_result_keeps_it_closed():
    obs = [Obs(day=d, entry_at=float(k), exit_at=k + 0.5, r=-1.0 if k < 2 else 1.0) for d in range(40) for k in range(5)]
    got = T.shuffle_test(obs)
    assert not got.passes


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
