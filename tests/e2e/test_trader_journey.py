"""TICKET-968: a trader's journey, end to end. Sign in, upload a tradebook, read the Mirror.

The walk goes through the app and nothing else: one HTTP client against the whole app, with
its database file, its file store and its pipeline. It never opens the database and never
calls a helper that does. Every step is taken from the page before it: the form that page
offers is the form sent, the link it offers is the link followed. A page that stops offering
the next step fails here, even when the route behind it still answers.

The tradebook is the synthetic one the app ships as its demo file, sent through the ordinary
upload form. No figure is written down in this file. What is checked is that the rows counted
in the file are the rows the review and the Scope say were read, and that the Scope counts the
trades the review rebuilt.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

from fastapi.testclient import TestClient

from services.production.api.app import create_app

ROOT = Path(__file__).resolve().parents[2]
TRADEBOOK = ROOT / "data" / "fixtures" / "demo" / "scope_demo_tradebook.csv"
LOGIN_ID = "e2e-trader"
PASSWORD = "a-long-enough-password"
REDIRECTS = (301, 302, 303, 307, 308)
UNSEEN = ("script", "style", "svg")


class Page(HTMLParser):
    """One page as a trader meets it: where he is, its words, its links and its forms."""

    def __init__(self, html: str, status: int, at: str) -> None:
        super().__init__(convert_charrefs=True)
        self.status = status
        self.at = at
        self.anchors: list[dict[str, str]] = []
        self.forms: list[dict] = []
        self.dwell: list[str] = []
        self._words: list[str] = []
        self._open: list[dict[str, str]] = []
        self._form: dict | None = None
        self._unseen = 0
        self.feed(html)
        self.text = " ".join(" ".join(self._words).split())

    def handle_starttag(self, tag, attrs):
        a = {name: value or "" for name, value in attrs}
        if tag in UNSEEN:
            self._unseen += 1
        if a.get("data-dwell-line"):
            self.dwell.append(a["data-dwell-line"])
        if tag == "a":
            self._open.append({"href": a.get("href", ""), "rel": a.get("rel", ""), "text": ""})
        elif tag == "form":
            self._form = {"action": a.get("action", ""), "fields": {}, "buttons": []}
            self.forms.append(self._form)
        elif self._form is not None and tag == "input" and a.get("name"):
            kind = a.get("type", "text")
            ticked = kind not in ("checkbox", "radio") or "checked" in a
            if kind != "file" and ticked:
                self._form["fields"][a["name"]] = a.get("value", "")
        elif self._form is not None and tag == "button" and a.get("name"):
            self._form["buttons"].append((a["name"], a.get("value", "")))

    def handle_endtag(self, tag):
        if tag in UNSEEN and self._unseen:
            self._unseen -= 1
        elif tag == "form":
            self._form = None
        elif tag == "a" and self._open:
            anchor = self._open.pop()
            anchor["text"] = " ".join(anchor["text"].split())
            self.anchors.append(anchor)

    def handle_data(self, data):
        if self._unseen:
            return
        self._words.append(data)
        for anchor in self._open:
            anchor["text"] += data

    def links(self, pattern: str) -> list[str]:
        """Every address this page links to that matches, in page order, each once."""
        found = [a["href"] for a in self.anchors if re.search(pattern, a["href"])]
        return list(dict.fromkeys(found))

    def link(self, pattern: str) -> str:
        found = self.links(pattern)
        assert found, f"{self.at} offers no link matching {pattern}"
        return found[0]

    def link_saying(self, words: str) -> str:
        found = [a["href"] for a in self.anchors if a["text"].startswith(words)]
        assert found, f"{self.at} offers no link that says {words!r}"
        return found[0]

    def next_step(self) -> str:
        found = [a["href"] for a in self.anchors if "next" in a["rel"].split()]
        assert found, f"{self.at} offers no next step"
        return found[0]

    def form(self, action: str) -> dict:
        found = [form for form in self.forms if form["action"] == action]
        assert found, f"{self.at} offers no form that posts to {action}"
        return found[0]

    def figures(self, pattern: str) -> tuple[int, ...]:
        """The numbers a sentence on this page gives, as the page writes them."""
        found = re.search(pattern, self.text)
        assert found, f"{self.at} does not say /{pattern}/"
        return tuple(int(number.replace(",", "")) for number in found.groups())


class Trader:
    """One person at one browser. He opens addresses, follows links and sends forms."""

    def __init__(self) -> None:
        self.client = TestClient(create_app())

    def open(self, address: str) -> Page:
        return self._arrive(self.client.get(address.split("#")[0], follow_redirects=False))

    def follow(self, page: Page, pattern: str) -> Page:
        return self.open(page.link(pattern))

    def send(self, page: Page, action: str, files=None, **typed: str) -> Page:
        """Send the form the page offers, as it offers it, with what he types or attaches."""
        fields = {**page.form(action)["fields"], **typed}
        sent = self.client.post(action, data=fields, files=files, follow_redirects=False)
        return self._arrive(sent)

    def _arrive(self, response) -> Page:
        """Go where the app sends him, and return the page he ends on."""
        for _ in range(5):
            if response.status_code not in REDIRECTS:
                break
            response = self.client.get(response.headers["location"], follow_redirects=False)
        return Page(response.text, response.status_code, response.request.url.path)


def test_a_trader_signs_in_uploads_a_tradebook_and_reads_the_mirror():
    rows_sent = len(TRADEBOOK.read_text(encoding="utf-8").splitlines()) - 1
    assert rows_sent > 0, "the synthetic tradebook is empty"
    trader = Trader()

    # A stranger is shown the door, and is not shown a report.
    door = trader.open("/")
    assert (door.status, door.at) == (200, "/")
    assert trader.open("/mirror").at == "/login", "a signed-out visitor reached the report"

    # He answers the door's question and makes an account. He is asked to agree first.
    door = trader.follow(door, r"^/\?said=")
    asked = trader.send(door, "/signup", login_id=LOGIN_ID, password=PASSWORD)
    assert (asked.status, asked.at) == (200, "/consent"), (asked.status, asked.at)

    # The account is his. He signs out, and the report is closed to him again.
    account = trader.follow(asked, r"^/account$")
    assert account.status == 200 and LOGIN_ID in account.text, "the account page is not his"
    left = trader.send(account, "/logout")
    assert (left.status, left.at) == (200, "/")
    assert trader.open("/mirror").at == "/login", "signed out, and the report still opened"

    # Sign in. A wrong password is refused; his own lets him in, to the same question.
    sign_in = trader.open("/login")
    refused = trader.send(sign_in, "/login", login_id=LOGIN_ID, password=PASSWORD + "-not")
    assert (refused.status, refused.at) == (400, "/login"), (refused.status, refused.at)
    assert trader.open("/mirror").at == "/login", "a wrong password opened the report"
    sign_in = trader.open("/login")
    asked = trader.send(sign_in, "/login", login_id=LOGIN_ID, password=PASSWORD)
    assert (asked.status, asked.at) == (200, "/consent"), (asked.status, asked.at)

    # He agrees to what the page asks, as the page offers it, and uploads the tradebook.
    upload = trader.send(asked, "/consent")
    assert (upload.status, upload.at) == (200, "/upload"), (upload.status, upload.at)
    tradebook = {"file": ("tradebook.csv", TRADEBOOK.read_bytes(), "text/csv")}
    review = trader.send(upload, "/upload", files=tradebook)
    assert review.status == 200 and re.fullmatch(r"/imports/\d+", review.at), review.at

    # What we read: every row he sent, none set aside, and trades rebuilt from them.
    assert review.figures(r"Rows in the file ([\d,]+) rows?") == (rows_sent,)
    assert review.figures(r"Rows we could read ([\d,]+) rows?") == (rows_sent,)
    assert review.figures(r"Rows set aside ([\d,]+) rows?") == (0,)
    (trades,) = review.figures(r"Trades rebuilt ([\d,]+) trades?")
    assert trades > 0, "no trade was rebuilt from the tradebook"

    # On to his record: the question before it, the reveal, and the first page it shows.
    guess = trader.follow(review, r"^/guess$")
    assert (guess.status, guess.at) == (200, "/guess"), (guess.status, guess.at)
    answers = guess.form("/guess")["buttons"]
    assert answers, "the question offers no answer"
    reveal = trader.send(guess, "/guess", **dict(answers[:1]))
    assert (reveal.status, reveal.at) == (200, "/mirror/reveal"), (reveal.status, reveal.at)
    shown = trader.follow(reveal, r"^/mirror/fact/")
    assert shown.status == 200 and shown.dwell, f"{shown.at} is not a page of the report"

    # Home, and from Home the Scope. It counts the file he sent.
    home = trader.follow(shown, r"^/$")
    assert (home.status, home.at) == (200, "/")
    scope = trader.follow(home, r"^/mirror$")
    assert (scope.status, scope.at) == (200, "/mirror")
    assert scope.figures(r"([\d,]+) of ([\d,]+) rows read") == (rows_sent, rows_sent)
    assert scope.figures(r"rows read\W+([\d,]+) trades") == (trades,)

    # Every chapter the Scope offers opens.
    chapters = scope.links(r"^/mirror/chapter/\d+")
    assert chapters, "the Scope offers no chapter"
    for chapter in chapters:
        assert trader.open(chapter).status == 200, chapter

    # The report, from its first page to its last, by each page's own Next.
    page = trader.open(scope.link_saying("Continue"))
    first, pages = page.figures(r"([\d,]+) of ([\d,]+) All pages")
    assert first == 1, f"a new reader is sent to page {first}, not to the first"
    read: list[str] = []
    behind: list[str] = []
    for number in range(1, pages + 1):
        assert page.status == 200, (number, page.at, page.status)
        assert page.at not in read, f"Next led back to {page.at}"
        assert page.dwell, f"{page.at} has no dwell line"
        assert page.figures(r"([\d,]+) of ([\d,]+) All pages") == (number, pages), page.at
        read.append(page.at)
        behind += page.links(r"^/mirror/fact/[\w-]+/trades$")
        after = page.next_step()
        if number < pages:
            page = trader.open(after)
    assert len(read) == pages

    # After the last page, Next leaves the report for a page that opens.
    onward = trader.open(after)
    assert onward.status == 200, (after, onward.status)
    assert not onward.at.startswith("/mirror/fact/"), f"the report runs past its last page: {after}"

    # The trades behind a figure are one link away.
    assert behind, "no page of the report links to the trades behind it"
    assert trader.open(behind[0]).status == 200, behind[0]

    # He signs out, and the report is closed again.
    left = trader.send(trader.follow(onward, r"^/account$"), "/logout")
    assert (left.status, left.at) == (200, "/")
    assert trader.open("/mirror").at == "/login", "signed out, and the report still opened"
