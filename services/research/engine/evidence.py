"""Promotion evidence - Research Specification v1.0 sections 4.6, 5.2 and 5.4a.

Three quantities, named separately because v1.0 untangled them (section 5.2):

* **theta_min** - the practical threshold the shrunk training median must clear.
  0.25R for every conditional-R test, derived from delta_pool at the reference
  prevalence.
* **theta_hold** - what the hold-out is sized to replicate:
  ``max(theta_min, the 20th percentile of the shrunk training posterior)``, the
  quantile nearest zero, because a candidate that reached the hold-out is the one
  most likely to have been flattered by selection.
* **MDE** - the smallest effect the test had 80 per cent power to find at the
  realised sample, one-sided in the pre-registered direction, with the measured
  1.65x shuffle inflation. Reported on every null.

The two-part criterion (section 5.2, after Kruschke 2018): **is it real** -
P(theta beyond 0 | training) - and **is it big enough** - the shrunk training median
beyond theta_min. P_hold comes from an isolation-only fit that never sees the
training posterior. A kill overrides every tier: P_hold below 0.50 after P_train at
or above 0.95 is the classic overfit signature.

Both closed forms below reproduce the spec's own tables exactly at sigma_R = 1.4 and
a 4:1 comparison ratio, which is how they were checked. The MDE table is reproduced
only when the 1.65 inflation multiplies the *variance*; on the standard error it
would give 165 rather than 100 condition trades for 0.5R.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from scipy.stats import norm

THETA_MIN_R = 0.25
HOLD_QUANTILE = 0.20
SHUFFLE_INFLATION = 1.65  # measured (section 5.4a); multiplies the variance
POWER = 0.80
Z_POWER = float(norm.ppf(POWER))
Z_ONE_SIDED = float(norm.ppf(0.95))

P_TRAIN = {"Established": 0.95, "Likely": 0.80, "Exploratory": 0.60}
P_HOLD = {"Established": 0.80, "Likely": 0.65, "Exploratory": 0.40}
KILL_P_HOLD = 0.50

PENDING_GATES = ("robustness", "bh_q", "economic_significance", "sign_agreement")


def n_hold(theta_hold: float, sigma_r: float, comparison_ratio: float) -> int:
    """Condition trades in isolation at which an effect of theta_hold reaches
    P_hold >= 0.80, at the trader's sigma_R and comparison ratio (section 4.6)."""
    need = (Z_POWER * sigma_r / theta_hold) ** 2 * (1.0 + 1.0 / comparison_ratio)
    return max(1, math.ceil(need - 1e-9))


def n_for_confident_null(effect: float, sigma_r: float, comparison_ratio: float) -> int:
    """Condition trades for 80 per cent one-sided power at ``effect`` (section 5.4a)."""
    need = (
        (Z_ONE_SIDED + Z_POWER) ** 2
        * SHUFFLE_INFLATION
        * sigma_r**2
        * (1.0 + 1.0 / comparison_ratio)
        / effect**2
    )
    return math.ceil(need - 1e-9)


def mde(n_condition: int, n_comparison: int, sigma_r: float) -> float:
    """The smallest effect detectable with 80 per cent power at this sample."""
    se = sigma_r * math.sqrt(1.0 / n_condition + 1.0 / n_comparison)
    return (Z_ONE_SIDED + Z_POWER) * math.sqrt(SHUFFLE_INFLATION) * se


@dataclass(frozen=True)
class StatisticalCore:
    direction: str
    theta_min: float
    p_train: float
    m_train: float
    theta_hold: float
    p_hold: float
    real: bool
    big_enough: bool
    killed: bool
    kill_reason: str = ""


def _beyond(values: np.ndarray, bound: float, direction: str) -> np.ndarray:
    return values < bound if direction == "<" else values > bound


def statistical_core(
    train: np.ndarray,
    hold: np.ndarray,
    direction: str,
    theta_min: float,
) -> StatisticalCore:
    if direction not in ("<", ">"):
        raise ValueError("direction must be '<' or '>'")
    train = np.asarray(train, dtype=float).ravel()
    hold = np.asarray(hold, dtype=float).ravel()
    sign = -1.0 if direction == "<" else 1.0

    p_train = float(_beyond(train, 0.0, direction).mean())
    m_train = float(np.median(train))
    p_hold = float(_beyond(hold, 0.0, direction).mean())

    # The quantile nearest zero: the 20th percentile of the effect's magnitude.
    q = 1.0 - HOLD_QUANTILE if direction == "<" else HOLD_QUANTILE
    magnitude = max(0.0, sign * float(np.quantile(train, q)))
    theta_hold = max(theta_min, magnitude)

    real = p_train >= P_TRAIN["Established"]
    big_enough = bool(_beyond(np.array([m_train]), sign * theta_min, direction)[0])
    killed = real and p_hold < KILL_P_HOLD
    return StatisticalCore(
        direction=direction,
        theta_min=theta_min,
        p_train=p_train,
        m_train=m_train,
        theta_hold=theta_hold,
        p_hold=p_hold,
        real=real,
        big_enough=big_enough,
        killed=killed,
        kill_reason="hold-out contradicts a confident training fit" if killed else "",
    )


@dataclass(frozen=True)
class Finding:
    tier: str
    core: StatisticalCore
    n_condition: int
    n_comparison: int
    n_condition_isolation: int
    sigma_r: float
    n_hold: int
    mde: float
    power_at_theta_min: float
    pending_gates: tuple[str, ...] = PENDING_GATES
    failed_gate: str = ""
    null_statement: str = ""
    notes: list[str] = field(default_factory=list)


def _power(effect: float, n_condition: int, n_comparison: int, sigma_r: float) -> float:
    se = sigma_r * math.sqrt(SHUFFLE_INFLATION) * math.sqrt(1.0 / n_condition + 1.0 / n_comparison)
    return float(norm.cdf(effect / se - Z_ONE_SIDED))


def assess(
    core: StatisticalCore,
    *,
    n_condition: int,
    n_comparison: int,
    n_condition_isolation: int,
    sigma_r: float,
    n_min: tuple[int, int],
    diagnostics_failed: bool = False,
) -> Finding:
    """Tier a Finding from its evidence. Established and Likely cannot be awarded
    while any gate is unevaluated; inventing values for them would be worse."""
    ratio = n_comparison / max(n_condition, 1)
    size = mde(max(n_condition, 1), max(n_comparison, 1), sigma_r)
    hold_n = n_hold(core.theta_hold, sigma_r, max(ratio, 1e-9))
    power = _power(core.theta_min, max(n_condition, 1), max(n_comparison, 1), sigma_r)

    fired = core.real and core.big_enough
    if size <= core.theta_min:
        null = "no problem found"
    else:
        more = n_for_confident_null(core.theta_min, sigma_r, max(ratio, 1e-9)) - n_condition
        null = (
            f"no leak larger than {size:.2f}R found; smaller ones cannot be ruled out "
            f"at your history (about {max(more, 0)} more condition trades would bring "
            f"that to {core.theta_min:.2f}R)"
        )

    common = {
        "core": core,
        "n_condition": n_condition,
        "n_comparison": n_comparison,
        "n_condition_isolation": n_condition_isolation,
        "sigma_r": sigma_r,
        "n_hold": hold_n,
        "mde": size,
        "power_at_theta_min": power,
        "null_statement": "" if fired else null,
    }

    if diagnostics_failed:
        return Finding("Not enough evidence yet", failed_gate="kill: failed_diagnostics", **common)
    if core.killed:
        return Finding("Not enough evidence yet", failed_gate=f"kill: {core.kill_reason}", **common)
    if n_condition < n_min[0] // 2:
        return Finding(
            "Not enough evidence yet",
            failed_gate=f"n_condition {n_condition} below half the minimum {n_min[0]}",
            **common,
        )
    exploratory = (
        core.p_train >= P_TRAIN["Exploratory"] and core.p_hold >= P_HOLD["Exploratory"]
    )
    if n_condition < n_min[0] or n_comparison < n_min[1]:
        return Finding(
            "Exploratory" if exploratory else "Not enough evidence yet",
            failed_gate=(
                f"n_condition {n_condition} below {n_min[0]}"
                if n_condition < n_min[0]
                else f"n_comparison {n_comparison} below {n_min[1]}"
            ),
            **common,
        )
    if exploratory:
        return Finding("Exploratory", **common)
    return Finding("Not enough evidence yet", failed_gate="P_train or P_hold below Exploratory", **common)
