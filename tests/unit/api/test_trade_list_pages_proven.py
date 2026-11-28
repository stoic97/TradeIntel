"""TICKET-1059: the trade lists proven on the rendered page, at their boundaries.

Follow-up to the trade lists' first gate. Paging is read at exactly 100, 101 and 200 trades; a
figure's link is followed into a list of more than a hundred and its pages add up to the
figure; "Oldest" on a list of several groups and the group headings are read off the page as
they ship today, until the founder's two rulings on the ticket say otherwise.

Every trade here is made up: a bought option that closes four minutes after it opened, a winner
sold at 11.00 for +100 and a loser at 9.50 for -50, before charges (no charges file).
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from tests.helpers.upload import upload

HEADER = Path("data/fixtures/duplicates/clean.csv").read_text(encoding="utf-8").splitlines()[0]
OPTION = "WIDGETOIL 19 NOV 5000 CALL,{side},INTRADAY,MCX,Commodity,100,{price},{value},Traded"
SHARE = "Widget ETF,{side},DELIVERY,NSE,Equity,10,{price},{value},Traded"
FIRST = datetime(2026, 8, 3, 9, 0, tzinfo=ZoneInfo("Asia/Kolkata"))  # the times are written as IST


def at(i: int) -> datetime:
    """The i-th trade opens on a weekday, forty a day, eight minutes apart."""
    day, slot = divmod(i, 40)
    return FIRST + timedelta(days=day + 2 * (day // 5), minutes=8 * slot)


def option(i: int, win: bool) -> list[str]:
    opened, closed = at(i), at(i) + timedelta(minutes=4)
    out = "11.00" if win else "9.50"
    return [
        f"{opened:%Y-%m-%d},{opened:%H:%M:%S}," + OPTION.format(side="BUY", price="10.00", value="1000.00"),
        f"{closed:%Y-%m-%d},{closed:%H:%M:%S}," + OPTION.format(
            side="SELL", price=out, value=f"{float(out) * 100:.2f}"),
    ]


def share(i: int) -> list[str]:
    opened, closed = at(i) + timedelta(minutes=1), at(i) + timedelta(minutes=5)
    return [
        f"{opened:%Y-%m-%d},{opened:%H:%M:%S}," + SHARE.format(side="BUY", price="100.00", value="1000.00"),
        f"{closed:%Y-%m-%d},{closed:%H:%M:%S}," + SHARE.format(side="SELL", price="101.00", value="1010.00"),
    ]


def send(client, rows: list[str]) -> None:
    assert upload(client, content=("\n".join([HEADER, *rows]) + "\n").encode()).status_code == 303


def options(client, n: int, loser_every: int = 0) -> None:
    send(client, [line for i in range(n) for line in option(i, not (loser_every and i % loser_every == 0))])


LIST = "/mirror/fact/risk/trades"


def rows_on(html: str) -> int:
    return html.count('<article class="trade">')


def follow(client, href: str) -> list[str]:
    """Every page of a list, from its first page by its "Show the next 100" link."""
    pages = []
    while href:
        html = client.get(href.replace("&amp;", "&")).text
        pages.append(html)
        nxt = re.search(r'<a class="btn btn--secondary btn--block" href="([^"]+)">Show the next 100</a>', html)
        href = (LIST + nxt.group(1)) if nxt else None
        assert len(pages) <= 10, "the pages never end"
    return pages


def results(html: str) -> list[int]:
    """Each row's result in whole rupees, as the row prints it."""
    out = []
    for sign, digits in re.findall(r'<span class="trade__net[^"]*">\s*([+−-]?)₹([\d,]+)', html):
        out.append((-1 if sign in "−-" and sign else 1) * int(digits.replace(",", "")))
    return out


# ---------- 4. paging at exactly 100, 101 and 200 ----------

def test_a_hundred_trades_are_one_page_with_no_pager(client, engine):
    options(client, 100)
    html = client.get(LIST).text
    assert rows_on(html) == 100
    assert "Show the next 100" not in html and "Show the previous 100" not in html
    assert 'class="trade-pager' not in html  # neither the range line nor the pager


def test_a_hundred_and_one_trades_are_two_pages_the_second_holding_one(client, engine):
    options(client, 101)
    first, second = follow(client, LIST)
    assert (rows_on(first), rows_on(second)) == (100, 1)
    text = re.sub(r"<[^>]+>", "", first)
    assert "Trades 1–100 of 101." in text
    assert "Trades 101–101 of 101." in re.sub(r"<[^>]+>", "", second)
    assert "Show the previous 100" in second and "Show the next 100" not in second


def test_two_hundred_trades_are_exactly_two_full_pages(client, engine):
    options(client, 200)
    pages = follow(client, LIST)
    assert [rows_on(p) for p in pages] == [100, 100]
    assert "Trades 101–200 of 200." in re.sub(r"<[^>]+>", "", pages[1])
    past = client.get(LIST + "?page=3").text  # a page past the end shows the last page
    assert rows_on(past) == 100 and "Trades 101–200 of 200." in re.sub(r"<[^>]+>", "", past)


# ---------- 3. a figure's link into a list of more than a hundred, its pages adding up ----------
# 150 trades, every fifth a loser: 30 losers, 120 winners of +100 each. Your numbers counts 120
# winners; their list runs over two pages (100 and 20) and its rows add up to +12,000.

def test_a_figures_link_opens_exactly_its_trades_across_pages(client, engine):
    options(client, 150, loser_every=5)
    numbers = client.get("/numbers").text
    href = f"{LIST}?result=winners"
    assert f'href="{href}"' in numbers
    pages = follow(client, href)
    assert [rows_on(p) for p in pages] == [100, 20]
    every = [r for p in pages for r in results(p)]
    assert len(every) == 120 and set(every) == {100}
    assert sum(every) == 12_000
    head = re.sub(r"<[^>]+>", "", re.search(r'<div class="trades__title">.*?</div>', pages[0], re.DOTALL).group(0))
    assert "120 trades" in head and "12,000" in head  # the heading counts the whole list, not a page


# ---------- 1, 2. "Oldest" on a list of several groups, and its headings, as shipped ----------
# Option, share, option, share ... opened in turn: the risk list has two groups. As shipped,
# "Oldest" (the default) keeps the groups and runs oldest first inside each; any other sort is
# one list. Which one "Oldest" should be is the founder's ruling on the ticket (line 1).

def test_oldest_on_a_list_of_two_groups_runs_oldest_first_within_each_group(client, engine):
    send(client, [line for i in range(6) for line in (option(i, True) if i % 2 == 0 else share(i))])
    html = client.get(LIST).text
    titles = [re.sub(r"<[^>]+>", "", t) for t in re.findall(r'<span class="trades__day">(.*?)</span>', html)]
    assert titles == ["Premium paid", "Stocks, ETFs and futures: no premium to measure against"]
    oldest = client.get(LIST + "?sort=oldest").text
    assert re.findall(r'<span class="trades__day">(.*?)</span>', oldest) == re.findall(
        r'<span class="trades__day">(.*?)</span>', html)  # "Oldest" is the default order
    for group in re.findall(r'<section class="trades__group">.*?</section>', html, re.DOTALL):
        times = re.findall(r'<div class="trade__row"><span>[^<]*</span><span>([^<]+)</span>', group)
        assert len(times) == 3 and times == sorted(times)
    newest = client.get(LIST + "?sort=newest").text
    assert re.findall(r'<span class="trades__day">(.*?)</span>', newest) == ["Newest first"]


def test_the_group_headings_read_as_shipped(client, engine):
    options(client, 10, loser_every=2)
    def heads(href):
        return re.findall(r'<span class="trades__day">(.*?)</span>', client.get(href).text)
    assert heads(LIST) == ["Premium paid"]
    assert heads(LIST + "?result=losers") == ["Losers"]
    assert heads(LIST + "?result=losers&sort=newest") == ["Losers · newest first"]
    assert heads(LIST + "?sort=biggest-loss") == ["Biggest loss first"]


# ---------- 5. what a position with several legs shows in the dense row ----------
# A bought 5000 call (10.00 -> 12.00, +200) and a sold 5100 call (4.00 -> 5.00, -100), opened
# and closed together: one position, +100. Written down as it ships: one row named by the
# underlying and its count of legs, then each leg's side, strike, result, quantity and prices
# under it, in the open; only a one-line trade puts its prices behind "Prices".

def test_a_position_of_two_legs_is_one_row_with_its_legs_under_it(client, engine):
    send(client, [
        "2026-08-03,10:00:00,WIDGETOIL 19 NOV 5000 CALL,BUY,INTRADAY,MCX,Commodity,100,10.00,1000.00,Traded",
        "2026-08-03,10:00:05,WIDGETOIL 19 NOV 5100 CALL,SELL,INTRADAY,MCX,Commodity,100,4.00,400.00,Traded",
        "2026-08-03,10:30:00,WIDGETOIL 19 NOV 5000 CALL,SELL,INTRADAY,MCX,Commodity,100,12.00,1200.00,Traded",
        "2026-08-03,10:30:05,WIDGETOIL 19 NOV 5100 CALL,BUY,INTRADAY,MCX,Commodity,100,5.00,500.00,Traded",
    ])
    html = client.get(LIST).text
    (row,) = re.findall(r'<article class="trade">.*?</article>', html, re.DOTALL)
    text = " ".join(re.sub(r"<[^>]+>", " ", row).split())
    assert text.startswith("WIDGETOIL · 2 legs 03 Aug 2026 10:00 10:30 30 min +₹100")
    assert "Bought 5000 CE +₹200 Qty 100 · 10.00 → 12.00" in text
    assert "Sold 5100 CE −₹100 Qty 100 · 4.00 → 5.00" in text
    assert '<details class="trade__more">' not in row
