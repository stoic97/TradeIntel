"""Every finding carries two labels, in the type: when it was known, and how far it has got."""

from __future__ import annotations

import json
import types
from pathlib import Path

import pytest
from jinja2 import Environment

from services.production.api import findings as F
from services.production.api import scope_facts as SF
from services.production.api import scope_map as SM
from services.production.mirror import metrics as mx

TRIPS = mx.load_trips(json.loads(Path("tests/fixtures/mirror_contract/main.json").read_text()))
IMP = types.SimpleNamespace(fees_available=False, trips_refused=0, rows_in=40, rows_parsed=40,
                            id=1, trips_reconstructed=40, rows_excluded=0)
TIERS = ("Established", "Likely", "Exploratory")


# ---- 1. a finding can't be made without both labels

@pytest.mark.parametrize("known, rung", [
    (None, F.Rung.SEEN), (F.Known.AT_CLICK, None), ("", F.Rung.SEEN), (F.Known.AT_CLICK, ""),
    ("AT_CLICK", F.Rung.SEEN), (F.Known.AT_CLICK, "SEEN"),
])
def test_a_finding_without_both_labels_raises(known, rung):
    with pytest.raises(F.Unlabelled):
        F.Finding("clock", known, rung)


def test_a_finding_with_neither_label_cannot_even_be_written():
    with pytest.raises(TypeError):
        F.Finding("clock")  # type: ignore[call-arg]


def test_the_labels_are_the_rulings_and_only_those():
    assert [k.name for k in F.Known] == ["BEFORE", "AT_CLICK", "ONLY_AFTER"]
    assert [r.name for r in F.Rung] == ["SEEN", "WOULD_YOU_HAVE_KNOWN", "RUN_FORWARD"]


def test_a_finding_is_a_frozen_value():
    f = F.Finding("clock", F.Known.AT_CLICK, F.Rung.SEEN)
    with pytest.raises(AttributeError):
        f.rung = F.Rung.RUN_FORWARD  # type: ignore[misc]


# ---- 2. no finding reaches a template without both labels

def test_every_fact_the_report_decides_has_a_label():
    assert set(SM.FIGURES) <= set(F.LABELS)


def test_every_fact_leaves_the_place_it_is_decided_labelled():
    figs = SF.facts(SF.record_context(TRIPS), IMP)
    assert set(figs) == set(SM.FIGURES)
    for key, fig in figs.items():
        finding = fig["finding"]
        assert isinstance(finding, F.Finding) and finding.key == key
        assert isinstance(finding.known, F.Known) and isinstance(finding.rung, F.Rung)


def test_a_fact_with_no_label_stops_before_any_page(monkeypatch):
    monkeypatch.setitem(F.LABELS, "clock", None)
    with pytest.raises(F.Unlabelled):
        SF.facts(SF.record_context(TRIPS), IMP)
    monkeypatch.delitem(F.LABELS, "clock")
    with pytest.raises(F.Unlabelled):
        SF.facts(SF.record_context(TRIPS), IMP)


def test_a_template_reads_labels_only_through_a_finding():
    env = Environment()
    F.register(env)
    finding = F.Finding("clock", F.Known.AT_CLICK, F.Rung.SEEN)
    assert env.from_string("{{ f|known }} {{ f|rung }}").render(f=finding) == "AT_CLICK SEEN"
    for unlabelled in ({"key": "clock"}, "clock", None):
        with pytest.raises(F.Unlabelled):
            env.from_string("{{ f|known }}").render(f=unlabelled)


def test_nothing_is_called_a_rung_it_has_not_reached():
    """Nothing in the report has been picked using only earlier trades, or run forward yet."""
    assert {f.rung for f in F.LABELS.values()} == {F.Rung.SEEN}


def test_the_specs_tiers_are_not_the_labels():
    names = {m.name for m in F.Known} | {m.name for m in F.Rung}
    values = {m.value for m in F.Known} | {m.value for m in F.Rung}
    for tier in TIERS:
        assert tier.upper() not in names and tier not in values
