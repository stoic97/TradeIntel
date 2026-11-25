# Who runs it: the PR's author, by hand, on the branch, before the PR is raised.
# When: before every PR, and again after each merge of main.
# Writes: nothing in the branch; a throwaway worktree, removed at the end.
"""The pre-flight a Scope PR passes before it is raised (TICKET-1043).

    uv run python scripts/pr_preflight.py <head> <red-sha> [--suite] [--repo PATH] [--base REF]

Read-only on the branch: the merge happens in a throwaway worktree that is removed at the end.

1. Today's main. Fetch, then merge ``origin/main`` into <head> in a throwaway worktree. A
   conflict stops it, naming the files. Then ``tests/unit/repo`` runs on the merged tree (the
   full suite with ``--suite``), and pytest's last line and the merged sha are printed for the
   PR body.
3. RED as written. Every ``assert`` line of each test file the RED commit touched must still be
   in that file at <head>. One that a later commit changed is listed, and the PR waits: if RED
   was wrong, that is said on the ticket first.
4. The page. For each test file the branch changed, how many tests read a rendered page (a route
   through the test client) against how many read only a view. The reviewer holds this against
   the gate lines that ask for the page.

It ends "OK to raise." or "STOP: no PR until the lines above are fixed." with exit 0 or 1.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

PAGE_READ = re.compile(r"""\b(client|demo|page_of\([^)]*\)|c)\.(get|post)\(|\bfact_page\(|\bchapter_page\(""")
"""A test reads the page when it goes through a route (the test client) or renders a page helper."""


def _git(repo: str, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    out = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, encoding="utf-8", check=False)
    if check and out.returncode:
        raise SystemExit(f"git {' '.join(args)} failed:\n{out.stderr}")
    return out


def _asserts(text: str) -> list[str]:
    return [" ".join(line.split()) for line in text.splitlines() if line.strip().startswith("assert ")]


def red_changes(repo: str, red: str, head: str) -> dict[str, list[str]]:
    """Each test file the RED commit touched, with the RED assertions no longer in it at head.

    An assertion added later is not a change; one rewritten or removed is."""
    touched = _git(repo, "show", "--name-only", "--format=", red).stdout.split()
    out: dict[str, list[str]] = {}
    for path in touched:
        if not (path.startswith("tests/") and path.endswith(".py")):
            continue
        before = _asserts(_git(repo, "show", f"{red}:{path}").stdout)
        now = _git(repo, "show", f"{head}:{path}", check=False)
        after = set(_asserts(now.stdout)) if now.returncode == 0 else set()
        out[path] = [a for a in before if a not in after]
    return out


def page_tests(text: str) -> tuple[int, int]:
    """(tests that read a rendered page, tests) in one test file's source."""
    parts = re.split(r"(?m)^def (test_\w+)", text)
    bodies = [parts[i + 1] for i in range(1, len(parts) - 1, 2)]
    return sum(1 for b in bodies if PAGE_READ.search(b)), len(bodies)


def merged_with(repo: str, head: str, base: str = "origin/main") -> tuple[bool, list[str], str]:
    """Merge ``base`` into ``head`` in a throwaway worktree: (merged cleanly, conflicting files,
    the worktree's path while it exists). The worktree is removed before returning; callers that
    need to run tests on the merged tree use :func:`on_merged`."""
    ok, files, tree = False, [], ""
    with on_merged(repo, head, base) as (merged, conflicts, path):
        ok, files, tree = merged, conflicts, path
    return ok, files, tree


class on_merged:
    """``with on_merged(repo, head, base) as (ok, conflicts, path):`` the merged tree at ``path``."""

    def __init__(self, repo: str, head: str, base: str = "origin/main"):
        self.repo, self.head, self.base = repo, head, base
        self.path = Path(tempfile.mkdtemp(prefix="preflight_"))

    def __enter__(self) -> tuple[bool, list[str], str]:
        _git(self.repo, "worktree", "add", "-q", "--detach", str(self.path), self.head)
        merge = subprocess.run(
            ["git", "-C", str(self.path), "-c", "user.name=preflight", "-c", "user.email=preflight@local",
             "merge", "-q", "--no-edit", self.base], capture_output=True, text=True, encoding="utf-8", check=False)
        if merge.returncode:
            conflicts = _git(str(self.path), "diff", "--name-only", "--diff-filter=U", check=False).stdout.split()
            return False, sorted(conflicts), str(self.path)
        return True, [], str(self.path)

    def __exit__(self, *exc) -> None:
        _git(self.repo, "worktree", "remove", "--force", str(self.path), check=False)
        _git(self.repo, "worktree", "prune", check=False)


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("head")
    ap.add_argument("red", help="the RED commit's sha")
    ap.add_argument("--suite", action="store_true", help="run the full suite on the merged tree")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--base", default="origin/main")
    a = ap.parse_args(argv)
    stop = False

    _git(a.repo, "fetch", "-q", "origin", check=False)
    behind = _git(a.repo, "rev-list", "--count", f"{a.head}..{a.base}").stdout.strip()
    print(f"[1] {a.head} is {behind} commit(s) behind {a.base}")
    with on_merged(a.repo, a.head, a.base) as (ok, conflicts, path):
        if not ok:
            print("    CONFLICT, no PR: " + ", ".join(conflicts))
            return 1
        sha = _git(path, "rev-parse", "--short", "HEAD").stdout.strip()
        target = ["tests"] if a.suite else ["tests/unit/repo"]
        run = subprocess.run([sys.executable, "-m", "pytest", "-p", "no:cacheprovider", *target],
                             cwd=path, capture_output=True, text=True, encoding="utf-8", check=False)
        last = ([line for line in run.stdout.splitlines() if line.strip()] or ["(no output)"])[-1]
        print(f"    merged tree {sha} · {' '.join(target)}: exit {run.returncode} · {last}")
        stop |= run.returncode != 0

    print(f"\n[3] RED {a.red[:8]}: its assertions at {a.head}")
    for path, gone in red_changes(a.repo, a.red, a.head).items():
        print(f"    {path}: {len(gone)} changed since RED")
        for line in gone:
            print(f"      - {line[:110]}")
        stop |= bool(gone)

    print("\n[4] tests that read a rendered page")
    # The branch's own test files: what it changed since main, merges of main left out. A head
    # already on main (a dry run on a merged ticket) has none of its own: read from its RED on.
    changed = _git(a.repo, "diff", "--name-only", f"{a.base}...{a.head}", "--", "tests").stdout.split() or         _git(a.repo, "diff", "--name-only", f"{a.red}^", a.head, "--", "tests").stdout.split()
    for path in changed:
        source = _git(a.repo, "show", f"{a.head}:{path}", check=False)
        if source.returncode == 0 and path.endswith(".py"):
            read, total = page_tests(source.stdout)
            print(f"    {path}: {read} of {total}")

    print("\nSTOP: no PR until the lines above are fixed." if stop else "\nOK to raise.")
    return 1 if stop else 0


if __name__ == "__main__":
    raise SystemExit(main())
