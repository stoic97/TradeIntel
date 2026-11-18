"""TICKET-948: the running version is the tag when a tag is checked out, the short sha otherwise.

Production deploys tags (the release train), so /health and the admin page's "Running
deploy" say `v2026.11.14` on a tagged deploy. A sha on production then means a deploy that
skipped the train. A commit after a tag is a sha, not `v2026.11.14-1-g...`.
"""
import subprocess

import pytest

from services.production.api import cli, version
from tests.conftest import REAL_CODE_VERSION

GIT = ["git", "-c", "user.email=t@example.invalid", "-c", "user.name=t", "-c", "commit.gpgsign=false",
       "-c", "tag.gpgsign=false"]


def _git(repo, *args):
    return subprocess.run([*GIT, *args], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    _git(tmp_path, "init", "-q")
    (tmp_path / "a.txt").write_text("one")
    _git(tmp_path, "add", "a.txt")
    _git(tmp_path, "commit", "-q", "-m", "one")
    return tmp_path


def test_an_untagged_commit_is_its_short_sha(repo):
    assert version.describe(repo) == _git(repo, "rev-parse", "--short", "HEAD")


def test_a_tagged_commit_is_its_tag(repo):
    _git(repo, "tag", "-a", "v2026.11.14", "-m", "train: one")
    assert version.describe(repo) == "v2026.11.14"


def test_a_second_train_the_same_day_is_its_own_tag(repo):
    _git(repo, "tag", "-a", "v2026.11.14", "-m", "train")
    (repo / "a.txt").write_text("two")
    _git(repo, "commit", "-q", "-am", "hotfix")
    _git(repo, "tag", "-a", "v2026.11.14.2", "-m", "hotfix")
    assert version.describe(repo) == "v2026.11.14.2"


def test_a_commit_after_a_tag_is_a_sha_not_a_distance_from_the_tag(repo):
    _git(repo, "tag", "-a", "v2026.11.14", "-m", "train")
    (repo / "a.txt").write_text("two")
    _git(repo, "commit", "-q", "-am", "two")
    assert version.describe(repo) == _git(repo, "rev-parse", "--short", "HEAD")


def test_uncommitted_changes_are_marked_only_when_asked(repo):
    (repo / "a.txt").write_text("changed")
    sha = _git(repo, "rev-parse", "--short", "HEAD")
    assert version.describe(repo) == sha
    assert version.describe(repo, dirty=True) == f"{sha}-dirty"


def test_outside_a_repository_it_is_unknown(tmp_path):
    assert version.describe(tmp_path / "nowhere") == "unknown"


def test_the_app_and_the_cli_both_read_it_from_the_one_place(monkeypatch):
    calls = []
    monkeypatch.setattr(version, "describe", lambda where, dirty=False: calls.append(dirty) or "v1")
    assert REAL_CODE_VERSION() == "v1"
    assert cli.code_version() == "v1"
    assert calls == [False, True]  # the CLI keeps marking a dirty tree, as it always has
