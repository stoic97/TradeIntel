"""The migration chain read from the files on disk: what is wrong with it, if anything.

Used by tests/unit/repo/test_migration_heads.py, on main's own files and on scratch ones.
"""
import re
from pathlib import Path


def ids(path: Path) -> tuple[str, str | None]:
    """A migration file's (revision, down_revision), read from inside the file."""
    text = path.read_text(encoding="utf-8")
    rev = re.search(r"^revision = ['\"]([^'\"]+)['\"]", text, re.MULTILINE)
    down = re.search(r"^down_revision = (?:['\"]([^'\"]+)['\"]|None)", text, re.MULTILINE)
    assert rev and down, f"{path.name} names no revision or down_revision"
    return rev.group(1), down.group(1)


def chain_problems(versions: Path) -> list[str]:
    """Every way the files in `versions` fail to make one straight chain.

    One straight chain means: each revision id is used once and names its file; exactly one file
    has no parent; every parent is a revision some file holds; and no two files revise the same
    parent. Two files on one parent are two heads, which is also what a migration whose parent is
    behind the head looks like once the chain has moved past that parent.
    """
    problems: list[str] = []
    files: dict[str, str] = {}
    parent: dict[str, str | None] = {}
    for path in sorted(versions.glob("[0-9]*.py")):
        rev, down = ids(path)
        if rev in files:
            problems.append(f"revision {rev} is in both {files[rev]} and {path.name}")
            continue
        if not path.name.startswith(f"{rev}_"):
            problems.append(f"{path.name} says revision {rev} inside")
        files[rev] = path.name
        parent[rev] = down
    roots = [r for r, d in parent.items() if d is None]
    if len(roots) != 1:
        problems.append(f"{len(roots)} migrations have no parent: {sorted(roots)}")
    for rev, down in parent.items():
        if down is not None and down not in files:
            problems.append(f"{files[rev]} revises {down}, which no file holds")
    children: dict[str, list[str]] = {}
    for rev, down in parent.items():
        if down is not None:
            children.setdefault(down, []).append(rev)
    for down, kids in sorted(children.items()):
        if len(kids) > 1:
            names = ", ".join(files[k] for k in sorted(kids))
            problems.append(f"two heads: {names} all revise {down}; the later one is behind the head")
    heads = [r for r in parent if r not in children]
    if len(heads) != 1 and not any(p.startswith("two heads") for p in problems):
        problems.append(f"{len(heads)} heads: {sorted(heads)}")
    return problems
