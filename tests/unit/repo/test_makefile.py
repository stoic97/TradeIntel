"""The Makefile is the manual (methodology: "types `make help`, and sees every command").

TICKET-929 (findings C2 and L6). `make test` is a deploy check (handoff 12, step 2), so
it has to mean the whole suite: with `-x` it stopped at the first failure, and every
test collected after it never ran, so "green" said nothing. And every target has to work
from a fresh clone without an activated venv, the way the docs run things (`uv run`).
"""

from __future__ import annotations

import re
from pathlib import Path

MAKEFILE = Path("Makefile").read_text(encoding="utf-8")
GITIGNORE = Path(".gitignore").read_text(encoding="utf-8").splitlines()

CACHES = (".pytest_cache", ".ruff_cache", ".mypy_cache", ".hypothesis")


def targets() -> dict[str, str]:
    """Each target and its recipe (the tab-indented lines under it)."""
    found: dict[str, str] = {}
    current = None
    for line in MAKEFILE.splitlines():
        head = re.match(r"^([a-zA-Z_.-]+):(?!=)", line)
        if head and head.group(1) != ".PHONY":
            current = head.group(1)
            found[current] = ""
        elif line.startswith("\t") and current:
            found[current] += line + "\n"
        elif line.strip() and not line.startswith("\t"):
            current = None
    return found


def help_regex() -> re.Pattern[str]:
    """The pattern the help target itself greps with, read from the Makefile."""
    recipe = targets()["help"]
    pattern = re.search(r"grep -E '([^']+)'", recipe).group(1).replace("$$", "$")
    return re.compile(pattern, re.MULTILINE)


def test_make_test_runs_the_whole_suite_and_test_fast_is_the_one_that_stops():
    assert re.search(r"\bpytest tests -q\b", targets()["test"])
    assert "-x" not in targets()["test"], "make test is a deploy check: it runs to the end"
    assert "-x" in targets()["test-fast"]


def test_make_help_lists_every_target():
    listed = {m.group(0).split(":", 1)[0] for m in help_regex().finditer(MAKEFILE)}
    assert listed == set(targets()), set(targets()) ^ listed


def test_every_command_target_is_phony():
    phony = set(re.search(r"^\.PHONY:(.*)$", MAKEFILE, re.MULTILINE).group(1).split())
    files = {".dev-env"}  # a real file the target writes, so it must not be phony
    assert phony == set(targets()) - files


def test_no_target_needs_an_activated_venv():
    """Every Python tool runs through uv, as the docs do, so a fresh clone just works."""
    bare = re.compile(r"(?<![\w-])(?<!uv run )(?<!\$\(UV\) )(pytest|ruff|python|uvicorn)\b")
    for name, recipe in targets().items():
        for line in recipe.splitlines():
            assert not bare.search(line), f"{name}: {line.strip()}"


def test_make_clean_removes_every_tool_cache():
    for cache in CACHES:
        assert cache in targets()["clean"], cache


def test_every_tool_cache_is_ignored_by_the_repo_not_only_by_the_tool():
    for cache in CACHES:
        assert f"{cache}/" in GITIGNORE, cache
