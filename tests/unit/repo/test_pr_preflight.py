"""TICKET-1043: the pre-flight a PR passes before it is raised.

``scripts/pr_preflight.py`` merges today's main into the branch in a throwaway worktree and stops
on a conflict, naming the files; lists every assertion of the RED commit that a later commit
changed; and counts, per test file, the tests that read a rendered page. Each check is run here on
a made-up git history built in a temporary folder. No network, no real repository.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

PATH = Path("scripts/pr_preflight.py")


def pf():
    """The script, loaded as a module (it lives outside the packages)."""
    assert PATH.exists(), "no scripts/pr_preflight.py"
    spec = importlib.util.spec_from_file_location("pr_preflight", PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["pr_preflight"] = module
    spec.loader.exec_module(module)
    return module


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t",
                           "-c", "commit.gpgsign=false", *args],
                          check=True, capture_output=True, text=True).stdout.strip()


def commit(repo: Path, files: dict[str, str], message: str) -> str:
    for name, text in files.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(text, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture()
def repo(tmp_path):
    root = tmp_path / "r"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    commit(root, {"app.py": "A = 1\n", "tests/test_a.py": "def test_a():\n    assert 1\n"}, "start")
    git(root, "checkout", "-q", "-b", "work")
    return root


RED = '''def test_the_page_says_it(client):
    page = client.get("/numbers").text
    assert "five worst days" not in page
    assert "Those 2 days came to" in page


def test_the_view_says_it():
    view = build()
    assert view["count"] == 2
'''


# ---------- 3. RED left as written ----------

def test_an_unchanged_red_lists_nothing(repo):
    red = commit(repo, {"tests/test_b.py": RED}, "RED")
    head = commit(repo, {"app.py": "A = 2\n"}, "GREEN")
    assert pf().red_changes(str(repo), red, head) == {"tests/test_b.py": []}


def test_a_red_assertion_rewritten_later_is_listed(repo):
    red = commit(repo, {"tests/test_b.py": RED}, "RED")
    head = commit(repo, {"tests/test_b.py": RED.replace("Those 2 days came to", "Your 2 worst days:")},
                  "GREEN")
    assert pf().red_changes(str(repo), red, head) == {
        "tests/test_b.py": ['assert "Those 2 days came to" in page']}


def test_an_assertion_added_after_red_is_not_a_change(repo):
    red = commit(repo, {"tests/test_b.py": RED}, "RED")
    head = commit(repo, {"tests/test_b.py": RED + "    assert view['net'] == 0\n"}, "more")
    assert pf().red_changes(str(repo), red, head) == {"tests/test_b.py": []}


# ---------- 4. tests that read a rendered page ----------

def test_a_test_through_a_route_counts_as_reading_the_page():
    assert pf().page_tests(RED) == (1, 2)


# ---------- 1. today's main, merged ----------

def test_a_branch_that_merges_cleanly_passes(repo):
    commit(repo, {"app.py": "A = 2\n"}, "on the branch")
    git(repo, "checkout", "-q", "main")
    commit(repo, {"other.py": "B = 1\n"}, "main moved")
    git(repo, "checkout", "-q", "work")
    ok, files, tree = pf().merged_with(str(repo), "work", base="main")
    assert ok and files == [] and tree
    assert git(repo, "rev-parse", "HEAD") == git(repo, "rev-parse", "work")  # the branch is untouched
    assert len(git(repo, "worktree", "list").splitlines()) == 1  # the throwaway worktree is gone


def test_a_conflict_with_main_names_the_file_and_stops(repo):
    commit(repo, {"app.py": "A = 2\n"}, "on the branch")
    git(repo, "checkout", "-q", "main")
    commit(repo, {"app.py": "A = 3\n"}, "main moved the same line")
    git(repo, "checkout", "-q", "work")
    ok, files, _ = pf().merged_with(str(repo), "work", base="main")
    assert not ok and files == ["app.py"]
    assert len(git(repo, "worktree", "list").splitlines()) == 1
