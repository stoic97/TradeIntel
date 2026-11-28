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


def test_the_factor_names_r12_and_never_r2():
    assert any("R12" in f.checks for f in factor_map.FACTORS)
    assert not any("R2" in f.checks for f in factor_map.FACTORS)


def test_no_finding_sentence_before_r12_is_signed(monkeypatch):
    monkeypatch.setattr(mx, "size_after_check", lambda trips: SimpleNamespace(passes=True))
    assert mx.R12_SIGNED is False
    assert mx.size_sentence_may_show([object()]) is False
