"""What the finding bar's three levels say on the page (TICKET-909)."""

from __future__ import annotations

from services.production.api import scope_facts as SF
from services.production.mirror import metrics as mx
from services.shared.conditions import b2_shuffle as T
from tests.unit.api.test_scope_chapters import IMP, TRIPS, chapter_page, readable
from tests.unit.api.test_scope_facts import fact_page
from tests.unit.api.test_upload import client, engine  # noqa: F401

WATCHING = "Something showed up here, but it didn't clear the bar a finding has to clear. Upload more months to confirm."
CLOSED = "No difference we can stand behind."


def result(level: str) -> T.ShuffleResult:
    return T.ShuffleResult(40, 80, -500.0, 0.01, 0.2, (-1.0, 2.0), level, 18)


def test_too_few_trades_says_how_many_more_after_the_opening_sentence():
    check = mx.post_loss_check(mx.same_day_trips(TRIPS))
    assert check.level == T.NOT_ENOUGH
    need_c, need_o = T.MIN_CONDITION - check.n_condition, T.MIN_COMPARISON - check.n_comparison
    for page in (readable(fact_page("down")), readable(chapter_page(3))):
        assert CLOSED in page
        assert (f"There aren't enough trades yet to test it: it needs {need_c} more right after two "
                f"straight losses and {need_o} more of your other trades.") in page
        assert page.index(CLOSED) < page.index("There aren't enough trades yet")


def test_worth_watching_is_said_and_never_called_a_finding(monkeypatch):
    monkeypatch.setattr(mx, "post_loss_check", lambda trips: result(T.WORTH_WATCHING))
    monkeypatch.setattr(mx, "post_loss_sentence_may_show", lambda trips: False)
    for page in (readable(fact_page("down")), readable(chapter_page(3))):
        assert CLOSED in page and WATCHING in page
        assert "finding" not in page.lower().split(CLOSED.lower())[1].split("upload more")[0].replace(
            "the bar a finding has to clear", "")


def test_a_finding_needs_no_second_line(monkeypatch):
    monkeypatch.setattr(mx, "post_loss_check", lambda trips: result(T.FINDING))
    monkeypatch.setattr(mx, "post_loss_sentence_may_show", lambda trips: True)
    page = readable(fact_page("down"))
    assert WATCHING not in page and "There aren't enough trades yet" not in page
    assert "After two straight losses, your next trades averaged" in page


def test_the_facts_carry_the_level_from_the_one_test():
    figs = SF.facts(SF.record_context(TRIPS), IMP)
    assert figs["down"]["post_loss_level"] == T.NOT_ENOUGH
    assert figs["down"]["post_loss_needs"]["condition"] > 0


def test_scope_home_says_how_many_checks_the_bar_corrects_for(client):  # noqa: F811
    from tests.unit.api.test_read_again import send, words
    send(client)
    said = words(client.get("/mirror").text)
    assert ("Every finding here clears a bar corrected for every check we run on your trades: "
            "today 1 of the 18 on our fixed list.") in said
