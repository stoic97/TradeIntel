"""TICKET-1019: train 1's tag predates the release classifier and the market units.

Train 1 tags ``09919b5``, which is older than ``deploy/classify_release.py`` (TICKET-990) and
than ``deploy/scope-market.service`` / ``.timer`` (TICKET-998). Run as written, step d's "where"
block stopped with ``CHECK DID NOT RUN - no classifier`` (never Path A), and the Path A block
stopped on ``scope-market.service was not installed`` after ``git checkout`` and ``uv sync``,
leaving the box on the tag with the old code still running.

The blocks are taken from the runbook and run in bash against a throwaway git repo shaped like
that: a live commit, a tag that has neither file, and an ``origin/main`` that has both. git is
real (only ``fetch`` is stubbed), as are cmp, cp and python3 running the real classifier;
uv, systemctl, sqlite3 and chown are stubbed. Tags, shas and paths are made up.
"""
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

DEPLOY = Path("docs/runbooks/deploy.md").read_text(encoding="utf-8")
CLASSIFIER = Path("deploy/classify_release.py").read_text(encoding="utf-8")
LIVE_TAG = "v2099.01.01"
TAG = "v2099.01.02"
PATHS = re.compile(r"/srv/scope|/etc/systemd/system|/etc/cron\.daily|/var/backups|/opt/uv/python|/tmp")
BASH, GIT, PY = shutil.which("bash"), shutil.which("git"), shutil.which("python3")
needs_tools = pytest.mark.skipif(not (BASH and GIT and PY), reason="needs bash, git and python3")


def _block(found) -> str:
    sec = DEPLOY[DEPLOY.index("### d. Deploy the tag"):DEPLOY.index("### e. Check production")]
    blocks, cur = [], []
    for line in sec.splitlines():
        if line.startswith("    "):
            cur.append(line.strip())
        elif cur:
            blocks.append("\n".join(cur))
            cur = []
    hits = [b for b in blocks if found(b)]
    assert len(hits) == 1, len(hits)
    return hits[0]


def _where() -> str:
    return _block(lambda b: "git describe" in b and "git fetch" in b)


def _path_a() -> str:
    return _block(lambda b: "systemctl restart scope" in b and "systemctl stop scope" not in b)


class Droplet:
    """A temp dir standing in for the droplet, with /srv/scope a real git repo."""

    def __init__(self, root: Path, tag_has_new_files: bool):
        self.root = root
        for d in ("bin", "tmp", "etc/systemd/system", "etc/cron.daily", "var/backups/scope", "srv/scope"):
            (root / d).mkdir(parents=True, exist_ok=True)
        self.srv = root / "srv/scope"
        self.git("init", "-q")
        self.git("config", "user.email", "t@example.invalid")
        self.git("config", "user.name", "t")
        self._commit({".gitignore": "data/\n", "deploy/scope.service": "unit\n",
                      "deploy/backup.sh": "backup\n", "migrations/versions/0001_made_up.py": "",
                      "app.txt": "live\n"}, "live")
        self.git("tag", LIVE_TAG)
        newer = {"deploy/classify_release.py": CLASSIFIER, "deploy/scope-market.service": "market\n",
                 "deploy/scope-market.timer": "timer\n"}
        self._commit({"app.txt": "tagged\n", **(newer if tag_has_new_files else {})}, "tag")
        self.git("tag", TAG)
        self._commit({"app.txt": "main\n", **newer}, "main")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")
        self.git("checkout", "-q", "--detach", LIVE_TAG)
        (self.srv / "data").mkdir()
        (self.srv / "data/scope.db").write_text("live\n")
        stubs = {"git": f'case "$1" in fetch) exit 0;; esac\nexec {GIT} "$@"\n',
                 "uv": "exit 0\n", "systemctl": "exit 0\n", "chown": "exit 0\n",
                 "sqlite3": 'case "$2" in .backup*) p=${2#*\\\'}; p=${p%\\\'}; : > "$p";; esac\nexit 0\n'}
        for name, body in stubs.items():
            p = root / "bin" / name
            p.write_text(f'#!/usr/bin/env bash\necho "{name} $*" >> "$BOX/calls"\n{body}')
            p.chmod(0o755)

    def git(self, *args: str) -> str:
        return subprocess.run([GIT, "-C", str(self.srv), *args], check=True,
                              capture_output=True, text=True).stdout

    def _commit(self, files: dict[str, str], msg: str) -> None:
        for path, text in files.items():
            (self.srv / path).parent.mkdir(parents=True, exist_ok=True)
            (self.srv / path).write_text(text)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", msg)

    def run(self, block: str) -> list[str]:
        block = re.sub(r"(?m)^TAG=[^\s;]*", f"TAG={TAG}", block)
        block = PATHS.sub(lambda m: "$BOX" + m.group(0), block)
        paste = 'export BOX="$PWD"; export PATH="$BOX/bin:$PATH"\n' + block + "\n"
        done = subprocess.run([BASH, "--noprofile", "--norc"], input=paste, cwd=self.root,
                              capture_output=True, text=True, timeout=120, env=dict(os.environ))
        return done.stdout.splitlines()

    @property
    def calls(self) -> list[str]:
        log = self.root / "calls"
        return log.read_text().splitlines() if log.exists() else []


@needs_tools
def test_an_older_tag_is_classified_with_main_s_classifier_and_reads_path_a(tmp_path):
    out = Droplet(tmp_path, tag_has_new_files=False).run(_where())
    assert not [line for line in out if line.startswith("STOP")], out
    assert f"classifier: from origin/main ({TAG} predates it)" in out, out
    assert "PATH A - additive or no migration" in out, out
    assert out[-1] == "DONE where", out


@needs_tools
def test_path_a_on_an_older_tag_skips_the_units_it_lacks_and_reaches_the_restart(tmp_path):
    box = Droplet(tmp_path, tag_has_new_files=False)
    out = box.run(_path_a())
    assert not [line for line in out if line.startswith("STOP")], out
    assert f"scope-market.service: not in {TAG}, skipped" in out, out
    assert f"scope-market.timer: not in {TAG}, skipped" in out, out
    assert any(c.startswith("systemctl restart scope") for c in box.calls), box.calls
    assert out[-1] == "DONE path-a", out
    assert not (tmp_path / "etc/systemd/system/scope-market.service").exists()


@needs_tools
def test_a_tag_that_has_them_uses_its_own_classifier_and_installs_the_units(tmp_path):
    box = Droplet(tmp_path, tag_has_new_files=True)
    where = box.run(_where())
    assert f"classifier: from {TAG}" in where, where
    assert "PATH A - additive or no migration" in where, where
    out = box.run(_path_a())
    assert not [line for line in out if line.startswith("STOP")], out
    assert "scope-market.service updated" in out and "scope-market.timer updated" in out, out
    assert (tmp_path / "etc/systemd/system/scope-market.service").read_text() == "market\n"
    assert out[-1] == "DONE path-a", out
