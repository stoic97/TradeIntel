"""Batch 2 of Phase 4 (handoff 10): consent, the consent ledger, what we can check.

Each page moves onto layout.html and the kit's markup and keeps the app's own words
(handoff 6, 11): frozen here from the pages as they read before the move, with the
consent promises read from the versioned text itself (accounts/consent.py), never
written into the page. The only change is counts written by the count filter. The
kit's "I don't agree" and its declined page are new copy and wait for D9.
"""

from __future__ import annotations

import re
import types
from datetime import UTC, datetime

import pytest

from services.production.accounts import consent as cs
from services.shared.schemas import scope_v1 as s
from tests.unit.api.templating import TEMPLATES, template_env

NS = types.SimpleNamespace


def verdict(id_, state, reason, need=None, unit=None):
    return NS(test=NS(id=id_), state=NS(value=state), reason=reason, need=need,
              unit=NS(value=unit) if unit else None)


SHORT = [verdict("T02", "insufficient_sample", "needs 200, has 40")]
WAITING = [verdict("T03", "required_data_missing", "price series")]
ALL_KINDS = NS(total=19, enough=[verdict("T01", "enough", "62 trips", 50, "round_trips")],
               short=SHORT, waiting=WAITING,
               undetermined=[verdict("T04", "undetermined", "by session")],
               blocked=SHORT + WAITING)
NONE_ENOUGH = NS(total=19, enough=[], short=SHORT, waiting=WAITING, undetermined=[],
                 blocked=SHORT + WAITING)
TEXT = cs.CURRENT
LEDGER = [NS(at=datetime(2026, 9, 8, tzinfo=UTC), purpose=s.ConsentPurpose.DIAGNOSIS,
             granted=True, terms_version="0-draft")]

CONTEXT = {
    "consent.html": {"text": TEXT, "error": "Tick the first box to continue."},
    "consent_ledger.html": {"text": TEXT, "state": {TEXT.purposes[0].enum: True},
                            "events": LEDGER},
    "eligibility.html": {"result": ALL_KINDS, "trips": 1240, "days": 8,
                         "framework": NS(version="0.3"), "draft": True},
    "eligibility.html#none": {"result": NONE_ENOUGH, "trips": 40, "days": 8,
                              "framework": NS(version="0.3"), "draft": False},
    "eligibility_unreadable.html": {},
}

SAID = {
    "consent.html": (
        "Your data Before you upload A tradebook is among the most sensitive files you own. Here is exactly what happens to it. The same promises are made in plainer words on plusev.in ; if the two ever disagree, this page is the one you agreed to, and we want to hear about it. Tick the first box to continue. What we store The file you upload, exactly as your broker produced it. The reconstruction we build from it — your trades matched into round trips. And the Journals written from those trades. We also record which lines you open and how long you read them, so that a later version can put the lines that matter to you first; that is a record of what you read, never of anything you type. Nothing else about you. For how long Until you delete it. Who can access it The two people who run the product: the founder, and the engineer who runs the server. No third party receives the file, and no external service touches anything derived from it — there is no analytics, no error reporting and no email in this product. If that ever changes, this page names the service before it does. What deletion covers The file, every artefact derived from it, and every Journal. Backups roll off within 30 days, so your data is gone from those too. What we keep is the record that you consented and the record that you deleted — the proof that both happened. What deletion cannot undo Your file and everything derived from it can be deleted at any time. What cannot be undone is that looking at your data informed decisions we have already made about the engine. This is the same as any research partnership, and we say so plainly. What you are agreeing to Process my tradebook to produce my own record We read your file, reconstruct your trades, and show you what they say. This is the product: without it there is nothing to run. Use my tradebook to check and calibrate the engine Your history helps us find out where our reconstruction and our measurements are wrong. We do this by running our own code against your trades and comparing what it says with what your file shows. You can refuse this and still get everything else, exactly as it is. Agree and continue You can withdraw any of these at any time, from your settings."
    ),
    "consent_ledger.html": (
        "Your data What you agreed to Every change is kept, so this reads as a history rather than a current state. Process my tradebook to produce my own record Currently granted. Withdraw this and stop using Scope Use my tradebook to check and calibrate the engine Not granted. Your ledger When Purpose Decision Version 08 Sep 2026 diagnosis granted 0-draft"
    ),
    "eligibility.html": (
        "Eligibility What we can check Your 1,240 trades across 8 trading days, against the 19 checks in our research library. 1 have enough to work with. 1 need more history than you have given us so far, 1 are waiting on something that is not your trades at all, and 1 we cannot judge from this page. The minimums below come from our pre-registered framework, version 0.3, which is still a draft — the thresholds are written down but not yet fixed. When they are fixed, this page says so and the numbers stop moving. Enough to work with Check What it needs What you have T01 50 round trips 62 trips Not enough history yet Check Why not T02 needs 200, has 40 Waiting on something that is not your trades Check What is missing T03 price series We cannot tell from here Check Why we cannot say T04 by session These need the trades sorted into groups this page does not build — by session, or by the cells of a map. Not knowing is not the same as not having enough, and it is not the same as having it. What this page is not A check with enough to work with has not been run, and a check without enough has found nothing — there is nothing yet to find either way. None of this says anything about how you trade. It says what your file can and cannot support. The checks are named by their identifiers here. They belong to the research library, and naming them in our own words before they have been run would be telling you what they would say. Go to your record — counted from your own trades, and separate from all of this."
    ),
    "eligibility.html#none": (
        "Eligibility What we can check Your 40 trades across 8 trading days, against the 19 checks in our research library. None of them has enough to work with yet. 1 need more history than you have given us so far, 1 are waiting on something that is not your trades at all. The minimums below come from our pre-registered framework, version 0.3, fixed before we looked at anyone's trades. Enough to work with None of them, on this history. Not enough history yet Check Why not T02 needs 200, has 40 Waiting on something that is not your trades Check What is missing T03 price series What this page is not A check with enough to work with has not been run, and a check without enough has found nothing — there is nothing yet to find either way. None of this says anything about how you trade. It says what your file can and cannot support. The checks are named by their identifiers here. They belong to the research library, and naming them in our own words before they have been run would be telling you what they would say. Go to your record — counted from your own trades, and separate from all of this."
    ),
    "eligibility_unreadable.html": (
        "Eligibility We cannot say yet Before we tell you which checks your history can support, we have to read the list of checks and the minimum each one needs. We could not do that just now, so rather than show you a number we cannot stand behind, we are showing you nothing. This is ours to fix, not yours. Your file and everything built from it are untouched. Your record is counted from your own trades and does not depend on any of this."
    ),
}


def render(case: str) -> str:
    name = case.split("#")[0]
    return template_env().get_template(name).render(title="T", csrf_token="x", **CONTEXT[case])


def words(html: str) -> str:
    """What the page says in its main column, as read aloud: decoration left out."""
    main = html.split("<main", 1)[1].split("</main>", 1)[0].split(">", 1)[1]
    main = re.sub(r'<span[^>]*aria-hidden="true"[^>]*>[^<]*</span>', " ", main)
    return " ".join(re.sub(r"<[^>]+>", " ", main).split())


@pytest.mark.parametrize("name", sorted({c.split("#")[0] for c in CONTEXT}))
def test_the_page_stands_on_the_layout(name):
    source = (TEMPLATES / name).read_text()
    assert '{% extends "layout.html" %}' in source and "base.html" not in source


@pytest.mark.parametrize("case", list(CONTEXT))
def test_it_says_what_it_said_before(case):
    assert words(render(case)) == SAID[case]


def test_consent_reads_its_promises_from_the_versioned_text():
    page = render("consent.html")
    for promise in (TEXT.what_we_store, TEXT.how_long, TEXT.who_can_access,
                    TEXT.what_deletion_covers, TEXT.what_deletion_cannot_undo):
        assert f'<p class="body">{promise}</p>' in page.replace("&#39;", "'")


def test_consent_keeps_each_purposes_field_and_ticks_only_the_required():
    page = render("consent.html")
    for purpose in TEXT.purposes:
        box = page.split(f'name="{purpose.key}" value="yes"', 1)[1].split(">", 1)[0]
        assert ("checked" in box) is bool(purpose.required), purpose.key
    assert '<button class="btn btn--primary btn--block" type="submit">Agree and continue' in page
    assert "I don" not in page  # the kit's "I don't agree" waits for D9


def test_the_ledger_withdraws_through_the_apps_route_on_the_account_tab():
    page = render("consent_ledger.html")
    assert page.count('<form method="post" action="/settings/consent/withdraw">') == 1
    assert f'<input type="hidden" name="purpose" value="{TEXT.purposes[0].key}">' in page
    assert 'href="/account" aria-current="page"' in page


def test_what_we_can_check_is_the_kits_tables():
    page = render("eligibility.html")
    assert page.count('<section class="import__section">') == 5
    assert '<span class="num">1,240</span> trades' in page
    assert '<a class="link import__next" href="/mirror">' in page
