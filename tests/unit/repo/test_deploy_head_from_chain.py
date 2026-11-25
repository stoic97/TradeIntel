"""TICKET-1073 follow-up (review of 25 Nov 20:00): the deploy block takes the live head from the chain.

Main's migrations chain 0019 -> 0022 -> 0020 -> 0021, so the highest number (0022) is not the head;
0021 is. The block in docs/runbooks/deploy.md is run here as written, against a scratch git repo:
a tag that is live and a tag to deploy, each holding migration files.
"""
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

DEPLOY = Path("docs/runbooks/deploy.md").read_text(encoding="utf-8")

pytestmark = pytest.mark.skipif(shutil.which("bash") is None or shutil.which("git") is None,
                                reason="needs bash and git")


def _block() -> str:
    """The head-check block as pasted on the server, its indent removed."""
    blocks = [b for b in re.findall(r"\n(    \( cd /srv/scope.*?\n    \)\n)", DEPLOY, re.DOTALL)
              if "DONE migration heads" in b]
    assert len(blocks) == 1, "one head-check block in deploy.md"
    return textwrap.dedent(blocks[0])


def _migration(rev: str, down: str | None) -> str:
    parent = "None" if down is None else f"'{down}'"
    return f"revision = '{rev}'\ndown_revision = {parent}\n"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _repo(tmp_path: Path, live: dict[str, str | None], new: dict[str, str | None]) -> Path:
    """A repo whose HEAD is the live tag `live1`; tag `new1` adds `new`'s files on top."""
    repo = tmp_path / "scope"
    versions = repo / "migrations" / "versions"
    versions.mkdir(parents=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    for rev, down in live.items():
        (versions / f"{rev}_m.py").write_text(_migration(rev, down))
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "live")
    _git(repo, "tag", "live1")
    for rev, down in new.items():
        (versions / f"{rev}_m.py").write_text(_migration(rev, down))
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "--allow-empty", "-m", "new")
    _git(repo, "tag", "new1")
    _git(repo, "checkout", "-q", "live1")
    return repo


def _run(repo: Path) -> subprocess.CompletedProcess:
    script = _block().replace("cd /srv/scope", f"cd {repo}").replace("TAG=v2026.11.14", "TAG=new1")
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=False)


MAIN = {"0019": None, "0022": "0019", "0020": "0022", "0021": "0020"}


def test_the_live_head_is_the_revision_no_file_revises_not_the_highest_number(tmp_path):
    out = _run(_repo(tmp_path, MAIN, {"0023": "0021"}))
    assert "live head: 0021" in out.stdout, out.stdout + out.stderr
    assert "live head: 0022" not in out.stdout


def test_a_new_migration_on_the_live_head_passes(tmp_path):
    out = _run(_repo(tmp_path, MAIN, {"0023": "0021"}))
    assert out.returncode == 0, out.stdout + out.stderr
    assert "DONE migration heads" in out.stdout


def test_a_new_migration_on_the_highest_number_but_not_the_head_stops(tmp_path):
    out = _run(_repo(tmp_path, MAIN, {"0023": "0022"}))
    assert out.returncode != 0, out.stdout
    assert "STOP:" in out.stdout
    assert "DONE migration heads" not in out.stdout


def test_two_new_migrations_on_one_parent_stop(tmp_path):
    out = _run(_repo(tmp_path, MAIN, {"0023": "0021", "0024": "0021"}))
    assert out.returncode != 0, out.stdout
    assert "STOP:" in out.stdout


def test_a_new_revision_already_in_the_live_chain_stops(tmp_path):
    repo = _repo(tmp_path, MAIN, {})
    versions = repo / "migrations" / "versions"
    _git(repo, "checkout", "-q", "new1")
    (versions / "0020_again.py").write_text(_migration("0020", "0021"))
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "reuse")
    _git(repo, "tag", "-f", "new1")
    _git(repo, "checkout", "-q", "live1")
    out = _run(repo)
    assert out.returncode != 0, out.stdout
    assert "STOP:" in out.stdout


def test_a_chain_of_new_migrations_in_order_passes(tmp_path):
    out = _run(_repo(tmp_path, MAIN, {"0023": "0021", "0024": "0023"}))
    assert out.returncode == 0, out.stdout + out.stderr


def test_the_block_never_picks_the_head_by_comparing_numbers():
    block = _block()
    assert '\\> "$head"' not in block
    assert not re.search(r"sort[^\n|]*\|\s*tail -1", block)
