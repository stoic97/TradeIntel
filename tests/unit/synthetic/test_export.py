"""Step A, cycle 6b - writing corpus A in the CTR shape, with its truth beside it.

The export is correct only if the engine's own import path turns the fills back
into exactly the generator's trips, and if the same corpus is the same bytes every
time it is written.
"""
import gzip
import json
from dataclasses import replace
from datetime import date

import pytest

from services.production.ctr.reconstruct import reconstruct
from services.research.evaluation.synthetic import corpus as cp
from services.research.evaluation.synthetic import export as ex
from services.research.evaluation.synthetic.trader import LONG
from services.shared.schemas.ctr_v1 import Side

MARKET = cp.synthetic_market(seed=1, n_days=700)


def _cell(test_id, k, n):
    return next(c for c in cp.grid() if (c.test_id, c.multiple, c.n_trades) == (test_id, k, n))


R11 = cp.planted_history(MARKET, _cell("R11", 2, 300), 0)  # adds: three-fill trips
R2 = cp.planted_history(MARKET, _cell("R2", 1, 300), 0)  # sizes of 1.25 units
S6 = cp.planted_history(MARKET, _cell("S6", 4, 300), 0)  # carried overnight


@pytest.mark.parametrize(
    "day,expiry",
    [
        (date(2024, 3, 5), date(2024, 3, 19)),
        (date(2024, 3, 19), date(2024, 3, 19)),
        (date(2024, 3, 20), date(2024, 4, 19)),
        (date(2024, 12, 31), date(2025, 1, 19)),
    ],
)
def test_each_trip_is_given_the_crude_future_expiring_on_the_19th(day, expiry):
    assert ex.contract_expiry(day) == expiry


def test_a_clean_null_is_written_on_its_own_market_not_the_shared_one():
    h = cp.clean_null(0)
    own = h.market.history
    fills = ex.to_fills(h, MARKET)
    first = h.trips[0]
    assert fills[0].ts.date() == own.dates[first.day]
    assert float(fills[0].price) == pytest.approx(first.entry_price, abs=0.005)
    ex.verify_round_trip(h, fills, MARKET)


def test_no_trip_is_carried_across_its_contracts_expiry():
    days = MARKET.history.dates
    for d, allowed in enumerate(MARKET.carry_allowed[:-1]):
        if allowed:
            assert ex.contract_expiry(days[d]) == ex.contract_expiry(days[d + 1])
    for t in S6.trips:
        if t.carried:
            entry, exit_ = days[t.day], days[int(MARKET.history.bars.day[t.exit_idx])]
            assert exit_ <= ex.contract_expiry(entry)


def test_a_fill_at_the_wrong_time_is_caught():
    fills = ex.to_fills(R2, MARKET)
    shifted = fills[-1].model_copy(update={"ts": fills[-1].ts.replace(second=58)})
    with pytest.raises(AssertionError, match="mismatch"):
        ex.verify_round_trip(R2, [*fills[:-1], shifted], MARKET)


def test_sizes_round_to_lots_and_never_to_zero():
    assert ex.lots(1.0) == 4
    assert ex.lots(1.25) == 5
    assert ex.lots(0.01) == 1


@pytest.mark.parametrize("h", [R11, R2, S6], ids=["adds", "sizes", "carry"])
def test_fills_reconstruct_into_exactly_the_generators_trips(h):
    fills = ex.to_fills(h, MARKET)
    assert len(fills) == 2 * len(h.trips) + sum(len(t.adds) for t in h.trips)
    recon = reconstruct(fills)
    assert not recon.open_positions and not recon.skipped
    trips = sorted(recon.round_trips, key=lambda r: r.entry_ts)
    assert len(trips) == len(h.trips)
    for r, t in zip(trips, h.trips, strict=True):
        assert r.direction.value == ("LONG" if t.direction == LONG else "SHORT")
        assert r.quantity == ex.lots(t.size) + sum(ex.lots(u) for _, _, u in t.adds)
        assert r.risk_unit is None  # no stop orders in CTR v1: R lives in the truth table
    ex.verify_round_trip(h, fills, MARKET)


def test_fills_carry_contract_identity_ist_times_and_their_order():
    fills = ex.to_fills(R11, MARKET)
    assert {f.symbol for f in fills} == {"CRUDEOIL"}
    assert all(f.expiry is not None and f.ts.utcoffset().total_seconds() == 19800 for f in fills)
    t = next(t for t in R11.trips if t.adds)
    k = sum(2 + len(p.adds) for p in R11.trips[: R11.trips.index(t)])
    entry, add, exit_ = fills[k : k + 3]
    assert (entry.ts.second, add.ts.second, exit_.ts.second) == (0, 30, 59)
    assert entry.side == add.side != exit_.side
    assert entry.side == (Side.BUY if t.direction == LONG else Side.SELL)


def test_a_carried_trip_stays_in_its_entry_contract():
    t = next(t for t in S6.trips if t.carried)
    k = sum(2 + len(p.adds) for p in S6.trips[: S6.trips.index(t)])
    entry, exit_ = ex.to_fills(S6, MARKET)[k : k + 2]
    assert exit_.ts.date() > entry.ts.date()
    assert entry.expiry == exit_.expiry


def test_a_broken_round_trip_is_caught_before_anything_is_written():
    fills = ex.to_fills(R2, MARKET)
    with pytest.raises(AssertionError, match="reconstruct"):
        ex.verify_round_trip(R2, fills[:-1], MARKET)  # drop the last exit: one left open


def _read(path):
    with gzip.open(path, "rt") as f:
        return [json.loads(line) for line in f]


def test_the_same_corpus_is_the_same_bytes_and_the_truth_sits_beside_it(tmp_path):
    hs = [R11, cp.clean_null(0), cp.adversarial_null(MARKET, 1)]
    a = ex.write_corpus(hs, MARKET, tmp_path / "a", {"crude_sha256": "synthetic"})
    b = ex.write_corpus(hs, MARKET, tmp_path / "b", {"crude_sha256": "synthetic"})
    assert a["corpus_sha256"] == b["corpus_sha256"]
    for name in ("fills", "trips", "histories"):
        fa = (tmp_path / "a" / f"{name}.jsonl.gz").read_bytes()
        assert fa == (tmp_path / "b" / f"{name}.jsonl.gz").read_bytes()
    assert a["histories"] == {"adversarial_null": 1, "clean_null": 1, "planted": 1}

    trips = _read(tmp_path / "a" / "trips.jsonl.gz")
    assert len(trips) == sum(len(h.trips) for h in hs) == a["tables"]["trips"]["rows"]
    planted = [r for r in trips if r["history_id"] == ex.history_id(R11)]
    assert [r["r_multiple"] for r in planted] == [t.r_multiple for t in R11.trips]
    assert any("R11" in r["applied"] for r in planted)

    rows = {r["history_id"]: r for r in _read(tmp_path / "a" / "histories.jsonl.gz")}
    row = rows[ex.history_id(R11)]
    assert row["cell"]["test_id"] == "R11" and row["planting"]["reached"] is True
    assert row["truth"]["avoidable_cost_r"] == R11.truth["avoidable_cost_r"]
    assert json.loads((tmp_path / "a" / "manifest.json").read_text()) == a


def test_float_noise_moves_the_corpus_digest_but_not_the_decision_digest(tmp_path):
    # Another numpy or CPU moves the 16th digit of R and risk; nothing else (§12.1).
    t0 = R2.trips[0]
    noisy_trip = replace(
        t0, r_multiple=t0.r_multiple + 1e-15, risk_per_unit=t0.risk_per_unit * (1 + 1e-15)
    )
    noisy = replace(R2, trips=(noisy_trip, *R2.trips[1:]))
    a = ex.write_corpus([R2], MARKET, tmp_path / "a", {})
    b = ex.write_corpus([noisy], MARKET, tmp_path / "b", {})
    assert a["corpus_sha256"] != b["corpus_sha256"]
    assert a["decision_sha256"] == b["decision_sha256"]


def test_a_changed_label_changes_the_decision_digest(tmp_path):
    t0 = R2.trips[0]
    other = "TIME" if t0.exit_reason != "TIME" else "STOP"
    relabelled = replace(R2, trips=(replace(t0, exit_reason=other), *R2.trips[1:]))
    a = ex.write_corpus([R2], MARKET, tmp_path / "a", {})
    b = ex.write_corpus([relabelled], MARKET, tmp_path / "b", {})
    assert a["decision_sha256"] != b["decision_sha256"]


def test_a_changed_trip_changes_the_corpus_digest(tmp_path):
    base = ex.write_corpus([R2], MARKET, tmp_path / "a", {})
    other = cp.planted_history(MARKET, _cell("R2", 1, 300), 1)  # a different seed
    moved = ex.write_corpus([other], MARKET, tmp_path / "b", {})
    assert base["corpus_sha256"] != moved["corpus_sha256"]
