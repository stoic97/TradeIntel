"""TICKET-996, per the founder's ruling of 24 Nov 2026 (option B, TICKET-1063): the measure is
registered as its own row, R12, and stops using R2's name. Until R12 is signed (PR #263), no page
calls the result a finding: the two averages stand side by side and nothing is claimed."""
from types import SimpleNamespace

from services.production.api import factor_map
from services.production.mirror import metrics as mx
from services.shared.conditions import r2_shuffle


def test_the_check_is_named_r12_not_r2():
    assert r2_shuffle.CHECK == "R12"
    assert mx.CHECKS_RUN == ("B2", "R12")


def test_the_size_fact_never_names_r2():
    size_factors = [f for f in factor_map.FACTORS if "size" in f.facts]
    assert size_factors and not any("R2" in f.checks for f in size_factors)


def test_no_finding_sentence_before_r12_is_signed(monkeypatch):
    monkeypatch.setattr(mx, "size_after_check", lambda trips: SimpleNamespace(passes=True))
    assert mx.R12_SIGNED is False
    assert mx.size_sentence_may_show([object()]) is False


def test_its_labels_and_its_factor_under_r12():
    from services.production.api import findings, trade_list
    assert findings.of("size")
    factor = next(f for f in factor_map.FACTORS if "size" in f.facts)
    assert "size" in factor.facts and "after" in factor.filters
    assert "size" in trade_list.FACTS_WITH_TRADES
    assert any(f.name == "after" for f in trade_list.FILTERS)
