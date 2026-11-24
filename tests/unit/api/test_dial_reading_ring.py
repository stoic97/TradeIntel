"""TICKET-1037: the dial's ring says where the trader is in his report, and nothing else.

The bezel's ticks measured nothing. With the reading passed in, the ring is one segment per
wedge: not opened yet, opened, or the one to read next. "Opened" is recorded on the server when
a fact page is served (no script), per upload, so a new upload starts unread. A chapter's
centre says how many of its facts he has read; the hub's centre keeps his result.

A view that passes no reading is drawn exactly as before, so the kit's recorded cases
(tests/fixtures/scope_geometry/cases.json) still hold byte for byte.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from sqlalchemy import inspect, select

from services.production.api import scope_geometry as G
from services.production.api import scope_map as S
from tests.unit.api import figure_pages as P

ROOT = Path(__file__).resolve().parents[3]
KIT_JS = ROOT / "docs/design/scope-kit/static/js/scope-geometry.js"


def _view(progress=None, label=None, read_line=None):
    items = [{"name": n, "figure": "3 trades", "href": "/x"} for n in ("One", "Two", "Three")]
    view = {"kind": "chapter", "items": items, "centre": {"name": "Your patterns", "scopeHref": "/s"}}
    if progress is not None:
        view["progress"] = progress
        view["progressLabel"] = label
    if read_line is not None:
        view["centre"]["readLine"] = read_line
    return view


def _svg(view, size="phone"):
    return G.render_dial_svg(G.build_dial(view, size, {}))


def segments(svg: str) -> list[str]:
    return re.findall(r'class="scope__progress-seg scope__progress-seg--([a-z]+)"', svg)


# ---------- the geometry ----------

def test_the_ring_replaces_the_ticks_when_the_reading_is_given():
    svg = _svg(_view(["opened", "current", "unread"], "1 of 3 facts read"))
    assert "scope__tick" not in svg
    assert segments(svg) == ["opened", "current", "unread"]
    assert 'aria-label="The Scope inside this chapter. 1 of 3 facts read."' in svg


def test_a_view_with_no_reading_is_drawn_as_before():
    svg = _svg(_view())
    assert "scope__tick--minor" in svg
    assert segments(svg) == []


def test_the_ring_replaces_the_opened_dots_and_the_top_arc():
    view = _view(["opened", "unread", "unread"], "1 of 3 facts read")
    view["items"][0]["opened"] = True
    svg = _svg(view)
    assert "scope__opened" not in svg
    assert "scope__arc" not in svg


def test_a_chapter_centre_says_how_many_facts_are_read():
    svg = _svg(_view(["opened", "current", "unread"], "1 of 3 facts read", "1 of 3 facts read"))
    assert re.search(r'class="scope__centre-read"[^>]*><tspan[^>]*>1 of 3 facts read</tspan>', svg)


def test_the_kit_draws_the_same_ring():
    js = KIT_JS.read_text(encoding="utf-8")
    for needle in ("scope__progress-seg scope__progress-seg--", "view.progress", "scope__centre-read",
                   "progressLabel"):
        assert needle in js, needle


def test_the_css_styles_each_state():
    for css in (ROOT / "services/production/api/static/css/components.css",
                ROOT / "docs/design/scope-kit/static/css/components.css"):
        text = css.read_text(encoding="utf-8")
        for state in ("unread", "opened", "current"):
            assert f".scope__progress-seg--{state}" in text
        assert ".scope__centre-read" in text


# ---------- the record ----------

def test_the_fact_read_table_is_migrated():
    from services.production.db.session import make_engine, run_migrations
    engine = make_engine("sqlite:///:memory:")
    run_migrations(engine)
    cols = {c["name"] for c in inspect(engine).get_columns("fact_read")}
    assert {"trader_id", "import_id", "fact_key", "period", "book", "opened_at"} <= cols
    migration = ROOT / "migrations/versions/0020_fact_reads.py"
    # It chains on the migration before it, main's head when it merges (the one-head rule);
    # the number moves with main, so the test reads it instead of pinning it.
    before = sorted(p.name[:4] for p in migration.parent.glob("[0-9]*.py") if p.name[:4] < "0020")[-1]
    assert f"down_revision = '{before}'" in migration.read_text(encoding="utf-8")


@pytest.fixture()
def reader():
    from fastapi.testclient import TestClient

    from services.production.api.app import create_app
    app = create_app()
    client = TestClient(app)
    P._sign_up(client, app.state.engine, "visitor")
    P._consent(client)
    client.post("/upload/demo", data={"csrf_token": P._token(client, "/upload")},
                follow_redirects=False)
    return app, client


def _first_dial(html: str) -> str:
    return re.search(r'<svg class="scope__svg".*?</svg>', html, flags=re.DOTALL).group(0)


def test_opening_a_fact_page_marks_its_segment(reader):
    _app, client = reader
    chapter = S.chapter(2)
    keys = [f.key for f in chapter.facts]
    before = _first_dial(client.get("/mirror/chapter/2").text)
    assert "opened" not in segments(before)
    assert f"0 of {len(keys)} read" in before

    assert client.get(f"/mirror/fact/{keys[0]}").status_code == 200
    after = _first_dial(client.get("/mirror/chapter/2").text)
    assert segments(after)[0] == "opened"
    assert segments(after)[1] == "current"  # the one to read next
    assert f"1 of {len(keys)} read" in after


def test_the_hub_marks_a_chapter_once_every_fact_in_it_is_open(reader):
    _app, client = reader
    hub = _first_dial(client.get("/mirror").text)
    assert "scope__tick" not in hub
    assert segments(hub) and "opened" not in segments(hub)
    chapter = S.chapter(3)
    for f in chapter.facts:
        client.get(f"/mirror/fact/{f.key}")
    states = segments(_first_dial(client.get("/mirror").text))
    order = [c.number for c in S.CHAPTERS]
    assert states[order.index(3)] == "opened"
    assert "scope__opened" not in client.get("/mirror").text  # the dots are gone


def test_a_new_upload_starts_unread():
    """A second upload is a new import; what he opened in the first is not carried over."""
    from fastapi.testclient import TestClient

    from services.production.api.app import create_app
    from services.production.db import models as m
    from services.production.db.session import make_session
    app = create_app()
    client = TestClient(app)
    P._sign_up(client, app.state.engine, "reader")
    P._consent(client)
    P._upload(client, P.CLEAN)
    key = S.chapter(2).facts[0].key
    client.get(f"/mirror/fact/{key}")
    assert "opened" in segments(_first_dial(client.get("/mirror/chapter/2").text))
    again = P.CLEAN.read_bytes() + b"\n"  # the same trades, a new file: a new upload
    client.post("/upload", files={"file": (P.CLEAN.name, again, "text/csv")},
                data={"csrf_token": P._token(client, "/upload")}, follow_redirects=False)
    with make_session(app.state.engine) as sess:
        assert len(sess.scalars(select(m.Import.id)).all()) == 2
    assert "opened" not in segments(_first_dial(client.get("/mirror/chapter/2").text))


def test_a_fact_page_writes_one_row_per_upload(reader):
    from services.production.db import models as m
    from services.production.db.session import make_session
    app, client = reader
    key = S.chapter(1).facts[0].key
    client.get(f"/mirror/fact/{key}")
    client.get(f"/mirror/fact/{key}")
    with make_session(app.state.engine) as sess:
        rows = sess.scalars(select(m.FactRead).where(m.FactRead.fact_key == key)).all()
    assert len(rows) == 1
    assert rows[0].period == "all"


def test_the_sample_leaves_nothing_behind():
    from fastapi.testclient import TestClient

    from services.production.api.app import create_app
    from services.production.db import models as m
    from services.production.db.session import make_session
    app = create_app()
    client = TestClient(app)
    key = S.chapter(1).facts[0].key
    client.get(f"/sample/fact/{key}")
    with make_session(app.state.engine) as sess:
        assert sess.scalars(select(m.FactRead.id)).first() is None


def test_deletion_takes_his_reading():
    from services.production.accounts import deletion
    from services.production.db import models as m
    src = Path(deletion.__file__).read_text(encoding="utf-8")
    assert src.count("m.FactRead") >= 2  # deleted, and checked for in nothing_remains
    assert m.FactRead.__tablename__ == "fact_read"
