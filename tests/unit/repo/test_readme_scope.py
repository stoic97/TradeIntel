"""TICKET-932: the README describes Scope and covers the repository as it stands.

Every check reads the disk, so a folder or a script added later without its README row
turns this red, and a row left behind for a script that is gone turns it red too.
"""

from __future__ import annotations

import hashlib
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
README = ROOT / "README.md"

# The four rules are kept word for word (TICKET-932): sha256 of rules_block() at 932's base.
RULES_SHA256 = "71ddcd5ddc2b50d00a39611a485e7b336400234e161e250aeb535d8194dcf958"

PYPROJECT_DESCRIPTION = "PlusEV Scope \u2014 trade-level diagnosis app and research engine"
TOP_LEVEL = ("migrations/", "deploy/", "docs/", "data/", "scripts/", "tests/")
RUN_STEPS = ("uv sync", "make .dev-env", "make run", "make test")


def readme() -> str:
    return README.read_text(encoding="utf-8")


def section(text: str, heading: str) -> str:
    """The body under '## heading', up to the next '## ' heading or the end."""
    out: list[str] = []
    inside = False
    for line in text.replace("\r\n", "\n").split("\n"):
        if line.startswith("## "):
            if inside:
                break
            inside = line[3:].strip() == heading
            continue
        if inside:
            out.append(line)
    return "\n".join(out)


def rules_block(text: str) -> str:
    body = section(text, "Rules")
    return "\n".join(line.rstrip() for line in body.split("\n")).strip()


def _has_files(p: Path) -> bool:
    return any(f.is_file() and "__pycache__" not in f.parts for f in p.rglob("*"))


def subfolders(rel: str) -> list[str]:
    base = ROOT / rel
    return sorted(
        p.name
        for p in base.iterdir()
        if p.is_dir() and not p.name.startswith(("_", ".")) and _has_files(p)
    )


def script_rows() -> dict[str, list[str]]:
    rows: dict[str, list[str]] = {}
    for line in section(readme(), "Scripts").split("\n"):
        m = re.match(r"\|\s*`([^`]+)`\s*\|", line.strip())
        if m:
            rows[m.group(1)] = [c.strip() for c in line.strip().strip("|").split("|")]
    return rows


def test_the_title_names_scope() -> None:
    title = readme().lstrip().split("\n", 1)[0]
    assert title.startswith("# ") and "Scope" in title, title


def test_run_it_locally_lists_the_steps() -> None:
    body = section(readme(), "Run it locally")
    missing = [s for s in RUN_STEPS if s not in body]
    assert not missing, f"'## Run it locally' does not say: {missing}"


def test_every_services_folder_has_a_layout_row() -> None:
    layout = section(readme(), "Layout")
    missing = [
        f"services/{side}/{name}/"
        for side in ("production", "research", "shared")
        for name in subfolders(f"services/{side}")
        if f"`services/{side}/{name}/`" not in layout
    ]
    assert not missing, f"layout table has no row for: {missing}"


def test_the_top_level_folders_have_a_layout_row() -> None:
    layout = section(readme(), "Layout")
    missing = [d for d in TOP_LEVEL if f"`{d}`" not in layout]
    assert not missing, f"layout table has no row for: {missing}"


def test_every_script_has_a_full_row_and_no_row_is_stale() -> None:
    rows = script_rows()
    scripts = sorted(
        p.name for p in (ROOT / "scripts").iterdir()
        if p.is_file() and not p.name.startswith(".")
    )
    missing = [s for s in scripts if s not in rows]
    assert not missing, f"'## Scripts' has no row for: {missing}"
    stale = [r for r in rows if r not in scripts]
    assert not stale, f"'## Scripts' has rows for scripts that are gone: {stale}"
    thin = [s for s in scripts if len(rows[s]) < 4 or not all(rows[s])]
    assert not thin, f"rows need purpose, when it is used, and still in use: {thin}"


def test_tradedna_only_in_one_formerly_line() -> None:
    hits = [ln for ln in readme().split("\n") if "tradedna" in ln.lower().replace(" ", "")]
    assert len(hits) == 1 and "formerly" in hits[0].lower(), hits


def test_pyproject_describes_scope_and_keeps_its_name() -> None:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    project = tomllib.loads(text)["project"]
    assert project["description"] == PYPROJECT_DESCRIPTION
    assert project["name"] == "tradeintel"


def test_the_four_rules_are_kept_word_for_word() -> None:
    digest = hashlib.sha256(rules_block(readme()).encode("utf-8")).hexdigest()
    assert digest == RULES_SHA256, "README '## Rules' changed; TICKET-932 keeps them word for word"


def test_the_readme_points_at_the_docs_index() -> None:
    assert "docs/README.md" in section(readme(), "Where the docs live")