"""Which code is running: the tag when a tag is checked out, the short sha otherwise.

Production deploys only tags (the release train, docs/runbooks/deploy.md), so on production
this reads `v2026.11.14`, and a sha there means a deploy that skipped the train. A commit
after a tag reads as its sha, not as `v2026.11.14-1-g...`: staging runs `main`, and "one
commit past the last train" is not a version anyone deployed.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

UNKNOWN = "unknown"


def _git(where: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=where, capture_output=True, text=True, check=True
    ).stdout.strip()


def describe(where: Path, dirty: bool = False) -> str:
    """The tag on HEAD, else HEAD's short sha; `-dirty` appended on request when the tree
    has uncommitted changes. 'unknown' when there is no repository or no git."""
    try:
        try:
            name = _git(where, "describe", "--tags", "--exact-match", "HEAD")
        except subprocess.CalledProcessError:
            name = _git(where, "rev-parse", "--short", "HEAD")
        if not name:
            return UNKNOWN
        if dirty and _git(where, "status", "--porcelain"):
            return f"{name}-dirty"
        return name
    except (subprocess.CalledProcessError, OSError):  # no repository, no git
        return UNKNOWN
