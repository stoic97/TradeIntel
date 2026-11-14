"""`make hash-check` before and after the lock (TICKET-937, methodology §4).

Before: the target ran `shasum -c` on a `.sha256` that does not exist until the framework is
locked, so it failed on every run and nobody read it. Proposed to the founder, and pinned here:
before the lock it says so and passes; after it, a changed file fails, and so does a lock that
cannot be checked.
"""

from __future__ import annotations

import hashlib
import importlib.util
import re
import sys
from pathlib import Path

import pytest

SCRIPT = Path("scripts/hash_check.py")
DRAFT = "framework:\n  id: tradedna_framework\n  status: draft            # draft -> locked at kickoff\n"
LOCKED = DRAFT.replace("status: draft", "status: locked")


def hash_check():
    spec = importlib.util.spec_from_file_location("hash_check", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def framework(tmp_path):
    return tmp_path / "framework_v1.yaml"


def lock(framework: Path) -> None:
    digest = hashlib.sha256(framework.read_bytes()).hexdigest()
    framework.with_name(framework.name + ".sha256").write_text(f"{digest}  {framework}\n")


def test_before_the_lock_it_says_so_and_passes(framework):
    framework.write_text(DRAFT)
    code, message = hash_check().check(framework)
    assert (code, message.startswith("not locked yet")) == (0, True)


def test_after_the_lock_an_unchanged_file_passes(framework):
    framework.write_text(LOCKED)
    lock(framework)
    assert hash_check().check(framework)[0] == 0


def test_after_the_lock_a_changed_file_fails(framework):
    framework.write_text(LOCKED)
    lock(framework)
    framework.write_text(LOCKED + "  theta_min: 0.30\n")
    code, message = hash_check().check(framework)
    assert code == 1 and "changed since the lock" in message


def test_a_lock_nobody_can_check_fails(framework):
    framework.write_text(LOCKED)
    code, message = hash_check().check(framework)
    assert code == 1 and "does not exist" in message


def test_a_hash_written_before_the_lock_fails(framework):
    framework.write_text(DRAFT)
    lock(framework)
    assert hash_check().check(framework)[0] == 1


def test_the_repository_today_is_not_locked_and_the_check_passes():
    """The real framework is still a draft, so `make hash-check` passes and says why."""
    assert hash_check().check()[0] == 0


def test_make_hash_check_runs_the_check():
    recipe = Path("Makefile").read_text(encoding="utf-8").split("hash-check:", 1)[1].split("\n\n", 1)[0]
    assert re.search(r"python scripts/hash_check\.py", recipe)
    assert "shasum -a 256 -c" not in recipe
