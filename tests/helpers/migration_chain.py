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
    """Every way the files in `versions` fail to make one straight chain."""
    problems: list[str] = []
    seen: dict[str, str] = {}
    for path in sorted(versions.glob("[0-9]*.py")):
        rev, _ = ids(path)
        if rev in seen:
            problems.append(f"revision {rev} is in both {seen[rev]} and {path.name}")
        seen[rev] = path.name
    return problems
