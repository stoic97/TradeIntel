"""The rupee sign is drawn in the app's own fonts, not a system fallback (TR-013).

The self-hosted files were the latin subset only, and the latin subset has no glyph
for ₹ (U+20B9): it is in latin-ext. With one @font-face and no unicode-range, the
browser uses the latin file for every character, finds no ₹ in it and falls back to
a system font, so every rupee figure on the Scope would sit in a different face from
the digits beside it.

The fix is a second face per family and weight, serving the latin-ext file under a
unicode-range that names U+20B9. These tests read every stylesheet the app serves,
so they keep holding when the design kit's stylesheets replace scope.css.

What they cannot see is the glyph inside the file. That was measured when the files
were added (the commit that added them says how), and handoff section 12 checks it
again in a browser on the server.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

STATIC = Path("services/production/api/static")
RUPEE = 0x20B9

# Every face the app's type rules use (handoff section 7): Plex Sans for headings and
# UI, Plex Mono for every figure, Source Serif 4 for the Mirror's sentences.
FACES = [
    ("IBM Plex Sans", "400 600"),
    ("IBM Plex Mono", "400"),
    ("IBM Plex Mono", "500"),
    ("IBM Plex Mono", "600"),  # the kit sets slice numbers and the centre label in it
    ("Source Serif 4", "400 600"),
]

FONT_FACE = re.compile(r"@font-face\s*\{(.*?)\}", re.DOTALL)


def font_faces(css: str) -> list[dict]:
    """Each @font-face as its family, weight, file and unicode ranges."""
    faces = []
    for body in FONT_FACE.findall(css):
        def prop(name, body=body):
            m = re.search(rf"{name}\s*:\s*([^;]+);", body)
            return m.group(1).strip() if m else None
        src = prop("src") or ""
        url = re.search(r"url\(\s*[\"']?([^\"')]+)", src)
        faces.append({
            "family": (prop("font-family") or "").strip("\"'"),
            "weight": prop("font-weight"),
            "url": url.group(1) if url else None,
            "ranges": ranges(prop("unicode-range")),
        })
    return faces


def ranges(value: str | None) -> list[tuple[int, int]]:
    """'U+0100-02BA, U+20B9' as [(0x100, 0x2BA), (0x20B9, 0x20B9)]; none if absent."""
    if not value:
        return []
    out = []
    for part in value.split(","):
        lo, _, hi = part.strip().removeprefix("U+").removeprefix("u+").partition("-")
        out.append((int(lo, 16), int(hi or lo, 16)))
    return out


def names(ranges_: list[tuple[int, int]], codepoint: int) -> bool:
    return any(lo <= codepoint <= hi for lo, hi in ranges_)


def served_faces() -> list[dict]:
    return [f for css in sorted(STATIC.rglob("*.css")) for f in font_faces(css.read_text())]


def test_a_unicode_range_is_read_as_its_code_points():
    assert ranges("U+0100-02BA, U+20B9") == [(0x100, 0x2BA), (0x20B9, 0x20B9)]
    assert names(ranges("U+0100-02BA, U+20AD-20C0"), RUPEE)
    assert not names(ranges("U+0000-00FF, U+2000-206F"), RUPEE)
    assert ranges(None) == []


def test_a_face_without_a_unicode_range_names_no_character():
    """CSS reads a missing range as every character, which is exactly the fallback
    trap: the browser picks the latin file for ₹ and it has no glyph. So only a face
    that names U+20B9 counts as serving it."""
    face = font_faces('@font-face { font-family: "X"; src: url("/static/fonts/x.woff2"); }')[0]
    assert not names(face["ranges"], RUPEE)


@pytest.mark.parametrize("family,weight", FACES)
def test_the_rupee_sign_has_a_face_of_its_own_in_every_font_the_app_uses(family, weight):
    serving = [f for f in served_faces()
               if f["family"] == family and f["weight"] == weight
               and names(f["ranges"], RUPEE)]
    assert serving, f"no {family} {weight} face names U+20B9"
    for face in serving:
        assert face["url"].startswith("/static/fonts/"), face["url"]
        assert (STATIC / face["url"].removeprefix("/static/")).is_file(), face["url"]
