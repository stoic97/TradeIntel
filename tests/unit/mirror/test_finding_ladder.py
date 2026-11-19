"""The ladder from a finding to a rule, in the trader's words (TICKET-925).

Every finding on every page shows its rung on a five-rung ladder. The rung comes from the
Finding's own label (TICKET-917), never from a string in a template. Nothing shows a rung
above its label, the rungs not reached are drawn and say so, and the research spec's tiers
never reach a page.
"""

from __future__ import annotations

import html
import re
from pathlib import Path

import pytest

from services.production.api import findings as F
from services.production.api import scope_map as SM

TIERS = ("Established", "Likely", "Exploratory")
RUNGS = ["SEEN", "WOULD_YOU_HAVE_KNOWN", "SET_AS_YOUR_RULE", "RUN_FORWARD", "VERDICT"]
NAMES = ["Seen", "Would you have known?", "Set as your rule", "Run forward", "Verdict"]
NOT_YET = "Not yet reached"
TEMPLATE = Path("services/production/api/templates/scope/_ladder.html")

LADDER = re.compile(r'<ol class="ladder" data-ladder="([^"]+)">(.*?)</ol>', re.S)
RUNG = re.compile(r'<li[^>]*data-rung="([^"]+)" data-reached="(yes|no)"[^>]*>(.*?)</li>', re.S)

CHAPTER_FACTS = {c.number: [f.key for f in c.facts] for c in SM.CHAPTERS}
FACT_KEYS = [key for keys in CHAPTER_FACTS.values() for key in keys]
FINDING_PAGES = ([f"/mirror/chapter/{n}" for n in CHAPTER_FACTS]
                 + [f"/mirror/fact/{key}" for key in FACT_KEYS])
OTHER_PAGES = ["/", "/mirror", "/rules", "/factors", "/eligibility", "/budget", "/journals"]


def page(client, path: str) -> str:
    response = client.get(path)
    assert response.status_code == 200, f"{path} answered {response.status_code}"
    return response.text


def ladders(text: str) -> list[tuple[str, list[tuple[str, bool, str]]]]:
    """Each ladder on a page: the fact it is for, then its rungs as (key, reached, words)."""
    out = []
    for key, inner in LADDER.findall(text):
        rungs = [(rung, reached == "yes", html.unescape(re.sub(r"<[^>]+>", " ", words)))
                 for rung, reached, words in RUNG.findall(inner)]
        out.append((key, rungs))
    return out


def tiers_in(text: str) -> list[str]:
    return [tier for tier in TIERS if re.search(rf"\b{tier}\b", text)]


def the_ladder():
    assert hasattr(F, "ladder"), "findings.ladder is not written yet"
    return F.ladder


# ---- gate 1: the spec's tiers reach no page (rendered HTML, not template source)

def test_no_page_prints_a_tier_of_the_research_spec(client):
    for path in FINDING_PAGES:
        assert not tiers_in(page(client, path)), path
    for path in OTHER_PAGES:
        assert not tiers_in(client.get(path).text), path


def test_that_reading_catches_a_tier_and_leaves_a_longer_word_alone():
    assert tiers_in("<p>Likely</p>") == ["Likely"]
    assert tiers_in("<p>Unlikely, and likely not</p>") == []


# ---- every finding on every page shows its ladder

def test_every_fact_page_draws_the_ladder_of_its_own_finding(client):
    for key in FACT_KEYS:
        found = ladders(page(client, f"/mirror/fact/{key}"))
        assert [k for k, _ in found] == [key], key
        assert [rung for rung, _, _ in found[0][1]] == RUNGS, key


def test_every_card_on_a_chapter_draws_the_ladder_of_its_own_finding(client):
    for n, keys in CHAPTER_FACTS.items():
        found = ladders(page(client, f"/mirror/chapter/{n}"))
        assert [k for k, _ in found] == keys, n


# ---- gate 2: no finding displays a rung above the one its label carries

def test_no_finding_shows_a_rung_above_the_one_its_label_carries(client):
    drawn = 0
    for path in FINDING_PAGES:
        for key, rungs in ladders(page(client, path)):
            top = RUNGS.index(F.LABELS[key].rung.name)
            reached = [rung for rung, is_reached, _ in rungs if is_reached]
            assert reached == RUNGS[:top + 1], (path, key)
            drawn += 1
    assert drawn, "no ladder was drawn on any page"


# ---- gate 3: the rungs not reached are visible and plainly marked

def test_the_rungs_not_reached_are_drawn_and_say_so(client):
    drawn = 0
    for path in FINDING_PAGES:
        for key, rungs in ladders(page(client, path)):
            assert len(rungs) == len(RUNGS), (path, key)
            for (rung, reached, words), name in zip(rungs, NAMES, strict=True):
                assert name in words, (path, key, rung)
                assert (NOT_YET in words) is (not reached), (path, key, rung)
            drawn += 1
    assert drawn, "no ladder was drawn on any page"


# ---- the rung comes from the type, not from a string in a template

def test_the_ladder_is_read_from_the_label_in_the_type():
    ladder = the_ladder()
    for label, count in ((F.Rung.SEEN, 1), (F.Rung.WOULD_YOU_HAVE_KNOWN, 2),
                         (F.Rung.RUN_FORWARD, 4)):
        steps = ladder(F.Finding("clock", F.Known.AT_CLICK, label))
        assert [s.key for s in steps] == RUNGS
        assert [s.name for s in steps] == NAMES
        assert [s.reached for s in steps] == [i < count for i in range(len(RUNGS))]


def test_no_label_reaches_the_verdict_yet():
    ladder = the_ladder()
    for label in F.Rung:
        assert not ladder(F.Finding("clock", F.Known.AT_CLICK, label))[-1].reached


def test_a_ladder_is_drawn_only_for_a_finding():
    ladder = the_ladder()
    for unlabelled in ({"key": "clock"}, "clock", None):
        with pytest.raises(F.Unlabelled):
            ladder(unlabelled)


def test_the_rungs_words_are_in_the_type_not_in_the_template():
    assert TEMPLATE.exists(), "scope/_ladder.html is not written yet"
    source = TEMPLATE.read_text(encoding="utf-8")
    for words in [*NAMES, NOT_YET]:
        assert words not in source, words


def test_the_ladders_words_are_not_the_specs_tiers():
    ladder = the_ladder()
    for step in ladder(F.Finding("clock", F.Known.AT_CLICK, F.Rung.SEEN)):
        assert not tiers_in(f"{step.name} {step.says} {step.state}")
